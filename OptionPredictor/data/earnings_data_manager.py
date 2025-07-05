# data/earnings_data_manager.py
import datetime as dt
import pandas as pd
import os
import requests
import logging
import yfinance as yf
from functools import lru_cache

# Configure logging for this module
logger = logging.getLogger(__name__)

# --- Safe Ticker Helper for yfinance ---
@lru_cache(maxsize=128)
def _safe_ticker(symbol: str):
    """
    Returns a yfinance Ticker object, with caching and basic error handling.
    """
    try:
        return yf.Ticker(symbol)
    except Exception as e:
        logger.warning(f"Failed to create yfinance Ticker for {symbol}: {e}")
        return None

class EarningsDataManager:
    def __init__(self):
        # Alpha Vantage key, default to demo
        self.AV_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "HHFA73KA7RDGGB3O")
        self.base_url = "https://www.alphavantage.co/query"

    @lru_cache(maxsize=32) # Cache API responses for a short period
    def _av_json(self, params_tuple): # Changed parameter name to indicate it's a tuple
        """tiny helper that returns json or None (never raises)."""
        try:
            # Convert the tuple back to a dictionary before passing to requests.get
            r = requests.get(self.base_url, params=dict(params_tuple), timeout=10)
            r.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
            if not r.text.strip():
                return None
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.warning(f"Alpha Vantage API request failed: {e}")
            return None
        except ValueError as e: # JSON decoding error
            logger.warning(f"Alpha Vantage API response not valid JSON: {e}")
            return None

    def get_earnings_data(self, symbol: str) -> dict | None:
        """
        Fetches the next earnings date and previous EPS/Revenue for a given ticker.
        Returns a dictionary with parsed data or None if fetching fails.
        """
        sym = symbol.upper()
        tk = _safe_ticker(sym)
        if tk is None:
            return None

        earnings_data = {"symbol": sym}

        # --- 1) NEXT EARNINGS DATE – yfinance calendar ──────────────────
        next_earnings_date = None
        try:
            cal = tk.calendar
            if isinstance(cal, pd.DataFrame) and not cal.empty:
                if "Earnings Date" in cal.index:
                    raw = cal.loc["Earnings Date"].dropna().iloc[0]
                else: # fallback for newer yfinance versions or different structures
                    raw = cal.iloc[0, 0]
                next_earnings_date = pd.to_datetime(raw).strftime("%Y-%m-%d")
            elif isinstance(cal, dict):
                arr = cal.get("Earnings Date") or cal.get("earningsDate")
                if arr:
                    next_earnings_date = pd.to_datetime(arr[0]).strftime("%Y-%m-%d")
        except Exception as e:
            logger.warning(f"Failed to fetch next earnings date for {sym} via yfinance: {e}")

        earnings_data["next_earnings_date"] = next_earnings_date

        # --- 2) PREVIOUS QUARTER EPS – Alpha Vantage ────────────────────
        eps_js = self._av_json(tuple(sorted({"function": "EARNINGS", "symbol": sym, "apikey": self.AV_KEY}.items())))
        if eps_js and eps_js.get("quarterlyEarnings"):
            try:
                last = eps_js["quarterlyEarnings"][0]
                earnings_data["last_quarter_fiscal_date_ending"] = last.get("fiscalDateEnding")
                earnings_data["reported_eps"] = float(last["reportedEPS"])
                earnings_data["estimated_eps"] = float(last["estimatedEPS"])
                earnings_data["surprise_percentage"] = float(last["surprisePercentage"])
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse EPS data for {sym} from Alpha Vantage: {e}")
        
        # --- 3) REVENUE – Alpha Vantage ──────────────────────────────────
        inc_js = self._av_json(tuple(sorted({"function": "INCOME_STATEMENT", "symbol": sym, "apikey": self.AV_KEY}.items())))
        if inc_js and inc_js.get("quarterlyReports"):
            try:
                # Ensure it's not empty and has totalRevenue
                if inc_js["quarterlyReports"] and "totalRevenue" in inc_js["quarterlyReports"][0]:
                    earnings_data["last_quarter_total_revenue"] = float(inc_js["quarterlyReports"][0]["totalRevenue"])
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse Revenue data for {sym} from Alpha Vantage: {e}")

        return earnings_data