#!/usr/bin/env python3
"""
Script to view user connection history with IP addresses.
This script shows when users connected, from what IP addresses, and when they disconnected.
"""

import sqlite3
import os
from datetime import datetime
from tabulate import tabulate


def view_connection_history(username: str = None, limit: int = 50):
    """View user connection history from the database."""
    db_path = "chat.db"

    if not os.path.exists(db_path):
        print(f"❌ Database file {db_path} not found.")
        return

    try:
        # Connect to the database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if user_connections table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='user_connections'")
        if not cursor.fetchone():
            print(
                "❌ user_connections table not found. Please run the migration script first.")
            return

        # Build the query
        if username:
            query = """
                SELECT username, ip_address, user_agent, connected_at
                FROM user_connections 
                WHERE username = ?
                ORDER BY connected_at DESC
                LIMIT ?
            """
            cursor.execute(query, (username, limit))
        else:
            query = """
                SELECT username, ip_address, user_agent, connected_at
                FROM user_connections 
                ORDER BY connected_at DESC
                LIMIT ?
            """
            cursor.execute(query, (limit,))

        connections = cursor.fetchall()

        if not connections:
            if username:
                print(f"📭 No connection history found for user '{username}'")
            else:
                print("📭 No connection history found")
            return

        # Format the data for display
        headers = ["Username", "IP Address", "User Agent", "Connected At"]
        table_data = []

        for conn in connections:
            username, ip_address, user_agent, connected_at = conn

            # Format timestamps
            connected_str = connected_at if connected_at else "Unknown"

            # Truncate user agent if too long
            user_agent_short = user_agent[:50] + "..." if user_agent and len(
                user_agent) > 50 else user_agent or "Unknown"

            table_data.append([
                username,
                ip_address,
                user_agent_short,
                connected_str
            ])

        # Display the table
        print(
            f"📊 User Connection History{f' for {username}' if username else ''}")
        print(f"📈 Showing {len(table_data)} most recent connections")
        print()
        print(tabulate(table_data, headers=headers, tablefmt="grid"))

        # Show some statistics
        print()
        print("📈 Connection Statistics:")

        # Total connections
        cursor.execute("SELECT COUNT(*) FROM user_connections")
        total_connections = cursor.fetchone()[0]
        print(f"   Total connections: {total_connections}")

        # Unique users
        cursor.execute("SELECT COUNT(DISTINCT username) FROM user_connections")
        unique_users = cursor.fetchone()[0]
        print(f"   Unique users: {unique_users}")

        # Unique IP addresses
        cursor.execute(
            "SELECT COUNT(DISTINCT ip_address) FROM user_connections")
        unique_ips = cursor.fetchone()[0]
        print(f"   Unique IP addresses: {unique_ips}")

        # Most active users
        print("\n🏆 Most Active Users:")
        cursor.execute("""
            SELECT username, COUNT(*) as connection_count
            FROM user_connections 
            GROUP BY username 
            ORDER BY connection_count DESC 
            LIMIT 5
        """)
        active_users = cursor.fetchall()
        for user, count in active_users:
            print(f"   {user}: {count} connections")

        # Most common IP addresses
        print("\n🌐 Most Common IP Addresses:")
        cursor.execute("""
            SELECT ip_address, COUNT(*) as connection_count
            FROM user_connections 
            GROUP BY ip_address 
            ORDER BY connection_count DESC 
            LIMIT 5
        """)
        common_ips = cursor.fetchall()
        for ip, count in common_ips:
            print(f"   {ip}: {count} connections")

    except Exception as e:
        print(f"❌ Error viewing connection history: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        username = sys.argv[1]
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        view_connection_history(username, limit)
    else:
        view_connection_history()
