# ===========================
# Future Imports
# ===========================
from __future__ import annotations

# ===========================
# Standard Library Imports
# ===========================
import datetime as dt
import random
import re
import time
import warnings
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Dict, List

# ===========================
# Third-Party Library Imports
# ===========================
import numpy as np
import pandas as pd
import pandas_ta as ta
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from pytrends.request import TrendReq


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

class MomentumProvider(DataProvider):
    """
    Calculates common and unique momentum/technical signals from historical price data.
    Handles cases where insufficient data prevents indicator calculation.
    """
    def __init__(self, price_provider: DataProvider = None) -> None:
        self.price_provider = price_provider or YahooPriceProvider()

    def fetch(self, symbol: str, **kwargs) -> Dict[str, Any]:
        try:
            df = self.price_provider.fetch(symbol, period="1y", interval="1d")
            
            if df.empty or "Close" not in df.columns or "High" not in df.columns or "Low" not in df.columns:
                print(f"[{symbol}] Insufficient OHLC data for momentum calculation.")
                return {}

            # Ensure 'Close', 'High', 'Low' columns are numeric (already done in YahooPriceProvider, but safe check)
            df["Close"] = pd.to_numeric(df["Close"], errors="coerce").dropna()
            df["High"] = pd.to_numeric(df["High"], errors="coerce").dropna()
            df["Low"] = pd.to_numeric(df["Low"], errors="coerce").dropna()

            if df["Close"].empty or df["High"].empty or df["Low"].empty:
                print(f"[{symbol}] OHLC price data is empty after cleaning for {symbol}.")
                return {}

            momentum_signals = {}
            
            # --- Ensure enough data for indicators ---
            # BBands/KC defaults to length=20. RSI to 14. SMA200 requires 200.
            min_required_data = 200 
            if len(df) < min_required_data: 
                print(f"[{symbol}] Not enough data ({len(df)} days) for full indicator calculation (min {min_required_data}). Some signals may be skipped.")
            
            # --- Calculate SMAs for Golden/Death Cross ---
            df['SMA50'] = ta.sma(df['Close'], length=50)
            df['SMA200'] = ta.sma(df['Close'], length=200)

            # --- Calculate Bollinger Bands and Keltner Channels ---
            # Call ta functions directly and join the results to df
            bbands_df = ta.bbands(close=df['Close'], length=20, std=2.0)
            kc_df = ta.kc(high=df['High'], low=df['Low'], close=df['Close'], length=20, scalar=2.0)

            # Append these to the main DataFrame if they exist and are not empty
            if bbands_df is not None and not bbands_df.empty:
                # Explicitly rename columns to ensure consistent access, as pandas_ta sometimes changes suffixes
                # Standard pandas_ta names for bbands are e.g., BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
                df = df.join(bbands_df, how='left') 

            if kc_df is not None and not kc_df.empty:
                # Standard pandas_ta names for kc are e.g., KCL_20_2.0, KCM_20_2.0, KCU_20_2.0
                df = df.join(kc_df, how='left')
            
            # --- Calculate RSI ---
            df['RSI'] = ta.rsi(df['Close'], length=14)

            latest_close = df["Close"].iloc[-1]
            
            # --- 1. Price vs. SMA50 (for price_above_sma50) ---
            if "SMA50" in df.columns and pd.notna(df["SMA50"].iloc[-1]):
                latest_sma50 = df["SMA50"].iloc[-1]
                momentum_signals["price_above_sma50"] = bool(latest_close > latest_sma50)
            else:
                momentum_signals["price_above_sma50"] = False


            # --- 2. Golden Cross / Death Cross (50-day and 200-day SMA crossover) ---
            if "SMA50" in df.columns and "SMA200" in df.columns and \
               len(df) >= 201 and pd.notna(df['SMA50'].iloc[-1]) and pd.notna(df['SMA200'].iloc[-1]) and \
               pd.notna(df['SMA50'].iloc[-2]) and pd.notna(df['SMA200'].iloc[-2]): # Ensure previous values exist
                
                sma50_curr = df['SMA50'].iloc[-1]
                sma200_curr = df['SMA200'].iloc[-1]
                sma50_prev = df['SMA50'].iloc[-2]
                sma200_prev = df['SMA200'].iloc[-2]

                if sma50_curr > sma200_curr and sma50_prev <= sma200_prev:
                    momentum_signals["GoldenCross"] = True
                    print(f"[{symbol}] Golden Cross detected!")
                elif sma50_curr < sma200_curr and sma50_prev >= sma200_prev:
                    momentum_signals["DeathCross"] = True
                    print(f"[{symbol}] Death Cross detected!")
            
            # --- 3. Bollinger Band Squeeze (Bollinger Bands within Keltner Channels) ---
            # Reference columns explicitly by their standard names generated by pandas_ta
            bb_l_col = 'BBL_20_2.0'
            bb_u_col = 'BBU_20_2.0'
            kc_l_col = 'KCL_20_2.0' # Default scalar for kc is 2.0, so this name is correct
            kc_u_col = 'KCU_20_2.0'

            if all(col in df.columns and pd.notna(df[col].iloc[-1]) for col in [bb_l_col, bb_u_col, kc_l_col, kc_u_col]):
                bb_lower = df[bb_l_col].iloc[-1]
                bb_upper = df[bb_u_col].iloc[-1]
                kc_lower = df[kc_l_col].iloc[-1]
                kc_upper = df[kc_u_col].iloc[-1]

                is_squeeze = (bb_lower > kc_lower) and (bb_upper < kc_upper)
                if is_squeeze:
                    momentum_signals["BollingerBandSqueeze"] = True
                    print(f"[{symbol}] Bollinger Band Squeeze detected!")
                else:
                    momentum_signals["BollingerBandSqueeze"] = False
            else:
                momentum_signals["BollingerBandSqueeze"] = False # Default to false if not calculable


            # --- 4. RSI Overbought / Oversold ---
            if "RSI" in df.columns and pd.notna(df["RSI"].iloc[-1]):
                latest_rsi = df["RSI"].iloc[-1]
                if latest_rsi >= 70:
                    momentum_signals["RSI_Overbought"] = True
                    print(f"[{symbol}] RSI Overbought ({latest_rsi:.2f})")
                elif latest_rsi <= 30:
                    momentum_signals["RSI_Oversold"] = True
                    print(f"[{symbol}] RSI Oversold ({latest_rsi:.2f})")
            
            # --- General Momentum Signal for the Detector's original structure (optional mapping) ---
            if momentum_signals.get("GoldenCross") or momentum_signals.get("DeathCross") or \
               momentum_signals.get("BollingerBandSqueeze") or momentum_signals.get("RSI_Overbought") or \
               momentum_signals.get("RSI_Oversold"):
               
               momentum_signals["MomentumSignal"] = {"strong_signal_detected": True}
            elif momentum_signals.get("price_above_sma50"):
                 momentum_signals["MomentumSignal"] = {"direction": "above_sma50"} # Simpler flag
            else:
                 momentum_signals["MomentumSignal"] = {} # Default to empty if no signals

            # --- Debugging: Print final signals for this symbol ---
            print(f"[{symbol}] Final Momentum Signals calculated: {momentum_signals}")

            return momentum_signals

        except Exception as e:
            print(f"Error calculating momentum for {symbol}: {e}")
            import traceback
            traceback.print_exc()
            return {} # Return empty dict on error
        
