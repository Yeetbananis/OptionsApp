import time
import threading
import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, Iterable, List
from core.models.providers import ProviderHub

import numpy as np # Ensure this import is here
import pandas as pd # Ensure this import is here

class MarketDataService:
    DB_FILE = Path("market_cache.sqlite3")

    def __init__(self, ttl_sec: int = 900) -> None:
        self.ttl_sec = ttl_sec
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.DB_FILE, check_same_thread=False)
        self._create_table()
        # NEW: Proactively fetch global data on init for Macro
        # This call will trigger ProviderHub.get_macro_data() and cache the result.
        # It is essential this is robust to avoid startup errors.
        try:
            self_init_global_data = self.get_metrics("GLOBAL")
            print("MarketDataService: GLOBAL macro data fetched on startup.")
        except Exception as e:
            print(f"MarketDataService: Error fetching GLOBAL macro data on startup: {e}")


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
            raw = ProviderHub.get_macro_data() # Call specific method for macro data
        else:
            raw = ProviderHub.get(symbol) # Existing call for stock symbols

        if raw.get("error"):
            self._write(symbol, raw)
            return raw

        # --- REVISED _clean function ---
        def _clean(v: Any) -> Any:
            if isinstance(v, pd.Series):
                # Convert to numeric, coerce errors to NaN, drop NaNs, then to list
                return pd.to_numeric(v, errors='coerce').dropna().tolist()
            if isinstance(v, pd.DataFrame):
                # If it's a DataFrame, check for common price columns.
                # If "Close" exists, clean and return it.
                if "Close" in v.columns:
                    return pd.to_numeric(v["Close"], errors='coerce').dropna().tolist()
                # Otherwise, try to clean all columns if they are numeric-like
                # This is a more generalized approach for DataFrames
                cleaned_df = v.apply(pd.to_numeric, errors='coerce')
                # If after coercion, all columns are numeric, we can convert to numpy array.
                # Otherwise, it's safer to just return the DataFrame or handle specific cases.
                # For this context, assuming we mainly deal with single-column DataFrames or numeric data.
                if cleaned_df.notna().all().all() and not cleaned_df.empty: # Check if all values are now valid numbers
                    return cleaned_df.squeeze().tolist() # .squeeze() can convert 1-column DF to Series
                
                # If DataFrame contains mixed types or is not fully numeric after coercion,
                # it's best to return it as-is or handle specific cases.
                # For the current usage (sparklines), this path might not be taken often.
                print(f"DEBUG: _clean: DataFrame for non-Close column contains non-numeric data after coercion for '{symbol}'. Returning as-is. Data sample: {v.head()}")
                return v
            if isinstance(v, (np.floating, np.integer)):
                return float(v)
            # Handle list of dictionaries for MacroEvents (or other structured lists)
            if isinstance(v, list) and all(isinstance(item, dict) for item in v):
                return v # Return as-is, assume it's clean (e.g., list of macro events or insider transactions)
            # Recursively clean dictionaries if they contain pandas objects
            if isinstance(v, dict):
                return {k: _clean(val) for k, val in v.items()}
            return v # Default case for other types (strings, bools, etc. already cleaned by _to_float if from yfinance/finnhub)

        # For GLOBAL symbol, raw is already adapted in get_macro_data to be { "MacroEvents": [...] }
        # So payload should just be raw directly.
        if symbol == "GLOBAL":
            # Apply _clean recursively to the raw dictionary returned by ProviderHub.get_macro_data()
            # This ensures any Series/DataFrame objects *inside* the macro data (though unlikely for current setup) are cleaned.
            payload = _clean(raw)
        else:
            payload = {k: _clean(v) for k, v in raw.items()} # Existing logic for stock symbols

        self._write(symbol, payload)
        return payload

    def bulk_prefetch(self, symbols: Iterable[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        threads: List[threading.Thread] = []

        def _job(sym: str) -> None:
            # Wrap get_metrics call in a try-except to prevent a single symbol failure from stopping the whole batch
            try:
                out.append(self.get_metrics(sym))
            except Exception as e:
                print(f"Error in bulk_prefetch for {sym}: {e}")
                out.append({"symbol": sym, "error": str(e)}) # Add an error entry

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
            print(f"MarketDataService: Cache for {symbol} is stale. Invalidating.")
            self.invalidate(symbol) # Invalidate stale cache
            return None
        return json.loads(payload)

    def _write(self, symbol: str, payload: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO idea_cache(symbol, ts, payload) VALUES (?, ?, ?)",
                (symbol.upper(), int(time.time()), json.dumps(payload)),
            )