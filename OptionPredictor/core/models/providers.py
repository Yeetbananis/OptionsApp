# ===========================
# Future Imports
# ===========================
from __future__ import annotations

# ===========================
# Standard Library Imports
# ===========================
import datetime as dt
import random
import warnings
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Dict, List

# ===========================
# Third-Party Library Imports
# ===========================
import pandas as pd
import yfinance as yf


# --- TURN OFF NOISY FUTUREWARNINGS ---
warnings.filterwarnings("ignore", category=FutureWarning, module="(pytrends|pandas|yfinance)")

# --- BASE & HELPERS ---
class DataProvider(ABC):
    @abstractmethod
    def fetch(self, symbol: str, **kwargs) -> Any: ...

def _annualised_vol(close: pd.Series, win: int = 30) -> pd.Series:
    # Ensure index is datetime for proper rolling calculations
    if not isinstance(close.index, pd.DatetimeIndex):
        close.index = pd.to_datetime(close.index)
    return close.pct_change().rolling(win).std() * (252**0.5)

def _safe_last(series: pd.Series, dtype=float) -> Any:
    if hasattr(series, "empty") and series.empty:
        return dtype()
    if hasattr(series, "squeeze"):
        series = series.squeeze()
    if len(series) == 0:
        return dtype()
    val = series.dropna().iloc[-1]
    try:
        return dtype(val.item()) if hasattr(val, "item") else dtype(val)
    except (ValueError, TypeError):
        return dtype()

# --- MOCK PROVIDERS FOR NEW FEATURES ---
class MockUnusualOptionsProvider(DataProvider):
    """Simulates fetching unusual options activity like sweeps."""
    def fetch(self, symbol: str, **kwargs) -> Dict[str, Any]:
        if random.random() > 0.7:  # 30% chance of having a signal
            return {
                "premium": random.randint(100_000, 2_000_000),
                "sentiment": random.choice(["bullish", "bearish"]),
                "aggressor": random.choice(["sweep", "block"]),
                "oi_change_pct": round(random.uniform(15, 80), 1)
            }
        return {}

class MockMomentumProvider(DataProvider):
    """Simulates detecting price momentum signals."""
    def fetch(self, symbol: str, **kwargs) -> Dict[str, Any]:
        if random.random() > 0.6: # 40% chance of signal
            return {
                "price_sma_crossed": random.choice([50, 200]),
                "consecutive_days": random.randint(3, 7)
            }
        return {}

class MockEarningsProvider(DataProvider):
    """Simulates fetching real earnings dates."""
    def fetch(self, symbol: str, **kwargs) -> Dict[str, Any]:
        if random.random() > 0.5: # 50% chance of upcoming earnings
            days_out = random.randint(1, 14)
            earnings_date = (dt.date.today() + dt.timedelta(days=days_out)).isoformat()
            return {
                "date": earnings_date,  # Changed from earnings_date to date
                "days_until": days_out,
                "expected_move_pct": round(random.uniform(3.0, 15.0), 1)
            }
        return {}

class MockMacroProvider(DataProvider):
    """Simulates fetching macro economic events."""
    @lru_cache(maxsize=1)
    def fetch(self, symbol: str = "GLOBAL", **kwargs) -> List[Dict[str, Any]]:
        # This is a global provider, symbol doesn't matter.
        events = []
        today = dt.date.today()
        # Ensure at least one event exists for demonstration
        events.append({"event_name": "CPI Report", "date": (today + dt.timedelta(days=random.randint(1,4))).isoformat()})
        if random.random() > 0.7:
            events.append({"event_name": "FOMC Meeting", "date": (today + dt.timedelta(days=random.randint(2,6))).isoformat()})
        return events

