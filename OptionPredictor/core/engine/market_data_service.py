# market_data_service.py
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List

from core.models.providers import ProviderHub


class MarketDataService:
    DB_FILE = Path("market_cache.sqlite3")

    def __init__(self, ttl_sec: int = 900) -> None:
        self.ttl_sec = ttl_sec
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.DB_FILE, check_same_thread=False)
        self._create_table()

    def get_metrics(self, symbol: str) -> Dict[str, Any]:
        cached = self._read(symbol)
        if cached:
            return cached

        raw = ProviderHub.get(symbol)
        if raw.get("error"):
            self._write(symbol, raw)
            return raw

        import numpy as np, pandas as pd

        def _clean(v):
            if isinstance(v, pd.Series):
                return v.dropna().to_numpy(dtype=float).tolist()
            if isinstance(v, pd.DataFrame):
                if "Close" in v.columns:
                    return v["Close"].dropna().to_numpy(dtype=float).tolist()
                return v.squeeze().to_numpy(dtype=float).tolist()
            if isinstance(v, (np.floating, np.integer)):
                return float(v)
            return v

        payload = {k: _clean(v) for k, v in raw.items()}
        self._write(symbol, payload)
        return payload



    def bulk_prefetch(self, symbols: Iterable[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        threads: List[threading.Thread] = []

        def _job(sym: str) -> None:
            out.append(self.get_metrics(sym))

        for sym in symbols:
            t = threading.Thread(target=_job, args=(sym,), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
        return out

    def invalidate(self, symbol: str | None = None) -> None:
        with self._lock, self._conn:
            if symbol:
                self._conn.execute("DELETE FROM idea_cache WHERE symbol = ?", (symbol.upper(),))
            else:
                self._conn.execute("DELETE FROM idea_cache")

    def close(self) -> None:
        self._conn.close()

    # ────────── internal ──────────
    def _create_table(self) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS idea_cache (symbol TEXT PRIMARY KEY, ts INTEGER, payload TEXT)"
            )

    def _read(self, symbol: str) -> Dict[str, Any] | None:
        with self._lock, self._conn:
            row = self._conn.execute(
                "SELECT ts, payload FROM idea_cache WHERE symbol = ?", (symbol.upper(),)
            ).fetchone()
        if not row:
            return None
        ts, payload = row
        if time.time() - ts > self.ttl_sec:
            return None
        return json.loads(payload)

    def _write(self, symbol: str, payload: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO idea_cache(symbol, ts, payload) VALUES (?, ?, ?)",
                (symbol.upper(), int(time.time()), json.dumps(payload)),
            )
