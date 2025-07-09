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


# In providers.py

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
            
            df = df.copy()

            # Ensure 'Close', 'High', 'Low' columns are numeric (already done in YahooPriceProvider, but safe check)
            df["Close"] = pd.to_numeric(df["Close"], errors="coerce").dropna()
            df["High"] = pd.to_numeric(df["High"], errors="coerce").dropna()
            df["Low"] = pd.to_numeric(df["Low"], errors="coerce").dropna()

            if df["Close"].empty or df["High"].empty or df["Low"].empty:
                print(f"[{symbol}] OHLC price data is empty after cleaning for {symbol}.")
                return {}

            momentum_signals = {}

            # --- Calculate SMAs (SMA50 moved here for robustness) ---
            # Ensure enough data for SMA50 (min 50 days)
            if len(df) >= 50:
                df['SMA50'] = ta.sma(df['Close'], length=50)
            else:
                df['SMA50'] = np.nan # Assign NaN if not enough data

            # Calculate SMA200 only if enough data (min 200 days)
            if len(df) >= 200:
                df['SMA200'] = ta.sma(df['Close'], length=200)
            else:
                df['SMA200'] = np.nan # Assign NaN if not enough data


            # --- Ensure enough data for other indicators ---
            # BBands/KC defaults to length=20. RSI to 14.
            min_required_data_for_full_indicators = 200 # For SMA200, otherwise 20 for BB/KC
            if len(df) < min_required_data_for_full_indicators: 
                print(f"[{symbol}] Not enough data ({len(df)} days) for all indicators (min {min_required_data_for_full_indicators}). Some may be skipped.")

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
        # In providers.py -> class YahooPriceProvider

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

            # --- FIX START ---
            # This is the new line to add. It de-duplicates the columns, keeping the first occurrence.
            # This prevents errors where df['Close'] would return a DataFrame instead of a Series.
            input_df = input_df.loc[:,~input_df.columns.duplicated()]
            # --- FIX END ---

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
        
# In data/providers.py


# =============================================================
# Helper function to be placed inside the providers.py file,
# before the FundamentalDataProvider class definition.
# =============================================================
def _to_float(val: Any) -> float | None:
    """
    Robustly converts a value to a float, handling formatted strings
    like '1.5b', '250m', '75k', etc., and also '0m', '0k', etc.
    Added explicit string conversion and debug for problematic values.
    """
    if isinstance(val, (int, float)):
        return float(val)
    
    # Crucial: Ensure the value is treated as a string for parsing
    if not isinstance(val, str):
        # If it's not a string and not a number, try converting it to string.
        # This catches pandas Series, numpy objects, etc.
        try:
            val_str = str(val).lower().strip()
        except Exception:
            return None # Cannot even convert to string
    else:
        val_str = val.lower().strip()

    # Handle empty strings or 'nan' strings
    if not val_str or val_str in ['nan', 'n/a', 'none']:
        return None

    multipliers = {'t': 1e12, 'b': 1e9, 'm': 1e6, 'k': 1e3}

    # Check for a known multiplier suffix
    if val_str and val_str[-1] in multipliers:
        multiplier = multipliers[val_str[-1]]
        numeric_part_str = val_str[:-1]
        try:
            # Handle cases like '0m', '0k' gracefully
            if numeric_part_str == '0':
                return 0.0 # Explicitly return 0.0 for "0m", "0k" etc.
            return float(numeric_part_str) * multiplier
        except (ValueError, TypeError):
            print(f"DEBUG: _to_float failed to convert numeric part '{numeric_part_str}' from '{val}' with multiplier. Returning None.")
            return None # Failed to convert the numeric part
    
    # Try direct conversion if no suffix
    try:
        return float(val_str)
    except (ValueError, TypeError):
        # This is where the '0m' error *might* originate if it bypasses the multiplier check
        # For example, if val_str was "0m" and the suffix check failed for some reason
        # or if the string was something truly unparseable.
        print(f"DEBUG: _to_float failed direct conversion for '{val_str}' (original: '{val}'). Returning None.")
        return None

