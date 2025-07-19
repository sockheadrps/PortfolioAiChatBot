from fastapi import WebSocket
import json
from datetime import datetime
from server.utils.models import UserListMessage, ChatMessageData
from server.db.db import SessionLocal
from server.db.dbmodels import UserConnection


class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        self.active_connections[username] = websocket

        # Get client IP address
        client_ip = self._get_client_ip(websocket)
        user_agent = self._get_user_agent(websocket)

        # Record connection in database
        await self._record_connection(username, client_ip, user_agent)

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
            "Welcome to Ryan's Portfolio Chat! This AI runs on CPU-only hardware, not GPU-accelerated infrastructure, which limits LLM performance. The LLM is quite accurate, its just not running on optimal hardware.",
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

    def _get_client_ip(self, websocket: WebSocket) -> str:
        """Extract client IP address from WebSocket connection"""
        try:
            # Try to get IP from headers first (for proxy/load balancer scenarios)
            forwarded_for = websocket.headers.get("x-forwarded-for")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip()

            # Fallback to direct client IP
            client_host = websocket.client.host
            return client_host if client_host else "unknown"
        except Exception:
            return "unknown"

    def _get_user_agent(self, websocket: WebSocket) -> str:
        """Extract user agent from WebSocket connection"""
        try:
            return websocket.headers.get("user-agent", "unknown")
        except Exception:
            return "unknown"

    async def _record_connection(self, username: str, ip_address: str, user_agent: str):
        """Record user connection in database"""
        try:
            db = SessionLocal()
            connection_record = UserConnection(
                username=username,
                ip_address=ip_address,
                user_agent=user_agent,
                connected_at=datetime.utcnow()
            )
            db.add(connection_record)
            db.commit()

            print(f"📊 Recorded connection: {username} from {ip_address}")
        except Exception as e:
            print(f"❌ Error recording connection: {e}")
        finally:
            db.close()
