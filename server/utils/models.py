from pydantic import BaseModel, Field, model_validator
from typing import Literal, Union, List
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
