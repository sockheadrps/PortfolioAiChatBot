from pydantic import BaseModel, Field, model_validator
from typing import Literal, Union, List, Optional
from datetime import datetime

class ChatMessageData(BaseModel):
    user: str = Field(..., title="Username of the sender")
    message: str = Field(..., title="Text of the chat message")
    timestamp: datetime = Field(default_factory=datetime.utcnow, title="UTC timestamp of when the message was sent")


class JoinData(BaseModel):
    user: str = Field(..., title="Username of the user joining")


class LeaveData(BaseModel):
    user: str = Field(..., title="Username of the user leaving")


class ServerBroadcastData(BaseModel):
    message: str = Field(..., title="System-wide broadcast message (server-generated)")


# Private Message Models
class PmInviteMessage(BaseModel):
    model_config = {"populate_by_name": True}
    
    type: Literal["pm_invite"] = "pm_invite"
    sender: str = Field(..., alias="from", title="Username of the sender")


class PmAcceptMessage(BaseModel):
    model_config = {"populate_by_name": True}
    
    type: Literal["pm_accept"] = "pm_accept"
    sender: str = Field(..., alias="from", title="Username of the sender")


class PmDeclineMessage(BaseModel):
    model_config = {"populate_by_name": True}
    
    type: Literal["pm_decline"] = "pm_decline"
    sender: str = Field(..., alias="from", title="Username of the sender")


class PmTextMessage(BaseModel):
    model_config = {"populate_by_name": True}
    
    type: Literal["pm_message"] = "pm_message"
    sender: str = Field(..., alias="from", title="Username of the sender")
    ciphertext: str = Field(..., title="Encrypted message content")


class PmDisconnectMessage(BaseModel):
    model_config = {"populate_by_name": True}
    
    type: Literal["pm_disconnect"] = "pm_disconnect"
    sender: str = Field(..., alias="from", title="Username of the sender")


class PubkeyRequestMessage(BaseModel):
    model_config = {"populate_by_name": True}
    
    type: Literal["pubkey_request"] = "pubkey_request"
    sender: str = Field(..., alias="from", title="Username requesting the public key")


class PubkeyResponseMessage(BaseModel):
    model_config = {"populate_by_name": True}
    
    type: Literal["pubkey_response"] = "pubkey_response"
    sender: str = Field(..., alias="from", title="Username sending the public key")
    public_key: str = Field(..., title="Base64 encoded public key")


# System Messages
class UserListMessage(BaseModel):
    type: Literal["user_list"] = "user_list"
    users: List[str] = Field(..., title="List of online usernames")


# Union of all private message types
PrivateMessage = Union[
    PmInviteMessage,
    PmAcceptMessage, 
    PmDeclineMessage,
    PmTextMessage,
    PmDisconnectMessage,
    PubkeyRequestMessage,
    PubkeyResponseMessage
]


class WsEvent(BaseModel):
    event: Literal["chat_message", "user_join", "user_leave", "server_broadcast"]
    data: Union[ChatMessageData, JoinData, LeaveData, ServerBroadcastData]

    @model_validator(mode="before")
    @classmethod
    def validate_event_type(cls, values):
        event = values.get("event")
        data = values.get("data")

        expected_data_types = {
            "chat_message": ChatMessageData,
            "user_join": JoinData,
            "user_leave": LeaveData,
            "server_broadcast": ServerBroadcastData,
        }

        if event not in expected_data_types:
            raise ValueError(f"Invalid event: {event}. Allowed: {list(expected_data_types.keys())}")

        expected_type = expected_data_types[event]
        try:
            expected_type.model_validate(data)
        except Exception as e:
            raise ValueError(f"Data validation failed for event '{event}': {e}")

        return values