class FundamentalDataProvider(DataProvider):
    """
    Fetches fundamental data and sanitizes formatted numbers (e.g., '1.5b')
    into proper floating-point values before returning them.
    """
    def __init__(self, price_provider: DataProvider = None) -> None:
        self.price_provider = price_provider or YahooPriceProvider()

    @lru_cache(maxsize=128)
    def fetch(self, symbol: str, session=None, **kwargs) -> Dict[str, Any]:
        fundamentals = {}
        try:
            ticker_obj = yf.Ticker(symbol, session=session)
            info = ticker_obj.info

            if not isinstance(info, dict) or len(info) <= 1:
                print(f"[{symbol}] yfinance info object is not valid. Aborting fundamental fetch.")
                return {}

            current_price = _to_float(info.get('currentPrice') or info.get('regularMarketPrice'))

            # Sanitize all numeric fields using the _to_float helper
            fundamentals["current_pe"] = _to_float(info.get("trailingPE"))
            fundamentals["forwardPE"] = _to_float(info.get("forwardPE"))
            fundamentals["pegRatio"] = _to_float(info.get("pegRatio"))
            fundamentals["market_cap"] = _to_float(info.get("marketCap"))
            # --- FIX: Standardize the 'dividendYield' key to camelCase ---
            fundamentals["dividendYield"] = _to_float(info.get("dividendYield"))
            fundamentals["beta"] = _to_float(info.get("beta"))
            fundamentals["short_percent_of_float"] = _to_float(info.get("shortPercentOfFloat"))
            fundamentals["priceToBook"] = _to_float(info.get("priceToBook"))
            fundamentals["enterpriseValue"] = _to_float(info.get("enterpriseValue"))
            fundamentals["grossMargins"] = _to_float(info.get("grossMargins"))
            fundamentals["profitMargins"] = _to_float(info.get("profitMargins"))
            fundamentals["revenueGrowth"] = _to_float(info.get("revenueGrowth"))
            fundamentals["earningsGrowth"] = _to_float(info.get("earningsGrowth"))
            fundamentals["returnOnEquity"] = _to_float(info.get("returnOnEquity"))
            fundamentals["debtToEquity"] = _to_float(info.get("debtToEquity"))

            # In providers.py, find this block within FundamentalDataProvider.fetch:
            try:
                recs = ticker_obj.recommendations
                if recs is not None and not recs.empty:
                    # FIX: Convert the DataFrame to a JSON-serializable format (list of dicts)
                    # We'll also specifically select columns that are useful for caching if needed
                    # Or, if only summary is needed, this can be even more simplified.
                    # For now, let's keep the structure that _update_analyst_ratings expects.
                    # _update_analyst_ratings expects recs.iloc[-1] and then specific columns.
                    # So, saving the whole DataFrame as a list of dicts is too verbose.
                    # Let's save only the latest rating as a dictionary to avoid DataFrame serialization.
                    
                    # If you want to keep the full recommendations history,
                    # you must convert the DataFrame to a list of records.
                    # For a simple fix that allows JSON serialization:
                    fundamentals["recommendations"] = recs.to_dict(orient='records') # Convert entire DataFrame to list of dicts
                    
                    # Or, if only the latest is truly needed for caching:
                    # if not recs.empty:
                    #     latest_ratings = recs.iloc[-1].to_dict()
                    #     fundamentals["recommendations"] = latest_ratings
                    # else:
                    #     fundamentals["recommendations"] = {}
                else:
                    fundamentals["recommendations"] = [] # Ensure it's an empty list if no recs
            except Exception as e:
                print(f"Could not fetch or process recommendations for {symbol}: {e}")
                fundamentals["recommendations"] = [] # Ensure it's an empty list on error

            fundamentals["analyst_target_mean_price"] = _to_float(info.get("targetMeanPrice"))
            fundamentals["analyst_target_high_price"] = _to_float(info.get("targetHighPrice"))
            fundamentals["analyst_target_low_price"] = _to_float(info.get("targetLowPrice"))
            fundamentals["analyst_target_median_price"] = _to_float(info.get("targetMedianPrice"))

            quarterly_financials_df = ticker_obj.quarterly_financials
            if (quarterly_financials_df is not None and not quarterly_financials_df.empty and
                'Basic EPS' in quarterly_financials_df.index):

                eps_df_transposed = quarterly_financials_df.T
                eps_series = pd.to_numeric(eps_df_transposed['Basic EPS'], errors='coerce').dropna()
                eps_series = eps_series.sort_index()

                if len(eps_series) >= 4:
                    ttm_eps_series = eps_series.rolling(window=4, min_periods=4).sum()
                    price_df = self.price_provider.fetch(symbol, period="5y", interval="1mo")

                    if not price_df.empty and 'Close' in price_df.columns:
                        price_df['Close'] = pd.to_numeric(price_df['Close'], errors='coerce')
                        min_date = max(price_df.index.min(), ttm_eps_series.index.min())
                        max_date = min(price_df.index.max(), ttm_eps_series.index.max())

                        if min_date < max_date:
                            full_date_range = pd.date_range(start=min_date, end=max_date, freq='D')
                            ttm_eps_daily = ttm_eps_series.reindex(full_date_range).ffill()
                            aligned_prices = price_df['Close'].reindex(full_date_range).bfill()
                            historical_pe = aligned_prices / ttm_eps_daily
                            
                            historical_pe = historical_pe[
                                historical_pe.notna() & (historical_pe != np.inf) &
                                (historical_pe != -np.inf) & (ttm_eps_daily != 0)
                            ]
                            historical_pe = historical_pe[(historical_pe > 0) & (historical_pe < 1000)]

                            if not historical_pe.empty:
                                fundamentals["historical_pe_avg"] = historical_pe.mean()
                                fundamentals["historical_pe_median"] = historical_pe.median()
                                fundamentals["historical_pe_min"] = historical_pe.min()
                                fundamentals["historical_pe_max"] = historical_pe.max()
                                fundamentals["historical_pe_std"] = historical_pe.std()
            
            try:
                earnings_dates_df = ticker_obj.earnings_dates
                if earnings_dates_df is not None and not earnings_dates_df.empty:
                    current_naive_date = dt.date.today()
                    past_earnings_dates_df = earnings_dates_df[earnings_dates_df.index.date < current_naive_date]
                    if not past_earnings_dates_df.empty:
                        latest_report_row = past_earnings_dates_df.sort_index(ascending=False).iloc[0]
                        
                        report_date = latest_report_row.name.strftime("%Y-%m-%d")
                        reported_eps = _to_float(latest_report_row.get("Reported EPS"))
                        estimated_eps = _to_float(latest_report_row.get("Estimated EPS"))
                        surprise_pct = _to_float(latest_report_row.get("Surprise(%)"))

                        if (surprise_pct is None and reported_eps is not None and estimated_eps is not None and estimated_eps != 0):
                            surprise_pct = ((reported_eps - estimated_eps) / abs(estimated_eps)) * 100
                            
                        fundamentals["latest_earnings_report"] = {
                            "date": report_date, "reported_eps": reported_eps,
                            "estimated_eps": estimated_eps, "surprise_pct": surprise_pct
                        }

                        if report_date and current_price is not None:
                            recent_price_df = self.price_provider.fetch(symbol, period="1mo", interval="1d")
                            if not recent_price_df.empty and 'Close' in recent_price_df.columns:
                                prices_after_earnings = recent_price_df.loc[recent_price_df.index.date >= pd.to_datetime(report_date).date(), 'Close']
                                
                                if len(prices_after_earnings) >= 2:
                                    report_date_price = prices_after_earnings.iloc[0]
                                    next_day_price = prices_after_earnings.iloc[1]
                                    
                                    if report_date_price and not pd.isna(report_date_price) and next_day_price and not pd.isna(next_day_price) and report_date_price != 0:
                                        fundamentals["earnings_1d_price_change_pct"] = ((next_day_price - report_date_price) / report_date_price) * 100
                                    
                                    if len(prices_after_earnings) >= 4:
                                        day3_price = prices_after_earnings.iloc[3]
                                        if report_date_price and not pd.isna(report_date_price) and day3_price and not pd.isna(day3_price) and report_date_price != 0:
                                            fundamentals["earnings_3d_price_change_pct"] = ((day3_price - report_date_price) / report_date_price) * 100
            except Exception as e:
                print(f"[{symbol}] Warning: Could not fetch latest earnings report details or price reaction: {e}")

            return fundamentals

        except Exception as e:
            print(f"Error fetching fundamental data for {symbol}: {e}")
            return {}

