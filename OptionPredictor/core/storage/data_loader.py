import datetime as _dt
import logging
from pathlib import Path
import pandas as pd
import sqlite3
import numpy as np
from tenacity import retry, stop_after_attempt, wait_exponential
import requests
import io

# Configure logging for the loader
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - LOADER - %(message)s')

# Set up a cache for price data
_price_cache = {}

# Define cache directory and database
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(__file__).parent / "prices.db"

# ---------------------------------------------------------------------------

def _parse_date(dt_like) -> _dt.date:
    """Parses various date inputs into a datetime.date object."""
    if isinstance(dt_like, _dt.datetime):
        return dt_like.date()
    if isinstance(dt_like, _dt.date):
        return dt_like
    if isinstance(dt_like, str):
        try:
            return _dt.datetime.strptime(dt_like, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Invalid date string format: '{dt_like}'. Use YYYY-MM-DD.")
    raise TypeError(f"Unsupported date type: {type(dt_like)}")

def _init_db():
    """Initialize the SQLite database for price data."""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                symbol TEXT,
                date TEXT,
                adj_close REAL,
                PRIMARY KEY (symbol, date)
            )
        """)
        conn.commit()

def _load_from_db(symbol: str, start: _dt.date, end: _dt.date) -> pd.Series:
    """Load price data from the SQLite database."""
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT date, adj_close FROM prices
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            conn,
            params=(symbol.upper(), start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")),
            index_col="date",
            parse_dates=["date"]
        )
    return df["adj_close"] if not df.empty else pd.Series(dtype=float)

def _save_to_db(symbol: str, df: pd.DataFrame):
    """Save price data to the SQLite database."""
    with sqlite3.connect(DB_PATH) as conn:
        df = df.reset_index().rename(columns={df.index.name or "index": "date"})
        df["symbol"] = symbol.upper()
        if "Adj Close" in df.columns:
            df = df.rename(columns={"Adj Close": "adj_close"})
        elif "adj_close" not in df.columns:
            cols = [c for c in df.columns if c not in ("symbol","date")]
            df = df.rename(columns={cols[0]: "adj_close"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df[["symbol","date","adj_close"]].to_sql("prices", conn, if_exists="replace", index=False)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=60))
def get_prices(
    symbol: str,
    start_date: str | _dt.date | _dt.datetime,
    end_date: str | _dt.date | _dt.datetime,
    force_refresh: bool = False,
) -> pd.Series:
    """
    Retrieves daily close prices for a given symbol and date range.
    Primary source: Stooq. Fallback: yfinance.
    Uses local SQLite database for caching.
    """
    sym   = symbol.strip().upper()
    start = _parse_date(start_date)
    end   = _parse_date(end_date)
    if start > end:
        raise ValueError(f"Start date ({start}) after end date ({end}).")
    
    key = (symbol.upper(), start, end)
    if key in _price_cache and not force_refresh:
        logging.info(f"Memory cache hit for {symbol} [{start} to {end}]")
        return _price_cache[key]


    _init_db()
    db_data = _load_from_db(sym, start, end)

    # Return cache if full range present
    if not db_data.empty and not force_refresh:
        if db_data.index.min().date() <= start and db_data.index.max().date() >= end:
            logging.info(f"Database hit for {sym} [{start} to {end}]")
            return db_data.loc[str(start):str(end)]
        logging.info(f"Database incomplete for {sym}; re-downloading.")

    # ─── Primary: Stooq ────────────────────────────────────────────
    logging.info(f"Attempting Stooq download for {sym} [{start} to {end}]")
    url = (
        f"https://stooq.com/q/d/l/?s={sym.lower()}.us"
        f"&d1={start.strftime('%Y%m%d')}&d2={end.strftime('%Y%m%d')}&i=d"
    )
    try:
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        df   = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"], index_col="Date")
        if df.empty:
            raise RuntimeError("Stooq returned no data")
        if "Close" in df.columns:
            df = df.rename(columns={"Close":"Adj Close"})
        logging.info(f"Stooq download succeeded for {sym} ({len(df)} rows)")
    except Exception as e:
        # ─── Fallback: yfinance ────────────────────────────────────────
        logging.warning(f"Stooq failed for {sym}: {e}; falling back to yfinance")
        import yfinance as yf
        yf_start = start.strftime("%Y-%m-%d")
        yf_end   = (end + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
        df = yf.download(sym, start=yf_start, end=yf_end, progress=False, threads=False)
        if df.empty:
            raise RuntimeError(f"yfinance also returned no data for {sym}")
        df.index = pd.to_datetime(df.index)
        logging.info(f"yfinance download succeeded for {sym} ({len(df)} rows)")

    # Extract the appropriate series
    if "Adj Close" in df.columns:
        series = df["Adj Close"]
    elif "Close" in df.columns:
        series = df["Close"]
    else:
        raise RuntimeError("No close data in downloaded DataFrame")

    # Merge with cache and save
    parts = [db_data, series]
    # drop any empty Series before concatenating
    parts = [p for p in parts if not p.empty]
    combined = pd.concat(parts).drop_duplicates().sort_index()
    _save_to_db(sym, combined.to_frame(name="adj_close"))

    # Return exact requested slice
    out = combined.loc[str(start):str(end)]
    if out.empty:
        raise RuntimeError(f"No data in final series for {sym} [{start}:{end}]")
    
    _price_cache[key] = out
    return out


# -------------------------------------------------------------------------------
# Simulated earnings calendar and option chain for testing
# -------------------------------------------------------------------------------

def get_earnings_calendar(symbol: str, start_date, end_date) -> pd.DataFrame:
    start = _parse_date(start_date)
    end   = _parse_date(end_date)
    if start > end:
        raise ValueError(f"Start date ({start}) after end date ({end}).")
    date_range = pd.date_range(start=start, end=end, freq='90D')
    df = pd.DataFrame({
        "Symbol": symbol.upper(),
        "Earnings Date": date_range
    })
    logging.info(f"Simulated earnings calendar for {symbol} with {len(df)} entries")
    return df

def get_option_chain(symbol: str, date) -> pd.DataFrame:
    trade_date = _parse_date(date)
    expirations = pd.date_range(start=trade_date, periods=3, freq='M').date
    strikes = np.arange(100, 200, 10)
    types = ['call', 'put']
    rows = []
    for exp in expirations:
        for strike in strikes:
            for t in types:
                bid   = np.random.uniform(0, 10)
                ask   = bid + np.random.uniform(0, 1)
                iv    = np.random.uniform(0.1, 0.5)
                delta = np.random.uniform(0, 1) if t=='call' else np.random.uniform(-1,0)
                rows.append([exp, strike, t, bid, ask, iv, delta])
    df = pd.DataFrame(rows, columns=["expiration","strike","option_type","bid","ask","iv","delta"])
    logging.info(f"Simulated option chain for {symbol} on {trade_date} with {len(df)} rows")
    return df

if __name__ == "__main__":
    print("--- Testing Data Loader ---")
    test_symbol = "SPY"
    test_start = "2023-05-04"
    test_end = _dt.date.today()

    try:
        print(f"\nFetching {test_symbol} prices from {test_start} to {test_end}...")
        prices = get_prices(test_symbol, test_start, test_end)
        print(f"Loaded {len(prices)} data points.")
        print(prices.tail())

        print(f"\nFetching simulated earnings calendar for {test_symbol}...")
        earnings = get_earnings_calendar(test_symbol, test_start, test_end)
        print(earnings.head())

        print(f"\nFetching simulated option chain for {test_symbol}...")
        chain = get_option_chain(test_symbol, "2023-10-27")
        print(chain.head())
    except Exception as e:
        print(f"Error during self-test: {e}")
        logging.exception("Loader self-test failure")
