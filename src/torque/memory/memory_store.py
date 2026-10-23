import sqlite3
import threading
from pathlib import Path

from torque.memory.memory_types import Memory
from torque.paths import MEMORY_DB


class MemoryStore:
    """
    SQLite-backed key/value memory. One connection guarded by a lock, so
    it is safe to share between the chat thread and the background worker.
    """

    def __init__(self, db_path=None):

        db = Path(db_path) if db_path else MEMORY_DB

        db.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()

        self.conn = sqlite3.connect(db, check_same_thread=False)

        with self._lock:

            self.conn.execute("PRAGMA journal_mode=WAL")

            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    category   TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            self.conn.commit()

    def save(self, memory: Memory):
        """Insert, or update value/category/updated_at (created_at is kept)."""

        with self._lock:

            self.conn.execute(
                """
                INSERT INTO memories (key, value, category, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    category = excluded.category,
                    updated_at = excluded.updated_at
                """,
                (
                    memory.key,
                    memory.value,
                    memory.category,
                    memory.created_at.isoformat(),
                    memory.updated_at.isoformat(),
                ),
            )

            self.conn.commit()

    def get(self, key: str):

        with self._lock:

            row = self.conn.execute(
                "SELECT value FROM memories WHERE key = ?",
                (key,),
            ).fetchone()

        return row[0] if row else None

    def get_all(self):
        """Newest first: [(key, value, category), ...]"""

        with self._lock:

            return self.conn.execute(
                """
                SELECT key, value, category
                FROM memories
                ORDER BY updated_at DESC
                """
            ).fetchall()

    def delete(self, key: str):

        with self._lock:

            self.conn.execute("DELETE FROM memories WHERE key = ?", (key,))

            self.conn.commit()

    def close(self):

        with self._lock:
            self.conn.close()
