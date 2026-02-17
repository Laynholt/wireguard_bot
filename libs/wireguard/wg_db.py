import os
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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
    Создаёт базу и таблицу users при отсутствии, добавляет недостающие столбцы.
    """
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                name TEXT PRIMARY KEY,
                allowed_ip TEXT,
                private_key TEXT NOT NULL,
                public_key TEXT NOT NULL,
                preshared_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                commented INTEGER NOT NULL DEFAULT 0,
                stats_json TEXT
            )
            """
        )
        cols = {row[1] for row in conn.execute('PRAGMA table_info(users)').fetchall()}
        # если в старой схеме столбца нет, добавим его
        if "allowed_ip" not in cols:
            conn.execute('ALTER TABLE users ADD COLUMN allowed_ip TEXT')
        # если allowed_ip уже есть, но порядок колонок другой, не трогаем (порядок в SQLite логический, не физический)
    try:
        os.chmod(_db_path(), 0o600)
    except OSError:
        pass


def upsert_user(
    name: str,
    private_key: str,
    public_key: str,
    preshared_key: str,
    created_at: Optional[str] = None,
    commented: int = 0,
    allowed_ip: Optional[str] = None,
    stats_json: Optional[str] = None,
) -> None:
    init_db()
    created_at = created_at or datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            """
            INSERT INTO users (name, allowed_ip, private_key, public_key, preshared_key, created_at, commented, stats_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                allowed_ip=COALESCE(excluded.allowed_ip, users.allowed_ip),
                private_key=excluded.private_key,
                public_key=excluded.public_key,
                preshared_key=excluded.preshared_key,
                created_at=excluded.created_at,
                commented=excluded.commented,
                stats_json=COALESCE(excluded.stats_json, users.stats_json)
            """,
            (name, allowed_ip, private_key, public_key, preshared_key, created_at, commented, stats_json),
        )


def set_stats(name: str, stats_json: Optional[str]) -> None:
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
    return {row[0]: row[1] for row in rows if row[1]}


def list_users() -> Iterable[Tuple[str, int]]:
    init_db()
    with _conn() as conn:
        rows = conn.execute("SELECT name, commented FROM users").fetchall()
    return [(row[0], row[1]) for row in rows]


def get_user(name: str) -> Optional[sqlite3.Row]:
    init_db()
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
    return row


def get_users_created_at(names: Iterable[str]) -> Dict[str, Optional[str]]:
    """
    Возвращает created_at для списка пользователей одним запросом.
    """
    unique_names = list(dict.fromkeys(names))
    if not unique_names:
        return {}

    placeholders = ",".join(["?"] * len(unique_names))
    query = f"SELECT name, created_at FROM users WHERE name IN ({placeholders})"

    init_db()
    with _conn() as conn:
        rows = conn.execute(query, unique_names).fetchall()

    return {row["name"]: row["created_at"] for row in rows}


def remove_user(name: str) -> None:
    init_db()
    with _conn() as conn:
        conn.execute("DELETE FROM users WHERE name=?", (name,))


def set_commented(name: str, commented: int) -> None:
    init_db()
    with _conn() as conn:
        conn.execute("UPDATE users SET commented=? WHERE name=?", (commented, name))


def set_allowed_ip(name: str, allowed_ip: Optional[str]) -> None:
    """
    Обновляет поле allowed_ip для пользователя.
    """
    init_db()
    with _conn() as conn:
        conn.execute("UPDATE users SET allowed_ip=? WHERE name=?", (allowed_ip, name))
