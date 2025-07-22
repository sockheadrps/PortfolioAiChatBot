from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from server.db.db import SessionLocal
from server.auth.auth import get_user_by_username
from server.chat.portfolio_assistant import PortfolioAssistant
from server.cache.client_cache import client_cache
import json
import os
import time
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from dotenv import load_dotenv
from server.chat.portfolio_assistant import OLLAMA_CONFIG

load_dotenv()


router = APIRouter()

# Pydantic models for request/response


class CacheEntry(BaseModel):
    question: str
    response: str


class CacheRequest(BaseModel):
    question: str
    response: Optional[str] = None


class CacheResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

# Get database session


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Simple admin authentication using environment variable


def get_admin_user(request: Request):
    admin_username = os.getenv("ADMIN_USERNAME")
    admin_password = os.getenv("ADMIN_PASSWORD")

    print(
        f"🔍 Checking credentials: {admin_username} / {'SET' if admin_password else 'NOT SET'}")

    if not admin_username or not admin_password:
        raise HTTPException(
            status_code=500, detail="Admin credentials not configured")

    # Get credentials from request headers
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        raise HTTPException(
            status_code=401, detail="Basic authentication required")

    import base64
    try:
        credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
        username, password = credentials.split(":", 1)
        print(
            f"🔐 Decoded credentials: {username} / {'SET' if password else 'NOT SET'}")
    except:
        raise HTTPException(
            status_code=401, detail="Invalid authentication format")

    if username != admin_username or password != admin_password:
        print(
            f"❌ Invalid credentials: expected {admin_username}, got {username}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    print(f"✅ Authentication successful for: {username}")
    return username


async def get_admin_user_async(request: Request):
    return get_admin_user(request)

# Get cache file path


def get_cache_file_path():
    return os.path.join(os.getcwd(), "cache_data.json")

# Load cache data


def load_cache_data():
    print("🔍 Loading cache data...")
    try:
        cache_file = get_cache_file_path()
        print(f"📁 Cache file path: {cache_file}")

        if os.path.exists(cache_file):
            print(
                f"✅ Cache file exists, size: {os.path.getsize(cache_file)} bytes")
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"📊 Loaded {len(data)} cache entries")
                return data
        else:
            print("❌ Cache file does not exist")
            return {}
    except Exception as e:
        print(f"❌ Error loading cache data: {e}")
        import traceback
        traceback.print_exc()
        return {}

# Save cache data


def save_cache_data(cache_data):
    print("💾 Saving cache data...")
    try:
        cache_file = get_cache_file_path()
        print(f"📁 Saving to: {cache_file}")

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        print(f"✅ Saved {len(cache_data)} cache entries")
        return True
    except Exception as e:
        print(f"❌ Error saving cache data: {e}")
        import traceback
        traceback.print_exc()
        return False


@router.get("/cache/status", response_model=CacheResponse)
async def get_cache_status(request: Request, admin: str = Depends(get_admin_user)):
    """Get cache status and statistics - includes both server and client cache"""
    print("📊 Cache status requested")
    try:
        print("🔄 Loading cache data...")
        cache_data = load_cache_data()
        print(f"📊 Server cache data loaded: {len(cache_data)} entries")

        # Also get client-side cache information
        client_cache_response = await get_public_cache_entries()
        client_entries = []
        if client_cache_response.success and client_cache_response.data:
            client_entries = client_cache_response.data.get("entries", [])
        print(f"📊 Client cache data loaded: {len(client_entries)} entries")

        # Calculate combined statistics
        server_hits = sum(entry.get("hitCount", 0)
                          for entry in cache_data.values())
        client_hits = sum(entry.get("hit_count", 0)
                          for entry in client_entries)
        total_hits = server_hits + client_hits
        total_misses = 0  # This would need to be tracked separately in a real implementation

        # Count unique entries (avoid duplicates)
        all_questions = set(cache_data.keys())
        for entry in client_entries:
            all_questions.add(entry["question"])
        unique_entries = len(all_questions)

        stats = {
            "total_entries": unique_entries,
            "server_entries": len(cache_data),
            "client_entries": len(client_entries),
            "questions": list(all_questions),
            "cache_file_exists": os.path.exists(get_cache_file_path()),
            "cache_file_size": os.path.getsize(get_cache_file_path()) if os.path.exists(get_cache_file_path()) else 0,
            "total_hits": total_hits,
            "server_hits": server_hits,
            "client_hits": client_hits,
            "total_misses": total_misses
        }

        print(f"📈 Stats calculated: {stats}")
        return CacheResponse(
            success=True,
            message=f"Cache status retrieved successfully (Server: {len(cache_data)}, Client: {len(client_entries)}, Unique: {unique_entries})",
            data=stats
        )
    except Exception as e:
        print(f"❌ Error in get_cache_status: {e}")
        import traceback
        traceback.print_exc()
        return CacheResponse(
            success=False,
            message=f"Error getting cache status: {str(e)}"
        )


