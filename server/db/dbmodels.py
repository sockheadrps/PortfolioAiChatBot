from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    message = Column(String, nullable=False)
    response = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    ip_address = Column(String, nullable=True)  # Store IP address


class UserConnection(Base):
    __tablename__ = "user_connections"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, index=True, nullable=False)
    ip_address = Column(String, nullable=False)
    user_agent = Column(String, nullable=True)  # Store browser/device info
    connected_at = Column(DateTime, nullable=False)