# In data/providers.py, add this new class
class FinnhubProfileProvider(DataProvider):
    """Fetches company profile data from the reliable Finnhub API."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    @lru_cache(maxsize=128)
    def fetch(self, symbol: str, **kwargs) -> Dict[str, Any]:
        try:
            url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={self.api_key}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # If data is empty, it means the ticker is likely not found on Finnhub
            if not data:
                return {}

            # Normalize Finnhub's keys to match what our UI expects from yfinance
            profile = {
                "longBusinessSummary": data.get("description", "No company profile available."),
                "sector": data.get("finnhubIndustry", "N/A"),
                "industry": "N/A", # Finnhub combines sector/industry
                "logo_url": data.get("logo", "")
            }
            return profile
        except Exception as e:
            print(f"Error fetching Finnhub profile for {symbol}: {e}")
            return {} # Return empty dict on any failure
        
class FinnhubFundamentalsProvider(DataProvider):
    """
    Fetches key financial metrics from the reliable Finnhub API and
    sanitizes formatted numbers into proper floating-point values.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key

    @lru_cache(maxsize=128)
    def fetch(self, symbol: str, **kwargs) -> Dict[str, Any]:
        try:
            url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={self.api_key}"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json().get("metric", {})

            if not data:
                return {}

            mkt_cap_millions = _to_float(data.get("marketCapitalization"))
            full_market_cap = mkt_cap_millions * 1e6 if mkt_cap_millions is not None else None
            
            dividend_yield_percent = _to_float(data.get("dividendYieldTTM"))
            dividend_yield_decimal = dividend_yield_percent / 100.0 if dividend_yield_percent is not None else None

            fundamentals = {
                "trailingPE": _to_float(data.get("peTTM")),
                "forwardPE": _to_float(data.get("forwardPE")),
                "pegRatio": _to_float(data.get("pegRatioTTM")),
                "marketCap": full_market_cap,
                "dividendYield": dividend_yield_decimal,
                "beta": _to_float(data.get("beta")),
                "fiftyTwoWeekLow": _to_float(data.get("52WeekLow")),
                "fiftyTwoWeekHigh": _to_float(data.get("52WeekHigh")),
                "averageVolume": _to_float(data.get("10DayAverageTradingVolume")),
                "trailingEps": _to_float(data.get("epsTTM")),
                # --- FIX: Add Price-to-Book ratio from the correct API key ---
                "priceToBook": _to_float(data.get("pbAnnual")),
            }
            return fundamentals
        except Exception as e:
            print(f"Error fetching Finnhub fundamentals for {symbol}: {e}")
            return {}
        
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
        


