import json
import os
import hashlib
import pickle
from pathlib import Path
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any, Optional
import subprocess
import chromadb
from chromadb.config import Settings



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

        print("📁 Loading software and electrical projects...")
        software_projects = load_file("server/chat/projects.json", default_type="software")
        electrical_projects = load_file("server/chat/electrical.json", default_type="electrical")

        self.projects = software_projects + electrical_projects
        print(f"✅ Loaded {len(self.projects)} total projects")


    

    
    def _ensure_initialized(self):
        """Lazy initialization of model and database only when needed."""
        if self.model is None:
            self._initialize_model()
        if self.collection is None:
            self._initialize_chromadb()
            self._populate_database()
    
    def _get_file_hash(self) -> str:
        """Generate hash of projects file for cache invalidation."""
        try:
            with open(self.projects_file, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
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
Skills: {', '.join(proj['skills'])}
Notes:
- """ + "\n- ".join(proj['notes'])
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
                        "skills": ", ".join(project.get("skills", []))
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
                'timestamp': os.path.getmtime(self.projects_file)
            }
            with open(cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            print(f"💾 Embeddings cached to {cache_file}")
        except Exception as e:
            print(f"⚠️ Failed to cache embeddings: {e}")
    
    def query_portfolio(self, question: str, top_k: int = 3, filter_type: Optional[str] = None) -> List[str]:
        """Query the portfolio database for relevant projects (with optional type filter)."""
        self._ensure_initialized()

        if not self.model or not self.collection:
            return []

        try:
            q_embedding = self.model.encode([question], convert_to_numpy=True)[0]
            q_embedding_list = self._ensure_list_format([q_embedding])
            q_embedding = q_embedding_list[0] if q_embedding_list else []

            results = self.collection.query(
                query_embeddings=[q_embedding],
                n_results=min(top_k, self.collection.count()),
                include=['documents', 'distances'],
                where={"type": filter_type} if filter_type else None
            )

            documents = results['documents'][0] if results['documents'] else []

            if documents:
                distances = results.get('distances', [[]])[0]
                print(f"🔍 Found {len(documents)} relevant projects (best match: {distances[0]:.3f})")

            return documents

        except Exception as e:
            print(f"❌ Error querying portfolio: {e}")
            return []

    
    def ask_ollama(self, query: str, matches: List[str]) -> str:
        """Generate response using Ollama with relevant project context."""
        try:
            
            
            if not matches:
                return self._get_fallback_response(query)
            
            # Create context from matches
            context = "\n---\n".join(matches)
            prompt = f"""You are an assistant that explains Ryan's software and electrical projects clearly and concisely. Label electrical projects as such. Use few words and only the most relevant details.

Context about Ryan's projects:
{context}

User question: {query}

Provide a helpful, concise response based on the project information above."""

            
            # Call Ollama
            result = subprocess.run(
                ["ollama", "run", "mistral"],
                input=prompt.encode(),
                capture_output=True,
                timeout=30  # 30 second timeout
            )
            
            if result.returncode == 0:
                response = result.stdout.decode().strip()
                return response if response else self._get_fallback_response(query)
            else:
                print(f"❌ Ollama error: {result.stderr.decode()}")
                return self._get_simple_response(matches, query)
                
        except subprocess.TimeoutExpired:
            print("⏰ Ollama request timed out")
            return "I'm thinking about that... Could you try asking again in a moment?"
        except FileNotFoundError:
            print("❌ Ollama not found - using simple responses")
            matches = self.query_portfolio(query)
            return self._get_simple_response(matches, query)
        except Exception as e:
            print(f"❌ Error with Ollama: {e}")
            matches = self.query_portfolio(query)
            return self._get_simple_response(matches, query)
    
    def _get_simple_response(self, matches: List[str], query: str) -> str:
        """Generate a simple response without Ollama."""
        if not matches:
            return self._get_fallback_response(query)
        
        # Extract project name from first match
        first_match = matches[0]
        lines = first_match.split('\n')
        project_name = "a project"
        skills = []
        
        for line in lines:
            if line.strip().startswith("Project:"):
                project_name = line.split("Project:")[1].strip()
            elif line.strip().startswith("Skills:"):
                skills_text = line.split("Skills:")[1].strip()
                skills = [s.strip() for s in skills_text.split(',')][:4]
        
        query_lower = query.lower()
        
        if any(word in query_lower for word in ['skills', 'technologies', 'tech']):
            return f"I have experience with {', '.join(skills)} and more, particularly in projects like {project_name}."
        elif any(word in query_lower for word in ['project', 'work', 'built']):
            return f"I worked on {project_name}, which involved {', '.join(skills[:3])}. It's a great example of my development experience."
        else:
            return f"That relates to my work on {project_name}. I used technologies like {', '.join(skills[:3])} for this project."
    
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
    
    def get_response(self, query: str) -> str:
        """Main optimized method to get a response to a query."""
        # Ensure all components are ready
        if not self.projects:
            return self._get_fallback_response(query)
        
        try:
            filter_type = self.infer_filter_type(query)
            matches = self.query_portfolio(query, filter_type=filter_type)
            return self.ask_ollama(query, matches)
        except Exception as e:
            print(f"❌ Error getting response: {e}")
            return self._get_fallback_response(query)
    

    def infer_filter_type(self, question: str) -> Optional[str]:
        """Infer whether the user is asking about electrical or software projects."""
        q = question.lower()

        if any(word in q for word in ["ups", "generator", "ats", "transformer", "relay", "wiring", "electrical", "data center", "tegg", "voltage", "load bank", "retrofit", "qa", "commissioning"]):
            return "electrical"

        if any(word in q for word in ["python", "code", "project", "github", "api", "websocket", "model", "fastapi", "plotly", "pyo3", "async", "chatbot", "frontend"]):
            return "software"

        return None  # fallback to no filter

    
    @classmethod
    def cleanup_cache(cls):
        """Clean up class-level cached resources."""
        cls._model_cache = None
        cls._chroma_client = None
        print("🧹 Cleaned up cached resources") 