class YahooPriceProvider(DataProvider):
    """
    Single-responsibility price fetcher.
    1. Try yfinance.download           (fast, multi-thread)
    2. Fallback to yfinance.Ticker.history
    3. If network fails ➜ deterministic synthetic series

    Always returns a non-empty DataFrame with a numeric 'Close' column.
    """

    @lru_cache(maxsize=256)
    def fetch(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        # normalize for Yahoo: convert any "BRK.B" style into "BRK-B"
        yf_symbol = symbol.replace('.', '-')

        import numpy as np, datetime as dt, hashlib

        # ---- attempt yfinance.download -----------------------------
        try:
            df = yf.download(
                tickers=yf_symbol,
                period=period,
                interval=interval,
                threads=False,  # Changed to False to avoid multiindex issues
                progress=False,
                auto_adjust=False,
            )
            if not df.empty:
                # Handle potential MultiIndex columns from yfinance
                if isinstance(df.columns, pd.MultiIndex):
                    # Flatten the MultiIndex columns
                    df.columns = ['_'.join(col).strip() if isinstance(col, tuple) else col for col in df.columns]
                    # Find the close column
                    close_cols = [col for col in df.columns if 'Close' in col]
                    if close_cols:
                        df['Close'] = df[close_cols[0]]
                
                df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
                df = df.dropna(subset=["Close"])
        except Exception as e:
            print(f"yfinance.download failed for {yf_symbol}: {e}")
            df = pd.DataFrame()

        # ---- attempt Ticker.history -------------------------------
        if df.empty:
            try:
                tf = {"7d": "7d", "30d": "1mo", "1y": "1y", "5y": "5y", "max": "max"}[period]
                ticker_obj = yf.Ticker(symbol)
                df = ticker_obj.history(period=tf, interval=interval, auto_adjust=False)
                if not df.empty:
                    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
                    df = df.dropna(subset=["Close"])
            except Exception as e:
                print(f"Ticker.history failed for {yf_symbol}: {e}")
                df = pd.DataFrame()

        # ---- final fallback – synthetic walk -----------------------
        if df.empty:
            print(f"Creating synthetic data for {symbol}")
            idx = pd.bdate_range(end=dt.date.today(), periods=252)
            rng = np.random.default_rng(
                int(hashlib.md5(symbol.encode()).hexdigest(), 16) % 2**32
            )
            log_r = rng.normal(0.0003, 0.02, size=len(idx))
            df = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(log_r))}, index=idx)

        # add 50-day SMA for momentum detectors
        if len(df) >= 50:
            df["SMA50"] = df["Close"].rolling(50).mean()
        else:
            df["SMA50"] = df["Close"].mean()  # fallback for short series

        return df


class IVRankProvider(DataProvider):
    def __init__(self, price_provider: DataProvider | None = None) -> None:
        self.price_provider = price_provider or YahooPriceProvider()

    def fetch(self, symbol: str, **_) -> Dict[str, float]:
        """
        Returns 3 keys:
           iv            – latest 30-day σ
           iv_rank       – percentile rank inside one-year window
           iv_sparkline  – list[float] last 30 IV values (for charts)
        """
        try:
            df = self.price_provider.fetch(symbol, period="1y")
            if df.empty or "Close" not in df.columns:
                return {"iv": 0.0, "iv_rank": 0.0, "iv_sparkline": []}

            iv_series = _annualised_vol(df["Close"])
            if iv_series.empty or iv_series.dropna().empty:
                return {"iv": 0.0, "iv_rank": 0.0, "iv_sparkline": []}

            iv = _safe_last(iv_series, float)
            iv_clean = iv_series.dropna()
            if len(iv_clean) == 0:
                return {"iv": 0.0, "iv_rank": 0.0, "iv_sparkline": []}
                
            iv_min, iv_max = iv_clean.min(), iv_clean.max()
            iv_rank = (
                (iv - iv_min) / (iv_max - iv_min) * 100.0
                if iv_max > iv_min
                else 0.0
            )

            return {
                "iv": iv,
                "iv_rank": iv_rank,                       # Changed from IVRank_%
                "iv_sparkline": (
                    iv_clean
                    .tail(30)
                    .to_numpy(dtype=float)
                    .tolist()
                ),
            }
        except Exception as exc:
            print(f"Error calculating IV Rank for {symbol}: {exc}")
            return {"iv": 0.0, "iv_rank": 0.0, "iv_sparkline": []}

class PushshiftRedditProvider(DataProvider):
    ENDPOINT = "https://api.pushshift.io/reddit/search/comment/"
    def fetch(self, symbol: str, lookback_h: int = 24) -> Dict[str, int]:
        # Mock data since Pushshift API is often unreliable
        if random.random() > 0.8:  # 20% chance of mentions
            return {"mentions": random.randint(50, 500)}
        return {"mentions": 0}

def _series_tail_list(ser: pd.Series, n=30) -> list[float]:
    return ser.dropna().tail(n).to_numpy(dtype=float).tolist()

def _df_close_tail_list(df: pd.DataFrame, n=30) -> list[float]:
    return _series_tail_list(pd.to_numeric(df['Close'], errors='coerce'), n)

class GoogleTrendsProvider(DataProvider):
    def __init__(self) -> None:
        try:
            from pytrends.request import TrendReq
            self._pt = TrendReq(hl="en-US", tz=360)
        except Exception: 
            self._pt = None

    def fetch(self, symbol: str, **_) -> Dict[str, float]:
        # Mock data since pytrends can be unreliable
        if random.random() > 0.7:  # 30% chance of trends
            return {"trends": random.uniform(20, 100)}
        return {"trends": 0.0}
        



# --- ADAPTERS FOR CLEAN METRICS ---
class IVAdapter:
    @staticmethod
    def adapt(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "IVRank_%": round(raw.get("iv_rank", 0.0), 1),
            "IV_σ": round(raw.get("iv", 0.0) * 100, 2),
            "IV_sparkline": raw.get("iv_sparkline", [])
        }

class RedditAdapter:
    @staticmethod
    def adapt(raw: Dict[str, int]) -> Dict[str, int]:
        return {"RedditMentions_24h": raw.get("mentions", 0)}

