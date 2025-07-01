from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Union
from pydantic import BaseModel, Field, ValidationError
from fastapi import Request
import json
import uvicorn
from models import ChatMessageData, JoinData, LeaveData, ServerBroadcastData, WsEvent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],  
    allow_headers=["*"],  
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

active_connections = []

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        print("Client connected")
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        print("Client disconnected")

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_json(json.loads(message))

manager = ConnectionManager()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await websocket.receive_json()
                print(data)
                try:
                    event = WsEvent(**data)
                    await manager.broadcast(event.model_dump_json())
                except ValidationError as e:
                    await manager.send_message(f"Validation error: {e.json()}", websocket)
            except json.JSONDecodeError:
                await manager.send_message("Error: Received invalid JSON", websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket)

async def validate_ws_event(request: WsEvent):
    event = request.event
    data = request.data
    match event:
        case "chat_message":
            message = ChatMessageData.model_validate(data)
            await manager.broadcast(message.model_dump_json())
        case "user_join":
            JoinData.model_validate(data)
        case "user_leave":
            LeaveData.model_validate(data)
        case "server_broadcast":
            ServerBroadcastData.model_validate(data)
        case _:
            raise HTTPException(status_code=422, detail=f"Invalid event: {event}. Allowed events are ['chat_message', 'user_join', 'user_leave', 'server_broadcast'].")

    return request

@app.get("/", response_class=HTMLResponse)
async def get_root_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/chat", response_class=HTMLResponse)
async def get_html_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/chat")
async def send_event(request: WsEvent = Depends(validate_ws_event)):
    try:
        await manager.broadcast(request.model_dump_json())  
        return {"status": "Event sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send event: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8080)