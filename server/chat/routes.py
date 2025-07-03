from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException
from jose import jwt, JWTError
from typing import List
import json
from pydantic import ValidationError
from server.chat.manager import ConnectionManager
from server.auth.auth import SECRET_KEY, ALGORITHM
from server.utils.models import WsEvent, ChatMessageData, JoinData, LeaveData, ServerBroadcastData

router = APIRouter()
manager = ConnectionManager()

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

    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await websocket.receive_json()
                try:
                    event = WsEvent(**data)
                    await manager.broadcast(event.model_dump_json())
                except ValidationError as e:
                    await manager.send_message(f"Validation error: {e.json()}", websocket)
            except json.JSONDecodeError:
                await manager.send_message("Error: Received invalid JSON", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@router.post("/chat")
async def send_event(request: WsEvent):
    try:
        await manager.broadcast(request.model_dump_json())
        return {"status": "Event sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send event: {str(e)}")
