import sqlite3
import json
from datetime import datetime

DATABASE_FILE = "chat_history.db"

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conversation_id INTEGER NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        sources TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
    )
    """)
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

def create_conversation():
    """Creates a new conversation with a default title."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Use a temporary title that indicates it's new
    title = "New Conversation"
    cursor.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"id": new_id, "title": title}

def get_conversations():
    """Retrieves all conversations, sorted by most recent first."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM conversations ORDER BY created_at DESC")
    conversations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return conversations

def get_messages(conversation_id: int):
    """Retrieves all messages for a specific conversation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content, sources FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
        (conversation_id,)
    )
    messages = []
    for row in cursor.fetchall():
        msg = dict(row)
        msg['sources'] = json.loads(msg['sources']) if msg.get('sources') else []
        messages.append(msg)
    conn.close()
    return messages

def add_message(conversation_id: int, role: str, content: str, sources: list = None):
    """Adds a new message to a specific conversation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    sources_json = json.dumps(sources) if sources else None
    cursor.execute(
        "INSERT INTO messages (conversation_id, role, content, sources) VALUES (?, ?, ?, ?)",
        (conversation_id, role, content, sources_json)
    )
    conn.commit()
    conn.close()

# --- NEW DATABASE FUNCTIONS ---
def update_conversation_title(conversation_id: int, new_title: str):
    """Updates the title of a specific conversation."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE conversations SET title = ? WHERE id = ?", (new_title, conversation_id))
    conn.commit()
    conn.close()

def delete_conversation(conversation_id: int):
    """Deletes a conversation and all its associated messages."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # The ON DELETE CASCADE in the table definition will handle deleting messages automatically
    cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    conn.close()