@router.get("/cache/entries", response_model=CacheResponse)
async def get_cache_entries(request: Request, admin: str = Depends(get_admin_user)):
    """Get all cache entries (admin only) - includes both server and client cache"""
    try:
        # Load server-side cache
        cache_data = load_cache_data()

        # Get client cache entries
        client_entries = client_cache.get_all_entries()

        # Combine server and client entries
        all_entries = []

        # Add server entries
        for question, data in cache_data.items():
            all_entries.append({
                "question": question,
                "response": data.get("response", ""),
                "timestamp": data.get("timestamp", 0),
                "hit_count": data.get("hitCount", 0),
                "model": data.get("model", "unknown"),
                "source": "server"
            })

        # Add client entries (avoid duplicates)
        existing_questions = {entry["question"] for entry in all_entries}
        for entry in client_entries:
            if entry["question"] not in existing_questions:
                entry["source"] = "client"
                all_entries.append(entry)
            else:
                # Update hit count if client entry has more hits
                for server_entry in all_entries:
                    if server_entry["question"] == entry["question"]:
                        if entry.get("hit_count", 0) > server_entry.get("hit_count", 0):
                            server_entry["hit_count"] = entry["hit_count"]
                        break

        return CacheResponse(
            success=True,
            message=f"Retrieved {len(all_entries)} cache entries (server: {len(cache_data)}, client: {len(client_entries)})",
            data={"entries": all_entries}
        )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error getting cache entries: {str(e)}"
        )


@router.get("/cache/public/entries", response_model=CacheResponse)
async def get_public_cache_entries():
    """Get all cache entries (public access for frontend sync)"""
    try:
        cache_data = load_cache_data()

        entries = []
        for question, data in cache_data.items():
            entries.append({
                "question": question,
                "response": data.get("response", ""),
                "timestamp": data.get("timestamp", 0),
                "hit_count": data.get("hitCount", 0),
                "model": data.get("model", "unknown")
            })

        return CacheResponse(
            success=True,
            message=f"Retrieved {len(entries)} cache entries",
            data={"entries": entries}
        )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error getting cache entries: {str(e)}"
        )


@router.get("/cache/client/entries", response_model=CacheResponse)
async def get_client_cache_entries():
    """Get client cache entries"""
    try:
        entries = client_cache.get_all_entries()
        return CacheResponse(
            success=True,
            message=f"Retrieved {len(entries)} client cache entries",
            data={"entries": entries}
        )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error getting client cache entries: {str(e)}"
        )


@router.post("/cache/client/add", response_model=CacheResponse)
async def add_client_cache_entry(request: CacheRequest):
    """Add a client cache entry"""
    try:
        if not request.question:
            return CacheResponse(
                success=False,
                message="Question is required"
            )

        success = client_cache.cache_response(
            question=request.question,
            response=request.response or "",
            model="client",
            user_id="anonymous"
        )

        if success:
            return CacheResponse(
                success=True,
                message=f"Client cache entry added for: {request.question}"
            )
        else:
            return CacheResponse(
                success=False,
                message="Failed to save client cache entry"
            )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error adding client cache entry: {str(e)}"
        )


@router.get("/cache/client/check", response_model=CacheResponse)
async def check_client_cache(request: Request):
    """Check if a question exists in client cache"""
    try:
        question = request.query_params.get("question", "")
        if not question:
            return CacheResponse(
                success=False,
                message="Question parameter is required"
            )

        cached_response = client_cache.get_cached_response(question)

        if cached_response:
            # Increment hit count
            client_cache.increment_hit_count(question)
            return CacheResponse(
                success=True,
                message="Cached response found",
                data={"cached": True, "response": cached_response}
            )
        else:
            return CacheResponse(
                success=True,
                message="No cached response found",
                data={"cached": False}
            )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error checking client cache: {str(e)}"
        )


