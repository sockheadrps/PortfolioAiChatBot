#!/usr/bin/env python3
"""
Simple script to view chat history from the database.
Usage: python view_chat_history.py [username] [limit]
"""

from server.db.dbmodels import ChatHistory
from server.db.db import SessionLocal
import sys
import os
from datetime import datetime

# Add the server directory to the path so we can import the database modules
sys.path.append(os.path.join(os.path.dirname(__file__), 'server'))


def view_chat_history(username=None, limit=50):
    """View chat history from the database."""
    try:
        db = SessionLocal()
        query = db.query(ChatHistory)

        if username:
            query = query.filter(ChatHistory.username == username)
            print(f"📋 Chat history for user: {username}")
        else:
            print("📋 All chat history:")

        # Order by timestamp descending (most recent first) and limit results
        chat_history = query.order_by(
            ChatHistory.timestamp.desc()).limit(limit).all()

        if not chat_history:
            print("No chat history found.")
            return

        print(f"Found {len(chat_history)} entries:\n")
        print("=" * 80)

        for i, entry in enumerate(chat_history, 1):
            print(f"Entry {i}:")
            print(f"  ID: {entry.id}")
            print(f"  User: {entry.username}")
            print(f"  IP Address: {entry.ip_address or 'Unknown'}")
            print(f"  Timestamp: {entry.timestamp}")
            print(f"  Message: {entry.message}")
            print(
                f"  Response: {entry.response[:200]}{'...' if len(entry.response) > 200 else ''}")
            print("-" * 80)

    except Exception as e:
        print(f"❌ Error retrieving chat history: {e}")
    finally:
        db.close()


def main():
    """Main function to handle command line arguments."""
    username = None
    limit = 50

    if len(sys.argv) > 1:
        username = sys.argv[1]

    if len(sys.argv) > 2:
        try:
            limit = int(sys.argv[2])
        except ValueError:
            print("❌ Invalid limit value. Using default limit of 50.")

    view_chat_history(username, limit)


if __name__ == "__main__":
    main()
