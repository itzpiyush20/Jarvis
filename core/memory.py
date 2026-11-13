import sqlite3
from datetime import datetime
from typing import List, Dict, Optional
from config import DB_PATH

class MemoryManager:
    """Manages long-term memory, reminders, and notes using local SQLite."""

    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)
        self._shared_conn = None
        if self.db_path == ":memory:":
            self._shared_conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._init_db()

    def _get_connection(self):
        if self._shared_conn is not None:
            return self._shared_conn
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Reminders & Tasks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    due_date TEXT,
                    is_urgent INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending', -- pending, completed, cancelled
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Notes & Memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def add_task(self, title: str, due_date: Optional[str] = None, is_urgent: bool = False) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (title, due_date, is_urgent) VALUES (?, ?, ?)",
                (title, due_date, 1 if is_urgent else 0)
            )
            conn.commit()
            return cursor.lastrowid

    def get_pending_tasks(self, urgent_only: bool = False) -> List[Dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT * FROM tasks WHERE status = 'pending'"
            params = []
            if urgent_only:
                query += " AND is_urgent = 1"
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def complete_task(self, task_id: int):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,))
            conn.commit()

    def add_note(self, content: str, category: str = "general") -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO notes (content, category) VALUES (?, ?)", (content, category))
            conn.commit()
            return cursor.lastrowid

    def search_notes(self, query: str) -> List[Dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM notes WHERE content LIKE ? ORDER BY created_at DESC LIMIT 10",
                (f"%{query}%",)
            )
            return [dict(row) for row in cursor.fetchall()]
