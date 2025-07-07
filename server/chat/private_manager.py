
from fastapi import WebSocket
import json
from typing import Union
from server.utils.models import PrivateMessage


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

    async def send_to_user(self, username: str, payload: Union[dict, PrivateMessage]):
        if username in self.private_connections:
            try:
                # Validate the message if it's a dict
                if isinstance(payload, dict):
                    # Try to validate the message structure
                    try:
                        # This will validate the structure but we'll still send the original dict
                        # to maintain compatibility
                        validated = self._validate_message(payload)
                        print(f"✅ Validated message type: {payload.get('type')}")
                    except Exception as e:
                        print(f"⚠️  Message validation failed for {username}: {e}")
                        # Continue sending anyway for backwards compatibility
                
                message_to_send = payload.model_dump(by_alias=True) if hasattr(payload, 'model_dump') else payload
                print(f"Sending to {username}: {message_to_send}")
                await self.private_connections[username].send_json(message_to_send)
            except Exception:
                # Connection is closed, remove it from private connections
                if username in self.private_connections:
                    del self.private_connections[username]
    
    def _validate_message(self, payload: dict) -> PrivateMessage:
        """Validate a message payload against the PrivateMessage models"""
        msg_type = payload.get("type")
        if not msg_type:
            raise ValueError("Message missing 'type' field")
        
        # Import specific models for validation
        from server.utils.models import (
            PmInviteMessage, PmAcceptMessage, PmDeclineMessage, 
            PmTextMessage, PmDisconnectMessage, PubkeyRequestMessage, PubkeyResponseMessage
        )
        
        type_to_model = {
            "pm_invite": PmInviteMessage,
            "pm_accept": PmAcceptMessage,
            "pm_decline": PmDeclineMessage,
            "pm_message": PmTextMessage,
            "pm_disconnect": PmDisconnectMessage,
            "pubkey_request": PubkeyRequestMessage,
            "pubkey_response": PubkeyResponseMessage,
        }
        
        if msg_type not in type_to_model:
            raise ValueError(f"Unknown message type: {msg_type}")
        
        model_class = type_to_model[msg_type]
        return model_class.model_validate(payload)