@router.get("/cache/client/stats", response_model=CacheResponse)
async def get_client_cache_stats():
    """Get client cache statistics"""
    try:
        stats = client_cache.get_cache_stats()
        return CacheResponse(
            success=True,
            message="Client cache statistics retrieved",
            data=stats
        )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error getting client cache stats: {str(e)}"
        )


@router.post("/cache/hit", response_model=CacheResponse)
async def increment_hit_count(request: CacheRequest, admin: str = Depends(get_admin_user)):
    """Increment hit count for a cache entry (admin only)"""
    try:
        cache_data = load_cache_data()

        if request.question in cache_data:
            cache_data[request.question]["hitCount"] = cache_data[request.question].get(
                "hitCount", 0) + 1

            if save_cache_data(cache_data):
                return CacheResponse(
                    success=True,
                    message=f"Incremented hit count for: {request.question}",
                    data={"hitCount": cache_data[request.question]["hitCount"]}
                )
            else:
                return CacheResponse(
                    success=False,
                    message="Failed to save cache data"
                )
        else:
            return CacheResponse(
                success=False,
                message=f"Cache entry not found for: {request.question}"
            )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error incrementing hit count: {str(e)}"
        )


@router.post("/cache/public/hit", response_model=CacheResponse)
async def increment_public_hit_count(request: CacheRequest):
    """Increment hit count for a cache entry (public access for frontend)"""
    try:
        cache_data = load_cache_data()

        if request.question in cache_data:
            cache_data[request.question]["hitCount"] = cache_data[request.question].get(
                "hitCount", 0) + 1

            if save_cache_data(cache_data):
                return CacheResponse(
                    success=True,
                    message=f"Incremented hit count for: {request.question}",
                    data={"hitCount": cache_data[request.question]["hitCount"]}
                )
            else:
                return CacheResponse(
                    success=False,
                    message="Failed to save cache data"
                )
        else:
            return CacheResponse(
                success=False,
                message=f"Cache entry not found for: {request.question}"
            )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error incrementing hit count: {str(e)}"
        )


@router.post("/cache/add", response_model=CacheResponse)
async def add_cache_entry(
    request: CacheRequest,
    admin: str = Depends(get_admin_user)
):
    """Add a new cache entry"""
    try:
        cache_data = load_cache_data()

        # If no response provided, generate one using the bot
        if not request.response:
            try:
                print(f"🤖 Generating response for: {request.question}")
                portfolio_assistant = PortfolioAssistant()

                # Get the response as a string instead of streaming
                response_stream = portfolio_assistant.get_response_stream(
                    request.question, "admin")
                response = ""

                for chunk in response_stream:
                    if chunk and not chunk.startswith("[PROGRESS|") and not chunk.startswith("[STATUS|"):
                        response += chunk

                print(f"✅ Generated response: {len(response)} characters")
                request.response = response

            except Exception as e:
                print(f"❌ Error generating response: {e}")
                import traceback
                traceback.print_exc()
                request.response = f"Error generating response: {str(e)}"

        # Add to cache
        cache_data[request.question] = {
            "response": request.response,
            "timestamp": int(time.time() * 1000),
            "hitCount": 0,
            "model": OLLAMA_CONFIG["MODEL"]
        }

        if save_cache_data(cache_data):
            return CacheResponse(
                success=True,
                message=f"Added cache entry for: {request.question}",
                data={"question": request.question,
                      "response_length": len(request.response)}
            )
        else:
            return CacheResponse(
                success=False,
                message="Failed to save cache data"
            )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error adding cache entry: {str(e)}"
        )


@router.delete("/cache/remove", response_model=CacheResponse)
async def remove_cache_entry(
    request: CacheRequest,
    admin: str = Depends(get_admin_user)
):
    """Remove a cache entry (server or client)"""
    try:
        cache_data = load_cache_data()

        # Check if it's a server cache entry
        if request.question in cache_data:
            del cache_data[request.question]

            if save_cache_data(cache_data):
                return CacheResponse(
                    success=True,
                    message=f"Removed server cache entry for: {request.question}"
                )
            else:
                return CacheResponse(
                    success=False,
                    message="Failed to save cache data"
                )
        else:
            # Check if it's a client cache entry by looking at public entries
            client_cache_response = await get_public_cache_entries()
            client_entries = []
            if client_cache_response.success and client_cache_response.data:
                client_entries = client_cache_response.data.get("entries", [])

            # Find the client entry
            client_entry = None
            for entry in client_entries:
                if entry["question"] == request.question:
                    client_entry = entry
                    break

            if client_entry:
                # For client entries, we can't directly remove them from the server
                # but we can return a success message indicating it was found
                # The frontend will need to handle the actual removal from client storage
                return CacheResponse(
                    success=True,
                    message=f"Client cache entry found for: {request.question} (remove from client storage)",
                    data={"question": request.question, "source": "client"}
                )
            else:
                return CacheResponse(
                    success=False,
                    message=f"Cache entry not found for: {request.question}"
                )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error removing cache entry: {str(e)}"
        )


