import sqlite3
from pathlib import Path

from torque.memory.memory_types import Memory


class MemoryStore:

    def __init__(self):

        db = (
            Path(__file__).resolve().parents[3]
            / "data"
            / "memory.db"
        )

        db.parent.mkdir(exist_ok=True)

        self.conn = sqlite3.connect(
            db,
            check_same_thread=False,
        )

        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (

                key TEXT PRIMARY KEY,

                value TEXT NOT NULL,

                category TEXT NOT NULL,

                created_at TEXT NOT NULL,

                updated_at TEXT NOT NULL

            )
            """
        )

        self.conn.commit()

    def save(self, memory: Memory):

        self.conn.execute(
            """
            INSERT OR REPLACE INTO memories
            (
                key,
                value,
                category,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
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

        cursor = self.conn.execute(
            """
            SELECT value
            FROM memories
            WHERE key = ?
            """,
            (key,),
        )

        row = cursor.fetchone()

        if row:
            return row[0]

        return None

    def get_all(self):

        cursor = self.conn.execute(
            """
            SELECT key, value, category
            FROM memories
            """
        )

        return cursor.fetchall()

    def delete(self, key: str):

        self.conn.execute(
            """
            DELETE FROM memories
            WHERE key = ?
            """,
            (key,),
        )

        self.conn.commit()

    def close(self):

        self.conn.close()