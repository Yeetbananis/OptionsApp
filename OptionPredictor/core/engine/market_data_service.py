import time
import threading
import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, Iterable, List
from core.models.providers import ProviderHub

class MarketDataService:
    DB_FILE = Path("market_cache.sqlite3")

    def __init__(self, ttl_sec: int = 900) -> None:
        self.ttl_sec = ttl_sec
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.DB_FILE, check_same_thread=False)
        self._create_table()
        # NEW: Proactively fetch global data on init for Macro
        # This call will trigger ProviderHub.get_macro_data() and cache the result.
        self_init_global_data = self.get_metrics("GLOBAL") # Ensure this is fetched on startup

    def get_metrics(self, symbol: str) -> Dict[str, Any]:
        cached = self._read(symbol)
        if cached:
            # If cached and it's GLOBAL, return it directly
            if symbol == "GLOBAL":
                print(f"MarketDataService: Returning cached GLOBAL macro data.")
                return cached
            # For other symbols, proceed to check for freshness and re-fetch if needed
            return cached

        # If not cached or cache is stale, fetch using ProviderHub
        # Special handling for GLOBAL: ensure it's fetched by its specific method
        if symbol == "GLOBAL":
            print(f"MarketDataService: Fetching GLOBAL macro data from ProviderHub.")
            raw = ProviderHub.get_macro_data() # NEW: Call specific method for macro data
        else:
            raw = ProviderHub.get(symbol) # Existing call for stock symbols

        if raw.get("error"):
            self._write(symbol, raw)
            return raw

        import numpy as np, pandas as pd # Ensure these imports are at the top of market_data_service.py if not already.

        def _clean(v):
            if isinstance(v, pd.Series):
                return v.dropna().to_numpy(dtype=float).tolist()
            if isinstance(v, pd.DataFrame):
                # For macro events, payload could be a list of dicts.
                # If it's a DataFrame, check for common price columns.
                if "Close" in v.columns:
                    return v["Close"].dropna().to_numpy(dtype=float).tolist()
                # If it's a generic DataFrame, try to squeeze it
                return v.squeeze().to_numpy(dtype=float).tolist()
            if isinstance(v, (np.floating, np.integer)):
                return float(v)
            # Handle list of dictionaries for MacroEvents
            if isinstance(v, list) and all(isinstance(item, dict) for item in v):
                return v # Return as-is, assume it's clean (e.g., list of macro events)
            return v # Default case for other types

        # For GLOBAL symbol, raw is already adapted in get_macro_data to be { "MacroEvents": [...] }
        # So payload should just be raw directly.
        if symbol == "GLOBAL":
            payload = raw # Raw data from get_macro_data is already adapted
        else:
            payload = {k: _clean(v) for k, v in raw.items()} # Existing logic for stock symbols

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