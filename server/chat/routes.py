from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from jose import jwt, JWTError
from typing import List
import json
from pydantic import ValidationError
from server.chat.manager import ConnectionManager
from server.auth.auth import SECRET_KEY, ALGORITHM
from server.utils.models import WsEvent, ChatMessageData, JoinData, LeaveData, ServerBroadcastData
from server.chat.private_manager import PrivateConnectionManager
from server.chat.bot_user import initialize_bot, get_bot


router = APIRouter()
manager = ConnectionManager()
private_manager = PrivateConnectionManager()


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
                await manager.broadcast(json.dumps({
                    "event": "chat_message",
                    "data": {
                        "user": username,
                        "message": data["data"]["message"]
                    }
                }))

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
