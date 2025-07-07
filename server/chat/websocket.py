from fastapi import APIRouter, WebSocket, Query, WebSocketDisconnect
from jose import jwt, JWTError
from ..auth.auth import SECRET_KEY, ALGORITHM
from .manager import ConnectionManager
from .private_manager import PrivateConnectionManager
import json


router = APIRouter()
manager = ConnectionManager()
private_manager = PrivateConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("sub") is None:
            await websocket.close(code=1008)
            return
    except JWTError:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await manager.broadcast(json.dumps(data))
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@