class InsiderTransactionsProvider(DataProvider):
    """Fetches recent insider transactions from the Finnhub API."""
    def __init__(self, api_key: str):
        self.api_key = api_key

    @lru_cache(maxsize=128)
    def fetch(self, symbol: str, **kwargs) -> List[Dict[str, Any]]:
        url = f"https://finnhub.io/api/v1/stock/insider-transactions?symbol={symbol}&token={self.api_key}"
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json().get('data', [])

            # We only want the most recent transactions
            recent_transactions = sorted(data, key=lambda x: x.get('transactionDate'), reverse=True)[:15]

            # Format the data for display
            formatted = []
            for tx in recent_transactions:
                change_char = "➕" if tx['change'] > 0 else "➖" if tx['change'] < 0 else "⚪"
                formatted.append({
                    "date": tx.get('transactionDate'),
                    "name": tx.get('name', 'N/A').title(),
                    "share": tx.get('share'),
                    "change": f"{change_char} {abs(tx.get('change', 0)):,}",
                    "price": f"${tx.get('transactionPrice', 0):.2f}"
                })
            return formatted
        except Exception as e:
            print(f"Error fetching insider transactions for {symbol}: {e}")
            return []
        
# In data/providers.py, add this new class

class OptionsChainProvider(DataProvider):
    """Fetches the full options chain for several upcoming expiries."""
    @lru_cache(maxsize=32)
    def fetch(self, symbol: str, session=None, **kwargs) -> Dict[str, Dict[str, pd.DataFrame]]:
        try:
            ticker_obj = yf.Ticker(symbol, session=session)
            expirations = ticker_obj.options

            if not expirations:
                return {}

            # Fetch for the next 4 available weekly/monthly expirations
            options_data = {}
            for expiry in expirations[:4]:
                chain = ticker_obj.option_chain(expiry)
                options_data[expiry] = {
                    "calls": chain.calls,
                    "puts": chain.puts
                }
            return options_data
        except Exception as e:
            print(f"Error fetching options chain for {symbol}: {e}")
            return {}
        
