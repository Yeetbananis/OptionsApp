# idea_cache.py
"""
Simple SQLite + LRU wrapper dedicated to Idea objects.
Key   = symbol + YYYY-MM-DD
Value = JSON list of Idea dicts
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import List

from core.models.idea_models import Idea


class IdeaCache:
    DB_FILE = Path("idea_suite_cache.sqlite3")

    def __init__(self, ttl_sec: int = 900) -> None:
        self.ttl_sec = ttl_sec
        # allow cross-thread access; protected by _lock
        self._conn = sqlite3.connect(self.DB_FILE, check_same_thread=False)
        self._lock = threading.Lock()
        self._create_table()

    # ────────── public ──────────
    def read(self, symbol: str) -> List[Idea] | None:
        key = self._make_key(symbol)
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT ts, payload FROM idea_cache WHERE k = ?",
                (key,),
            ).fetchone()

        if not row:
            return None
        ts, payload = row
        if time.time() - ts > self.ttl_sec:
            return None
        raw = json.loads(payload)
        return [Idea(**obj) for obj in raw]

    def write(self, symbol: str, ideas: List[Idea]) -> None:
        key = self._make_key(symbol)
        payload = json.dumps([asdict(idea) for idea in ideas])
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO idea_cache(k, ts, payload) VALUES (?, ?, ?)",
                (key, int(time.time()), payload),
            )

    # ────────── helpers ──────────
    def _create_table(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS idea_cache (k TEXT PRIMARY KEY, ts INTEGER, payload TEXT)"
            )

    @staticmethod
    @lru_cache(maxsize=1024)
    def _make_key(symbol: str) -> str:
        from datetime import date

        return f"{symbol.upper()}_{date.today().isoformat()}"