class TrendsAdapter:
    @staticmethod
    def adapt(raw: Dict[str, float]) -> Dict[str, float]:
        return {"GoogleTrendScore": raw.get("trends", 0.0)}

class UnusualOptionsAdapter:
    @staticmethod
    def adapt(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {"UnusualActivity": raw} if raw else {}

class MomentumAdapter:
    @staticmethod
    def adapt(raw: Dict[str, Any]) -> Dict[str, Any]:
        return {"MomentumSignal": raw} if raw else {}

class EarningsAdapter:
    @staticmethod
    def adapt(raw: Dict[str, Any]) -> Dict[str, Any]:
        # Replacing the old stub metric
        return {"UpcomingEarnings": raw} if raw else {}

class MacroAdapter:
    @staticmethod
    def adapt(raw: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"MacroEvents": raw} if raw else {}

# --- PROVIDER HUB FACADE ---
class ProviderHub:
    _price = YahooPriceProvider()
    _iv = IVRankProvider(_price)
    _reddit = PushshiftRedditProvider()
    _trends = GoogleTrendsProvider()
    _unusual_options = MockUnusualOptionsProvider()
    _momentum = MockMomentumProvider()
    _earnings = MockEarningsProvider()
    _macro = MockMacroProvider()

    @classmethod
    @lru_cache(maxsize=512)
    def get(cls, symbol: str) -> Dict[str, Any]:
        """
        Unified data access. Guarantees:
          • price_sparkline is a list[float] (never Series/DataFrame)
          • Always returns at least synthetic data, never {'error': ...}
        """
        import numpy as np, pandas as pd, datetime as dt, hashlib

        # ---------- helper: synthetic price series ---------------------
        def _static_price_list(n: int = 30) -> list[float]:
            rng = np.random.default_rng(
                      int(hashlib.md5(symbol.encode()).hexdigest(), 16) % 2**32
                  )
            pct = rng.normal(0.0003, 0.02, size=n)
            return (100 * np.exp(np.cumsum(pct))).tolist()

        # ---------- price & sparkline ----------------------------------
        try:
            price_df = cls._price.fetch(symbol)
            if price_df.empty or "Close" not in price_df.columns:
                spark = _static_price_list()
                last_price = spark[-1]
                above_sma = False
            else:
                close = pd.to_numeric(price_df["Close"], errors="coerce").dropna()
                if len(close) == 0:
                    spark = _static_price_list()
                    last_price = spark[-1]
                    above_sma = False
                else:
                    spark = close.tail(30).to_numpy(dtype=float).tolist()
                    last_price = float(close.iloc[-1])
                    
                    # Handle SMA50 check
                    if "SMA50" in price_df.columns and len(price_df) > 0:
                        sma50 = price_df["SMA50"].iloc[-1]
                        above_sma = bool(last_price > float(sma50)) if not pd.isna(sma50) else False
                    else:
                        above_sma = False
        except Exception as e:
            print(f"Error fetching price data for {symbol}: {e}")
            spark = _static_price_list()
            last_price = spark[-1]
            above_sma = False

        # ---------- other providers ------------------------------------
        try:
            iv_raw = cls._iv.fetch(symbol)
        except Exception as e:
            print(f"Error fetching IV data for {symbol}: {e}")
            iv_raw = {}
            
        try:
            reddit_raw = cls._reddit.fetch(symbol)
        except Exception as e:
            print(f"Error fetching Reddit data for {symbol}: {e}")
            reddit_raw = {}
            
        try:
            trends_raw = cls._trends.fetch(symbol)
        except Exception as e:
            print(f"Error fetching trends data for {symbol}: {e}")
            trends_raw = {}

        try:
            unusual_raw = cls._unusual_options.fetch(symbol)
        except Exception as e:
            print(f"Error fetching unusual options data for {symbol}: {e}")
            unusual_raw = {}
            
        try:
            momentum_raw = cls._momentum.fetch(symbol)
        except Exception as e:
            print(f"Error fetching momentum data for {symbol}: {e}")
            momentum_raw = {}
            
        try:
            earnings_raw = cls._earnings.fetch(symbol)
        except Exception as e:
            print(f"Error fetching earnings data for {symbol}: {e}")
            earnings_raw = {}

        # ---------- assemble ------------------------------------------
        data: Dict[str, Any] = {
            "price_sparkline": spark,
            "last_price": last_price,
            "price_above_sma50": above_sma,
        }
        data.update(IVAdapter.adapt(iv_raw))
        data.update(RedditAdapter.adapt(reddit_raw))
        data.update(TrendsAdapter.adapt(trends_raw))
        data.update(UnusualOptionsAdapter.adapt(unusual_raw))
        data.update(MomentumAdapter.adapt(momentum_raw))
        data.update(EarningsAdapter.adapt(earnings_raw))
        
        return data