from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from jose import jwt, JWTError
from typing import List
import json
import asyncio
from pydantic import ValidationError
from server.chat.manager import ConnectionManager
from server.auth.auth import SECRET_KEY, ALGORITHM
from server.utils.models import WsEvent, ChatMessageData, JoinData, LeaveData, ServerBroadcastData
from server.chat.private_manager import PrivateConnectionManager
from server.chat.bot_user import initialize_bot, get_bot


router = APIRouter()
manager = ConnectionManager()
private_manager = PrivateConnectionManager()


async def _handle_bot_button_click(bot, username: str, message: str, manager: ConnectionManager):
    """Handle bot responses to button clicks - process gallery commands without showing text"""
    try:
        # Get bot response to button click (usually gallery commands)
        bot_response = bot.portfolio_assistant.handle_button_click(message, username)
        
        if bot_response and bot_response.strip():
            # Check if response contains gallery commands
            if "[GALLERY_SHOW|" in bot_response:
                # Send gallery commands directly as a special event type that frontend can process silently
                await manager.broadcast(json.dumps({
                    "event": "gallery_commands",
                    "data": {
                        "user": bot.username,
                        "commands": bot_response
                    }
                }))
            else:
                # If it's not gallery commands, send as regular message (e.g., error messages)
                await manager.broadcast(json.dumps({
                    "event": "chat_message",
                    "data": {
                        "user": bot.username,
                        "message": bot_response
                    }
                }))
        
    except Exception as e:
        print(f"❌ Error handling button click: {e}")
        # Send error message as regular chat
        await manager.broadcast(json.dumps({
            "event": "chat_message",
            "data": {
                "user": bot.username,
                "message": "Sorry, I couldn't process that button click."
            }
        }))


async def _handle_bot_public_response(bot, username: str, message: str, manager: ConnectionManager):
    """Handle bot responses to public chat messages with streaming support"""
    import asyncio
    
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
                    any(word in cleaned_msg for word in ['help', 'options', 'list', 'show'])
                )
                
                # Explicitly NOT hobby selections (common chat messages + cancel commands)
                is_chat_message = any(word in cleaned_msg for word in [
                    'hi', 'hello', 'hey', 'thanks', 'thank you', 'ok', 'okay', 
                    'bye', 'goodbye', 'cool', 'nice', 'awesome', 'great',
                    'cancel', 'nevermind', 'never mind', 'stop', 'exit', 'quit'
                ])
                
                # If it's clearly a chat message or not a hobby selection, clear the waiting state
                if is_chat_message or not is_hobby_selection:
                    print(f"🔄 Clearing hobby selection state for {username} - message: '{message}' (chat_message: {is_chat_message}, hobby_selection: {is_hobby_selection})")
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
            
            # Generate streaming bot response using portfolio assistant
            response_buffer = ""
            is_first_chunk = True
            
            try:
                # Clean the message by removing @bot mentions (but not for button clicks)
                cleaned_message = message
                if '@bot' in message.lower() and not message.startswith("[BUTTON_CLICK|"):
                    import re
                    cleaned_message = re.sub(r'@bot\b', '', message, flags=re.IGNORECASE).strip()
                
                for chunk in bot.portfolio_assistant.get_response_stream(cleaned_message, username):
                    if chunk:
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
                
                # Send completion signal
                await manager.broadcast(json.dumps({
                    "event": "bot_message_stream",
                    "data": {
                        "user": bot.username,
                        "chunk": "",
                        "is_first": False,
                        "is_complete": True,
                        "full_message": response_buffer
                    }
                }))
                
            except Exception as stream_error:
                print(f"❌ Error in streaming response: {stream_error}")
                # Fallback to complete message if streaming fails
                fallback_response = bot.portfolio_assistant.get_response(cleaned_message, username)
                
                await manager.broadcast(json.dumps({
                    "event": "chat_message",
                    "data": {
                        "user": bot.username,
                        "message": fallback_response
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
        raise HTTPException(status_code=500, detail=f"Failed to send event: {str(e)}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, username)
    await private_manager.connect(websocket, username)
    
    # Initialize bot if not already done
    bot = get_bot()
    if bot is None:
        await initialize_bot(manager, private_manager)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "chat_message":
                message_text = data["data"]["message"]
                
                # Check if this is a button click - don't broadcast button clicks
                is_button_click = message_text.startswith("[BUTTON_CLICK|")
                
                if not is_button_click:
                    # Broadcast the user's message (but not button clicks)
                    await manager.broadcast(json.dumps({
                        "event": "chat_message",
                        "data": {
                            "user": username,
                            "message": message_text
                        }
                    }))
                
                # Check if bot should respond to public message
                bot = get_bot()
                if bot and username != bot.username:
                    if is_button_click:
                        # Handle button clicks separately - don't broadcast the response as text
                        asyncio.create_task(_handle_bot_button_click(bot, username, message_text, manager))
                    else:
                        # Start bot response handling in background (don't await)
                        asyncio.create_task(_handle_bot_public_response(bot, username, message_text, manager))

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

            else:
                await manager.send_message("Unknown message type", websocket)

    except WebSocketDisconnect:
        manager.disconnect(username)
        private_manager.disconnect(username)
        # Broadcast updated user list to all remaining users
        await manager.broadcast_user_list()
    except Exception as e:
        # Handle any other exceptions that might occur
        print(f"WebSocket error for user {username}: {e}")
        manager.disconnect(username)
        private_manager.disconnect(username)
        # Broadcast updated user list to all remaining users
        await manager.broadcast_user_list()