@router.post("/cache/regenerate", response_model=CacheResponse)
async def regenerate_cache_entry(
    request: CacheRequest,
    admin: str = Depends(get_admin_user)
):
    """Regenerate a specific cache entry"""
    try:
        cache_data = load_cache_data()

        if request.question not in cache_data:
            return CacheResponse(
                success=False,
                message=f"Cache entry not found for: {request.question}"
            )

        # Generate new response
        portfolio_assistant = PortfolioAssistant()
        response_stream = portfolio_assistant.get_response_stream(
            request.question, "admin")
        response = ""
        for chunk in response_stream:
            if chunk and not chunk.startswith("[PROGRESS|"):
                response += chunk

        # Update cache entry
        cache_data[request.question] = {
            "response": response,
            "timestamp": int(time.time() * 1000),
            # Preserve hit count
            "hitCount": cache_data[request.question].get("hitCount", 0),
            "model": OLLAMA_CONFIG["MODEL"]
        }

        if save_cache_data(cache_data):
            return CacheResponse(
                success=True,
                message=f"Regenerated cache entry for: {request.question}",
                data={"question": request.question,
                      "response_length": len(response)}
            )
        else:
            return CacheResponse(
                success=False,
                message="Failed to save cache data"
            )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error regenerating cache entry: {str(e)}"
        )


@router.post("/cache/regenerate-all", response_model=CacheResponse)
async def regenerate_all_cache_entries(admin: str = Depends(get_admin_user)):
    """Regenerate all cache entries"""
    try:
        cache_data = load_cache_data()

        if not cache_data:
            return CacheResponse(
                success=True,
                message="No cache entries to regenerate"
            )

        portfolio_assistant = PortfolioAssistant()
        regenerated_count = 0
        failed_count = 0

        for question in list(cache_data.keys()):
            try:
                # Generate new response
                response_stream = portfolio_assistant.get_response_stream(
                    question, "admin")
                response = ""
                for chunk in response_stream:
                    if chunk and not chunk.startswith("[PROGRESS|"):
                        response += chunk

                # Update cache entry
                cache_data[question] = {
                    "response": response,
                    "timestamp": int(time.time() * 1000),
                    # Preserve hit count
                    "hitCount": cache_data[question].get("hitCount", 0),
                    "model": OLLAMA_CONFIG["MODEL"]
                }
                regenerated_count += 1

            except Exception as e:
                print(f"Error regenerating cache entry for '{question}': {e}")
                failed_count += 1

        if save_cache_data(cache_data):
            return CacheResponse(
                success=True,
                message=f"Regenerated {regenerated_count} cache entries, {failed_count} failed",
                data={
                    "regenerated": regenerated_count,
                    "failed": failed_count,
                    "total": len(cache_data)
                }
            )
        else:
            return CacheResponse(
                success=False,
                message="Failed to save cache data"
            )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error regenerating all cache entries: {str(e)}"
        )


@router.post("/cache/listen-tts", response_model=CacheResponse)
async def listen_tts_for_cache_entry(
    request: CacheRequest,
    admin: str = Depends(get_admin_user)
):
    """Generate and return TTS audio for a specific cache entry to listen to"""
    try:
        cache_data = load_cache_data()

        if request.question not in cache_data:
            return CacheResponse(
                success=False,
                message=f"Cache entry not found for: {request.question}"
            )

        # Get the cached response text
        response_text = cache_data[request.question]["response"]

        # Import TTS function
        from server.voice.synth import synthesize_to_base64

        # Generate TTS audio
        try:
            audio_base64 = synthesize_to_base64(response_text)
            print(f"✅ Generated TTS for listening: {request.question}")

            return CacheResponse(
                success=True,
                message=f"TTS audio generated for: {request.question}",
                data={"question": request.question, "audio": audio_base64}
            )
        except Exception as tts_error:
            print(f"❌ TTS generation error: {tts_error}")
            return CacheResponse(
                success=False,
                message=f"Error generating TTS audio: {str(tts_error)}"
            )

    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error generating TTS: {str(e)}"
        )