class PeerComparisonProvider(DataProvider):
    """
    Fetches a list of peers from Finnhub and then gathers key fundamental
    metrics for each peer to create a comparison table.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.fundamentals_provider = FinnhubFundamentalsProvider(api_key)

    @lru_cache(maxsize=128)
    def fetch(self, symbol: str, **kwargs) -> pd.DataFrame:
        print(f"[{symbol}] Fetching peer comparison data...")
        peers_url = f"https://finnhub.io/api/v1/stock/peers?symbol={symbol}&token={self.api_key}"
        try:
            response = requests.get(peers_url, timeout=10)
            response.raise_for_status()
            peer_tickers = response.json()

            if not peer_tickers:
                print(f"[{symbol}] No peers found.")
                return pd.DataFrame()

            # --- FIX: Ensure the primary symbol appears only once ---
            unique_peers = set(peer_tickers)
            unique_peers.discard(symbol)
            comparison_list = [symbol] + list(unique_peers)
            comparison_list = comparison_list[:10]

            all_peers_data = []
            for peer_symbol in comparison_list:
                funda_data = self.fundamentals_provider.fetch(peer_symbol)
                if funda_data:
                    # --- FIX: Removed "Div. Yield" ---
                    all_peers_data.append({
                        "Ticker": peer_symbol,
                        "Market Cap": funda_data.get("marketCap"),
                        "P/E Ratio": funda_data.get("trailingPE"),
                        "P/B Ratio": funda_data.get("priceToBook"),
                        "EPS": funda_data.get("trailingEps")
                    })

            if not all_peers_data:
                return pd.DataFrame()

            df = pd.DataFrame(all_peers_data)
            df = df.set_index("Ticker")

            def fmt_large_num(n):
                if not isinstance(n, (int, float)): return "N/A"
                if abs(n) >= 1e12: return f"{n/1e12:.2f} T"
                if abs(n) >= 1e9: return f"{n/1e9:.2f} B"
                if abs(n) >= 1e6: return f"{n/1e6:.2f} M"
                return f"{n:,.0f}"

            df["Market Cap"] = df["Market Cap"].apply(fmt_large_num)
            
            for col in ["P/E Ratio", "P/B Ratio", "EPS"]:
                df[col] = df[col].apply(lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else "N/A")

            return df.reset_index()

        except Exception as e:
            print(f"Error fetching peer comparison data for {symbol}: {e}")
            return pd.DataFrame()
        
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
    
class FundamentalAdapter:
    @staticmethod
    def adapt(raw: Dict[str, Any]) -> Dict[str, Any]:
        # Fundamental data is already well-structured, so just pass it through
        return raw if raw else {}

class MacroAdapter:
    @staticmethod
    def adapt(raw: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {"MacroEvents": raw} if raw else {}

# --- PROVIDER HUB ---



class ProviderHub:
    _price = YahooPriceProvider()
    _iv = IVRankProvider(_price)
    _trends = GoogleTrendsProvider()
    _momentum = MomentumProvider()
    _earnings = YfinanceEarningsProvider()
    _macro = HardcodedMacroProvider()
    _fundamental = FundamentalDataProvider(_price)
    # Instantiate new provider with your Finnhub key
    _insider = InsiderTransactionsProvider(api_key="d114k6hr01qse6lf8c1gd114k6hr01qse6lf8c20")

    @classmethod
    def get_macro_data(cls) -> Dict[str, Any]:
        """
        Fetches global macro economic events and wraps them in a dictionary
        to maintain a consistent return type.
        """
        try:
            # The fix is to wrap the list from fetch() in a dictionary
            events_list = cls._macro.fetch("GLOBAL")
            return {"MacroEvents": events_list}
        except Exception as e:
            print(f"Error fetching macro data: {e}")
            return {"error": str(e), "MacroEvents": []}

    @classmethod
    @lru_cache(maxsize=512)
    def get(cls, symbol: str) -> Dict[str, Any]:
        """
        Unified data access for a specific symbol. Guarantees:
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
            price_df = cls._price.fetch(symbol, period="max")
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

                    if len(close) >= 50:
                        sma50 = close.rolling(window=50).mean().iloc[-1]
                        above_sma = bool(last_price > float(sma50)) if not pd.isna(sma50) else False
                    else:
                        above_sma = False
        except Exception as e:
            print(f"Error fetching price data for {symbol}: {e}")
            spark = _static_price_list()
            last_price = spark[-1]
            above_sma = False

        # ---------- other providers (with error handling) -----------------
        providers_to_fetch = {
            "iv": cls._iv.fetch,
            "trends": cls._trends.fetch,
            "momentum": cls._momentum.fetch,
            "earnings": cls._earnings.fetch,
            "fundamental": cls._fundamental.fetch,
            "insider": cls._insider.fetch
        }
        
        raw_data = {}
        for key, fetch_func in providers_to_fetch.items():
            try:
                raw_data[key] = fetch_func(symbol)
            except Exception as e:
                print(f"Error fetching {key} data for {symbol}: {e}")
                raw_data[key] = {} # Ensure it's an empty dict on failure

        # ---------- assemble ------------------------------------------
        data: Dict[str, Any] = {
            "price_sparkline": spark,
            "last_price": last_price,
            "price_above_sma50": above_sma,
            "price_df": price_df # Pass the full DataFrame for charting
        }
        
        # Adapt and update data
        data.update(IVAdapter.adapt(raw_data.get("iv", {})))
        data.update(TrendsAdapter.adapt(raw_data.get("trends", {})))
        data.update(MomentumAdapter.adapt(raw_data.get("momentum", {})))
        data.update(EarningsAdapter.adapt(raw_data.get("earnings", {})))
        data.update(FundamentalAdapter.adapt(raw_data.get("fundamental", {})))
        # A simple pass-through for insider data
        data["insider_transactions"] = raw_data.get("insider", [])

        return data