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

# ========== CONFIGURATION ==========
# WebSocket Endpoints - Configure your chat connections here
WEBSOCKET_CONFIG = {
    # Local development
    "LOCAL_WS_URL": "ws://localhost:8080/ws",
    
    # Production
    "PRODUCTION_WS_URL": "wss://chat.socksthoughtshop.lol/ws",
    
    # Current active URL (should match frontend)
    "ACTIVE_WS_URL": "wss://chat.socksthoughtshop.lol/ws"
}

# Ollama Configuration - Customize your AI model settings here
OLLAMA_CONFIG = {
    # Ollama API URL
    "API_URL": "http://localhost:11434/api/generate",
    
    # Model name (options: mistral, tinyllama, llama2, llama3.2, codellama, deepseek-r1:latest, etc.)
    "MODEL": "llama3.2",
    
    # Request timeout in seconds
    "TIMEOUT": 300,
    
    # Stream responses for real-time typing effect
    "STREAM": True
}



PROMPT_CONFIG = {
    "CURRENT_STYLE": "default",
    
    "STYLES": {
        "default": """You are Ryan's personal portfolio assistant. You ONLY answer questions about Ryan's professional work, projects, skills, and technical experience.

IMPORTANT: Only respond to questions about:
- Programming/software projects (Python, JavaScript, FastAPI, etc.)
- Electrical engineering work (QA, manufacturing, AIDA press projects, TEGG work)
- Hardware/hobby projects (PCBs, electronics, guitars, etc.)
- Technical skills and professional experience
- Development tools, technologies, and methodologies used

For anything else (cooking, general life advice, non-technical topics), politely decline and redirect to portfolio topics.

For software/programming projects, include any available GitHub links if present in the context. For electrical, manufacturing, or hardware projects, focus on the technical skills and experience rather than code repositories.

Use ONLY the facts provided in the context below. Do not make up information.

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
            
            # Only initialize if we have projects
            if self.projects:
                self._ensure_initialized()
                print(f"✅ Portfolio Assistant ready with {len(self.projects)} projects")
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
                if default_type:
                    for proj in data:
                        proj.setdefault("type", default_type)
                return data

        print("📁 Loading software, electrical, and hobby projects...")
        software_projects = load_file("server/chat/projects.json", default_type="software")
        electrical_projects = load_file("server/chat/electrical.json", default_type="electrical")
        hobby_projects = load_file("server/chat/hobby.json", default_type="hobby")

        self.projects = software_projects + electrical_projects + hobby_projects
        print(f"✅ Loaded {len(self.projects)} total projects")



    def list_hobby_projects(self) -> str:
        hobbies = [proj for proj in self.projects if proj.get("type") == "hobby"]
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
                user_state["awaiting_hobby_choice"] = False  # Reset only on success
                project = hobby_projects[index]
                return self._summarize_project(project)

        # Try match by name
        for proj in hobby_projects:
            if selection in proj["name"].lower():
                user_state["awaiting_hobby_choice"] = False  # Reset only on success
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
                relative_path = image_path.replace("C:/Users/rpski/Desktop/chat/server/static/assets/", "")
                full_path = image_path  # Use the absolute path for file operations
            elif image_path.startswith("/static/assets/"):
                # Relative path starting with /static/assets/
                relative_path = image_path.replace("/static/assets/", "")
                full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
            elif image_path.startswith("/assets/"):
                # Relative path starting with /assets/
                relative_path = image_path.replace("/assets/", "")
                full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
            elif image_path.startswith("assets/"):
                # Relative path starting with assets/ (no leading slash)
                relative_path = image_path.replace("assets/", "")
                full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
            else:
                # For non-standard paths, skip image
                print(f"🔍 Skipping non-standard image path in summary: {image_path}")
                return
            
            # Initialize empty list for image files
            image_files_to_show = []
            
            # Check if it's a directory with multiple images
            if os.path.isdir(full_path):
                # Get all image files from the directory
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                
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
                image_gallery = self._create_image_gallery(image_files_to_show, proj["name"])
                if image_gallery:
                    lines.append(f"\n{image_gallery}")

        if proj.get("notes"):
            lines.append("\n**Highlights:**\n" + "\n".join(f"- {n}" for n in proj["notes"]))

        return "\n".join(lines)


    def render_project_detail(self, project: dict) -> str:
        out = f"**{project['name']}**\n\n{project['description']}\n\n"
        if project.get("notes"):
            out += "Highlights:\n" + "\n".join(f"- {note}" for note in project["notes"]) + "\n\n"
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
                    hobby_projects = [p for p in self.projects if p.get("type") == "hobby"]
                    
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
                        gallery_result = self._process_project_image(image_path, proj_name)
                        if gallery_result:
                            gallery_commands.append(gallery_result)
                    
                    if gallery_commands:
                        # Return just the gallery commands - the issue might be in frontend processing
                        return "\n".join(gallery_commands)
                    else:
                        return "Sorry, I couldn't load the images for these projects."
                    
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
            images_str = "||".join(images)  # Use || as separator to avoid conflicts
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
            relative_path = image_path.replace("C:/Users/rpski/Desktop/chat/server/static/assets/", "")
            full_path = image_path  # Use the absolute path for file operations
        elif image_path.startswith("/static/assets/"):
            # Relative path starting with /static/assets/
            relative_path = image_path.replace("/static/assets/", "")
            full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
        elif image_path.startswith("/assets/"):
            # Relative path starting with /assets/
            relative_path = image_path.replace("/assets/", "")
            full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
        elif image_path.startswith("assets/"):
            # Relative path starting with assets/ (no leading slash)
            relative_path = image_path.replace("assets/", "")
            full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
        else:
            # For non-standard paths, skip image
            print(f"🔍 Skipping non-standard image path: {image_path}")
            return None
        
        # Initialize empty list for image files
        image_files_to_show = []
        
        # Check if it's a directory with multiple images
        if os.path.isdir(full_path):
            # Get all image files from the directory
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
            
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
            desc += "Highlights:\n" + "\n".join(f"- {note}" for note in hobby["notes"]) + "\n\n"
        
        if hobby.get("image"):
            # Handle image paths (directories or single files)
            import os
            image_path = hobby['image']
            
            # Determine if we have an absolute or relative path and process accordingly
            if image_path.startswith("C:/Users/rpski/Desktop/chat/server/static/assets/"):
                # Absolute path - convert to relative
                relative_path = image_path.replace("C:/Users/rpski/Desktop/chat/server/static/assets/", "")
                full_path = image_path  # Use the absolute path for file operations
            elif image_path.startswith("/static/assets/"):
                # Relative path starting with /static/assets/
                relative_path = image_path.replace("/static/assets/", "")
                full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
            elif image_path.startswith("/assets/"):
                # Relative path starting with /assets/
                relative_path = image_path.replace("/assets/", "")
                full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
            elif image_path.startswith("assets/"):
                # Relative path starting with assets/ (no leading slash)
                relative_path = image_path.replace("assets/", "")
                full_path = f"server/static/assets/{relative_path}"  # Convert to absolute for file operations
            else:
                # Unsupported path format
                desc += f"📷 Images: {image_path}"
                return desc
            
            # Initialize empty list for image files
            image_files_to_show = []
            
            # Check if it's a directory with multiple images
            if os.path.isdir(full_path):
                # Get all image files from the directory
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                
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
                gallery_result = self._create_image_gallery(image_files_to_show, hobby['name'])
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
            # Include all three JSON files in the hash calculation
            file_paths = [
                "server/chat/projects.json",
                "server/chat/electrical.json", 
                "server/chat/hobby.json"
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
                PortfolioAssistant._model_cache = SentenceTransformer("all-MiniLM-L6-v2")
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
                return
            
            print("📊 Generating and caching embeddings...")
            
            # Create corpus texts
            corpus_texts = []
            for proj in self.projects:
                text = f"""Project: {proj['name']}
                    Description: {proj['description']}
                    Skills: {", ".join(proj.get("skills", []))}
                    Code URL: {proj.get("code_url", "N/A")}
                    Notes:
                    - """ + "\n- ".join(proj['notes'])
                if proj.get("image"):
                    text += f"\nImage: {proj['image']}"
                corpus_texts.append(text.strip())
            
            # Check for cached embeddings
            embedding_cache_file = self.cache_dir / f"embeddings_{self._get_file_hash()}.pkl"
            
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
                            raise ValueError("Cached embeddings don't match current texts")
                except Exception as e:
                    print(f"⚠️ Cache invalid ({e}), regenerating...")
                    embeddings = self._generate_embeddings(corpus_texts)
                    self._cache_embeddings(corpus_texts, embeddings, embedding_cache_file)
            else:
                embeddings = self._generate_embeddings(corpus_texts)
                self._cache_embeddings(corpus_texts, embeddings, embedding_cache_file)
            
            # Add to ChromaDB in batches for better performance
            batch_size = 10
            for i in range(0, len(corpus_texts), batch_size):
                batch_texts = corpus_texts[i:i+batch_size]
                batch_embeddings = embeddings[i:i+batch_size]
                batch_ids = [f"proj_{j}" for j in range(i, min(i+batch_size, len(corpus_texts)))]
                
                # Create metadata for each project including type
                batch_metadatas = []
                for j in range(i, min(i+batch_size, len(corpus_texts))):
                    project = self.projects[j]
                    metadata = {
                        "type": project.get("type", "software"),
                        "name": project.get("name", f"Project {j}"),
                        "code_url": project.get("code_url", ""),
                        "skills": ", ".join(project.get("skills", [])),
                        "image": project.get("image", "")
                    }
                    batch_metadatas.append(metadata)
                
                self.collection.add(
                    documents=batch_texts,
                    embeddings=batch_embeddings,
                    ids=batch_ids,
                    metadatas=batch_metadatas
                )
            
            print(f"✅ Added {len(corpus_texts)} projects to ChromaDB (optimized)")
            
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
                embeddings = [emb.numpy().tolist() if hasattr(emb, 'numpy') else emb for emb in embeddings]
            elif hasattr(embeddings[0], 'tolist'):  # List of numpy arrays
                embeddings = [emb.tolist() if hasattr(emb, 'tolist') else emb for emb in embeddings]
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
        embeddings = self.model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        
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
        direct_matches = self._find_direct_project_matches(question, filter_type)
        if direct_matches:
            print(f"🎯 Found direct project name match: {[m['metadata']['name'] for m in direct_matches]}")
            return direct_matches[:top_k]

        try:
            q_embedding = self.model.encode([question], convert_to_numpy=True)[0]
            q_embedding_list = self._ensure_list_format([q_embedding])
            q_embedding = q_embedding_list[0] if q_embedding_list else []

            results = self.collection.query(
                query_embeddings=[q_embedding],
                n_results=min(top_k, self.collection.count()),
                include=['documents', 'distances', 'metadatas'],
                where={"type": filter_type} if filter_type else None
            )

            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            if documents:
                distances = results.get('distances', [[]])[0]
                print(f"🔍 Found {len(documents)} relevant projects (best match: {distances[0]:.3f})")

            return [
                {
                    "text": doc,
                    "metadata": meta
                }
                for doc, meta in zip(documents, metadatas)
            ]

        except Exception as e:
            print(f"❌ Error querying portfolio: {e}")
            return []
    
    def _find_direct_project_matches(self, question: str, filter_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Find projects by direct name matching and skill-based matching before falling back to semantic search."""
        question_lower = question.lower().strip()
        
        # Special handling for manufacturing queries - prioritize AIDA project
        if "manufacturing" in question_lower and filter_type == "electrical":
            for i, project in enumerate(self.projects):
                if (project.get("type") == "electrical" and 
                    "aida" in project.get("name", "").lower() and
                    "manufacturing" in " ".join(project.get("skills", [])).lower()):
                    
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
        
        # Remove common query words to extract project name
        query_words = ["what", "is", "tell", "me", "about", "@bot", "whats", "what's"]
        for word in query_words:
            question_lower = question_lower.replace(word, "").strip()
        
        matches = []
        
        for i, project in enumerate(self.projects):
            # Skip if filter doesn't match
            if filter_type and project.get("type") != filter_type:
                continue
                
            project_name = project["name"].lower()
            
            # Check if the cleaned question matches the project name (full or partial)
            if (question_lower in project_name or 
                project_name.split()[0] in question_lower or  # First word of project name
                any(word in project_name for word in question_lower.split() if len(word) > 3)):  # Significant words
                
                # Create the same format as ChromaDB results
                text = f"""Project: {project['name']}
                    Description: {project['description']}
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
                        "name": project.get("name", f"Project {i}"),
                        "code_url": project.get("code_url", ""),
                        "skills": ", ".join(project.get("skills", [])),
                        "image": project.get("image", "")
                    }
                })
                
        return matches

    
    def ask_ollama_stream(self, query: str, matches: List[str], user_id: str = "default", filter_type: str = None) -> Iterator[str]:
        """Generate streaming response using Ollama HTTP API with relevant project context."""
        print(f"[📤] Sending prompt to Ollama model: {OLLAMA_CONFIG['MODEL']}")
        try:
            if not matches:
                yield self._get_fallback_response(query)
                return
            
            # Check if any matches have images - be selective based on query type
            projects_with_images = []
            query_lower = query.lower()

            # Show images for visual requests OR when asking about experience/projects in domains that have images
            should_show_images = any(phrase in query_lower for phrase in [
                "show me", "images", "pictures", "photos", "visual", "see the", "look at",
                "projects he built", "project showcases", "manufacturing projects", 
                "hobby projects", "electronics projects", "hardware projects",
                "press projects", "assembly projects", "view projects",
                # Experience-based queries that should show images if available
                "manufacturing experience", "electrical experience", "hardware experience",
                "manufacturing", "press", "assembly", "servo", "aida", "electrical qa",
                "hobby", "hobbies", "electronics", "pcb"
            ])

            # Detect if this is a broad project listing query
            is_broad_query = any(phrase in query_lower for phrase in [
                "programming projects", "software projects", "projects", "portfolio", 
                "all projects", "what projects", "work on", "built", "developed"
            ])
            
            # Only populate images if the query specifically requests visual information
            if should_show_images:
                if is_broad_query:
                    # For broad queries, check multiple matches for images
                    for m in matches[:2]:  # Only consider top 2 most relevant matches
                        image_path = m['metadata'].get('image', '')
                        project_name = m['metadata'].get('name', '').lower()
                        
                        # Skip projects that don't match the query context
                        if any(word in query_lower for word in ["manufacturing", "press", "assembly", "tonnage", "aida", "servo"]):
                            # For manufacturing queries, prefer AIDA project
                            if "tegg" in project_name and "aida" not in project_name:
                                continue
                        elif any(word in query_lower for word in ["electrical", "qa", "infrared", "tegg", "thermal"]):
                            # For electrical QA queries, prefer TEGG project  
                            if "aida" in project_name and "tegg" not in project_name:
                                continue
                            
                        if image_path and image_path.strip():
                            projects_with_images.append({
                                'name': m['metadata'].get('name', 'Project'),
                                'image': image_path
                            })
                else:
                    # For specific project queries, only show images if the TOP/most relevant match has images
                    if matches and len(matches) > 0:
                        top_match = matches[0]
                        image_path = top_match['metadata'].get('image', '')
                        if image_path and image_path.strip():
                            projects_with_images.append({
                                'name': top_match['metadata'].get('name', 'Project'),
                                'image': image_path
                            })
            
            # Store image data globally for button clicks (shared across all users)
            if projects_with_images:
                self.current_project_images = projects_with_images
            
            # Create context from matches
            context_parts = []
            for m in matches:
                text = m['text']
                github_url = m['metadata'].get('code_url', '')
                image_path = m['metadata'].get('image', '')
                project_type = m['metadata'].get('type', '')
                project_name = m['metadata'].get('name', 'Project')

                # Only include GitHub for software/programming projects
                github_line = ""
                if project_type == "software" and github_url and github_url != "N/A":
                    github_line = f"\nGitHub: {github_url}"
                    print(f"🔍 GitHub URL: {github_line}")

                # Create context entry without GitHub for non-software projects
                context_parts.append(
                    f"Project: {project_name}\n"
                    f"{text}{github_line}\n"
                )

            context = "\n---\n".join(context_parts)
            
            # Use current active prompt style
            current_style = PROMPT_CONFIG["CURRENT_STYLE"]
            prompt_template = PROMPT_CONFIG["STYLES"][current_style]
            prompt = prompt_template.format(context=context, query=query)
            
            # Call Ollama HTTP API with streaming
            payload = {
                "model": OLLAMA_CONFIG["MODEL"],
                "prompt": prompt,
                "stream": OLLAMA_CONFIG["STREAM"]
            }
            
            try:
                response = requests.post(
                    OLLAMA_CONFIG["API_URL"],
                    json=payload,
                    stream=True,
                    timeout=OLLAMA_CONFIG["TIMEOUT"]
                )
                
                if response.status_code == 200:
                    buffer = ""
                    response_complete = False
                    
                    for line in response.iter_lines():
                        if line:
                            try:
                                data = json.loads(line.decode('utf-8'))
                                if 'response' in data:
                                    chunk = data['response']
                                    buffer += chunk
                                    
                                    # Yield complete words/sentences for smoother display
                                    if chunk in [' ', '.', '!', '?', '\n'] or len(buffer) >= 10:
                                        yield buffer
                                        buffer = ""
                                
                                # Check if generation is done
                                if data.get('done', False):
                                    if buffer:  # Yield any remaining content
                                        yield buffer
                                    response_complete = True
                                    break
                                    
                            except json.JSONDecodeError:
                                continue
                    
                    # Add image button if response completed successfully and we have images
                    if response_complete and projects_with_images:
                        yield "\n\n[BUTTON|view_project_images|View Images]"
                    
                        
                else:
                    print(f"❌ Ollama HTTP error: {response.status_code}")
                    yield self._get_simple_response(matches, query)
                    
            except requests.exceptions.ConnectionError:
                print("❌ Cannot connect to Ollama - is it running?")
                yield self._get_simple_response(matches, query)
            except requests.exceptions.Timeout:
                print("⏰ Ollama request timed out")
                yield "I'm thinking about that... Could you try asking again in a moment?"
                
        except Exception as e:
            print(f"❌ Error with Ollama streaming: {e}")
            yield self._get_simple_response(matches, query)
    
    def _get_simple_response(self, matches: List[Dict[str, Any]], query: str) -> str:
        if not matches:
            return self._get_fallback_response(query)

        match = matches[0]
        meta = match.get("metadata", {})
        project_name = meta.get("name", "a project")
        skills = meta.get("skills", "").split(", ")[:3]
        code_url = meta.get("code_url")
        image = meta.get("image")
        
        response = f"I worked on {project_name}, which involved {', '.join(skills)}."
        
        # Always include GitHub link if available (and not empty/N/A)
        if code_url and code_url != "N/A" and code_url.strip():
            response += f"\n\n**GitHub:** {code_url}"
        
        if image:
            response += f"\n\nImages available: {image}"
        return response


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
    
    def get_response_stream(self, query: str, user_id: str = "default") -> Iterator[str]:
        """Main optimized method to get a streaming response to a query, with hobby handling."""
        
        # Check for button clicks first
        button_result = self.handle_button_click(query, user_id)
        if button_result:
            yield button_result
            return
        
        # Clear any old global image data when starting a new query (not a button click)
        self.current_project_images = []
        
        if not self.projects:
            yield self._get_fallback_response(query)
            return

        user_state = self.get_user_state(user_id)

        # If waiting for user to pick a hobby, check if this is actually a hobby selection
        if user_state.get("awaiting_hobby_choice"):
            # Check if the query looks like a hobby selection (number or hobby name match)
            cleaned_query = query.strip().lower()
            hobby_projects = user_state.get("last_hobby_list", [])
            
            # Is this a number selection (1, 2, 3)?
            is_number_selection = cleaned_query.isdigit() and 1 <= int(cleaned_query) <= len(hobby_projects)
            
            # Is this a hobby name match?
            is_name_match = any(cleaned_query in proj["name"].lower() for proj in hobby_projects)
            
            if is_number_selection or is_name_match:
                # This looks like a hobby selection, handle it
                result = self.handle_hobby_selection(query, user_id)
                yield result or "Please click a 'View Photos' button to see project details."
                return
            else:
                # This is a different question, clear the hobby state and continue processing
                print(f"[DEBUG] Clearing hobby state for unrelated query: {query}")
                user_state["awaiting_hobby_choice"] = False
                user_state["last_hobby_list"] = []
                # Continue processing the new query below

        # If user asked about hobbies - expanded detection
        hobby_keywords = [
            "hobbies", "hobby projects", "hobby project", "personal projects", 
            "hardware projects", "electronics projects", "diy projects",
            "side projects", "hobby showcases", "hobby work", "what hobbies",
            "tell me about his hobbies", "hardware work", "electronics work"
        ]
        if any(keyword in query.lower() for keyword in hobby_keywords):
            yield self.handle_hobby_list(user_id)
            return
        
        # Intercept software/project list questions and respond with predefined text
        if any(kw in query.lower() for kw in [
            "programming projects", "software projects", "code projects", "python projects",
            "what projects has he built", "list his projects", "developer projects"
        ]):
            yield from self._predefined_software_projects()
            return

        # Check if the query is portfolio-related before processing
        if not self.is_portfolio_related(query):
            yield self._get_off_topic_response(query)
            return

        try:
            filter_type = self.infer_filter_type(query)
            print(f"[DEBUG] Filter type detected: {filter_type} for query: '{query}'")
            
            # Detect broad queries that should return more results
            is_broad_query = any(phrase in query.lower() for phrase in [
                "programming projects", "software projects", "projects", "portfolio", 
                "all projects", "what projects", "work on", "built", "developed"
            ])
            
            # Use more results for broad queries
            top_k = 6 if is_broad_query else 3
            matches = self.query_portfolio(query, top_k=top_k, filter_type=filter_type)
            print(f"[DEBUG] Found {len(matches)} matches for '{query}' (filter={filter_type}, top_k={top_k})")
            print(f"[DEBUG] Project names: {[m.get('metadata', {}).get('name', 'Unknown') for m in matches]}")
            yield from self.ask_ollama_stream(query, matches, user_id, filter_type)
        except Exception as e:
            print(f"❌ Error getting streaming response: {e}")
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
            "https://github.com/sockheadrps/rpaudio"
        )

    def is_portfolio_related(self, question: str) -> bool:
        """Check if a question is related to portfolio topics (projects, skills, experience)."""
        q = question.lower()
        
        # Portfolio-related keywords
        portfolio_keywords = [
            # General portfolio terms
            "project", "projects", "work", "experience", "skill", "skills", "portfolio", "built", "developed", "created",
            "technologies", "technology", "expertise", "background", "accomplishments", "achievements",
            
            # Programming/Software
            "programming", "software", "python", "javascript", "code", "coding", "github", "api", "websocket", 
            "model", "fastapi", "plotly", "pyo3", "async", "chatbot", "frontend", "library", "app", "application", 
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
            "optimization", "performance", "security", "scalability"
        ]
        
        # Check if any portfolio keywords are present
        if any(keyword in q for keyword in portfolio_keywords):
            return True
            
        # Check for common question patterns about portfolio
        portfolio_patterns = [
            "what did", "what have", "tell me about", "show me", "can you", "how did", "what projects",
            "what work", "what experience", "what skills", "what technologies", "what tools"
        ]
        
        if any(pattern in q for pattern in portfolio_patterns):
            return True
            
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

        if any(word in q for word in ["programming", "software", "python", "code", "github", "api", "websocket", "model", "fastapi", "plotly", "pyo3", "async", "chatbot", "frontend", "library", "app", "application", "development"]):
            return "software"
        if any(word in q for word in ["hardware", "hobby", "hobbies", "pcb", "etching", "soldering", "prototyping", "embedded", "microcontroller", "midi", "ble", "rgb", "led", "strip", "guitar", "overlay", "effects", "musical", "interface", "design"]):
            return "hobby"

        return None  # fallback to no filter

    
    @classmethod
    def cleanup_cache(cls):
        """Clean up class-level cached resources."""
        cls._model_cache = None
        cls._chroma_client = None
        print("🧹 Cleaned up cached resources") 