@router.put("/cache/update", response_model=CacheResponse)
async def update_cache_entry(
    request: CacheRequest,
    admin: str = Depends(get_admin_user)
):
    """Update the response text for a specific cache entry (server or client)"""
    try:
        cache_data = load_cache_data()

        # Check if it's a server cache entry
        if request.question in cache_data:
            if not request.response:
                return CacheResponse(
                    success=False,
                    message="Response text cannot be empty"
                )

            # Update the response text
            cache_data[request.question]["response"] = request.response
            cache_data[request.question]["timestamp"] = datetime.now().isoformat()

            # Save updated cache data
            save_cache_data(cache_data)

            print(f"✅ Updated server cache entry: {request.question}")

            return CacheResponse(
                success=True,
                message=f"Server cache entry updated for: {request.question}",
                data={"question": request.question,
                      "response_length": len(request.response),
                      "source": "server"}
            )
        else:
            # Check if it's a client cache entry by looking at public entries
            client_cache_response = await get_public_cache_entries()
            client_entries = []
            if client_cache_response.success and client_cache_response.data:
                client_entries = client_cache_response.data.get("entries", [])

            # Find the client entry
            client_entry = None
            for entry in client_entries:
                if entry["question"] == request.question:
                    client_entry = entry
                    break

            if client_entry:
                if not request.response:
                    return CacheResponse(
                        success=False,
                        message="Response text cannot be empty"
                    )

                # Move client entry to server cache with updated response
                cache_data[request.question] = {
                    "response": request.response,
                    "timestamp": datetime.now().isoformat(),
                    "hitCount": client_entry.get("hit_count", 0),
                    "model": client_entry.get("model", "unknown")
                }

                # Save updated cache data
                save_cache_data(cache_data)

                print(
                    f"✅ Moved and updated client cache entry: {request.question}")

                return CacheResponse(
                    success=True,
                    message=f"Client cache entry moved to server and updated for: {request.question}",
                    data={"question": request.question,
                          "response_length": len(request.response),
                          "source": "client_to_server"}
                )
            else:
                return CacheResponse(
                    success=False,
                    message=f"Cache entry not found for: {request.question}"
                )

    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error updating cache entry: {str(e)}"
        )


@router.post("/cache/regenerate-tts", response_model=CacheResponse)
async def regenerate_tts_for_cache_entry(
    request: CacheRequest,
    admin: str = Depends(get_admin_user)
):
    """Regenerate TTS audio for a specific cache entry"""
    try:
        cache_data = load_cache_data()

        if request.question not in cache_data:
            return CacheResponse(
                success=False,
                message=f"Cache entry not found for: {request.question}"
            )

        # Get the cached response text
        response_text = cache_data[request.question]["response"]

        # Import TTS function
        from server.voice.synth import synthesize_to_base64

        # Generate new TTS audio
        try:
            audio_base64 = synthesize_to_base64(response_text)
            print(f"✅ Generated TTS for: {request.question}")

            return CacheResponse(
                success=True,
                message=f"TTS audio regenerated for: {request.question}",
                data={"question": request.question,
                      "audio_length": len(audio_base64)}
            )
        except Exception as tts_error:
            print(f"❌ TTS generation error: {tts_error}")
            return CacheResponse(
                success=False,
                message=f"Error generating TTS audio: {str(tts_error)}"
            )

    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error regenerating TTS: {str(e)}"
        )


@router.delete("/cache/clear", response_model=CacheResponse)
async def clear_all_cache_entries(admin: str = Depends(get_admin_user)):
    """Clear all cache entries"""
    try:
        cache_file = get_cache_file_path()
        if os.path.exists(cache_file):
            os.remove(cache_file)

        return CacheResponse(
            success=True,
            message="All cache entries cleared successfully"
        )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error clearing cache entries: {str(e)}"
        )


@router.get("/cache/test", response_class=HTMLResponse)
async def test_cache_endpoint():
    """Test endpoint to check if cache routes are working"""
    return HTMLResponse(content="""
        <h1>Cache Test Endpoint</h1>
        <p>✅ Cache routes are working!</p>
        <p>Environment variables:</p>
        <ul>
            <li>ADMIN_USERNAME: """ + str(os.getenv("ADMIN_USERNAME", "NOT SET")) + """</li>
            <li>ADMIN_PASSWORD: """ + str("SET" if os.getenv("ADMIN_PASSWORD") else "NOT SET") + """</li>
        </ul>
        <p>Current working directory: """ + str(os.getcwd()) + """</p>
        <p>Available files in current directory:</p>
        <ul>
    """ + "".join([f"<li>{f}</li>" for f in os.listdir(".") if os.path.isfile(f)][:10]) + """
        </ul>
    """)


