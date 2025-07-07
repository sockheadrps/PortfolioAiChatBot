from fastapi import WebSocket
import json
from server.utils.models import UserListMessage, ChatMessageData

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        self.active_connections[username] = websocket
        
        # Send welcome message to the new user
        await self.send_welcome_message(websocket, username)
        
        await self.broadcast_user_list()


    def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: str):
        # Create a copy of connections to avoid modification during iteration
        connections_copy = list(self.active_connections.items())
        parsed_message = json.loads(message)
        
        for username, connection in connections_copy:
            try:
                await connection.send_json(parsed_message)
            except Exception:
                # Connection is closed, remove it from active connections
                if username in self.active_connections:
                    del self.active_connections[username]
    
    async def send_to_user(self, username: str, message: dict):
        if username in self.active_connections:
            try:
                await self.active_connections[username].send_json(message)
            except Exception:
                # Connection is closed, remove it from active connections
                if username in self.active_connections:
                    del self.active_connections[username]

    async def broadcast_user_list(self):
        usernames = list(self.active_connections.keys())
        message = UserListMessage(users=usernames)
        # Create a copy of connections to avoid modification during iteration
        connections_copy = list(self.active_connections.items())
        
        for username, ws in connections_copy:
            try:
                await ws.send_json(message.model_dump(by_alias=True))
            except Exception:
                # Connection is closed, remove it from active connections
                if username in self.active_connections:
                    del self.active_connections[username]
    
    async def send_welcome_message(self, websocket: WebSocket, username: str):
        """Send welcome messages to a newly connected user"""
        welcome_messages = [
            "📢 Welcome to the chat! 📢",
        ]
        
        for message_text in welcome_messages:
            welcome_msg = {
                "event": "chat_message",
                "data": {
                    "user": "System",
                    "message": message_text
                }
            }
            await websocket.send_json(welcome_msg)




