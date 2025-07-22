from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends
from jose import jwt, JWTError
from typing import List
import json
import asyncio
import difflib
from pydantic import ValidationError
from server.chat.manager import ConnectionManager
from server.auth.auth import SECRET_KEY, ALGORITHM
from server.utils.models import WsEvent, ChatMessageData, JoinData, LeaveData, ServerBroadcastData
from server.chat.private_manager import PrivateConnectionManager
from server.chat.bot_user import initialize_bot, get_bot
from server.db.db import SessionLocal
from server.db.dbmodels import ChatHistory
from server.cache.client_cache import client_cache
import asyncio
from server.voice.synth import synthesize_to_base64


router = APIRouter()
manager = ConnectionManager()
private_manager = PrivateConnectionManager()


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate similarity between two text strings using difflib.
    Returns a value between 0.0 (completely different) and 1.0 (identical).
    """
    # Normalize text for better comparison
    text1_normalized = text1.lower().strip()
    text2_normalized = text2.lower().strip()

    # Use difflib's SequenceMatcher for similarity calculation
    similarity = difflib.SequenceMatcher(
        None, text1_normalized, text2_normalized).ratio()

    return similarity


async def _handle_bot_button_click(bot, username: str, message: str, manager: ConnectionManager, ip_address: str = None):
    """Handle bot responses to button clicks - process gallery commands without showing text"""
    try:
        # Get bot response to button click (usually gallery commands)
        bot_response = bot.portfolio_assistant.handle_button_click(
            message, username)

        if bot_response and bot_response.strip():
            # Check if response contains gallery commands
            if "[GALLERY_SHOW|" in bot_response:
                # Send gallery commands only to the user who clicked the button
                await manager.send_to_user(username, {
                    "event": "gallery_commands",
                    "data": {
                        "user": bot.username,
                        "commands": bot_response
                    }
                })
            else:
                # If it's not gallery commands, send as regular message (e.g., error messages)
                # Error messages should be sent to everyone for context
                await manager.broadcast(json.dumps({
                    "event": "chat_message",
                    "data": {
                        "user": bot.username,
                        "message": bot_response
                    }
                }))

    except Exception as e:
        print(f"❌ Error handling button click: {e}")
        # Send error message as regular chat to the specific user who clicked
        await manager.send_to_user(username, {
            "event": "chat_message",
            "data": {
                "user": bot.username,
                "message": "Sorry, I couldn't process that button click."
            }
        })


async def _handle_bot_public_response(bot, username: str, message: str, manager: ConnectionManager, ip_address: str = None):
    """Handle bot responses to public chat messages with streaming support"""

    message_lower = message.lower()

    # Respond to @bot mentions OR button clicks OR if bot is waiting for input from this user
    bot_should_respond = False

    if '@bot' in message_lower:
        bot_should_respond = True
    elif message.startswith("[BUTTON_CLICK|"):
        bot_should_respond = True
    else:
        # Check if bot is waiting for input from this specific user
        try:
            user_state = bot.portfolio_assistant.get_user_state(username)
            if user_state.get("awaiting_hobby_choice"):
                # Only respond if the message looks like a hobby selection
                # (number, project name, or direct hobby-related content)
                cleaned_msg = message.strip().lower()

                # Check if it's a hobby selection (number 1-3, project names, or hobby-related)
                is_hobby_selection = (
                    # Valid number selection
                    (cleaned_msg.isdigit() and 1 <= int(cleaned_msg) <= 3) or
                    # Contains hobby project keywords
                    any(word in cleaned_msg for word in [
                        'esp32', 'van', 'controller', 'guitar', 'midi', 'overlay',
                        'ble', 'rgb', 'strip', 'pcb', 'mosfet'
                    ]) or
                    # Help/option requests
                    any(word in cleaned_msg for word in [
                        'help', 'options', 'list', 'show'])
                )

                # Explicitly NOT hobby selections (common chat messages + cancel commands)
                is_chat_message = any(word in cleaned_msg for word in [
                    'hi', 'hello', 'hey', 'thanks', 'thank you', 'ok', 'okay',
                    'bye', 'goodbye', 'cool', 'nice', 'awesome', 'great',
                    'cancel', 'nevermind', 'never mind', 'stop', 'exit', 'quit'
                ])

                # If it's clearly a chat message or not a hobby selection, clear the waiting state
                if is_chat_message or not is_hobby_selection:
                    print(
                        f"🔄 Clearing hobby selection state for {username} - message: '{message}' (chat_message: {is_chat_message}, hobby_selection: {is_hobby_selection})")
                    user_state["awaiting_hobby_choice"] = False
                    bot_should_respond = False
                else:
                    bot_should_respond = True
        except Exception as e:
            print(f"❌ Error checking user state for routing: {e}")

    if bot_should_respond:
        try:
            # Send typing indicator
            await manager.broadcast(json.dumps({
                "event": "bot_typing",
                "data": {
                    "user": bot.username,
                    "typing": True
                }
            }))

            # Add delay to make it feel more natural
            await asyncio.sleep(1.0)

            # Clean the message by removing @bot mentions (but not for button clicks)
            cleaned_message = message
            if '@bot' in message.lower() and not message.startswith("[BUTTON_CLICK|"):
                import re
                cleaned_message = re.sub(
                    r'@bot\b', '', message, flags=re.IGNORECASE).strip()

            # Check client cache first
            cached_response = client_cache.get_cached_response(cleaned_message)

            # Check server cache (admin cache) if client cache miss
            server_cached_response = None
            if not cached_response:
                try:
                    from server.cache.routes import load_cache_data
                    cache_data = load_cache_data()

                    # First check for exact match
                    if cleaned_message in cache_data:
                        server_cached_response = cache_data[cleaned_message]
                        print(
                            f"🎯 Server cache EXACT HIT for: {cleaned_message[:50]}...")
                    else:
                        # Check for fuzzy/similar matches
                        best_match = None
                        best_similarity = 0.0

                        for cached_question in cache_data.keys():
                            similarity = calculate_similarity(
                                cleaned_message, cached_question)
                            if similarity > best_similarity and similarity >= 0.8:  # 80% similarity threshold
                                best_similarity = similarity
                                best_match = cached_question

                        if best_match:
                            server_cached_response = cache_data[best_match]
                            print(
                                f"🎯 Server cache FUZZY HIT ({best_similarity:.2f}) for: {cleaned_message[:50]}...")
                            print(f"🎯 Matched with: {best_match[:50]}...")
                        else:
                            print(
                                f"❌ No server cache match found for: {cleaned_message[:50]}...")

                except Exception as e:
                    print(f"❌ Error checking server cache: {e}")

            # Check if this query should bypass cache (for YouTube gallery functionality)
            # Only bypass if we have a cached response AND the query specifically requests fresh content
            should_bypass_cache = False
            if cached_response or server_cached_response:
                # Only bypass if user explicitly asks for fresh/new content
                bypass_keywords = [
                    "fresh", "new", "latest", "update", "recent", "current",
                    "generate", "create", "make", "build", "develop"
                ]
                should_bypass_cache = any(
                    keyword in cleaned_message.lower() for keyword in bypass_keywords)

            # Debug cache bypass logic
            print(f"🔍 Cache check for: '{cleaned_message}'")
            print(f"🔍 Client cache found: {cached_response is not None}")
            print(
                f"🔍 Server cache found: {server_cached_response is not None}")
            print(f"🔍 Should bypass cache: {should_bypass_cache}")
            if should_bypass_cache:
                matching_keywords = [kw for kw in ["journey", "story", "professional", "background", "experience", "career",
                                                   "how did you", "your journey", "your story", "electrician coder", "bridging"] if kw in cleaned_message.lower()]
                print(f"🔍 Matching bypass keywords: {matching_keywords}")

            if (cached_response or server_cached_response) and not should_bypass_cache:
                # Use cached response (prefer client cache, fallback to server cache)
                if cached_response:
                    print(f"🎯 Client cache HIT for: {cleaned_message[:50]}...")
                    print(f"🎯 Cached response structure: {cached_response}")
                    response_buffer = cached_response["response"]
                    print(f"🎯 Response buffer length: {len(response_buffer)}")

                    # Clean up cached response by removing invalid button commands
                    import re

                    # Remove "View Images" button if no images are available
                    if "[BUTTON|view_project_images|View Images]" in response_buffer:
                        # Check if there are actually images available for this query
                        matches = bot.portfolio_assistant.query_portfolio(
                            cleaned_message, top_k=3)
                        projects_with_images = bot.portfolio_assistant._extract_project_images(
                            matches, top_n=2)
                        if not projects_with_images or len(projects_with_images) == 0:
                            response_buffer = response_buffer.replace(
                                "[BUTTON|view_project_images|View Images]", "")
                            print(
                                f"🎯 Removed invalid 'View Images' button from cached response")

                    # Remove YouTube gallery commands if no videos are available
                    youtube_match = re.search(
                        r'\[YOUTUBE_SHOW\|(.*?)\|([^|]+)\]', response_buffer)
                    if youtube_match:
                        videos_str = youtube_match.group(1)
                        videos = [v.strip()
                                  for v in videos_str.split('||') if v.strip()]
                        if not videos or len(videos) == 0:
                            response_buffer = re.sub(
                                r'\[YOUTUBE_SHOW\|.*?\|[^|]+\]', '', response_buffer)
                            print(
                                f"🎯 Removed invalid YouTube gallery command from cached response")

                    cache_source = "client"
                    # Increment client cache hit count
                    client_cache.increment_hit_count(cleaned_message)
                else:
                    print(f"🎯 Server cache HIT for: {cleaned_message[:50]}...")
                    response_buffer = server_cached_response["response"]

                    # Clean up cached response by removing invalid button commands
                    # Remove "View Images" button if no images are available
                    if "[BUTTON|view_project_images|View Images]" in response_buffer:
                        # Check if there are actually images available for this query
                        matches = bot.portfolio_assistant.query_portfolio(
                            cleaned_message, top_k=3)
                        projects_with_images = bot.portfolio_assistant._extract_project_images(
                            matches, top_n=2)
                        if not projects_with_images or len(projects_with_images) == 0:
                            response_buffer = response_buffer.replace(
                                "[BUTTON|view_project_images|View Images]", "")
                            print(
                                f"🎯 Removed invalid 'View Images' button from server cached response")

                    # Remove YouTube gallery commands if no videos are available
                    youtube_match = re.search(
                        r'\[YOUTUBE_SHOW\|(.*?)\|([^|]+)\]', response_buffer)
                    if youtube_match:
                        videos_str = youtube_match.group(1)
                        videos = [v.strip()
                                  for v in videos_str.split('||') if v.strip()]
                        if not videos or len(videos) == 0:
                            response_buffer = re.sub(
                                r'\[YOUTUBE_SHOW\|.*?\|[^|]+\]', '', response_buffer)
                            print(
                                f"🎯 Removed invalid YouTube gallery command from server cached response")

                    cache_source = "server"
                    # Increment server cache hit count
                    try:
                        from server.cache.routes import load_cache_data, save_cache_data
                        cache_data = load_cache_data()
                        if cleaned_message in cache_data:
                            cache_data[cleaned_message]["hitCount"] = cache_data[cleaned_message].get(
                                "hitCount", 0) + 1
                            save_cache_data(cache_data)
                    except Exception as e:
                        print(
                            f"❌ Error incrementing server cache hit count: {e}")

                # Generate TTS for cached response
                try:
                    voice_b64 = synthesize_to_base64(response_buffer)
                    print(f"🎯 Generated TTS for cached response")
                except Exception as e:
                    print(
                        f"❌ Failed to synthesize voice for cached response: {e}")
                    voice_b64 = None

                # Send cached response as complete message with TTS
                print(
                    f"🎯 Broadcasting cached response: {response_buffer[:100]}...")

                # Send cached response as a complete bot message with proper styling and TTS
                await manager.broadcast(json.dumps({
                    "event": "bot_message_stream",
                    "data": {
                        "user": bot.username,
                        "chunk": "",
                        "is_first": True,
                        "is_complete": True,
                        "full_message": response_buffer,
                        "voice_b64": voice_b64,
                        "cached": True,
                        "cache_source": cache_source
                    }
                }))

                print(f"🎯 Cached response sent successfully")

            else:
                if should_bypass_cache:
                    print(
                        f"🔄 Bypassing cache for YouTube gallery query: {cleaned_message[:50]}...")
                else:
                    print(
                        f"❌ Client cache MISS for: {cleaned_message[:50]}...")
                print(
                    f"🚀 Starting bot response generation for: '{cleaned_message}'")
                # Generate streaming bot response using portfolio assistant
                response_buffer = ""
                is_first_chunk = True

                try:
                    total_chunks = 0
                    estimated_total_chunks = 50  # Rough estimate for progress calculation

                    for chunk in bot.portfolio_assistant.get_response_stream(cleaned_message, username):
                        if chunk:
                            # Check if this is a status marker
                            if chunk.startswith("[STATUS|"):
                                # Parse status data
                                status_parts = chunk.strip("[]").split("|")
                                if len(status_parts) >= 2:
                                    status_message = status_parts[1]

                                    # Send status update
                                    await manager.broadcast(json.dumps({
                                        "event": "bot_message_stream",
                                        "data": {
                                            "user": bot.username,
                                            "chunk": "",
                                            "is_first": is_first_chunk,
                                            "is_complete": False,
                                            "status": status_message
                                        }
                                    }))
                            else:
                                # Regular text chunk
                                response_buffer += chunk

                                # Send streaming chunk
                                await manager.broadcast(json.dumps({
                                    "event": "bot_message_stream",
                                    "data": {
                                        "user": bot.username,
                                        "chunk": chunk,
                                        "is_first": is_first_chunk,
                                        "is_complete": False
                                    }
                                }))

                            is_first_chunk = False

                            # Small delay between chunks for better UX
                            await asyncio.sleep(0.1)

                    # Send completion signal with 100% progress
                    await manager.broadcast(json.dumps({
                        "event": "bot_message_stream",
                        "data": {
                            "user": bot.username,
                            "chunk": "",
                            "is_first": False,
                            "is_complete": True,
                            "full_message": response_buffer,
                            "progress": 100
                        }
                    }))

                    # synthesize the response to base64
                    try:
                        voice_b64 = synthesize_to_base64(response_buffer)
                    except Exception as e:
                        print(f"❌ Failed to synthesize voice: {e}")
                        voice_b64 = None

                    # Send final message + optional audio
                    await manager.broadcast(json.dumps({
                        "event": "bot_message_stream",
                        "data": {
                            "user": bot.username,
                            "chunk": "",
                            "is_first": False,
                            "is_complete": True,
                            "full_message": response_buffer,
                            "voice_b64": voice_b64  # Base64-encoded WAV
                        }
                    }))

                    print(
                        f"✅ Bot response generation completed, length: {len(response_buffer)}")
                    # Cache the response for future use
                    client_cache.cache_response(
                        question=cleaned_message,
                        response=response_buffer,
                        model="portfolio_assistant",
                        user_id=username
                    )

                    # save the response to db
                    bot.portfolio_assistant.save_response(
                        cleaned_message, username, response_buffer, ip_address)

                except Exception as stream_error:
                    print(f"❌ Error in streaming response: {stream_error}")
                    # Fallback to complete message if streaming fails
                    try:
                        # Use the streaming method but collect all chunks
                        fallback_response = ""
                        for chunk in bot.portfolio_assistant.get_response_stream(cleaned_message, username):
                            if chunk and not chunk.startswith("[PROGRESS|") and not chunk.startswith("[STATUS|"):
                                fallback_response += chunk

                        await manager.broadcast(json.dumps({
                            "event": "chat_message",
                            "data": {
                                "user": bot.username,
                                "message": fallback_response
                            }
                        }))
                    except Exception as fallback_error:
                        print(f"❌ Fallback also failed: {fallback_error}")
                        await manager.broadcast(json.dumps({
                            "event": "chat_message",
                            "data": {
                                "user": bot.username,
                                "message": "I'm having trouble processing that right now. Feel free to ask me about projects, skills, or development experience!"
                            }
                        }))

        except Exception as e:
            print(f"❌ Error generating bot response: {e}")
            # Send a fallback response
            await manager.broadcast(json.dumps({
                "event": "chat_message",
                "data": {
                    "user": bot.username,
                    "message": "I'm having trouble processing that right now. Feel free to ask me about projects, skills, or development experience!"
                }
            }))


@router.post("/chat")
async def send_event(request: WsEvent):
    try:
        await manager.broadcast(request.model_dump_json())
        return {"status": "Event sent successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send event: {str(e)}")


@router.get("/chat-history")
async def get_chat_history(username: str = None, limit: int = 50):
    """Get chat history from database, optionally filtered by username."""
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

        return {"chat_history": history_list, "count": len(history_list)}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve chat history: {str(e)}")
    finally:
        db.close()


@router.get("/chat-history/{username}")
async def get_user_chat_history(username: str, limit: int = 50):
    """Get chat history for a specific user."""
    try:
        db = SessionLocal()
        chat_history = db.query(ChatHistory).filter(
            ChatHistory.username == username
        ).order_by(ChatHistory.timestamp.desc()).limit(limit).all()

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

        return {"chat_history": history_list, "count": len(history_list), "username": username}

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve chat history: {str(e)}")
    finally:
        db.close()


@router.get("/chat-history-advanced")
async def get_advanced_chat_history(
    username: str = None,
    ip_address: str = None,
    exclude_ips: str = None,
    sort_by: str = "timestamp",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0
):
    """
    Get chat history with advanced filtering and sorting options.

    Parameters:
    - username: Filter by specific username
    - ip_address: Filter by specific IP address
    - exclude_ips: Comma-separated list of IP addresses to exclude
    - sort_by: Field to sort by (timestamp, username, ip_address)
    - sort_order: Sort order (asc, desc)
    - limit: Number of results to return
    - offset: Number of results to skip
    """
    try:
        db = SessionLocal()
        query = db.query(ChatHistory)

        # Apply filters
        if username:
            query = query.filter(ChatHistory.username == username)

        if ip_address:
            query = query.filter(ChatHistory.ip_address == ip_address)

        if exclude_ips:
            # Split comma-separated IPs and exclude each one
            excluded_ip_list = [ip.strip() for ip in exclude_ips.split(",")]
            for excluded_ip in excluded_ip_list:
                query = query.filter(ChatHistory.ip_address != excluded_ip)

        # Apply sorting
        if sort_by == "timestamp":
            if sort_order.lower() == "asc":
                query = query.order_by(ChatHistory.timestamp.asc())
            else:
                query = query.order_by(ChatHistory.timestamp.desc())
        elif sort_by == "username":
            if sort_order.lower() == "asc":
                query = query.order_by(ChatHistory.username.asc())
            else:
                query = query.order_by(ChatHistory.username.desc())
        elif sort_by == "ip_address":
            if sort_order.lower() == "asc":
                query = query.order_by(ChatHistory.ip_address.asc())
            else:
                query = query.order_by(ChatHistory.ip_address.desc())
        else:
            # Default to timestamp desc
            query = query.order_by(ChatHistory.timestamp.desc())

        # Apply pagination
        query = query.offset(offset).limit(limit)

        # Get total count for pagination info
        total_count_query = db.query(ChatHistory)
        if username:
            total_count_query = total_count_query.filter(
                ChatHistory.username == username)
        if ip_address:
            total_count_query = total_count_query.filter(
                ChatHistory.ip_address == ip_address)
        if exclude_ips:
            excluded_ip_list = [ip.strip() for ip in exclude_ips.split(",")]
            for excluded_ip in excluded_ip_list:
                total_count_query = total_count_query.filter(
                    ChatHistory.ip_address != excluded_ip)

        total_count = total_count_query.count()

        # Execute the main query
        chat_history = query.all()

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

        return {
            "chat_history": history_list,
            "count": len(history_list),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "filters": {
                "username": username,
                "ip_address": ip_address,
                "exclude_ips": exclude_ips.split(",") if exclude_ips else None
            },
            "sorting": {
                "sort_by": sort_by,
                "sort_order": sort_order
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve chat history: {str(e)}")
    finally:
        db.close()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    username = None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        is_guest = payload.get("is_guest", False)

        if username is None:
            await websocket.close(code=1008)
            return

        # Both regular users and guests are allowed to connect
        # Guest usernames will have "guest_" prefix to distinguish them
    except JWTError:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, username)
    await private_manager.connect(websocket, username)

    # Get client IP address for tracking
    client_ip = None
    try:
        # Try to get IP from headers first (for proxy/load balancer scenarios)
        forwarded_for = websocket.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            # Fallback to direct client IP
            client_ip = websocket.client.host if websocket.client.host else "unknown"
    except Exception:
        client_ip = "unknown"

    # Initialize bot if not already done
    bot = get_bot()
    if bot is None:
        await initialize_bot(manager, private_manager)

    try:
        while True:
            try:
                # Add timeout to prevent indefinite blocking
                # 5 minute timeout
                data = await asyncio.wait_for(websocket.receive_json(), timeout=300.0)
                msg_type = data.get("type")

                # Debug: Log received message
                print(
                    f"🔍 Received WebSocket message from {username}: type={msg_type}, data={data}")

                # Additional debugging for malformed messages
                if not isinstance(data, dict):
                    print(
                        f"⚠️ Received non-dict message from {username}: {type(data)} - {data}")
                    await manager.send_message("Invalid message format", websocket)
                    continue

                if msg_type is None:
                    print(
                        f"⚠️ Received message without type from {username}: {data}")
                    await manager.send_message("Message missing type field", websocket)
                    continue

                if msg_type == "chat_message":
                    message_text = data["data"]["message"]
                    # Use display name if provided, fallback to username
                    display_name = data["data"].get("displayName", username)

                    # Check if this is a button click - don't broadcast button clicks
                    is_button_click = message_text.startswith("[BUTTON_CLICK|")

                    if not is_button_click:
                        # Broadcast the user's message (but not button clicks)
                        await manager.broadcast(json.dumps({
                            "event": "chat_message",
                            "data": {
                                "user": display_name,  # Use display name for display
                                "message": message_text
                            }
                        }))

                    # Check if bot should respond to public message
                    bot = get_bot()
                    if bot and username != bot.username:
                        if is_button_click:
                            # Handle button clicks separately - don't broadcast the response as text
                            asyncio.create_task(_handle_bot_button_click(
                                bot, username, message_text, manager, client_ip))
                        else:
                            # Start bot response handling in background (don't await)
                            asyncio.create_task(_handle_bot_public_response(
                                bot, username, message_text, manager, client_ip))

                elif msg_type == "pm_invite":
                    recipient = data.get("to")

                    # Check if the recipient is the bot
                    bot = get_bot()
                    if bot and recipient == bot.username:
                        # Bot automatically accepts PM invites
                        await bot.handle_pm_invite(username)
                    else:
                        # Send invite to regular user
                        await private_manager.send_to_user(recipient, {
                            "type": "pm_invite",
                            "from": username
                        })

                elif msg_type == "pm_accept":
                    recipient = data.get("to")
                    await private_manager.send_to_user(recipient, {
                        "type": "pm_accept",
                        "from": username
                    })

                elif msg_type == "pm_decline":
                    recipient = data.get("to")
                    await private_manager.send_to_user(recipient, {
                        "type": "pm_decline",
                        "from": username
                    })

                elif msg_type == "pm_message":
                    recipient = data.get("to")
                    ciphertext = data.get("ciphertext")

                    # Check if the recipient is the bot
                    bot = get_bot()
                    if bot and recipient == bot.username:
                        # Bot handles the message and responds
                        await bot.handle_pm_message(username, ciphertext)
                    else:
                        # Send message to regular user
                        await private_manager.send_to_user(recipient, {
                            "type": "pm_message",
                            "from": username,
                            "ciphertext": ciphertext
                        })

                elif msg_type == "pm_disconnect":
                    recipient = data.get("to")

                    # Check if the recipient is the bot
                    bot = get_bot()
                    if bot and recipient == bot.username:
                        # Bot handles disconnect
                        await bot.handle_pm_disconnect(username)
                    else:
                        # Send disconnect to regular user
                        await private_manager.send_to_user(recipient, {
                            "type": "pm_disconnect",
                            "from": username
                        })

                elif msg_type == "pubkey_request":
                    recipient = data.get("to")

                    # Check if the recipient is the bot
                    bot = get_bot()
                    if bot and recipient == bot.username:
                        # Bot handles the public key request
                        await bot.handle_pubkey_request(username)
                    else:
                        # Send pubkey request to regular user
                        await private_manager.send_to_user(recipient, {
                            "type": "pubkey_request",
                            "from": username
                        })

                elif msg_type == "pubkey_response":
                    recipient = data.get("to")
                    public_key = data.get("public_key")

                    # Check if the recipient is the bot
                    bot = get_bot()
                    if bot and recipient == bot.username:
                        # Bot stores the user's public key
                        await bot.handle_pubkey_response(username, public_key)
                    else:
                        # Send pubkey response to regular user
                        await private_manager.send_to_user(recipient, {
                            "type": "pubkey_response",
                            "from": username,
                            "public_key": public_key
                        })

                elif msg_type == "display_name_change":
                    print(f"🔄 Display name change: {data}")
                    display_name = data["data"]["displayName"]
                    # Broadcast the display name change to all other users
                    await manager.broadcast(json.dumps({
                        "event": "display_name_change",
                        "data": {
                            "username": username,
                            "displayName": display_name
                        }
                    }))

                elif msg_type == "pubkey":
                    private_manager.register_pubkey(username, data["key"])

                elif msg_type == "request_pubkey":
                    target = data.get("user")
                    pubkey = private_manager.get_pubkey(target)
                    await websocket.send_json({
                        "type": "pubkey_response",
                        "user": target,
                        "key": pubkey
                    })

                elif msg_type == "ping":
                    # Respond to ping with pong
                    await websocket.send_json({"type": "pong"})
                    continue

                elif msg_type == "pong":
                    # Acknowledge pong (no response needed)
                    continue

                elif msg_type == "tts_request":
                    # Handle TTS request for cached responses
                    text = data.get("data", {}).get("text", "")
                    if text:
                        try:
                            # Synthesize the text to base64 audio
                            voice_b64 = synthesize_to_base64(text)

                            # Send TTS audio back to the requesting user
                            await websocket.send_json({
                                "type": "tts_response",
                                "data": {
                                    "voice_b64": voice_b64,
                                    "text": text
                                }
                            })
                            print(
                                f"✅ TTS generated for cached response: {len(text)} characters")
                        except Exception as e:
                            print(
                                f"❌ Failed to synthesize TTS for cached response: {e}")
                            await websocket.send_json({
                                "type": "tts_response",
                                "data": {
                                    "voice_b64": None,
                                    "text": text,
                                    "error": "TTS synthesis failed"
                                }
                            })
                    else:
                        await websocket.send_json({
                            "type": "tts_response",
                            "data": {
                                "voice_b64": None,
                                "text": "",
                                "error": "No text provided for TTS"
                            }
                        })

                else:
                    print(
                        f"❌ Unknown message type '{msg_type}' from {username}: {data}")
                    await manager.send_message("Unknown message type", websocket)

            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    # Connection is dead, break out of the loop
                    break
            except Exception as e:
                # Log the specific error but don't break the connection for recoverable errors
                print(f"⚠️ WebSocket message error for user {username}: {e}")
                # Send error message to client
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Message processing error, please try again"
                    })
                except Exception:
                    # Connection is dead, break out of the loop
                    break

    except WebSocketDisconnect:
        print(f"🔌 WebSocket disconnected for user {username}")
        manager.disconnect(username)
        private_manager.disconnect(username)
        # Broadcast updated user list to all remaining users
        await manager.broadcast_user_list()
    except Exception as e:
        # Handle any other exceptions that might occur
        print(f"❌ WebSocket error for user {username}: {e}")
        manager.disconnect(username)
        private_manager.disconnect(username)
        # Broadcast updated user list to all remaining users
        await manager.broadcast_user_list()
