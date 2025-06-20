# earnings_calendar.py

import functools
import logging
import datetime
from yahooquery import Ticker
import time

@functools.lru_cache(maxsize=None)
def fetch_earnings_calendar(sym: str) -> list[datetime.date]:
    time.sleep(0.5)  # throttle
    """
    Fetch upcoming earnings dates for a single ticker.
    Results are cached for the life of the process.
    """
    logging.info(f"Fetching earnings calendar for {sym}…")
    try:
        t = Ticker(sym)
        df = t.earnings_dates
        # if there's a multi‐index, take the symbol‐slice
        if hasattr(df, 'xs'):
            df = df.xs(sym, level=0)
        today = datetime.date.today()
        dates = [
            idx.to_pydatetime().date()
            for idx in df.index
            if idx.to_pydatetime().date() >= today
        ]
        return sorted(set(dates))
    except Exception as e:
        logging.warning(f"Failed to fetch earnings for {sym}: {e}")
        return []