@router.get("/cache/model-info", response_model=CacheResponse)
async def get_model_info():
    """Get current model configuration (public access)"""
    try:
        return CacheResponse(
            success=True,
            message="Current model configuration",
            data={"model": OLLAMA_CONFIG["MODEL"]}
        )
    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error getting model info: {str(e)}"
        )


@router.post("/cache/update-model", response_model=CacheResponse)
async def update_cache_models(admin: str = Depends(get_admin_user)):
    """Update all existing cache entries with current model (admin only)"""
    try:
        cache_data = load_cache_data()
        current_model = OLLAMA_CONFIG["MODEL"]
        updated_count = 0

        for question, data in cache_data.items():
            if not data.get("model") or data.get("model") == "unknown":
                cache_data[question]["model"] = current_model
                updated_count += 1

        if updated_count > 0:
            if save_cache_data(cache_data):
                return CacheResponse(
                    success=True,
                    message=f"Updated {updated_count} cache entries with model: {current_model}",
                    data={"updated_count": updated_count,
                          "model": current_model}
                )
            else:
                return CacheResponse(
                    success=False,
                    message="Failed to save cache data"
                )
        else:
            return CacheResponse(
                success=True,
                message="All cache entries already have model information",
                data={"updated_count": 0, "model": current_model}
            )

    except Exception as e:
        return CacheResponse(
            success=False,
            message=f"Error updating cache models: {str(e)}"
        )


@router.get("/cache/login", response_class=HTMLResponse)
async def get_cache_login_interface():
    """Serve the cache login interface"""
    print("🔐 Login interface accessed")
    try:
        # Try multiple possible paths for the HTML file
        possible_paths = [
            "server/static/cache_login_clean.html",
            "server/static/cache_login.html",
            "static/cache_login_clean.html",
            "static/cache_login.html",
            "cache_login_clean.html",
            "cache_login.html"
        ]

        html_content = None
        for path in possible_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                print(f"✅ Found login interface at: {path}")
                break
            except FileNotFoundError:
                print(f"❌ File not found: {path}")
                continue

        if html_content:
            return HTMLResponse(content=html_content)
        else:
            return HTMLResponse(content=f"""
                <h1>Cache Login Interface</h1>
                <p>Error: Could not find cache_login.html file. Tried paths: {', '.join(possible_paths)}</p>
                <p>Please ensure the file exists in one of these locations.</p>
            """)
    except Exception as e:
        print(f"❌ Error serving login interface: {e}")
        return HTMLResponse(content=f"""
            <h1>Cache Login Interface</h1>
            <p>Error loading cache login interface: {str(e)}</p>
            <p>Please check the server logs for more details.</p>
        """)


@router.get("/cache/admin", response_class=HTMLResponse)
async def get_cache_admin_interface(request: Request):
    """Serve the cache admin interface"""
    print("🔐 Admin interface accessed")

    # For the admin interface, we'll let the client-side handle authentication
    # The server-side check was causing issues because browsers don't send
    # Authorization headers on direct page loads
    try:
        # Try multiple possible paths for the HTML file
        possible_paths = [
            "server/static/cache_admin_clean.html",
            "server/static/cache_admin_test.html",
            "server/static/cache_admin.html",
            "static/cache_admin_clean.html",
            "static/cache_admin_test.html",
            "static/cache_admin.html",
            "cache_admin_clean.html",
            "cache_admin_test.html",
            "cache_admin.html"
        ]

        html_content = None
        for path in possible_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    html_content = f.read()
                print(f"✅ Found admin interface at: {path}")
                break
            except FileNotFoundError:
                print(f"❌ File not found: {path}")
                continue

        if html_content:
            return HTMLResponse(content=html_content)
        else:
            return HTMLResponse(content=f"""
                <h1>Cache Admin Interface</h1>
                <p>Error: Could not find cache_admin.html file. Tried paths: {', '.join(possible_paths)}</p>
                <p>Please ensure the file exists in one of these locations.</p>
            """)
    except Exception as e:
        print(f"❌ Error serving admin interface: {e}")
        return HTMLResponse(content=f"""
            <h1>Cache Admin Interface</h1>
            <p>Error loading cache admin interface: {str(e)}</p>
            <p>Please check the server logs for more details.</p>
        """)
 