from ui.events_calendar import PREGENERATED_EVENTS, EVENTS_BY_DATE # NEW: Import hardcoded events

class HardcodedMacroProvider(DataProvider):
    """
    Provides macro economic events by filtering hardcoded data from events_calendar.py.
    This eliminates web scraping fragility for non-earnings macro events.
    """
    @lru_cache(maxsize=1) # Cache the filtered events once per run
    def fetch(self, symbol: str = "GLOBAL", **kwargs) -> List[Dict[str, Any]]:
        # This provider doesn't actually 'fetch' but rather 'curates' from hardcoded data.
        
        # Filter events for the current month or future from PREGENERATED_EVENTS
        today = dt.date.today()
        current_month = today.month
        current_year = today.year
        
        relevant_events = []
        for event_date_str, label, tag, event_time, url, note in PREGENERATED_EVENTS:
            try:
                event_date = dt.datetime.strptime(event_date_str, "%Y-%m-%d").date()
                
                # Include events that are in the future or very near past (e.g., within last 7 days)
                # and potentially events for the current year, or upcoming year.
                # This makes it more flexible for the demo.
                time_threshold = today - dt.timedelta(days=7) # Include events from last 7 days too

                # Logic to determine if the event is relevant (future, or very recent past, or upcoming in current/next year)
                is_relevant_date = False
                if event_date >= today: # Event is in the future
                    is_relevant_date = True
                elif event_date.year == current_year and event_date >= time_threshold: # Event is in current year and recent past
                    is_relevant_date = True
                elif event_date.year == current_year + 1 and event_date.month <= 6: # Event is next year, up to June
                    is_relevant_date = True
                
                if not is_relevant_date:
                    continue # Skip this event if it doesn't meet the date criteria
                    
                # If we reach here, the date is relevant, so add the event
                event_name = label # Use the event label as the name
                
                relevant_events.append({
                    "event_name": event_name,
                    "date": event_date_str,
                    "currency": "", # Hardcoded events don't have currency, can be empty
                    "impact": "High", # All pregenerated events are considered high impact for thematic ideas
                    "actual": "N/A", # Hardcoded events don't have actual/forecast/previous
                    "forecast": "N/A",
                    "previous": "N/A"
                })
            except ValueError:
                # Skip events with unparseable dates
                continue
        
        print(f"HardcodedMacroProvider: Provided {len(relevant_events)} high-impact macro events from internal data.")
        return relevant_events

