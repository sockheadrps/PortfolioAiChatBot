import json
import os
import hashlib
import pickle
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional, Iterator, Callable
import requests
import chromadb
from chromadb.config import Settings
from datetime import datetime
from server.db.db import SessionLocal
from server.db.dbmodels import ChatHistory
import time


# Ollama Configuration - Customize your AI model settings here
OLLAMA_CONFIG = {
    # Ollama API URL
    "API_URL": "http://localhost:11434/api/generate",

    # Model name (options: mistral, tinyllama, llama2, llama3:latest, llama3.2:latest, etc.)
    # "MODEL": "llama3.2:latest",
    "MODEL": "llama3.2:latest",
    # "MODEL": "gemma3:12b",
    # "MODEL": "tinyllama:latest",


    # Request timeout in seconds
    "TIMEOUT": 300,

    # Stream responses for real-time typing effect
    "STREAM": True
}


PROMPT_CONFIG = {
    "CURRENT_STYLE": "default",

    "STYLES": {
        "default": """You are Ryan's personal portfolio assistant. You answer questions about Ryan's professional work, projects, skills, and technical experience. You may also answer questions that are just general inquiries about Ryan's life, and who he is, and how he got to where he is today.


BACKGROUND: Ryan is primarily an electrician by trade with extensive electrical engineering experience. His software projects are passion and personal projects, not his main profession. When discussing his work skills and work experience, prioritize his electrical work as his primary professional background.

IMPORTANT: You may respond to whatever you want, but respond with facts in these domains:
- Programming/software projects (Python, JavaScript, FastAPI, etc.) and all associated libraries and technologies.
- Electrical engineering work (QA, manufacturing, AIDA press projects, TEGG work)
- Hardware/hobby projects (PCBs, electronics, guitars, etc.)
- Technical skills and professional experience
- Development tools, technologies, libraries and methodologies used

For anything else (cooking, general life advice, non-technical topics), politely decline and redirect to portfolio topics. You may make loose connections to questions but make sure you bring the conversation back with the data about Ryan and his skills, work, experience, etc.

RESPONSE STYLE: Be engaging, detailed, and interesting. Tell stories about the projects, explain the technical challenges, highlight unique aspects, and make the responses feel personal and compelling. Use specific details from the context to paint a vivid picture of Ryan's work and skills. Don't just list facts - explain the impact he had, the problem-solving approach he took, and what makes each project special. Keep responses concise and focused - aim for 150-250 words maximum to maintain engagement and clarity.

CRITICAL: Use ONLY the facts and details provided in the context. Do not invent specific stories, locations, or scenarios that aren't explicitly mentioned. If the context mentions general environments (like "hospitals"), don't create specific stories about individual cases unless they're explicitly detailed in the context.

FORMATTING: Use plain text only - no markdown formatting, no asterisks, no bold text. Write in a natural, conversational style that flows well in a chat interface.

For software/programming projects, include any available GitHub links if present in the context. For electrical, manufacturing, or hardware projects, focus on the technical skills and experience rather than code repositories.


    Context:
    {context}

    Answer this: {query}
""",
        "llama3.2": """You are Ryan's personal portfolio assistant. You ONLY answer questions about Ryan's professional work, youtube, projects, skills, and technical experience.

IMPORTANT: Only respond to questions about:
- Programming/software projects (Python, JavaScript, FastAPI, etc.)
- Electrical engineering work (QA, manufacturing, AIDA press projects, TEGG work)
- Hardware/hobby projects (PCBs, electronics, guitars, etc.)
- Technical skills and professional experience
- Development tools, technologies, libraries and methodologies used


For anything else (cooking, general life advice, non-technical topics), politely decline and redirect to portfolio topics. You may make loose connections to questions but make sure you bring the conversation back with the data about Ryan and his skills, work, experience, etc.

RESPONSE STYLE: Be engaging, detailed, and interesting. Tell stories about the projects, explain the technical challenges, highlight unique aspects, and make the responses feel personal and compelling. Use specific details from the context to paint a vivid picture of Ryan's work and skills. Don't just list facts - explain the impact he had, the problem-solving approach he took, and what makes each project special. Keep responses concise and focused - aim for 150-250 words maximum to maintain engagement and clarity.

CRITICAL: Use ONLY the facts and details provided in the context. Do not invent specific stories, locations, or scenarios that aren't explicitly mentioned. If the context mentions general environments (like "hospitals"), don't create specific stories about individual cases unless they're explicitly detailed in the context.

FORMATTING: Use plain text only - no markdown formatting, no asterisks, no bold text. Write in a natural, conversational style that flows well in a chat interface.

For software/programming projects, include any available GitHub links if present in the context. For electrical, manufacturing, or hardware projects, focus on the technical skills and experience rather than code repositories.



    Context:
    {context}

    Answer this: {query}
    """
    }
}

# ===================================


