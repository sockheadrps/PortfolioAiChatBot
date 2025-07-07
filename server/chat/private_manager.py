
from fastapi import WebSocket
import json


class PrivateConnectionManager:
    def __init__(self):
        self.private_connections: dict[str, WebSocket] = {}
        self.public_keys: dict[str, str] = {}

    async def connect(self, websocket: WebSocket, username: str):
            self.private_connections[username] = websocket

    def disconnect(self, username: str):
        self.private_connections.pop(username, None)

    def register_pubkey(self, username: str, pubkey: str):
        print(f"Registering pubkey for {username}: {pubkey}")
        self.public_keys[username] = pubkey

    def get_pubkey(self, username: str) -> str:
        print(f"Getting pubkey for {username}: {self.public_keys.get(username)}")
        return self.public_keys.get(username)

    async def send_to_user(self, username: str, payload: dict):
        if username in self.private_connections:
            try:
                print(f"Sending to {username}: {payload}")
                await self.private_connections[username].send_json(payload)
            except Exception:
                # Connection is closed, remove it from private connections
                if username in self.private_connections:
                    del self.private_connections[username]
