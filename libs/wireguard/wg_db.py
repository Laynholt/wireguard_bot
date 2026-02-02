import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Optional, Iterable, Tuple

from ..core import config

DB_FILENAME = "wg_users.db"


def _db_path() -> str:
    return os.path.join(config.wireguard_folder, "config", DB_FILENAME)


@contextmanager
def _conn():
    path = _db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """
    Создает базу и таблицу users при отсутствии.
    """
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                name TEXT PRIMARY KEY,
                private_key TEXT NOT NULL,
                public_key TEXT NOT NULL,
                preshared_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                commented INTEGER NOT NULL DEFAULT 0,
                stats_json TEXT
            )
            """
        )
    try:
        os.chmod(_db_path(), 0o600)
    except OSError:
        # best effort, может быть Windows
        pass


def upsert_user(
    name: str,
    private_key: str,
    public_key: str,
    preshared_key: str,
    created_at: Optional[str] = None,
    commented: int = 0,
    stats_json: Optional[str] = None,
) -> None:
    init_db()
    created_at = created_at or datetime.utcnow().isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO users (name, private_key, public_key, preshared_key, created_at, commented, stats_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                private_key=excluded.private_key,
                public_key=excluded.public_key,
                preshared_key=excluded.preshared_key,
                created_at=excluded.created_at,
                commented=excluded.commented,
                stats_json=COALESCE(excluded.stats_json, users.stats_json)
            """,
            (name, private_key, public_key, preshared_key, created_at, commented, stats_json),
        )


def set_stats(name: str, stats_json: str) -> None:
    init_db()
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET stats_json=? WHERE name=?",
            (stats_json, name),
        )


def get_stats_all() -> Dict[str, str]:
    init_db()
    with _conn() as conn:
        rows = conn.execute("SELECT name, stats_json FROM users").fetchall()
    return {row["name"]: row["stats_json"] for row in rows if row["stats_json"]}


def list_users() -> Iterable[Tuple[str, int]]:
    init_db()
    with _conn() as conn:
        rows = conn.execute("SELECT name, commented FROM users").fetchall()
    return [(row["name"], row["commented"]) for row in rows]


def get_user(name: str) -> Optional[sqlite3.Row]:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
    return row


def remove_user(name: str) -> None:
    init_db()
    with _conn() as conn:
        conn.execute("DELETE FROM users WHERE name=?", (name,))


def set_commented(name: str, commented: int) -> None:
    init_db()
    with _conn() as conn:
        conn.execute("UPDATE users SET commented=? WHERE name=?", (commented, name))