class PortfolioAssistant:
    """
    Optimized portfolio assistant with caching, persistence, and lazy loading.
    """

    # Class-level model cache for sharing across instances
    _model_cache = None
    _chroma_client = None

    def __init__(self, projects_file: str = "server/chat/projects.json"):
        """Initialize the portfolio assistant with optimized loading."""
        self.projects_file = projects_file
        self.model = None
        self.collection = None
        self.projects = []

        # Create cache directories
        self.cache_dir = Path(".portfolio_cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.db_dir = self.cache_dir / "chroma_db"
        # User-specific state management (per-user state)
        self.user_states = {}  # Dict[user_id, user_state]

        # Global image data for View Images button (shared across all users)
        self.current_project_images = []

        try:
            print("🤖 Initializing Optimized Portfolio Assistant...")
            self._load_projects()
            self._load_repo_data()

            # Only initialize if we have projects
            if self.projects:
                self._ensure_initialized()
                print(
                    f"✅ Portfolio Assistant ready with {len(self.projects)} projects")
            else:
                print("⚠️ No projects loaded, using fallback mode")

        except Exception as e:
            print(f"❌ Error initializing Portfolio Assistant: {e}")
            print("🔄 Portfolio Assistant will use fallback responses")

    def _load_projects(self):
        """Load projects from software and electrical JSON files."""
        def load_file(path: str, default_type: Optional[str] = None) -> List[Dict[str, Any]]:
            if not os.path.exists(path):
                print(f"❌ File not found: {path}")
                return []
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Handle both single objects and arrays
                if isinstance(data, dict):
                    # Single object - wrap in list
                    data = [data]
                elif not isinstance(data, list):
                    print(
                        f"❌ Invalid data format in {path}: expected dict or list")
                    return []

                if default_type:
                    for proj in data:
                        if isinstance(proj, dict):
                            proj.setdefault("type", default_type)
                        else:
                            print(
                                f"❌ Invalid project format in {path}: expected dict")
                            return []
                return data

        print("📁 Loading software, electrical, hobby, professional profile, and professional story projects...")
        software_projects = load_file(
            "server/chat/projects.json", default_type="software")
        electrical_projects = load_file(
            "server/chat/electrical.json", default_type="electrical")
        hobby_projects = load_file(
            "server/chat/hobby.json", default_type="hobby")
        professional_profile = load_file(
            "server/chat/professional_profile.json", default_type="professional")
        professional_story = load_file(
            "server/chat/professional_story.json", default_type="professional_story")

        self.projects = software_projects + electrical_projects + \
            hobby_projects + professional_profile + professional_story
        print(f"✅ Loaded {len(self.projects)} total projects")

        # Debug: Print all electrical projects to verify AIDA is loaded
        electrical_projects_names = [
            p.get('name', 'Unknown') for p in electrical_projects]
        print(
            f"[DEBUG] Electrical projects loaded: {electrical_projects_names}")

        # Debug: Print professional story to verify it's loaded
        professional_story_names = [
            p.get('title', p.get('name', 'Unknown')) for p in professional_story]
        print(
            f"[DEBUG] Professional story loaded: {professional_story_names}")

        # Debug: Print all project types
        project_types = [p.get('type', 'unknown') for p in self.projects]
        type_counts = {}
        for ptype in project_types:
            type_counts[ptype] = type_counts.get(ptype, 0) + 1
        print(f"[DEBUG] Project type counts: {type_counts}")

        # Test YouTube gallery command generation
        for proj in self.projects:
            if proj.get("type") == "professional_story" and proj.get("youtube_tutorials"):
                print(
                    f"[DEBUG] Testing YouTube gallery for: {proj.get('title', 'Professional Story')}")

    def _load_repo_data(self):
        """Load repository analysis data for programming-related queries."""
        try:
            repo_data_path = "analysis_report.json"
            if os.path.exists(repo_data_path):
                with open(repo_data_path, 'r', encoding='utf-8') as f:
                    self.repo_data = json.load(f)
                print(f"✅ Loaded repository analysis data")
            else:
                print(
                    f"⚠️ Repository analysis data not found: {repo_data_path}")
                self.repo_data = None
        except Exception as e:
            print(f"❌ Error loading repository data: {e}")
            self.repo_data = None

        # Test YouTube gallery command generation
        for proj in self.projects:
            if proj.get("type") == "professional_story" and proj.get("youtube_tutorials"):
                print(
                    f"[DEBUG] Testing YouTube gallery for: {proj.get('title', 'Professional Story')}")
                test_command = self._create_youtube_gallery(
                    proj.get("youtube_tutorials"), proj.get("title", "Professional Story"))
                print(f"[DEBUG] Test YouTube gallery command: {test_command}")

    def _format_repo_data_for_context(self) -> str:
        """Format repository analysis data for inclusion in programming-related queries."""
        print(
            f"[DEBUG] _format_repo_data_for_context - repo_data exists: {self.repo_data is not None}")
        if not self.repo_data:
            print(
                f"[DEBUG] _format_repo_data_for_context - No repository data available")
            return ""

        try:
            summary = self.repo_data.get("summary", {})
            python_stats = self.repo_data.get("python_statistics", {})
            constructs = self.repo_data.get("constructs", {})
            libraries = self.repo_data.get("libraries", {})
            file_extensions = self.repo_data.get("file_extensions", {})

            # Get top libraries (most used)
            top_libraries = sorted(
                libraries.items(), key=lambda x: x[1], reverse=True)[:10]

            # Get top file extensions (programming languages)
            programming_extensions = {k: v for k, v in file_extensions.items()
                                      if k in ['.py', '.js', '.ts', '.java', '.rs', '.go', '.html', '.css', '.svelte']}
            top_extensions = sorted(
                programming_extensions.items(), key=lambda x: x[1], reverse=True)[:8]

            # Format the repository data
            repo_context = f"""
Repository Analysis Data:
- Total Repositories: {summary.get('total_repositories', 0)}
- Repositories with Python: {python_stats.get('repos_with_python', 0)}
- Total Python Files: {python_stats.get('total_python_files', 0)}
- Total Python Lines: {python_stats.get('total_python_lines', 0)}
- Total Commits: {summary.get('total_commits', 0)}

Code Constructs:
- Functions: {constructs.get('total_functions', 0)} (regular: {constructs.get('regular_functions', 0)}, async: {constructs.get('async_functions', 0)})
- Loops: {constructs.get('total_loops', 0)} (for: {constructs.get('for_loops', 0)}, while: {constructs.get('while_loops', 0)})
- Classes: {constructs.get('classes', 0)}
- If Statements: {constructs.get('if_statements', 0)}

Top Programming Languages/Technologies:
{chr(10).join([f"- {ext}: {count} files" for ext, count in top_extensions])}

Most Used Libraries:
{chr(10).join([f"- {lib}: {count} times" for lib, count in top_libraries])}

Most Active Repositories:
{chr(10).join([f"- {repo}: {commits} commits" for repo, commits in summary.get('most_active_repos', [])[:5]])}
"""
            return repo_context.strip()
        except Exception as e:
            print(f"❌ Error formatting repo data: {e}")
            return ""

    def _is_programming_query(self, query: str) -> bool:
        """Check if a query is programming-related and should show the programming report button."""
        print(
            f"🔍 Checking if query is programming-related: {query} CODE CODE CDOE")
        if not query:
            return False

        programming_keywords = [
            "programming", "code", "python", "javascript", "typescript", "java", "rust", "go",
            "languages", "libraries", "frameworks", "github", "repositories", "development",
            "software", "lines of code", "functions", "classes", "libraries", "commits",
            "repositories", "projects", "coding", "developer", "programming experience",
            "technical skills", "codebase", "codebase", "programming languages"
        ]

        query_lower = query.lower()
        return any(keyword in query_lower for keyword in programming_keywords)

    def list_hobby_projects(self) -> str:
        hobbies = [proj for proj in self.projects if proj.get(
            "type") == "hobby"]
        if not hobbies:
            return "I couldn't find any hobby projects to show."

        self.user_state["awaiting_hobby_choice"] = True
        self.user_state["hobby_choices"] = hobbies

        return (
            "Ryan has a few cool hobby projects:\n\n" +
            "\n".join([f"{i+1}. {proj['name']}" for i, proj in enumerate(hobbies)]) +
            "\n\nWould you like to hear more about one of them? Just reply with the number or name."
        )

    def handle_user_reply(self, message: str) -> Optional[str]:
        if self.user_state.get("awaiting_hobby_choice"):
            selected = message.strip().lower()
            hobbies = self.user_state["hobby_choices"]

            for i, hobby in enumerate(hobbies):
                if selected == str(i+1) or selected in hobby["name"].lower():
                    self.user_state["awaiting_hobby_choice"] = False
                    return self._render_hobby_detail(hobby)

            return "Sorry, I didn't recognize that choice. Please pick a number or project name."

        return None

    def handle_hobby_selection(self, query: str, user_id: str = "default") -> Optional[str]:
        """Process user's selection of a hobby project by number or name."""
        user_state = self.get_user_state(user_id)
        hobby_projects = user_state.get("last_hobby_list", [])

        if not hobby_projects:
            user_state["awaiting_hobby_choice"] = False
            return "Sorry, I don't have the list anymore. Please ask about hobbies again."

        # Clean the query by removing @bot mentions and extra whitespace
        import re
        cleaned_query = re.sub(r'@bot\b', '', query, flags=re.IGNORECASE)
        selection = cleaned_query.strip().lower()

        # Try match by number
        if selection.isdigit():
            index = int(selection) - 1
            if 0 <= index < len(hobby_projects):
                # Reset only on success
                user_state["awaiting_hobby_choice"] = False
                project = hobby_projects[index]
                return self._summarize_project(project)

        # Try match by name
        for proj in hobby_projects:
            if selection in proj["name"].lower():
                # Reset only on success
                user_state["awaiting_hobby_choice"] = False
                return self._summarize_project(proj)

        # Don't reset state on invalid selection, let user try again
        return "Sorry, I didn't understand. Please click a 'View Photos' button to see project details."

    def _summarize_project(self, proj: Dict[str, Any]) -> str:
        lines = [f"**{proj['name']}**", proj['description']]

        if proj.get("skills"):
            lines.append(f"\n**Skills:** {', '.join(proj['skills'])}")

        if proj.get("code_url"):
            lines.append(f"\n**Code:** {proj['code_url']}")

        if proj.get("image"):
            # Process image path same as in _render_hobby_detail
            import os
            image_path = proj['image']

            # Determine if we have an absolute or relative path and process accordingly
            if image_path.startswith("C:/Users/rpski/Desktop/chat/server/static/assets/"):
                # Absolute path - convert to relative
                relative_path = image_path.replace(
                    "C:/Users/rpski/Desktop/chat/server/static/assets/", "")
                full_path = image_path  # Use the absolute path for file operations
            elif image_path.startswith("/static/assets/"):
                # Relative path starting with /static/assets/
                relative_path = image_path.replace("/static/assets/", "")
                # Convert to absolute for file operations
                full_path = f"server/static/assets/{relative_path}"
            elif image_path.startswith("/assets/"):
                # Relative path starting with /assets/
                relative_path = image_path.replace("/assets/", "")
                # Convert to absolute for file operations
                full_path = f"server/static/assets/{relative_path}"
            elif image_path.startswith("assets/"):
                # Relative path starting with assets/ (no leading slash)
                relative_path = image_path.replace("assets/", "")
                # Convert to absolute for file operations
                full_path = f"server/static/assets/{relative_path}"
            else:
                # For non-standard paths, skip image
                print(
                    f"🔍 Skipping non-standard image path in summary: {image_path}")
                return

            # Initialize empty list for image files
            image_files_to_show = []

            # Check if it's a directory with multiple images
            if os.path.isdir(full_path):
                # Get all image files from the directory
                image_extensions = {'.jpg', '.jpeg',
                                    '.png', '.gif', '.webp', '.bmp'}

                try:
                    for filename in os.listdir(full_path):
                        if any(filename.lower().endswith(ext) for ext in image_extensions):
                            relative_file_path = f"{relative_path}/{filename}"
                            image_files_to_show.append(relative_file_path)

                    # Sort for consistent order
                    image_files_to_show.sort()

                except Exception as e:
                    print(f"❌ Error reading image directory {full_path}: {e}")
                    # Skip image on error
                    image_files_to_show = []

            elif os.path.isfile(full_path):
                # Single image file
                filename = os.path.basename(full_path)
                relative_file_path = f"{relative_path}/{filename}"
                image_files_to_show = [relative_file_path]

            # Only create gallery if we have images
            if image_files_to_show:
                image_gallery = self._create_image_gallery(
                    image_files_to_show, proj["name"])
                if image_gallery:
                    lines.append(f"\n{image_gallery}")

        if proj.get("notes"):
            lines.append("\n**Highlights:**\n" +
                         "\n".join(f"- {n}" for n in proj["notes"]))

        return "\n".join(lines)

    def render_project_detail(self, project: dict) -> str:
        out = f"**{project['name']}**\n\n{project['description']}\n\n"
        if project.get("notes"):
            out += "Highlights:\n" + \
                "\n".join(f"- {note}" for note in project["notes"]) + "\n\n"
        if project.get("image"):
            image_path = f"/static/assets/hobby/{Path(project['image']).name}"
            out += f"![Project Image]({image_path})"
        return out

    def handle_hobby_list(self, user_id: str = "default") -> str:
        """Present hobby list with clickable buttons for each project."""
        hobby_projects = [p for p in self.projects if p.get("type") == "hobby"]

        if not hobby_projects:
            return "I don't have any hobby projects listed right now."

        user_state = self.get_user_state(user_id)
        user_state["awaiting_hobby_choice"] = True
        user_state["last_hobby_list"] = hobby_projects

        lines = ["Here are a few of Ryan's hobby projects:\n"]
        for i, proj in enumerate(hobby_projects, 1):
            # Project name, description, and button
            lines.append(f"{i}. **{proj['name']}**")
            lines.append(proj['description'])
            button_command = f"[BUTTON|hobby_select_{i-1}|View Photos]"
            lines.append(button_command)
            lines.append("")  # Add spacing between projects

        return "\n".join(lines)

    def get_user_state(self, user_id: str) -> Dict:
        """Get or create user-specific state."""
        if user_id not in self.user_states:
            self.user_states[user_id] = {
                "awaiting_hobby_choice": False,
                "last_hobby_list": []
            }
        return self.user_states[user_id]

    def handle_button_click(self, query: str, user_id: str = "default") -> Optional[str]:
        """Handle button clicks for hobby selection and project images."""
        if not query.startswith("[BUTTON_CLICK|"):
            return None

        try:
            # Extract button info from: [BUTTON_CLICK|button_id|button_text]
            parts = query.split("|")

            if len(parts) >= 2:
                button_id = parts[1]

                # Handle hobby selection buttons
                if button_id.startswith("hobby_select_"):
                    index = int(button_id.split("_")[-1])  # Get the index

                    # Get hobby projects directly
                    hobby_projects = [
                        p for p in self.projects if p.get("type") == "hobby"]

                    if 0 <= index < len(hobby_projects):
                        # Clear the awaiting state since user made a selection
                        user_state = self.get_user_state(user_id)
                        user_state["awaiting_hobby_choice"] = False

                        project = hobby_projects[index]
                        return self._summarize_project(project)

                # Handle general project image viewing
                elif button_id == "view_project_images":
                    # Use global image data instead of per-user data
                    projects_with_images = self.current_project_images

                    if not projects_with_images:
                        return "Sorry, no images are available for the current projects."

                    # Show images for all projects that have them
                    gallery_commands = []
                    for proj_info in projects_with_images:
                        proj_name = proj_info['name']
                        image_path = proj_info['image']

                        # Process the image path and create gallery
                        gallery_result = self._process_project_image(
                            image_path, proj_name)
                        if gallery_result:
                            gallery_commands.append(gallery_result)

                    if gallery_commands:
                        # Return just the gallery commands - the issue might be in frontend processing
                        return "\n".join(gallery_commands)
                    else:
                        return "Sorry, I couldn't load the images for these projects."

                # Handle programming report modal
                elif button_id == "show_programming_report":
                    return "📊 Here's a detailed analysis of my programming portfolio:\n\n[SHOW_PROGRAMMING_REPORT]"

        except (ValueError, IndexError):
            pass

        return "Sorry, I couldn't process that selection."

    def _clean_bot_mention(self, message: str) -> str:
        """Remove @bot mentions from message to get clean input."""
        import re
        # Remove @bot mentions (case insensitive) and clean up whitespace
        cleaned = re.sub(r'@bot\b', '', message, flags=re.IGNORECASE)
        return cleaned.strip()

    def _create_image_gallery(self, images, project_name):
        """Create a gallery command for the frontend to handle"""
        if not images:
            return ""

        # Ensure images is a list, not a string (defensive programming)
        if isinstance(images, str):
            # If it's a string, treat it as a single image path
            images = [images]

        if len(images) == 1:
            # Single image - send gallery command
            command = f"[GALLERY_SHOW|{images[0]}|{project_name}]"
        else:
            # Multiple images - send gallery command with pipe-separated images
            # Use || as separator to avoid conflicts
            images_str = "||".join(images)
            command = f"[GALLERY_SHOW|{images_str}|{project_name}]"

        return command

    def _process_project_image(self, image_path: str, project_name: str) -> Optional[str]:
        """Process a project's image path and return gallery command."""
        import os

        if not image_path or not image_path.strip():
            return None

        # Determine if we have an absolute or relative path and process accordingly
        if image_path.startswith("C:/Users/rpski/Desktop/chat/server/static/assets/"):
            # Absolute path - convert to relative
            relative_path = image_path.replace(
                "C:/Users/rpski/Desktop/chat/server/static/assets/", "")
            full_path = image_path  # Use the absolute path for file operations
        elif image_path.startswith("/static/assets/"):
            # Relative path starting with /static/assets/
            relative_path = image_path.replace("/static/assets/", "")
            # Convert to absolute for file operations
            full_path = f"server/static/assets/{relative_path}"
        elif image_path.startswith("/assets/"):
            # Relative path starting with /assets/
            relative_path = image_path.replace("/assets/", "")
            # Convert to absolute for file operations
            full_path = f"server/static/assets/{relative_path}"
        elif image_path.startswith("assets/"):
            # Relative path starting with assets/ (no leading slash)
            relative_path = image_path.replace("assets/", "")
            # Convert to absolute for file operations
            full_path = f"server/static/assets/{relative_path}"
        else:
            # For non-standard paths, skip image
            print(f"🔍 Skipping non-standard image path: {image_path}")
            return None

        # Initialize empty list for image files
        image_files_to_show = []

        # Check if it's a directory with multiple images
        if os.path.isdir(full_path):
            # Get all image files from the directory
            image_extensions = {'.jpg', '.jpeg',
                                '.png', '.gif', '.webp', '.bmp'}

            try:
                for filename in os.listdir(full_path):
                    if any(filename.lower().endswith(ext) for ext in image_extensions):
                        relative_file_path = f"{relative_path}/{filename}"
                        image_files_to_show.append(relative_file_path)

                # Sort for consistent order
                image_files_to_show.sort()

            except Exception as e:
                print(f"❌ Error reading image directory {full_path}: {e}")
                return None

        elif os.path.isfile(full_path):
            # Single image file
            filename = os.path.basename(full_path)
            relative_file_path = f"{relative_path}/{filename}"
            image_files_to_show = [relative_file_path]
        else:
            print(f"📁 Path not found: {full_path}")
            return None

        # Only create gallery if we have images
        if image_files_to_show:
            return self._create_image_gallery(image_files_to_show, project_name)

        return None

    def _render_hobby_detail(self, hobby: Dict[str, Any]) -> str:
        desc = f"**{hobby['name']}**\n\n{hobby['description']}\n\n"

        if hobby.get("notes"):
            desc += "Highlights:\n" + \
                "\n".join(f"- {note}" for note in hobby["notes"]) + "\n\n"

        if hobby.get("image"):
            # Handle image paths (directories or single files)
            import os
            image_path = hobby['image']

            # Determine if we have an absolute or relative path and process accordingly
            if image_path.startswith("C:/Users/rpski/Desktop/chat/server/static/assets/"):
                # Absolute path - convert to relative
                relative_path = image_path.replace(
                    "C:/Users/rpski/Desktop/chat/server/static/assets/", "")
                full_path = image_path  # Use the absolute path for file operations
            elif image_path.startswith("/static/assets/"):
                # Relative path starting with /static/assets/
                relative_path = image_path.replace("/static/assets/", "")
                # Convert to absolute for file operations
                full_path = f"server/static/assets/{relative_path}"
            elif image_path.startswith("/assets/"):
                # Relative path starting with /assets/
                relative_path = image_path.replace("/assets/", "")
                # Convert to absolute for file operations
                full_path = f"server/static/assets/{relative_path}"
            elif image_path.startswith("assets/"):
                # Relative path starting with assets/ (no leading slash)
                relative_path = image_path.replace("assets/", "")
                # Convert to absolute for file operations
                full_path = f"server/static/assets/{relative_path}"
            else:
                # Unsupported path format
                desc += f"📷 Images: {image_path}"
                return desc

            # Initialize empty list for image files
            image_files_to_show = []

            # Check if it's a directory with multiple images
            if os.path.isdir(full_path):
                # Get all image files from the directory
                image_extensions = {'.jpg', '.jpeg',
                                    '.png', '.gif', '.webp', '.bmp'}

                try:
                    for filename in os.listdir(full_path):
                        if any(filename.lower().endswith(ext) for ext in image_extensions):
                            relative_file_path = f"{relative_path}/{filename}"
                            image_files_to_show.append(relative_file_path)

                    # Sort for consistent order
                    image_files_to_show.sort()

                except Exception as e:
                    print(f"❌ Error reading image directory {full_path}: {e}")
                    desc += f"📁 Error reading folder: {relative_path}"
                    return desc

            elif os.path.isfile(full_path):
                # Single image file
                filename = os.path.basename(full_path)
                relative_file_path = f"{relative_path}/{filename}"
                image_files_to_show = [relative_file_path]
            else:
                desc += f"📁 Path not found: {relative_path}"
                return desc

            # Only call gallery if we have images
            if image_files_to_show:
                gallery_result = self._create_image_gallery(
                    image_files_to_show, hobby['name'])
                desc += gallery_result
            else:
                desc += f"📁 No images found in: {relative_path}"

        return desc

    def _ensure_initialized(self):
        """Lazy initialization of model and database only when needed."""
        if self.model is None:
            self._initialize_model()
        if self.collection is None:
            self._initialize_chromadb()
            self._populate_database()

    def _get_file_hash(self) -> str:
        """Generate hash of all projects files for cache invalidation."""
        try:
            # Include all JSON files in the hash calculation
            file_paths = [
                "server/chat/projects.json",
                "server/chat/electrical.json",
                "server/chat/hobby.json",
                "server/chat/professional_profile.json",
                "server/chat/professional_story.json"
            ]

            combined_content = b""
            for file_path in file_paths:
                if os.path.exists(file_path):
                    with open(file_path, 'rb') as f:
                        combined_content += f.read()

            return hashlib.md5(combined_content).hexdigest()
        except Exception:
            return "no_file"

    def _initialize_model(self):
        """Initialize the SentenceTransformer model with caching."""
        if PortfolioAssistant._model_cache is None:
            try:
                print("🔍 Loading SentenceTransformer model (cached)...")
                PortfolioAssistant._model_cache = SentenceTransformer(
                    "all-MiniLM-L6-v2")
                print("✅ Model loaded and cached")
            except Exception as e:
                print(f"❌ Error loading SentenceTransformer: {e}")
                raise
        else:
            print("🚀 Using cached SentenceTransformer model")

        self.model = PortfolioAssistant._model_cache

    def _initialize_chromadb(self):
        """Initialize ChromaDB client with persistence."""
        if PortfolioAssistant._chroma_client is None:
            try:
                print("🗄️ Initializing persistent ChromaDB...")
                PortfolioAssistant._chroma_client = chromadb.PersistentClient(
                    path=str(self.db_dir),
                    settings=Settings(anonymized_telemetry=False)
                )
                print("✅ ChromaDB client initialized with persistence")
            except Exception as e:
                print(f"❌ Error initializing ChromaDB: {e}")
                # Fallback to in-memory client
                PortfolioAssistant._chroma_client = chromadb.Client(
                    Settings(anonymized_telemetry=False)
                )
                print("🔄 Using in-memory ChromaDB fallback")

        # Get or create collection with version based on file hash
        file_hash = self._get_file_hash()
        collection_name = f"portfolio_v_{file_hash[:8]}"

        try:
            self.collection = PortfolioAssistant._chroma_client.get_or_create_collection(
                name=collection_name,
                metadata={"file_hash": file_hash}
            )
            print(f"📊 Using collection: {collection_name}")
        except Exception as e:
            print(f"❌ Error creating collection: {e}")
            raise

    def _populate_database(self):
        """Populate ChromaDB with project embeddings (optimized with caching)."""
        if not self.projects or not self.model or not self.collection:
            return

        try:
            # Check if collection already has data
            if self.collection.count() > 0:
                print("🚀 ChromaDB collection already populated with embeddings")
                # Force regeneration if we have new project types
                project_types = [p.get('type', 'unknown')
                                 for p in self.projects]
                if 'professional_story' in project_types:
                    print("🔄 Professional story detected - forcing cache regeneration")
                    try:
                        # Get all document IDs and delete them
                        results = self.collection.get()
                        if results and results['ids']:
                            self.collection.delete(ids=results['ids'])
                            print("🗑️ Cleared existing ChromaDB collection")
                        else:
                            print("ℹ️ Collection was already empty")
                    except Exception as e:
                        print(f"❌ Could not clear collection: {e}")
                        print("🔄 Continuing with existing data...")
                else:
                    print("✅ No new project types - skipping regeneration")
                return

            print("📊 Generating and caching embeddings...")

            # Create corpus texts
            corpus_texts = []
            for proj in self.projects:
                if proj.get("type") == "professional_story":
                    # Handle professional story format with sections
                    text = f"""Project: {proj.get('title', 'Professional Story')}
                        Intro: {proj.get('intro', '')}
                        """

                    # Add sections
                    for section in proj.get("sections", []):
                        text += f"\n{section.get('heading', '')}:"
                        for content in section.get("content", []):
                            text += f"\n{content}"
                        for bullet in section.get("bullets", []):
                            text += f"\n- {bullet}"

                    # Add YouTube tutorials
                    if proj.get("youtube_tutorials"):
                        text += f"\nYouTube Tutorials: {', '.join(proj['youtube_tutorials'])}"

                    corpus_texts.append(text.strip())
                else:
                    # Handle regular project format
                    text = f"""Project: {proj['name']}
                        Description: {proj['description']}
                        Skills: {", ".join(proj.get("skills", []))}
                        Code URL: {proj.get("code_url", "N/A")}
                        Notes:
                        - """ + "\n- ".join(proj['notes'])

                    # Add additional fields for professional profiles
                    if proj.get("type") == "professional":
                        if proj.get("youtube_tutorials"):
                            text += f"\nYouTube Tutorials: {', '.join(proj['youtube_tutorials'])}"

                    # Add image if present
                    if proj.get("image"):
                        text += f"\nImage: {proj['image']}"

                    corpus_texts.append(text.strip())

            # Debug: Check if corpus_texts and projects have the same length
            print(
                f"[DEBUG] Projects count: {len(self.projects)}, Corpus texts count: {len(corpus_texts)}")
            if len(corpus_texts) != len(self.projects):
                print(
                    f"⚠️ WARNING: Mismatch between projects ({len(self.projects)}) and corpus texts ({len(corpus_texts)})")
                # Ensure they have the same length by truncating or padding
                if len(corpus_texts) > len(self.projects):
                    print(
                        f"⚠️ Truncating corpus_texts from {len(corpus_texts)} to {len(self.projects)}")
                    corpus_texts = corpus_texts[:len(self.projects)]
                else:
                    print(
                        f"⚠️ Padding corpus_texts from {len(corpus_texts)} to {len(self.projects)}")
                    while len(corpus_texts) < len(self.projects):
                        corpus_texts.append("")

            # Check for cached embeddings
            embedding_cache_file = self.cache_dir / \
                f"embeddings_{self._get_file_hash()}.pkl"

            # Force cache regeneration if we have professional story
            project_types = [p.get('type', 'unknown') for p in self.projects]
            if 'professional_story' in project_types and embedding_cache_file.exists():
                print("🔄 Professional story detected - clearing embedding cache")
                try:
                    embedding_cache_file.unlink()
                    print("🗑️ Deleted embedding cache file")
                except Exception as e:
                    print(f"⚠️ Could not delete cache file: {e}")

            # Also force ChromaDB regeneration if we have professional story with YouTube tutorials
            if 'professional_story' in project_types:
                for proj in self.projects:
                    if proj.get("type") == "professional_story" and proj.get("youtube_tutorials"):
                        print(
                            "🔄 Professional story with YouTube tutorials detected - forcing ChromaDB regeneration")
                        try:
                            # Get all document IDs and delete them
                            results = self.collection.get()
                            if results and results['ids']:
                                self.collection.delete(ids=results['ids'])
                                print(
                                    "🗑️ Cleared existing ChromaDB collection for YouTube tutorials")
                            break
                        except Exception as e:
                            print(f"❌ Could not clear collection: {e}")
                            print("🔄 Continuing with existing data...")

            if embedding_cache_file.exists():
                print("🚀 Loading cached embeddings...")
                try:
                    with open(embedding_cache_file, 'rb') as f:
                        cached_data = pickle.load(f)
                        if cached_data['texts'] == corpus_texts:
                            embeddings = cached_data['embeddings']
                            # Ensure cached embeddings are in proper format (convert tensors if needed)
                            embeddings = self._ensure_list_format(embeddings)
                            print("✅ Using cached embeddings")
                        else:
                            raise ValueError(
                                "Cached embeddings don't match current texts")
                except Exception as e:
                    print(f"⚠️ Cache invalid ({e}), regenerating...")
                    embeddings = self._generate_embeddings(corpus_texts)
                    self._cache_embeddings(
                        corpus_texts, embeddings, embedding_cache_file)
            else:
                embeddings = self._generate_embeddings(corpus_texts)
                self._cache_embeddings(
                    corpus_texts, embeddings, embedding_cache_file)

            # Add to ChromaDB in batches for better performance
            batch_size = 10
            # Use the length of projects, not corpus_texts, to avoid index errors
            total_projects = len(self.projects)
            for i in range(0, total_projects, batch_size):
                batch_texts = corpus_texts[i:i+batch_size]
                batch_embeddings = embeddings[i:i+batch_size]
                batch_ids = [f"proj_{j}" for j in range(
                    i, min(i+batch_size, total_projects))]

                # Create metadata for each project including type
                batch_metadatas = []
                for j in range(i, min(i+batch_size, total_projects)):
                    if j >= len(self.projects):
                        print(
                            f"⚠️ Index {j} out of range for projects (len={len(self.projects)})")
                        continue
                    project = self.projects[j]

                    # Handle different project types
                    if project.get("type") == "professional_story":
                        youtube_tutorials_raw = project.get(
                            "youtube_tutorials", [])
                        print(
                            f"[DEBUG] Raw YouTube tutorials for professional story: {youtube_tutorials_raw}")
                        youtube_tutorials_str = ", ".join(
                            youtube_tutorials_raw)
                        print(
                            f"[DEBUG] YouTube tutorials string: '{youtube_tutorials_str}'")

                        metadata = {
                            "type": project.get("type", "professional_story"),
                            "name": project.get("title", f"Professional Story {j}"),
                            "code_url": "",
                            "skills": "",
                            "image": "",
                            "youtube_tutorials": youtube_tutorials_str
                        }
                        print(
                            f"[DEBUG] Created metadata for professional story: {metadata}")
                    else:
                        metadata = {
                            "type": project.get("type", "software"),
                            "name": project.get("name", f"Project {j}"),
                            "code_url": project.get("code_url", ""),
                            "skills": ", ".join(project.get("skills", [])),
                            "image": project.get("image", "")
                        }

                        # Add additional metadata for professional profiles
                        if project.get("type") == "professional":
                            if project.get("youtube_tutorials"):
                                metadata["youtube_tutorials"] = ", ".join(
                                    project["youtube_tutorials"])
                                print(
                                    f"[DEBUG] Added YouTube tutorials to professional metadata: {metadata['youtube_tutorials']}")

                    batch_metadatas.append(metadata)

                    # Debug: Show batch array lengths
                    print(
                        f"[DEBUG] Batch {i//batch_size + 1}: texts={len(batch_texts)}, embeddings={len(batch_embeddings)}, metadatas={len(batch_metadatas)}, ids={len(batch_ids)}")

                    # Only add to ChromaDB if we have valid data
                    if batch_texts and batch_embeddings and batch_metadatas:
                        # Ensure all arrays have the same length
                        min_length = min(len(batch_texts), len(
                            batch_embeddings), len(batch_metadatas), len(batch_ids))
                        if min_length != len(batch_texts):
                            print(
                                f"⚠️ Truncating batch arrays to length {min_length} (texts: {len(batch_texts)}, embeddings: {len(batch_embeddings)}, metadatas: {len(batch_metadatas)}, ids: {len(batch_ids)})")

                        # Truncate all arrays to the minimum length
                        batch_texts = batch_texts[:min_length]
                        batch_embeddings = batch_embeddings[:min_length]
                        batch_metadatas = batch_metadatas[:min_length]
                        batch_ids = batch_ids[:min_length]

                self.collection.add(
                    documents=batch_texts,
                    embeddings=batch_embeddings,
                    ids=batch_ids,
                    metadatas=batch_metadatas
                )

                print(
                    f"✅ Added {len(corpus_texts)} projects to ChromaDB (optimized)")

        except Exception as e:
            print(f"❌ Error populating database: {e}")

    def _ensure_list_format(self, embeddings) -> List[List[float]]:
        """Ensure embeddings are in proper list format for ChromaDB."""
        # Handle different input types
        if embeddings is None:
            return []

        # If it's a list of tensors, convert each one
        if isinstance(embeddings, list) and len(embeddings) > 0:
            if hasattr(embeddings[0], 'numpy'):  # List of PyTorch tensors
                embeddings = [emb.numpy().tolist() if hasattr(
                    emb, 'numpy') else emb for emb in embeddings]
            elif hasattr(embeddings[0], 'tolist'):  # List of numpy arrays
                embeddings = [emb.tolist() if hasattr(
                    emb, 'tolist') else emb for emb in embeddings]
            return embeddings

        # If it's a single tensor or numpy array
        if hasattr(embeddings, 'numpy'):  # PyTorch tensor
            embeddings = embeddings.numpy()

        # Convert numpy array to list of lists
        if hasattr(embeddings, 'tolist'):
            return embeddings.tolist()

        return embeddings

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings with progress indication."""
        print(f"🔄 Generating embeddings for {len(texts)} documents...")
        embeddings = self.model.encode(
            texts, show_progress_bar=False, convert_to_numpy=True)

        # Ensure proper format using helper method
        return self._ensure_list_format(embeddings)

    def _cache_embeddings(self, texts: List[str], embeddings: List[List[float]], cache_file: Path):
        """Cache embeddings to disk for faster future loading."""
        try:
            cache_data = {
                'texts': texts,
                'embeddings': embeddings,
                'model_name': 'all-MiniLM-L6-v2',
                'projects': self.projects  # optional, for debug
            }
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            print(f"💾 Embeddings cached to {cache_file}")
        except Exception as e:
            print(f"⚠️ Failed to cache embeddings: {e}")

    def query_portfolio(self, question: str, top_k: int = 3, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query the portfolio database for relevant projects (with optional type filter)."""
        self._ensure_initialized()

        if not self.model or not self.collection:
            return []

        # First, try direct name matching for exact project names
        print(
            f"[DEBUG] Trying direct project matching for: '{question}' (filter: {filter_type})")
        direct_matches = self._find_direct_project_matches(
            question, filter_type)
        if direct_matches:
            print(
                f"🎯 Found direct project name match: {[m['metadata']['name'] for m in direct_matches]}")
            # Debug: Check metadata for YouTube tutorials
            for idx, match in enumerate(direct_matches):
                print(
                    f"[DEBUG] Direct match {idx} metadata: {match['metadata']}")
                if match['metadata'].get('type') in ['professional_story', 'professional']:
                    youtube_tutorials = match['metadata'].get(
                        'youtube_tutorials', '')
                    print(
                        f"[DEBUG] Direct match {idx} YouTube tutorials: '{youtube_tutorials}'")
            return direct_matches[:top_k]
        else:
            print(f"[DEBUG] No direct matches found, falling back to semantic search")

        try:
            q_embedding = self.model.encode(
                [question], convert_to_numpy=True)[0]
            q_embedding_list = self._ensure_list_format([q_embedding])
            q_embedding = q_embedding_list[0] if q_embedding_list else []

            # Check if collection has any documents
            collection_count = self.collection.count()
            print(f"[DEBUG] ChromaDB collection count: {collection_count}")

            if collection_count == 0:
                print(
                    f"[DEBUG] ChromaDB collection is empty, returning empty results")
                return []

            # Ensure n_results is at least 1
            n_results = max(1, min(top_k, collection_count))
            print(
                f"[DEBUG] Querying ChromaDB with n_results={n_results}, filter_type={filter_type}")

            results = self.collection.query(
                query_embeddings=[q_embedding],
                n_results=n_results,
                include=['documents', 'distances', 'metadatas'],
                where={"type": filter_type} if filter_type else None
            )

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            if documents:
                distances = results.get('distances', [[]])[0]
                print(
                    f"🔍 Found {len(documents)} relevant projects (best match: {distances[0]:.3f})")

            return [
                {
                    "text": doc,
                    "metadata": meta
                }
                for doc, meta in zip(documents, metadatas)
            ]

        except Exception as e:
            print(f"❌ Error querying portfolio: {e}")
            print(f"[DEBUG] Falling back to returning all projects for context")
            # Fallback: return all projects to ensure we have context for repository data
            fallback_matches = []
            for i, project in enumerate(self.projects):
                if filter_type and project.get("type") != filter_type:
                    continue

                project_display_name = project.get(
                    "name", project.get("title", f"Project {i}"))
                text = f"""Project: {project_display_name}
                    Description: {project.get('description', '')}
                    Skills: {", ".join(project.get("skills", []))}
                    Code URL: {project.get("code_url", "N/A")}
                    Notes:
                    - """ + "\n- ".join(project.get('notes', []))

                fallback_matches.append({
                    "text": text.strip(),
                    "metadata": {
                        "type": project.get("type", "software"),
                        "name": project_display_name,
                        "code_url": project.get("code_url", ""),
                        "skills": ", ".join(project.get("skills", [])),
                        "image": project.get("image", "")
                    }
                })

            return fallback_matches[:top_k]

    def _find_direct_project_matches(self, question: str, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find projects by direct name matching and skill-based matching before falling back to semantic search."""
        question_lower = question.lower().strip()

        # Special handling for LED/horticulture queries - prioritize LED grow light project
        if any(word in question_lower for word in ["led", "horticulture", "grow light", "hydroponic"]):
            print(f"[DEBUG] Looking for LED horticulture project...")
            for i, project in enumerate(self.projects):
                project_name = project.get('name', '').lower()
                project_type = project.get('type', '')
                project_skills = " ".join(project.get("skills", [])).lower()

                print(
                    f"[DEBUG] Checking project {i}: {project.get('name', 'Unknown')} (type: {project_type})")
                print(f"[DEBUG] Project name: '{project_name}'")
                print(f"[DEBUG] Project skills: '{project_skills}'")

                # Look specifically for the LED grow light project
                if (project_type == "hobby" and
                        "custom hydroponic hot pepper led grow light" in project_name):

                    print(
                        f"[DEBUG] Found LED horticulture project: {project['name']}")
                    # Create the same format as ChromaDB results for LED project
                    text = f"""Project: {project['name']}
                        Description: {project['description']}
                        Skills: {", ".join(project.get("skills", []))}
                        Code URL: {project.get("code_url", "N/A")}
                        Notes:
                        - """ + "\n- ".join(project.get('notes', []))

                    return [{
                        "text": text.strip(),
                        "metadata": {
                            "type": project.get("type", "hobby"),
                            "name": project.get("name", f"Project {i}"),
                            "code_url": project.get("code_url", ""),
                            "skills": ", ".join(project.get("skills", [])),
                            "image": project.get("image", "")
                        }
                    }]
            print(f"[DEBUG] No LED horticulture project found in direct search")

        # Special handling for manufacturing queries - prioritize AIDA project
        if "manufacturing" in question_lower:
            print(f"[DEBUG] Looking for AIDA manufacturing project...")
            print(f"[DEBUG] Filter type: {filter_type}")
            for i, project in enumerate(self.projects):
                print(
                    f"[DEBUG] Checking project {i}: {project.get('name', 'Unknown')} (type: {project.get('type', 'Unknown')})")
                if (project.get("type") == "electrical" and
                    "aida" in project.get("name", "").lower() and
                        "manufacturing" in " ".join(project.get("skills", [])).lower()):

                    print(
                        f"[DEBUG] Found AIDA manufacturing project: {project['name']}")
                    # Create the same format as ChromaDB results for AIDA project
                    text = f"""Project: {project['name']}
                        Description: {project['description']}
                        Skills: {", ".join(project.get("skills", []))}
                        Code URL: {project.get("code_url", "N/A")}
                        Notes:
                        - """ + "\n- ".join(project.get('notes', []))

                    return [{
                        "text": text.strip(),
                        "metadata": {
                            "type": project.get("type", "electrical"),
                            "name": project.get("name", f"Project {i}"),
                            "code_url": project.get("code_url", ""),
                            "skills": ", ".join(project.get("skills", [])),
                            "image": project.get("image", "")
                        }
                    }]
            print(f"[DEBUG] No AIDA manufacturing project found in direct search")

            # Fallback: Look for any electrical projects with manufacturing skills
            print(
                f"[DEBUG] Looking for any electrical projects with manufacturing skills...")
            manufacturing_projects = []
            for i, project in enumerate(self.projects):
                if (project.get("type") == "electrical" and
                        any("manufacturing" in skill.lower() for skill in project.get("skills", []))):
                    manufacturing_projects.append(project)
                    print(
                        f"[DEBUG] Found manufacturing project: {project['name']}")

            if manufacturing_projects:
                # Return the first manufacturing project found
                project = manufacturing_projects[0]
                text = f"""Project: {project['name']}
                    Description: {project['description']}
                    Skills: {", ".join(project.get("skills", []))}
                    Code URL: {project.get("code_url", "N/A")}
                    Notes:
                    - """ + "\n- ".join(project.get('notes', []))

                return [{
                    "text": text.strip(),
                    "metadata": {
                        "type": project.get("type", "electrical"),
                        "name": project.get("name", f"Project {i}"),
                        "code_url": project.get("code_url", ""),
                        "skills": ", ".join(project.get("skills", [])),
                        "image": project.get("image", "")
                    }
                }]

        # Special handling for professional profile queries
        if any(word in question_lower for word in ["professional", "profile", "background", "experience", "career", "resume", "cv", "about you", "your background"]):
            print(f"[DEBUG] Looking for professional profile...")
            for i, project in enumerate(self.projects):
                if project.get("type") == "professional":
                    print(
                        f"[DEBUG] Found professional profile: {project['name']}")
                    # Create the same format as ChromaDB results for professional profile
                    text = f"""Project: {project['name']}
                        Description: {project['description']}
                        Skills: {", ".join(project.get("skills", []))}
                        Code URL: {project.get("code_url", "N/A")}
                        Notes:
                        - """ + "\n- ".join(project.get('notes', []))

                    # Add YouTube tutorials if available
                    if project.get("youtube_tutorials"):
                        text += f"\nYouTube Tutorials: {', '.join(project['youtube_tutorials'])}"

                    return [{
                        "text": text.strip(),
                        "metadata": {
                            "type": project.get("type", "professional"),
                            "name": project.get("name", f"Project {i}"),
                            "code_url": project.get("code_url", ""),
                            "skills": ", ".join(project.get("skills", [])),
                            "image": project.get("image", ""),
                            "youtube_tutorials": ", ".join(project.get("youtube_tutorials", []))
                        }
                    }]
            print(f"[DEBUG] No professional profile found in direct search")

        # Special handling for professional story queries
        if any(word in question_lower for word in ["story", "journey", "path", "how did you", "how did you get", "your story", "your journey", "electrician coder", "bridging", "power systems and code"]):
            print(f"[DEBUG] Looking for professional story...")
            print(f"[DEBUG] Question: '{question_lower}'")
            print(
                f"[DEBUG] Available project types: {[p.get('type', 'unknown') for p in self.projects]}")
            for i, project in enumerate(self.projects):
                print(
                    f"[DEBUG] Checking project {i}: type={project.get('type', 'unknown')}, title={project.get('title', 'N/A')}")
                if project.get("type") == "professional_story":
                    print(
                        f"[DEBUG] Found professional story: {project.get('title', 'Professional Story')}")
                    # Create the same format as ChromaDB results for professional story
                    text = f"""Project: {project.get('title', 'Professional Story')}
                        Intro: {project.get('intro', '')}
                        """

                    # Add sections
                    for section in project.get("sections", []):
                        text += f"\n{section.get('heading', '')}:"
                        for content in section.get("content", []):
                            text += f"\n{content}"
                        for bullet in section.get("bullets", []):
                            text += f"\n- {bullet}"

                    # Add YouTube tutorials if available
                    if project.get("youtube_tutorials"):
                        text += f"\nYouTube Tutorials: {', '.join(project['youtube_tutorials'])}"

                    return [{
                        "text": text.strip(),
                        "metadata": {
                            "type": project.get("type", "professional_story"),
                            "name": project.get("title", f"Professional Story {i}"),
                            "code_url": "",
                            "skills": "",
                            "image": "",
                            "youtube_tutorials": ", ".join(project.get("youtube_tutorials", []))
                        }
                    }]
            print(f"[DEBUG] No professional story found in direct search")

        # Special handling for YouTube queries - prioritize professional story
        if any(word in question_lower for word in ["youtube", "video", "tutorial", "stream", "twitch", "reddit", "content"]):
            print(f"[DEBUG] Looking for YouTube/content projects...")
            for i, project in enumerate(self.projects):
                if project.get("type") == "professional_story" and project.get("youtube_tutorials"):
                    print(
                        f"[DEBUG] Found professional story with YouTube tutorials: {project.get('title', 'Professional Story')}")
                    # Create the same format as ChromaDB results for professional story
                    text = f"""Project: {project.get('title', 'Professional Story')}
                        Intro: {project.get('intro', '')}
                        """

                    # Add sections
                    for section in project.get("sections", []):
                        text += f"\n{section.get('heading', '')}:"
                        for content in section.get("content", []):
                            text += f"\n{content}"
                        for bullet in section.get("bullets", []):
                            text += f"\n- {bullet}"

                    # Add YouTube tutorials if available
                    if project.get("youtube_tutorials"):
                        text += f"\nYouTube Tutorials: {', '.join(project['youtube_tutorials'])}"

                    return [{
                        "text": text.strip(),
                        "metadata": {
                            "type": project.get("type", "professional_story"),
                            "name": project.get("title", f"Professional Story {i}"),
                            "code_url": "",
                            "skills": "",
                            "image": "",
                            "youtube_tutorials": ", ".join(project.get("youtube_tutorials", []))
                        }
                    }]
            print(f"[DEBUG] No YouTube projects found in direct search")

        # Remove common query words to extract project name
        query_words = ["what", "is", "tell", "me",
                       "about", "@bot", "whats", "what's"]
        for word in query_words:
            question_lower = question_lower.replace(word, "").strip()

        matches = []

        for i, project in enumerate(self.projects):
            # Skip if filter doesn't match
            if filter_type and project.get("type") != filter_type:
                continue

            # Handle different project formats (some use 'name', others use 'title')
            project_name = project.get(
                "name", project.get("title", f"Project {i}")).lower()

            # Check if the cleaned question matches the project name (full or partial)
            if (question_lower in project_name or
                # First word of project name
                project_name.split()[0] in question_lower or
                    any(word in project_name for word in question_lower.split() if len(word) > 3)):  # Significant words

                # Create the same format as ChromaDB results
                project_display_name = project.get(
                    "name", project.get("title", f"Project {i}"))
                text = f"""Project: {project_display_name}
                    Description: {project.get('description', '')}
                    Skills: {", ".join(project.get("skills", []))}
                    Code URL: {project.get("code_url", "N/A")}
                    Notes:
                    - """ + "\n- ".join(project.get('notes', []))
                if project.get("image"):
                    text += f"\nImage: {project['image']}"

                matches.append({
                    "text": text.strip(),
                    "metadata": {
                        "type": project.get("type", "software"),
                        "name": project_display_name,
                        "code_url": project.get("code_url", ""),
                        "skills": ", ".join(project.get("skills", [])),
                        "image": project.get("image", "")
                    }
                })

        return matches

    def ask_ollama_stream(
        self,
        query: str,
        matches: List[dict],
        user_id: str = "default",
        filter_type: Optional[str] = None,
        is_regenerate: bool = False
    ) -> Iterator[str]:
        """Generate a streaming response
          using Ollama HTTP API with project context."""
        print(f"[📤] Prompt → Ollama model {OLLAMA_CONFIG['MODEL']}")

        if not matches:
            yield self._get_fallback_response(query)
            return

        print(f"[DEBUG] Query: '{query}'")
        print(f"[DEBUG] Found {len(matches)} matches")
        for i, match in enumerate(matches):
            meta = match.get("metadata", {})
            print(
                f"[DEBUG] Match {i}: {meta.get('name', 'Unknown')} (type: {meta.get('type', 'unknown')})")
            print(f"[DEBUG]   - Image: '{meta.get('image', 'None')}'")
            print(
                f"[DEBUG]   - YouTube: '{meta.get('youtube_tutorials', 'None')}'")

        projects_with_images = self._extract_project_images(matches, top_n=2)
        if projects_with_images:
            self.current_project_images = projects_with_images

        context = self._build_context(matches, query)
        prompt = self._format_prompt(context, query)

        yield "[STATUS|Passing data to LLM...]"
        try:
            response = requests.post(
                OLLAMA_CONFIG["API_URL"],
                json={"model": OLLAMA_CONFIG["MODEL"],
                      "prompt": prompt, "stream": True},
                stream=True,
                timeout=OLLAMA_CONFIG["TIMEOUT"],
            )
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"❌ Ollama request failed: {e}")
            if is_regenerate:
                print(
                    f"🔄 Regenerate fallback: Providing alternative response for: {query}")
                yield self._get_alternative_response(matches, query)
            else:
                print(f"🔄 Falling back to simple response for: {query}")
                yield self._get_simple_response(matches, query)
            return

        if response.status_code != 200:
            print(f"❌ Ollama HTTP {response.status_code}")
            if is_regenerate:
                print(
                    f"🔄 Regenerate fallback: Providing alternative response for: {query}")
                yield self._get_alternative_response(matches, query)
            else:
                print(f"🔄 Falling back to simple response for: {query}")
                yield self._get_simple_response(matches, query)
            return

        # Stream the response and collect the full text simultaneously
        full_response = ""
        for chunk in self._stream_response(response):
            # Extract actual text content from status chunks
            if not chunk.startswith("[STATUS|"):
                full_response += chunk
            yield chunk

        # Append image‑gallery button only if we have actual images
        print(f"[DEBUG] projects_with_images: {projects_with_images}")
        if projects_with_images and len(projects_with_images) > 0:
            # Double-check that we have valid image paths
            valid_images = [
                img for img in projects_with_images if img.get("image", "").strip()]
            print(f"[DEBUG] valid_images after filtering: {valid_images}")
            if valid_images:
                print(
                    f"[DEBUG] Adding image gallery button with {len(valid_images)} images")
                yield "\n\n[BUTTON|view_project_images|View Images]"
            else:
                print(
                    f"[DEBUG] No valid images found, skipping image gallery button")
        else:
            print(f"[DEBUG] No projects_with_images found")

        # Insert YouTube gallery if applicable
        print(
            f"[DEBUG] Calling _maybe_append_youtube_gallery with query: '{query}'")
        youtube_added = self._maybe_append_youtube_gallery(
            matches, full_response, query)
        if youtube_added:
            print(f"[DEBUG] Adding YouTube gallery: {youtube_added}")
            yield f"\n\n{youtube_added}"
        else:
            print(f"[DEBUG] No YouTube gallery to add")

        # Add programming report button for programming-related queries
        if self._is_programming_query(query):
            yield "\n\n[BUTTON|show_programming_report|View Detailed Programming Report]"

        # Finally save the response
        self.save_query_and_response(query, full_response, user_id)

    # — Helpers —

    def _extract_project_images(self, matches: List[dict], top_n: int) -> List[dict]:
        imgs = []
        print(f"[DEBUG] Extracting project images from {len(matches)} matches")
        for i, m in enumerate(matches[:top_n]):
            try:
                metadata = m.get("metadata", {})
                if not metadata:
                    print(
                        f"⚠️ Warning: No metadata found in match {i}, skipping image extraction")
                    continue

                img = metadata.get("image", "").strip()
                project_name = metadata.get("name", "Project")
                print(
                    f"[DEBUG] Match {i} - Project: {project_name}, Image: '{img}'")

                if img and img != "N/A" and img != "":
                    # Check if the image file actually exists
                    import os
                    static_dir = "server/static"
                    image_path = os.path.join(static_dir, img.lstrip("/"))

                    if os.path.exists(image_path) or os.path.exists(image_path + ".jpg") or os.path.exists(image_path + ".png") or os.path.exists(image_path + ".jpeg"):
                        imgs.append({
                            "name": project_name,
                            "image": img
                        })
                        print(
                            f"[DEBUG] Added valid image for {project_name}: {img}")
                    else:
                        print(
                            f"[DEBUG] Image file does not exist: {image_path}")
                else:
                    print(f"[DEBUG] No valid image found for {project_name}")
            except Exception as e:
                print(f"❌ Error extracting project image: {e}")
                continue
        print(f"[DEBUG] Extracted {len(imgs)} valid images")
        return imgs

    def _build_context(self, matches: List[dict], query: str = "") -> str:
        parts = []
        for m in matches:
            try:
                md = m.get("metadata", {})
                if not md:
                    # Instead of skipping, use a default structure
                    lines = ["Project: Unknown Project"]
                    lines.append(m.get("text", ""))
                    parts.append("\n".join(lines))
                    continue

                lines = [f"Project: {md.get('name', 'Project')}"]
                lines.append(m.get("text", ""))
                if md.get("type") == "software" and md.get("code_url"):
                    lines.append(f"GitHub: {md['code_url']}")
                if md.get("type") in ("professional", "professional_story") and md.get("youtube_tutorials"):
                    lines.append(
                        f"YouTube Tutorials: {md['youtube_tutorials']}")
                parts.append("\n".join(lines))
            except Exception as e:
                print(f"❌ Error building context for match: {e}")
                # Try to salvage what we can from the match
                try:
                    lines = ["Project: Unknown Project"]
                    lines.append(m.get("text", ""))
                    parts.append("\n".join(lines))
                except:
                    continue

        context = "\n---\n".join(parts)

        # Add repository data for programming-related queries
        programming_keywords = ["programming", "code", "python", "javascript",
                                "languages", "libraries", "repositories", "github", "development", "software"]
        matching_keywords = [
            keyword for keyword in programming_keywords if keyword in query.lower()]
        print(f"[DEBUG] _build_context - Query: '{query}'")
        print(
            f"[DEBUG] _build_context - Matching programming keywords: {matching_keywords}")

        if query and matching_keywords:
            print(
                f"[DEBUG] _build_context - Adding repository data for programming query")
            repo_context = self._format_repo_data_for_context()
            if repo_context:
                print(f"[DEBUG] _build_context - Repository data added to context")
                context += f"\n\n{repo_context}"
            else:
                print(f"[DEBUG] _build_context - No repository data available")
        else:
            print(
                f"[DEBUG] _build_context - Not a programming query, skipping repository data")

        return context

    def _format_prompt(self, context: str, query: str) -> str:
        style = PROMPT_CONFIG["CURRENT_STYLE"]
        template = PROMPT_CONFIG["STYLES"][style]
        return template.format(context=context, query=query)

    def _stream_response(self, response: requests.Response) -> Iterator[str]:
        """
        Stream response chunks from Ollama.
        """
        buffer = ""
        count = 0

        for chunk in response.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            data = json.loads(chunk)
            text = data.get("response", "")
            buffer += text
            count += 1

            # periodic status
            if count % 10 == 0:
                yield f"[STATUS|Generated {count} chunks...]"

            # flush on punctuation or length
            if text in (" ", ".", "!", "?", "\n") or len(buffer) >= 10:
                yield buffer
                buffer = ""

            if data.get("done"):
                if buffer:
                    yield buffer
                    break

    def _collect_full_response(self, response: requests.Response) -> str:
        """
        Collect the full response text from Ollama without streaming.
        """
        full_text = ""
        for chunk in response.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            data = json.loads(chunk)
            text = data.get("response", "")
            full_text += text

            if data.get("done"):
                break

        return full_text

    def _maybe_append_youtube_gallery(self, matches: List[dict], full_text: str, query: str = "") -> Optional[str]:
        print(
            f"[DEBUG] _maybe_append_youtube_gallery called with query: '{query}'")
        print(f"[DEBUG] Checking {len(matches)} matches for YouTube content")
        for m in matches:
            if m["metadata"].get("type") in ("professional", "professional_story"):
                vids = m["metadata"].get("youtube_tutorials", "")
                if vids and vids.strip():  # Check if youtube_tutorials exists and is not empty
                    urls = [u.strip() for u in vids.split(",") if u.strip()]
                    if urls:  # Only proceed if we have valid URLs
                        print(f"[DEBUG] Found YouTube tutorials: {urls}")
                        # Only show YouTube gallery for general professional queries, not for specific technical questions
                        project_name = m["metadata"].get("name", "Project")

                        # Check if this is a general professional query vs a specific technical question
                        specific_technical_keywords = [
                            "electrical", "qa", "quality", "manufacturing", "datacenter",
                            "power", "ats", "inverter", "generator", "servo", "press",
                            "excel", "tracker", "audit", "construction", "powersystem"
                        ]

                        is_specific_technical = any(
                            keyword in query.lower() for keyword in specific_technical_keywords)

                        print(f"[DEBUG] Query: '{query}'")
                        print(
                            f"[DEBUG] Specific technical keywords found: {[kw for kw in specific_technical_keywords if kw in query.lower()]}")
                        print(
                            f"[DEBUG] is_specific_technical: {is_specific_technical}")

                        # Show YouTube gallery for general queries (including fun/hobby queries) that mention tutorials
                        fun_hobby_keywords = [
                            "fun", "hobby", "hobbies", "enjoy", "passion", "interest", "what does", "whats"]
                        is_fun_hobby_query = any(
                            keyword in query.lower() for keyword in fun_hobby_keywords)

                        if is_specific_technical:
                            print(
                                f"[DEBUG] Skipping YouTube gallery for specific technical query: '{query}'")
                        elif is_fun_hobby_query:
                            print(
                                f"[DEBUG] Adding YouTube gallery for fun/hobby query: '{query}'")
                            return self._create_youtube_gallery(urls, project_name)
                        else:
                            print(
                                f"[DEBUG] Adding YouTube gallery for general professional query: '{query}'")
                            return self._create_youtube_gallery(urls, project_name)
                    else:
                        print(
                            f"[DEBUG] No valid YouTube URLs found in: {vids}")
                else:
                    print(f"[DEBUG] No YouTube tutorials found in metadata")
        print(f"[DEBUG] No YouTube gallery created for any matches")
        return None

    def _get_simple_response(self, matches: List[Dict[str, Any]], query: str) -> str:
        if not matches:
            return self._get_fallback_response(query)

        match = matches[0]
        meta = match.get("metadata", {})
        project_name = meta.get("name", "a project")
        project_type = meta.get("type", "software")
        skills = meta.get("skills", "").split(", ")[:3]
        code_url = meta.get("code_url")
        image = meta.get("image")
        youtube_tutorials = meta.get("youtube_tutorials", "")

        print(f"[DEBUG] _get_simple_response - project_type: {project_type}")
        print(
            f"[DEBUG] _get_simple_response - youtube_tutorials: {youtube_tutorials}")

        # Handle different project types
        if project_type == "professional_story":
            # For professional story, return the full text content
            response = match.get("text", "")

            # Add YouTube gallery if available
            if youtube_tutorials:
                # Parse URLs and filter out empty ones
                if isinstance(youtube_tutorials, str):
                    youtube_urls = [
                        url.strip() for url in youtube_tutorials.split(",") if url.strip()]
                else:
                    youtube_urls = youtube_tutorials

                if youtube_urls:  # Only proceed if we have valid URLs
                    print(
                        f"[DEBUG] Creating YouTube gallery with URLs: {youtube_urls}")
                    gallery_command = self._create_youtube_gallery(
                        youtube_urls, project_name)
                    print(
                        f"[DEBUG] YouTube gallery command: {gallery_command}")
                    response += f"\n\n{gallery_command}"
                else:
                    print(f"[DEBUG] No valid YouTube URLs found")
            else:
                print(f"[DEBUG] No YouTube tutorials in metadata")

            return response

        elif project_type == "professional":
            # For professional profile, return the full text content
            response = match.get("text", "")

            # Add YouTube gallery if available
            if youtube_tutorials:
                # Parse URLs and filter out empty ones
                if isinstance(youtube_tutorials, str):
                    youtube_urls = [
                        url.strip() for url in youtube_tutorials.split(",") if url.strip()]
                else:
                    youtube_urls = youtube_tutorials

                if youtube_urls:  # Only proceed if we have valid URLs
                    print(
                        f"[DEBUG] Creating YouTube gallery with URLs: {youtube_urls}")
                    gallery_command = self._create_youtube_gallery(
                        youtube_urls, project_name)
                    print(
                        f"[DEBUG] YouTube gallery command: {gallery_command}")
                    response += f"\n\n{gallery_command}"
                else:
                    print(f"[DEBUG] No valid YouTube URLs found")
            else:
                print(f"[DEBUG] No YouTube tutorials in metadata")

            return response
        else:
            # For regular projects
            response = f"I worked on {project_name}, which involved {', '.join(skills)}."

            # Always include GitHub link if available (and not empty/N/A)
            if code_url and code_url != "N/A" and code_url.strip():
                response += f"\n\n**GitHub:** {code_url}"

        if image:
            response += f"\n\nImages available: {image}"
            # Add button for viewing images
            response += "\n\n[BUTTON|view_project_images|View Images]"

        return response

    def _get_alternative_response(self, matches: List[Dict[str, Any]], query: str) -> str:
        """Provide an alternative response when regenerating to avoid duplicates."""
        if not matches:
            return self._get_fallback_response(query)

        # For regenerate requests, provide a different perspective or format
        match = matches[0]
        meta = match.get("metadata", {})
        project_name = meta.get("name", "a project")
        project_type = meta.get("type", "software")
        skills = meta.get("skills", "").split(", ")[:3]

        # Create an alternative response format
        if project_type == "electrical":
            if "qa" in query.lower() or "quality" in query.lower():
                return f"Absolutely! Ryan's electrical QA experience is quite extensive. He's worked on {project_name}, where he applied {', '.join(skills)}. His approach to quality assurance involves systematic documentation, thorough testing protocols, and ensuring compliance with industry standards. This experience has given him a deep understanding of electrical systems and the importance of maintaining high quality standards in critical infrastructure."
            elif "manufacturing" in query.lower():
                return f"Ryan has significant manufacturing experience through his work on {project_name}. This involved {', '.join(skills)}, working with heavy machinery and industrial systems. His manufacturing background includes both assembly and retrofit work, giving him hands-on experience with production environments and the technical challenges of industrial automation."
            else:
                return f"Ryan's electrical work on {project_name} demonstrates his expertise in {', '.join(skills)}. This project showcases his ability to handle complex electrical systems and his attention to detail in ensuring reliable operation. His experience spans both installation and maintenance of critical electrical infrastructure."
        else:
            # For other project types, provide a different perspective
            return f"Looking at Ryan's work on {project_name}, he demonstrated proficiency in {', '.join(skills)}. This project highlights his technical capabilities and his ability to deliver results in challenging environments. His experience shows a strong foundation in both theoretical knowledge and practical application."

    def _get_fallback_response(self, query: str) -> str:
        """Provide fallback response when no relevant projects found."""
        fallbacks = [
            "That's an interesting question! I focus on web development, AI integration, and full-stack applications. What specific area interests you?",
            "Great question! My work spans Python, JavaScript, machine learning, and web technologies. Would you like to know more about any of these?",
            "I'd love to help! My projects involve modern web development, AI, and software engineering. What would you like to explore?",
            "Interesting! I work with technologies like Python, React, and AI systems. Is there a particular project type you're curious about?"
        ]

        import random
        return random.choice(fallbacks)

    def _create_youtube_links(self, text: str) -> str:
        """Convert YouTube URLs to clickable links in the text."""
        import re

        # Pattern to match YouTube URLs
        youtube_pattern = r'https://youtu\.be/([a-zA-Z0-9_-]+)'

        def replace_youtube_url(match):
            video_id = match.group(1)
            return f'[YouTube Video](https://youtu.be/{video_id})'

        # Replace YouTube URLs with clickable links
        text = re.sub(youtube_pattern, replace_youtube_url, text)

        return text

    def _clean_thinking_tags(self, text: str) -> str:
        """Remove any thinking tags that might have been generated by the LLM."""
        import re

        # Remove common thinking tags and their content
        patterns = [
            r'<think>.*?</think>',  # <think>...</think>
            r'<reasoning>.*?</reasoning>',  # <reasoning>...</reasoning>
            r'<thought>.*?</thought>',  # <thought>...</thought>
            r'<analysis>.*?</analysis>',  # <analysis>...</analysis>
            r'<step>.*?</step>',  # <step>...</step>
            r'<process>.*?</process>',  # <process>...</process>
        ]

        cleaned_text = text
        for pattern in patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text,
                                  flags=re.DOTALL | re.IGNORECASE)

        # Remove any remaining thinking tag markers
        cleaned_text = re.sub(r'<[^>]*think[^>]*>',
                              '', cleaned_text, flags=re.IGNORECASE)

        # Handle incomplete thinking tags (like <think> without closing tag)
        cleaned_text = re.sub(r'<think>.*', '', cleaned_text,
                              flags=re.DOTALL | re.IGNORECASE)
        cleaned_text = re.sub(r'<reasoning>.*', '',
                              cleaned_text, flags=re.DOTALL | re.IGNORECASE)

        # Remove thinking patterns that don't use tags
        thinking_patterns = [
            r'hmm,.*?(?=\n|$)',  # "Hmm, the user is asking..."
            r'looking at.*?(?=\n|$)',  # "Looking at the context..."
            r'i should.*?(?=\n|$)',  # "I should structure the response..."
            r'the user is asking.*?(?=\n|$)',  # "The user is asking about..."
        ]

        for pattern in thinking_patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text,
                                  flags=re.DOTALL | re.IGNORECASE)

        # Clean up extra whitespace and excessive line breaks
        cleaned_text = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned_text)
        # Normalize whitespace
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
        cleaned_text = cleaned_text.strip()

        return cleaned_text

    def _get_off_topic_response(self, query: str) -> str:
        """Provide response when question is not portfolio-related."""
        responses = [
            "I'm Ryan's portfolio assistant, so I can only help with questions about his professional work, projects, and technical skills. Feel free to ask about his programming projects, electrical engineering work, or hobby builds!",

            "I specialize in discussing Ryan's technical expertise and projects. I'd be happy to tell you about his software development work, manufacturing experience, or electronics projects instead!",

            "That's outside my area - I focus on Ryan's portfolio and professional experience. Ask me about his Python projects, electrical QA work, or hardware builds!",

            "I'm here to discuss Ryan's technical work and projects. I can tell you about his programming skills, manufacturing experience, or hobby electronics - what interests you?",

            "I only cover Ryan's professional portfolio and technical projects. Try asking about his software development, electrical engineering work, or PCB designs!"
        ]

        import random
        return random.choice(responses)

    def get_response(self, query: str, user_id: str = "default") -> str:
        """Get a single response string (non-streaming) for the bot."""
        print(
            f"[DEBUG] get_response called with query: '{query}' for user: {user_id}")
        try:
            # Try to get a direct match first (faster)
            direct_matches = self._find_direct_project_matches(query)
            print(f"[DEBUG] Direct matches: {direct_matches}")
            if direct_matches:
                print(f"[DEBUG] Found direct matches, using simple response")
                return self._get_simple_response(direct_matches, query)

            # If no direct match, try the full pipeline with timeout protection
            print(f"[DEBUG] No direct matches, trying full pipeline...")

            # Get the response stream and collect all chunks with timeout
            response_chunks = []
            import time
            start_time = time.time()
            timeout = 30  # 30 second timeout

            for chunk in self.get_response_stream(query, user_id):
                if time.time() - start_time > timeout:
                    print(f"[DEBUG] Timeout reached, returning partial response")
                    break
                print(f"[DEBUG] Got chunk: '{chunk[:50]}...'")
                response_chunks.append(chunk)

            # Join all chunks into a single response
            full_response = ''.join(response_chunks)
            print(f"[DEBUG] Full response length: {len(full_response)}")

            if not full_response.strip():
                print(f"[DEBUG] Empty response, using fallback")
                return self._get_fallback_response(query)

            return full_response

        except Exception as e:
            print(f"❌ Error in get_response: {e}")
            import traceback
            traceback.print_exc()
            return self._get_fallback_response(query)

    def get_response_stream(self, query: str, user_id: str = "default", bypass_predefined: bool = False) -> Iterator[str]:
        """Main optimized method to get a streaming response to a query, with hobby handling."""
        print(
            f"[DEBUG] get_response_stream called with query: '{query}' for user: {user_id}")
        print(f"[DEBUG] bypass_predefined: {bypass_predefined}")

        # Check for button clicks first
        button_result = self.handle_button_click(query, user_id)
        if button_result:
            print(
                f"[DEBUG] Button click handled, returning: {button_result[:50]}...")
            yield button_result
            return

        # Clear any old global image data when starting a new query (not a button click)
        self.current_project_images = []

        if not self.projects:
            print(f"[DEBUG] No projects loaded, using fallback")
            yield self._get_fallback_response(query)
            return

        user_state = self.get_user_state(user_id)
        print(f"[DEBUG] User state: {user_state}")

        # If waiting for user to pick a hobby, check if this is actually a hobby selection
        if user_state.get("awaiting_hobby_choice"):
            print(f"[DEBUG] User is awaiting hobby choice")
            # Check if the query looks like a hobby selection (number or hobby name match)
            cleaned_query = query.strip().lower()
            hobby_projects = user_state.get("last_hobby_list", [])

            # Is this a number selection (1, 2, 3)?
            is_number_selection = cleaned_query.isdigit() and 1 <= int(
                cleaned_query) <= len(hobby_projects)

            # Is this a hobby name match?
            is_name_match = any(
                cleaned_query in proj["name"].lower() for proj in hobby_projects)

            if is_number_selection or is_name_match:
                # This looks like a hobby selection, handle it
                result = self.handle_hobby_selection(query, user_id)
                yield result or "Please click a 'View Photos' button to see project details."
                return
        else:
            print(f"[DEBUG] User is not awaiting hobby choice")

        # If user asked about hobbies - expanded detection
        hobby_keywords = [
            "hobbies", "hobby projects", "hobby project", "personal projects",
            "hardware projects", "electronics projects", "diy projects",
            "side projects", "hobby showcases", "hobby work", "what hobbies",
            "tell me about his hobbies", "hardware work", "electronics work"
        ]
        if any(keyword in query.lower() for keyword in hobby_keywords):
            print(f"[DEBUG] Hobby keywords detected, handling hobby list")
            yield self.handle_hobby_list(user_id)
            return

        # Intercept software/project list questions and respond with predefined text
        # BUT skip predefined response if bypass_predefined is True
        if not bypass_predefined and any(kw in query.lower() for kw in [
            "programming projects", "software projects", "code projects", "python projects",
            "what projects has he built", "list his projects", "developer projects",
            "programming languages", "languages", "what languages", "programming language"
        ]):
            print(
                f"[DEBUG] Software project keywords detected, using predefined response")
            yield from self._predefined_software_projects()
            return
        elif bypass_predefined and any(kw in query.lower() for kw in [
            "programming projects", "software projects", "code projects", "python projects",
            "what projects has he built", "list his projects", "developer projects",
            "programming languages", "languages", "what languages", "programming language"
        ]):
            print(
                f"[DEBUG] Software project keywords detected but bypass_predefined=True, skipping predefined response")

        # Check if the query is portfolio-related before processing
        print(f"[DEBUG] Checking if query is portfolio-related: '{query}'")
        is_portfolio = self.is_portfolio_related(query)
        print(f"[DEBUG] Query portfolio-related: {is_portfolio}")

        if not is_portfolio:
            print(f"[DEBUG] Query not portfolio-related, using off-topic response")
            yield self._get_off_topic_response(query)
            return

        print(f"[DEBUG] Query is portfolio-related, proceeding with full processing")
        try:
            filter_type = self.infer_filter_type(query)
            print(
                f"[DEBUG] Filter type detected: {filter_type} for query: '{query}'")

            # Detect broad queries that should return more results
            is_broad_query = any(phrase in query.lower() for phrase in [
                "programming projects", "software projects", "projects", "portfolio",
                "all projects", "what projects", "work on", "built", "developed"
            ])

            # Use more results for broad queries
            top_k = 6 if is_broad_query else 3
            print(
                f"[DEBUG] Querying portfolio with top_k={top_k}, filter_type={filter_type}")
            matches = self.query_portfolio(
                query, top_k=top_k, filter_type=filter_type)
            print(
                f"[DEBUG] Found {len(matches)} matches for '{query}' (filter={filter_type}, top_k={top_k})")
            print(
                f"[DEBUG] Project names: {[m.get('metadata', {}).get('name', 'Unknown') for m in matches]}")

            # Check if this is a regenerate request
            is_regenerate = "[REGENERATE]" in query

            # Clear cache for programming-related queries that might have been incorrectly cached
            if self._is_programming_query(query) and not is_regenerate:
                print(f"[DEBUG] Programming query detected, checking cache...")
                # The cache bypass logic in routes.py should handle this, but we can add extra logging here

            yield from self.ask_ollama_stream(query, matches, user_id, filter_type, is_regenerate)
        except Exception as e:
            print(f"❌ Error getting streaming response: {e}")
            print(f"🔍 Query that failed: '{query}'")
            print(f"🔍 Filter type: {filter_type}")
            print(
                f"🔍 Number of matches: {len(matches) if 'matches' in locals() else 'N/A'}")
            import traceback
            traceback.print_exc()

            # Try to provide a more specific fallback for manufacturing queries
            if "manufacturing" in query.lower():
                print(
                    f"🔄 Providing manufacturing-specific fallback for: {query}")
                yield "Ryan has significant manufacturing experience working with AIDA America on servo press assembly and retrofit projects. He worked on presses ranging from 200 to 4,000 metric tons, installing electrical systems, routing communication cables, and integrating modern PLCs and safety interlocks. This work involved both in-house manufacturing and on-site retrofitting in live production environments."
            else:
                yield self._get_fallback_response(query)

    def _predefined_software_projects(self) -> Iterator[str]:
        yield (
            "Ryan has worked on several programming projects:\n\n"
            "1. **PyProfileDataGen**: Automatically enhances GitHub profiles with real-time visual analytics of Python repositories, utilizing skills such as Python, GitHub Actions, Data Visualization, Plotly, Pandas, Matplotlib, Regex, GitHub API, Automation, Heatmaps, and Word Clouds.\n"
            "https://github.com/sockheadrps/PyProfileDataGen\n\n"
            "2. **Palindrome Detection**: Built a custom NLP pipeline to classify palindromes with 99.88% accuracy using progressively refined models (LSTM → GRU → Transformer), employing skills such as Python, NLP, TensorFlow/Keras, LSTM, GRU, Transformer, Data Augmentation, Model Training, Contrastive Examples, and Active Learning.\n"
            "https://github.com/sockheadrps/PalindromeTransformerClassifier\n\n"
            "3. **FastAPI WebSocket Chat App**: A modern real-time chat application built with FastAPI, WebSockets, SQLite, and vanilla JS, utilizing skills such as FastAPI, WebSockets, Authentication, SQLite, JWT, Passlib, Bcrypt, RSA, Pydantic, Jinja2, SQLAlchemy, and JavaScript.\n"
            "https://github.com/sockheadrps/websocketchat\n\n"
            "4. **rpaudio**: A Rust-based Python library for non-blocking audio playback with a simple API, designed to work seamlessly with async runtimes and provide efficient, cross-platform audio control using Rust's safety and performance.\n"
            "https://github.com/sockheadrps/rpaudio\n\n"
            "[BUTTON|show_programming_report|View Detailed Programming Report]"
        )

    def is_portfolio_related(self, question: str) -> bool:
        """Check if a question is related to portfolio topics (projects, skills, experience)."""
        q = question.lower()
        print(f"[DEBUG] is_portfolio_related checking: '{q}'")

        # Portfolio-related keywords
        portfolio_keywords = [
            # General portfolio terms
            "project", "projects", "work", "experience", "skill", "skills", "portfolio", "built", "developed", "created",
            "technologies", "technology", "expertise", "background", "accomplishments", "achievements",

            # Programming/Software
            "programming", "software", "python", "javascript", "code", "coding", "github", "api", "websocket",
            "model", "fastapi", "plotly", "pyo3", "async", "chatbot", "frontend", "library", "libraries", "app", "application",
            "development", "web", "fullstack", "framework", "database", "algorithm", "nlp", "machine learning",
            "tensorflow", "keras", "rust", "pydantic", "jwt", "authentication", "encryption",

            # Electrical/Manufacturing
            "electrical", "qa", "infrared", "tegg", "thermal", "ultrasonic", "power distribution", "voltage",
            "inspection", "manufacturing", "press", "assembly", "retrofit", "tonnage", "metric", "aida",
            "servo", "mechanical", "industrial", "production",

            # Hardware/Hobbies
            "hardware", "hobby", "hobbies", "pcb", "etching", "soldering", "prototyping", "embedded",
            "microcontroller", "midi", "ble", "rgb", "led", "strip", "guitar", "overlay", "effects",
            "musical", "interface", "design", "electronics", "circuit", "van", "esp32", "controller",

            # Technical skills
            "technical", "engineering", "architect", "design", "implementation", "testing", "debugging",
            "optimization", "performance", "security", "scalability",

            # Personal/Life questions
            "fun", "hobby", "hobbies", "personal", "life", "about", "who", "what", "how", "when", "where", "why",
            "story", "journey", "background", "experience", "interests", "passion", "enjoy", "like", "love",

            # Content creation and sharing
            "youtube", "video", "tutorial", "tutorials", "content", "stream", "streaming", "twitch", "reddit",
            "mentor", "teaching", "sharing", "knowledge", "educational", "content creation"
        ]

        # Check if any portfolio keywords are present
        matching_keywords = [
            keyword for keyword in portfolio_keywords if keyword in q]
        if matching_keywords:
            print(f"[DEBUG] Found portfolio keywords: {matching_keywords}")
            return True

        # Check for common question patterns about portfolio
        portfolio_patterns = [
            "what did", "what have", "tell me about", "show me", "can you", "how did", "what projects",
            "what work", "what experience", "what skills", "what technologies", "what tools", "what libraries",
            "what does", "what do", "whats", "what's", "who is", "who's", "how is", "how's", "when does",
            "where does", "why does", "tell me", "show me", "can you tell", "do you know",
            "does he", "does she", "do they", "does ryan", "does he do", "does he have"
        ]

        matching_patterns = [
            pattern for pattern in portfolio_patterns if pattern in q]
        if matching_patterns:
            print(f"[DEBUG] Found portfolio patterns: {matching_patterns}")
            return True

        print(f"[DEBUG] No portfolio keywords or patterns found")
        return False

    def infer_filter_type(self, question: str) -> Optional[str]:
        """Infer whether the user is asking about electrical, software, or manufacturing projects."""
        q = question.lower()

        # Manufacturing/Industrial projects (AIDA press work)
        if any(word in q for word in ["manufacturing", "press", "assembly", "retrofit", "tonnage", "metric", "aida", "servo", "mechanical", "industrial", "production"]):
            return "electrical"  # AIDA project is stored as electrical type

        # Electrical projects (TEGG work)
        if any(word in q for word in ["electrical", "qa", "infrared", "tegg", "thermal", "ultrasonic", "power distribution", "voltage", "inspection"]):
            return "electrical"

        if any(word in q for word in ["programming", "software", "python", "code", "github", "api", "websocket", "model", "fastapi", "plotly", "pyo3", "async", "chatbot", "frontend", "library", "libraries", "app", "application", "development"]):
            return "software"
        if any(word in q for word in ["hardware", "hobby", "hobbies", "pcb", "etching", "soldering", "prototyping", "embedded", "microcontroller", "midi", "ble", "rgb", "led", "strip", "guitar", "overlay", "effects", "musical", "interface", "design"]):
            return "hobby"

        # Professional profile queries
        if any(word in q for word in ["professional", "profile", "background", "experience", "career", "resume", "cv", "about you", "your background", "work history", "professional experience", "skills", "expertise", "qualifications"]):
            return "professional"

        # Professional story queries
        if any(word in q for word in ["story", "journey", "path", "how did you", "how did you get", "your story", "your journey", "electrician coder", "bridging", "power systems and code", "mission critical", "data centers", "servo press"]):
            return "professional_story"

        return None  # fallback to no filter

    def save_query_and_response(self, query: str, response: str, username: str = "unknown", ip_address: str = None):
        """Save query and response to database with user information and IP address."""
        try:
            db = SessionLocal()
            chat_entry = ChatHistory(
                username=username,
                message=query,
                response=response,
                timestamp=datetime.utcnow(),
                ip_address=ip_address
            )
            db.add(chat_entry)
            db.commit()
            print(
                f"💾 Saved chat history for user {username} from {ip_address or 'unknown IP'}")
        except Exception as e:
            print(f"❌ Error saving chat history: {e}")
        finally:
            db.close()

    def save_response(self, query: str, username: str, response: str, ip_address: str = None):
        """Alias for save_query_and_response for compatibility."""
        self.save_query_and_response(query, response, username, ip_address)

    def get_chat_history(self, username: str = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieve chat history from database, optionally filtered by username."""
        try:
            db = SessionLocal()
            query = db.query(ChatHistory)

            if username:
                query = query.filter(ChatHistory.username == username)

            # Order by timestamp descending (most recent first) and limit results
            chat_history = query.order_by(
                ChatHistory.timestamp.desc()).limit(limit).all()

            # Convert to list of dictionaries
            history_list = []
            for entry in chat_history:
                history_list.append({
                    "id": entry.id,
                    "username": entry.username,
                    "message": entry.message,
                    "response": entry.response,
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "ip_address": entry.ip_address
                })

            return history_list

        except Exception as e:
            print(f"❌ Error retrieving chat history: {e}")
            return []
        finally:
            db.close()

    @classmethod
    def cleanup_cache(cls):
        """Clean up class-level cached resources."""
        cls._model_cache = None
        cls._chroma_client = None
        print("🧹 Cleaned up cached resources")

    def _create_youtube_gallery(self, youtube_urls, project_name):
        """Create a YouTube gallery command for the frontend to handle"""
        print(
            f"[DEBUG] _create_youtube_gallery called with URLs: {youtube_urls}, project: {project_name}")

        if not youtube_urls:
            print("[DEBUG] No YouTube URLs provided")
            return ""

        # Ensure youtube_urls is a list, not a string
        if isinstance(youtube_urls, str):
            youtube_urls = [youtube_urls]

        # Filter out empty or invalid URLs
        valid_urls = []
        for url in youtube_urls:
            if url and url.strip() and url.strip() != "":
                valid_urls.append(url.strip())

        if not valid_urls:
            print("[DEBUG] No valid YouTube URLs found after filtering")
            return ""

        if len(valid_urls) == 1:
            # Single video - send gallery command
            command = f"[YOUTUBE_SHOW|{valid_urls[0]}|{project_name}]"
        else:
            # Multiple videos - send gallery command with pipe-separated URLs
            videos_str = "||".join(valid_urls)
            command = f"[YOUTUBE_SHOW|{videos_str}|{project_name}]"

        print(f"[DEBUG] Created YouTube gallery command: {command}")
        return command

    def _stream_and_collect_single_pass(self, response: requests.Response) -> tuple[Iterator[str], str]:
        """
        Stream response chunks and collect full text in a single pass.
        Returns (chunk_generator, full_text)
        """
        chunks = []
        full_text = ""
        buffer = ""
        count = 0

        for chunk in response.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            data = json.loads(chunk)
            text = data.get("response", "")
            buffer += text
            full_text += text
            count += 1

            # periodic status
            if count % 10 == 0:
                status_chunk = f"[STATUS|Generated {count} chunks...]"
                chunks.append(status_chunk)

            # flush on punctuation or length
            if text in (" ", ".", "!", "?", "\n") or len(buffer) >= 10:
                chunks.append(buffer)
                buffer = ""

            if data.get("done"):
                if buffer:
                    chunks.append(buffer)
                    full_text += buffer
                break

        def replay_generator():
            for chunk in chunks:
                yield chunk

        return replay_generator(), full_text
