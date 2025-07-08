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


async def _handle_bot_public_response(bot, username: str, message: str, manager: ConnectionManager):
    """Handle bot responses to public chat messages with streaming support"""
    import asyncio
    
    message_lower = message.lower()
    
    # Only respond to @bot mentions
    if '@bot' in message_lower:
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
                for chunk in bot.portfolio_assistant.get_response_stream(message):
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
                fallback_response = bot.portfolio_assistant.get_response(message)
                
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
                
                # Broadcast the user's message
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
