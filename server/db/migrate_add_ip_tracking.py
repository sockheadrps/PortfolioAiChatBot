#!/usr/bin/env python3
"""
Database migration script to add IP address tracking to existing databases.
This script adds the ip_address column to the chat_history table and creates the user_connections table.
"""

import sqlite3
import os
from datetime import datetime


def migrate_database():
    """Migrate the database to add IP address tracking."""
    db_path = "chat.db"

    if not os.path.exists(db_path):
        print(
            f"❌ Database file {db_path} not found. Please run the application first to create the database.")
        return False

    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        print("🔍 Checking current database schema...")

        # Check if ip_address column already exists in chat_history
        cursor.execute("PRAGMA table_info(chat_history)")
        columns = [column[1] for column in cursor.fetchall()]

        if "ip_address" not in columns:
            print("📝 Adding ip_address column to chat_history table...")
            cursor.execute(
                "ALTER TABLE chat_history ADD COLUMN ip_address TEXT")
            print("✅ Added ip_address column to chat_history table")
        else:
            print("✅ ip_address column already exists in chat_history table")

        # Check if user_connections table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_connections'")
        if not cursor.fetchone():
            print("📝 Creating user_connections table...")
            cursor.execute("""
                CREATE TABLE user_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    user_agent TEXT,
                    connected_at DATETIME NOT NULL
                )
            """)
            cursor.execute(
                "CREATE INDEX idx_user_connections_username ON user_connections(username)")
            cursor.execute(
                "CREATE INDEX idx_user_connections_ip ON user_connections(ip_address)")
            cursor.execute(
                "CREATE INDEX idx_user_connections_connected_at ON user_connections(connected_at)")
            print("✅ Created user_connections table with indexes")
        else:
            print("✅ user_connections table already exists")

        # Commit the changes
        conn.commit()
        print("✅ Database migration completed successfully!")

        # Show some statistics
        cursor.execute("SELECT COUNT(*) FROM chat_history")
        chat_count = cursor.fetchone()[0]
        print(f"📊 Current chat history records: {chat_count}")

        cursor.execute("SELECT COUNT(*) FROM user_connections")
        connection_count = cursor.fetchone()[0]
        print(f"📊 Current user connection records: {connection_count}")

        return True

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    print("🚀 Starting database migration for IP address tracking...")
    success = migrate_database()
    if success:
        print("🎉 Migration completed successfully!")
    else:
        print("💥 Migration failed!")
        exit(1)
 