class YahooPriceProvider(DataProvider):
    """
    Single-responsibility price fetcher.
    Ensures High, Low, and Close columns are available and correctly named,
    handling MultiIndex columns from yfinance.
    """
    @lru_cache(maxsize=256)
    def fetch(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        yf_symbol = symbol.replace('.', '-') # Normalize for Yahoo

        import numpy as np, datetime as dt, hashlib

        df = pd.DataFrame() # Initialize empty DataFrame
        
        # --- Helper to process downloaded/history DataFrames ---
        def _process_yfinance_df(input_df: pd.DataFrame) -> pd.DataFrame:
            if input_df.empty:
                return pd.DataFrame()

            # Flatten MultiIndex columns if present (e.g., from yf.download with multiple tickers or some specific setups)
            if isinstance(input_df.columns, pd.MultiIndex):
                # For a single ticker download, it often looks like [('Close', ''), ('High', '')]
                # We want just 'Close', 'High', etc.
                # For cases where it could be ('Close', 'AAPL'), we just take the first level name.
                input_df.columns = [col[0].capitalize() if isinstance(col, tuple) else col.capitalize() for col in input_df.columns]
            else:
                # Just capitalize single-level columns
                input_df.columns = [col.capitalize() for col in input_df.columns]

            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            if all(col in input_df.columns for col in required_cols):
                # Select required columns and convert to numeric, dropping rows with NaNs
                processed_df = input_df[required_cols].apply(pd.to_numeric, errors='coerce').dropna()
                # Ensure index is DatetimeIndex, which pandas_ta expects
                if not isinstance(processed_df.index, pd.DatetimeIndex):
                    processed_df.index = pd.to_datetime(processed_df.index)
                return processed_df
            else:
                print(f"Warning: Missing required OHLCV columns for {yf_symbol} after processing.")
                return pd.DataFrame()

        # --- 1. Attempt yfinance.download ---
        try:
            download_df = yf.download(
                tickers=yf_symbol,
                period=period,
                interval=interval,
                threads=False,
                progress=False,
                auto_adjust=False, # Crucial: False to retain OHLCV columns
            )
            df = _process_yfinance_df(download_df)
        except Exception as e:
            print(f"yfinance.download failed for {yf_symbol}: {e}")
            df = pd.DataFrame() # Reset df on failure

        # --- 2. Attempt Ticker.history (if download failed or was incomplete) ---
        if df.empty:
            try:
                tf_map = {"7d": "7d", "30d": "1mo", "1y": "1y", "5y": "5y", "max": "max"}
                tf = tf_map.get(period, "1y") # Default to 1y if period not mapped
                
                ticker_obj = yf.Ticker(symbol)
                history_df = ticker_obj.history(period=tf, interval=interval, auto_adjust=False) # Keep auto_adjust=False
                df = _process_yfinance_df(history_df)
            except Exception as e:
                print(f"Ticker.history failed for {yf_symbol}: {e}")
                df = pd.DataFrame() # Reset df on failure

        # --- 3. Final fallback – synthetic OHLCV walk (if all else fails) ---
        if df.empty:
            print(f"Creating synthetic OHLCV data for {symbol}")
            idx = pd.bdate_range(end=dt.date.today(), periods=252) # 1 year of business days
            rng = np.random.default_rng(
                int(hashlib.md5(symbol.encode()).hexdigest(), 16) % 2**32
            )
            log_r = rng.normal(0.0003, 0.02, size=len(idx))
            close_prices = 100 * np.exp(np.cumsum(log_r))
            
            # Create synthetic High/Low/Open/Volume based on Close for robustness
            df = pd.DataFrame({
                "Close": close_prices,
                "Open": close_prices * (1 + rng.uniform(-0.005, 0.005, size=len(idx))),
                "High": close_prices * (1 + rng.uniform(0.001, 0.01, size=len(idx))),
                "Low": close_prices * (1 - rng.uniform(0.001, 0.01, size=len(idx))),
                "Volume": rng.integers(1_000_000, 10_000_000, size=len(idx))
            }, index=idx)
            # Ensure High is always >= Close and Open, Low is always <= Close and Open
            df['High'] = np.maximum(df['High'], np.maximum(df['Close'], df['Open']))
            df['Low'] = np.minimum(df['Low'], np.minimum(df['Close'], df['Open']))
            # Ensure values are float
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = df[col].astype(float)


        # Add 50-day SMA for momentum detectors (ensure enough data points)
        if len(df) >= 50:
            df["SMA50"] = df["Close"].rolling(50).mean()
        else:
            df["SMA50"] = np.nan # Assign NaN if not enough data to calculate

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
        
class YfinanceEarningsProvider(DataProvider):
    """
    Fetches upcoming earnings date and calculates expected move
    from yfinance's options data.
    """
    def fetch(self, symbol: str, **kwargs) -> dict | None:
        try:
            tk = yf.Ticker(symbol)
            cal = tk.calendar
            current_price = tk.info.get('currentPrice') or tk.info.get('regularMarketPrice')

            earnings_date_str = None
            # Check for DataFrame first (newer yfinance)
            if isinstance(cal, pd.DataFrame) and not cal.empty:
                if "Earnings Date" in cal.index:
                    earnings_date_raw = cal.loc["Earnings Date"].dropna().iloc[0]
                else:
                    # Fallback if "Earnings Date" not in index, assume first date is next
                    earnings_date_raw = cal.iloc[0, 0]

                if earnings_date_raw:
                    earnings_date_str = pd.to_datetime(earnings_date_raw).strftime("%Y-%m-%d")

            # Check for dictionary (older yfinance)
            elif isinstance(cal, dict):
                arr = cal.get("Earnings Date") or cal.get("earningsDate")
                if arr:
                    earnings_date_str = pd.to_datetime(arr[0]).strftime("%Y-%m-%d")

            if earnings_date_str:
                event_date_dt = dt.datetime.strptime(earnings_date_str, "%Y-%m-%d").date()
                days_until = (event_date_dt - dt.date.today()).days

                expected_move_pct = None
                if current_price and days_until > 0: # Only calculate if we have a price and it's a future event
                    expected_move_pct = self._calculate_expected_move_for_earnings(
                        tk, current_price, earnings_date_str
                    )
                    if expected_move_pct is not None:
                        expected_move_pct = round(expected_move_pct * 100, 2) # Convert to percentage

                return {
                    "date": earnings_date_str,
                    "days_until": days_until,
                    "expected_move_pct": expected_move_pct
                }
            return {} # Return empty dict if no earnings date found
        except Exception as e:
            print(f"Error fetching or calculating earnings from Yfinance for {symbol}: {e}")
            return {"error": str(e)}

    def _calculate_expected_move_for_earnings(self, ticker_obj: yf.Ticker, current_price: float, earnings_date_str: str) -> float | None:
        """
        Calculates the estimated expected move (as a decimal) using ATM options around earnings.
        """
        try:
            # Convert earnings date string to date object
            target_expiry_date = dt.datetime.strptime(earnings_date_str, "%Y-%m-%d").date()

            # Get available options expiry dates
            expiry_dates = ticker_obj.options
            if not expiry_dates:
                print(f"No options expiry dates found for {ticker_obj.ticker}")
                return None

            # Find the closest expiry date that is on or immediately after the earnings date
            closest_expiry = None
            min_days_after_earnings = float('inf')

            for exp_str in expiry_dates:
                exp_dt = dt.datetime.strptime(exp_str, "%Y-%m-%d").date()

                # We are looking for an expiry on or after the earnings date
                if exp_dt >= target_expiry_date:
                    days_diff = (exp_dt - target_expiry_date).days
                    if days_diff < min_days_after_earnings:
                        min_days_after_earnings = days_diff
                        closest_expiry = exp_str

            if not closest_expiry:
                print(f"No suitable options expiry found on or after earnings date {earnings_date_str} for {ticker_obj.ticker}.")
                return None

            # Fetch options chain for the closest expiry
            options_chain = ticker_obj.option_chain(closest_expiry)
            calls = options_chain.calls
            puts = options_chain.puts

            if calls.empty or puts.empty:
                print(f"No call or put options found for expiry {closest_expiry} for {ticker_obj.ticker}.")
                return None

            # Find At-the-Money (ATM) implied volatility
            # Average the implied volatility of the call and put closest to the current price

            # Filter for non-zero impliedVolatility to avoid division by zero or bad data
            calls_filtered = calls[calls['impliedVolatility'] > 0]
            puts_filtered = puts[puts['impliedVolatility'] > 0]

            if calls_filtered.empty or puts_filtered.empty:
                print(f"No valid IV found for ATM options for expiry {closest_expiry} for {ticker_obj.ticker}.")
                return None

            atm_call = calls_filtered.iloc[(calls_filtered['strike'] - current_price).abs().argsort()[:1]]
            atm_put = puts_filtered.iloc[(puts_filtered['strike'] - current_price).abs().argsort()[:1]]

            atm_iv = None
            if not atm_call.empty and not atm_put.empty:
                call_iv = atm_call['impliedVolatility'].iloc[0]
                put_iv = atm_put['impliedVolatility'].iloc[0]
                atm_iv = (call_iv + put_iv) / 2
            elif not atm_call.empty: # Fallback if only calls available
                atm_iv = atm_call['impliedVolatility'].iloc[0]
            elif not atm_put.empty: # Fallback if only puts available
                atm_iv = atm_put['impliedVolatility'].iloc[0]

            if atm_iv is None or atm_iv <= 0:
                print(f"ATM implied volatility could not be determined or is zero for {ticker_obj.ticker} on {closest_expiry}.")
                return None

            # Calculate days from today to the *selected expiry*
            days_to_expiry_for_calc = (dt.datetime.strptime(closest_expiry, "%Y-%m-%d").date() - dt.date.today()).days
            if days_to_expiry_for_calc <= 0:
                print(f"Calculated expiry days is <= 0 for {ticker_obj.ticker} on {closest_expiry}.")
                return None

            # Expected Move Formula: Stock Price * Implied Volatility * sqrt(Days to Expiry / 365)
            # This gives the expected move in absolute dollars.
            expected_move_abs = current_price * atm_iv * np.sqrt(days_to_expiry_for_calc / 365.0)

            # Convert to percentage of current price
            expected_move_pct_decimal = expected_move_abs / current_price

            return expected_move_pct_decimal

        except Exception as e:
            print(f"Detailed error calculating expected move for {ticker_obj.ticker} on {earnings_date_str}: {e}")
            import traceback
            traceback.print_exc() # Print full traceback for debugging
            return None

class PushshiftRedditProvider(DataProvider):
    """Simulates fetching unusual options activity like sweeps."""
    def fetch(self, symbol: str, **kwargs) -> Dict[str, int]:
        # Mock data since Pushshift API is often unreliable
        if random.random() > 0.8:  # 20% chance of mentions
            return {"mentions": random.randint(50, 500)}
        return {"mentions": 0}


def _series_tail_list(ser: pd.Series, n=30) -> list[float]:
    return ser.dropna().tail(n).to_numpy(dtype=float).tolist()

def _df_close_tail_list(df: pd.DataFrame, n=30) -> list[float]:
    return _series_tail_list(pd.to_numeric(df['Close'], errors='coerce'), n)

class GoogleTrendsProvider(DataProvider):
    """
    Fetches Google search interest for a given symbol using pytrends.
    This provides a 'GoogleTrendScore' from 0-100.
    """
    def __init__(self) -> None:
        try:
            # hl='en-US' (host language), tz=360 (timezone for PST is 420, ET is 300, etc. 360 is common)
            self._pt = TrendReq(hl="en-US", tz=360) 
        except Exception as e:
            print(f"Warning: pytrends TrendReq initialization failed: {e}. Google Trends will not be available.")
            self.has_pytrends = False
        else:
            self.has_pytrends = True

    def fetch(self, symbol: str, **kwargs) -> Dict[str, float]:
        if not self.has_pytrends:
            print("pytrends not initialized, returning mock data for GoogleTrendScore.")
            # Fallback to mock data if pytrends failed to initialize
            if random.random() > 0.7:
                return {"trends": random.uniform(20, 100)}
            return {"trends": 0.0}

        try:
            # Use a general query, potentially ticker + "stock" to avoid ambiguity
            query = f"{symbol} stock" if len(symbol) <= 4 else symbol # For short tickers, add "stock"

            # Build payload for the query:
            # kw_list: list of keywords to search
            # cat: category (0 for all categories)
            # timeframe: 'today 3-m' for past 3 months; could be 'today 12-m' for 1 year
            # geo: geographical area ('' for worldwide, 'US' for United States)
            # gprop: Google property ('', 'images', 'news', 'youtube', 'froogle')
            self._pt.build_payload(
                kw_list=[query],
                cat=0,
                timeframe='today 3-m', # Fetch data for the last 3 months
                geo='', # Worldwide
                gprop='' # All Google properties
            )

            # Get interest over time data
            df = self._pt.interest_over_time()

            if not df.empty and query in df.columns:
                # The latest value is usually the most relevant for "current" trend score
                # Drop 'isPartial' column if present before taking latest value
                if 'isPartial' in df.columns:
                    df = df.drop(columns=['isPartial'])

                latest_trend_score = df[query].iloc[-1]
                print(f"Google Trend Score for {symbol} ({query}): {latest_trend_score}")
                return {"trends": float(latest_trend_score)}
            else:
                print(f"No Google Trends data found for {symbol} ({query}).")
                return {"trends": 0.0} # Return 0 if no data found

        except Exception as e:
            # This could be due to rate limiting, network issues, or internal pytrends errors.
            print(f"Error fetching Google Trends for {symbol}: {e}. Returning 0.")
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
        # The raw dict from MomentumProvider already contains the individual flags
        # like GoldenCross, DeathCross, BollingerBandSqueeze, RSI_Overbought, RSI_Oversold, price_above_sma50.
        # We also return the existing 'MomentumSignal' if it's still used for a generic flag.
        
        # This adapter should simply pass through the raw signals as top-level keys
        # and potentially create a top-level 'MomentumSignal' if needed for other detectors
        adapted_data = {}
        if raw:
            # Add all specific signals directly
            adapted_data["GoldenCross"] = raw.get("GoldenCross", False)
            adapted_data["DeathCross"] = raw.get("DeathCross", False)
            adapted_data["BollingerBandSqueeze"] = raw.get("BollingerBandSqueeze", False)
            adapted_data["RSI_Overbought"] = raw.get("RSI_Overbought", False)
            adapted_data["RSI_Oversold"] = raw.get("RSI_Oversold", False)
            adapted_data["price_above_sma50"] = raw.get("price_above_sma50", False) # Ensure this also passes through
            
            # If the generic "MomentumSignal" key (which itself is a dict) is still
            # used by other detectors or for its 'strong_signal_detected' flag, include it.
            # Otherwise, it might be redundant now that individual flags are exposed.
            adapted_data["MomentumSignal"] = raw.get("MomentumSignal", {}) 

        # For debugging: Print what the adapter passes to IdeaEngine
        # (Comment out or remove in production for less console spam)
        # print(f"Adapter output: {adapted_data}") 

        return adapted_data

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
    _momentum = MomentumProvider()
    _earnings = YfinanceEarningsProvider() 
    _macro = HardcodedMacroProvider()

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
        # ADDED DELAY HERE TO PREVENT 429 ERRORS FROM GOOGLE TRENDS
        time.sleep(7) # Adjust this value (e.g., 5-15 seconds) based on your usage and how many symbols you query.

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

    @classmethod
    def get_macro_data(cls) -> Dict[str, Any]:
        """Explicitly fetches and adapts macro data."""
        try:
            macro_raw = cls._macro.fetch("GLOBAL") # Call the macro provider
            return MacroAdapter.adapt(macro_raw) # Adapt it here
        except Exception as e:
            print(f"Error fetching raw macro data: {e}")
            return {"MacroEvents": [], "error": str(e)} # Return empty list on error