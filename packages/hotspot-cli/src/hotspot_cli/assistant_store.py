from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional


class AssistantStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = path or Path.home() / ".hotspot-research-cli" / "assistant.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.available = True
        try:
            self._init_db()
        except sqlite3.Error:
            self.available = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.path))

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                create table if not exists query_cache (
                    query text not null,
                    window_days integer not null,
                    created_at real not null,
                    payload text not null,
                    primary key (query, window_days)
                )
                """
            )
            conn.execute(
                """
                create table if not exists history (
                    id integer primary key autoincrement,
                    created_at real not null,
                    kind text not null,
                    title text not null,
                    payload text not null
                )
                """
            )

    def get_cache(self, query: str, window_days: int, *, max_age_seconds: int) -> Optional[dict[str, Any]]:
        if not self.available:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "select created_at, payload from query_cache where query=? and window_days=?",
                    (query, window_days),
                ).fetchone()
        except (sqlite3.Error, json.JSONDecodeError):
            return None
        if not row:
            return None
        created_at, payload = row
        if time.time() - float(created_at) > max_age_seconds:
            return None
        try:
            data = json.loads(str(payload))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def set_cache(self, query: str, window_days: int, payload: dict[str, Any]) -> None:
        if not self.available:
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    insert into query_cache(query, window_days, created_at, payload)
                    values (?, ?, ?, ?)
                    on conflict(query, window_days)
                    do update set created_at=excluded.created_at, payload=excluded.payload
                    """,
                    (query, window_days, time.time(), json.dumps(payload, ensure_ascii=False)),
                )
        except sqlite3.Error:
            self.available = False

    def add_history(self, kind: str, title: str, payload: dict[str, Any]) -> None:
        if not self.available:
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    "insert into history(created_at, kind, title, payload) values (?, ?, ?, ?)",
                    (time.time(), kind, title, json.dumps(payload, ensure_ascii=False)),
                )
        except sqlite3.Error:
            self.available = False
