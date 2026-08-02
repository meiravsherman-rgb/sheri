"""SQLite conversation storage."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import DATABASE_PATH


def _connect() -> sqlite3.Connection:
    path = Path(DATABASE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_messages (
            message_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def append(chat_id: str, role: str, content: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO conversations (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def tail(chat_id: str, n: int = 20) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT role, content FROM conversations WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, n),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def is_seen(message_id: str) -> bool:
    conn = _connect()
    row = conn.execute(
        "SELECT 1 FROM seen_messages WHERE message_id = ?", (message_id,)
    ).fetchone()
    conn.close()
    return row is not None


def mark_seen(message_id: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT OR IGNORE INTO seen_messages (message_id, created_at) VALUES (?, ?)",
        (message_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
