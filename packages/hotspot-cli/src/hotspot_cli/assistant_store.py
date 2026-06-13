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
                    status text not null default 'ok',
                    source text not null default '',
                    payload text not null,
                    primary key (query, window_days)
                )
                """
            )
            self._ensure_column(conn, "query_cache", "status", "text not null default 'ok'")
            self._ensure_column(conn, "query_cache", "source", "text not null default ''")
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
            conn.execute(
                """
                create table if not exists user_profile (
                    id integer primary key check (id = 1),
                    updated_at real not null,
                    payload text not null
                )
                """
            )

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        rows = conn.execute(f"pragma table_info({table})").fetchall()
        if column not in {str(row[1]) for row in rows}:
            conn.execute(f"alter table {table} add column {column} {declaration}")

    def get_cache(self, query: str, window_days: int, *, max_age_seconds: int) -> Optional[dict[str, Any]]:
        if not self.available:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "select created_at, status, payload from query_cache where query=? and window_days=?",
                    (query, window_days),
                ).fetchone()
        except (sqlite3.Error, json.JSONDecodeError):
            return None
        if not row:
            return None
        created_at, status, payload = row
        if time.time() - float(created_at) > max_age_seconds:
            return None
        if status == "error":
            return None
        try:
            data = json.loads(str(payload))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def set_cache(self, query: str, window_days: int, payload: dict[str, Any], *, status: str = "ok", source: str = "") -> None:
        if not self.available:
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    insert into query_cache(query, window_days, created_at, status, source, payload)
                    values (?, ?, ?, ?, ?, ?)
                    on conflict(query, window_days)
                    do update set
                      created_at=excluded.created_at,
                      status=excluded.status,
                      source=excluded.source,
                      payload=excluded.payload
                    """,
                    (query, window_days, time.time(), status, source, json.dumps(payload, ensure_ascii=False)),
                )
        except sqlite3.Error:
            self.available = False

    def cache_stats(self) -> dict[str, Any]:
        if not self.available:
            return {"available": False, "path": str(self.path), "entries": 0, "statuses": {}, "sources": {}}
        try:
            with self._connect() as conn:
                entries = conn.execute("select count(*) from query_cache").fetchone()[0]
                statuses = dict(conn.execute("select status, count(*) from query_cache group by status").fetchall())
                sources = dict(conn.execute("select source, count(*) from query_cache group by source").fetchall())
                newest = conn.execute("select max(created_at) from query_cache").fetchone()[0]
        except sqlite3.Error:
            self.available = False
            return {"available": False, "path": str(self.path), "entries": 0, "statuses": {}, "sources": {}}
        return {
            "available": True,
            "path": str(self.path),
            "entries": int(entries or 0),
            "statuses": {str(key or "unknown"): int(value) for key, value in statuses.items()},
            "sources": {str(key or "unknown"): int(value) for key, value in sources.items()},
            "newest_age_seconds": None if newest is None else round(time.time() - float(newest), 2),
        }

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

    def get_profile(self) -> Optional[dict[str, Any]]:
        if not self.available:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute("select payload from user_profile where id=1").fetchone()
        except sqlite3.Error:
            return None
        if not row:
            return None
        try:
            data = json.loads(str(row[0]))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def set_profile(self, payload: dict[str, Any]) -> None:
        if not self.available:
            return
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    insert into user_profile(id, updated_at, payload)
                    values (1, ?, ?)
                    on conflict(id)
                    do update set updated_at=excluded.updated_at, payload=excluded.payload
                    """,
                    (time.time(), json.dumps(payload, ensure_ascii=False)),
                )
        except sqlite3.Error:
            self.available = False

    def clear_profile(self) -> None:
        if not self.available:
            return
        try:
            with self._connect() as conn:
                conn.execute("delete from user_profile where id=1")
        except sqlite3.Error:
            self.available = False
