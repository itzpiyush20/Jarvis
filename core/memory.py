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
            # Continuous Learning & User Personalization table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_learnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL, -- preference, habit, fact, context, correction
                    fact TEXT NOT NULL UNIQUE,
                    confidence REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Conversation History for multi-turn conversational context
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL, -- user, assistant
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Dynamic Assistant Settings table (User configurable via Telegram)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS assistant_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    description TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

        # Seed initial permanent baseline learnings if table is fresh
        self._seed_baseline_learnings()
        self._seed_default_settings()

    def _seed_default_settings(self):
        defaults = {
            "briefing_hour": ("8", "Hour of morning briefing in 24h format"),
            "briefing_minute": ("0", "Minute of morning briefing"),
            "meeting_alert_minutes": ("15", "Advance notice for calendar meetings in minutes"),
            "assistant_name": ("Jarvis", "Name of the assistant"),
            "user_name": ("Sir", "How the assistant addresses the user"),
            "user_city": ("New Delhi", "Primary user city"),
            "user_state": ("Delhi", "Primary user state"),
            "user_country": ("India", "Primary user country"),
            "voice_name": ("en-IN-PrabhatNeural", "Voice model for spoken responses"),
            "language": ("en-IN", "Primary regional language context")
        }
        for k, (v, desc) in defaults.items():
            if not self.get_setting(k):
                self.set_setting(k, v, desc)

    def get_setting(self, key: str, default: str = "") -> str:
        """Retrieves a dynamic configuration setting."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM assistant_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str, description: str = ""):
        """Sets or updates a dynamic configuration setting."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO assistant_settings (key, value, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (key, str(value), description))
            conn.commit()

    def get_all_settings(self) -> Dict[str, str]:
        """Returns all current dynamic settings."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM assistant_settings")
            return dict(cursor.fetchall())

    def _seed_baseline_learnings(self):
        baselines = [
            ("User is located in India (Timezone: Asia/Kolkata / IST, Currency: INR / ₹). Always present schedules, times, and cultural context in IST.", "context"),
            ("Format text messages cleanly and visually: use rich headers, bullets, and emojis; avoid raw markdown asterisks in output.", "preference"),
            ("Proactive Advisor: Provide proactive insights, decision-support context, and recommended next steps beyond raw factual answers.", "preference"),
            ("Continuous Learning: Actively adapt and update assistant behavior based on user feedback, corrections, and iterations.", "habit")
        ]
        for fact, cat in baselines:
            self.add_learning(fact, cat)

    def add_learning(self, fact: str, category: str = "preference"):
        """Stores a persistent user preference, fact, or correction."""
        fact = fact.strip()
        if not fact:
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO user_learnings (category, fact, updated_at) 
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(fact) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            """, (category, fact))
            conn.commit()

    def get_learnings(self, limit: int = 25) -> List[str]:
        """Returns list of all active user learnings and preferences."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT fact FROM user_learnings ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            )
            return [row[0] for row in cursor.fetchall()]

    def log_conversation(self, role: str, message: str):
        """Records a user or assistant message to conversation history."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO conversation_history (role, message) VALUES (?, ?)",
                (role, message)
            )
            conn.commit()

    def get_recent_history(self, limit: int = 6) -> List[Dict[str, str]]:
        """Returns the most recent multi-turn conversation exchanges."""
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, message FROM conversation_history ORDER BY id DESC LIMIT ?",
                (limit,)
            )
            rows = cursor.fetchall()
            # Return in chronological order
            return [{"role": r["role"], "message": r["message"]} for r in reversed(rows)]

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
