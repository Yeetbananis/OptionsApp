# filters.py

import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Union

@dataclass
class FilterConfig:
    """
    Configuration for entry-filtering in the backtester,
    including an intraday Time-of-Day window.
    """

    # ─── Time-of-Day window ────────────────────────────────────────────────
    # Raw strings from the UI (e.g. "09:30")
    tod_from_str: Optional[str] = None
    tod_to_str:   Optional[str] = None

    # Parsed dt.time objects
    tod_from: Optional[dt.time] = None
    tod_to:   Optional[dt.time] = None

    # ─── Weekdays to skip (0=Mon … 6=Sun) ─────────────────────────────────
    skip_weekdays: List[int] = field(default_factory=list)

    # ─── Seasonality: N days before expiry ────────────────────────────────
    days_before_expiry: Optional[int] = None

    # ─── Earnings buffer: ±X days around earnings ─────────────────────────
    earnings_buffer: Optional[int] = None
    earnings_calendar: Dict[str, List[dt.date]] = field(default_factory=dict)

    def __post_init__(self):
        # parse Time-of-Day strings into dt.time
        if self.tod_from_str:
            h, m = map(int, self.tod_from_str.split(":"))
            self.tod_from = dt.time(hour=h, minute=m)
        if self.tod_to_str:
            h, m = map(int, self.tod_to_str.split(":"))
            self.tod_to = dt.time(hour=h, minute=m)

    def allows(self, entry_dt: Union[dt.datetime, dt.date], expiry_date: dt.date, ticker: str) -> bool:
        print(f"Checking trade: entry_dt={entry_dt}, expiry_date={expiry_date}, ticker={ticker}")
        # Time-of-Day check
        if self.tod_from and self.tod_to and isinstance(entry_dt, dt.datetime):
            t = entry_dt.time()
            if t < self.tod_from or t > self.tod_to:
                print("Failed time-of-day filter")
                return False

        # Normalize entry_date
        if isinstance(entry_dt, dt.datetime):
            entry_date = entry_dt.date()
        elif isinstance(entry_dt, dt.date):
            entry_date = entry_dt
        else:
            print("Invalid entry_dt type")
            return False

        # Weekday filter
        if entry_date.weekday() in self.skip_weekdays:
            print(f"Skipped due to weekday {entry_date.weekday()} in skip_weekdays={self.skip_weekdays}")
            return False

        # Days before expiry
        if self.days_before_expiry is not None:
            dte = (expiry_date - entry_date).days
            if dte > self.days_before_expiry:
                print(f"Failed days_before_expiry filter: DTE={dte} > {self.days_before_expiry}")
                return False

        # Earnings buffer
        if self.earnings_buffer is not None:
            for ed in self.earnings_calendar.get(ticker, []):
                days_diff = abs((entry_date - ed).days)
                if days_diff <= self.earnings_buffer:
                    print(f"Failed earnings buffer filter: entry_date={entry_date}, earnings_date={ed}, days_diff={days_diff} <= {self.earnings_buffer}")
                    return False

        return True

    def passes(self, trade: dict) -> bool:
        entry_dt = trade.get("open")
        expiry_date = trade.get("expiry_date") or trade.get("expiry") or trade.get("exp_date")
        ticker = trade.get("ticker")

        if not entry_dt or not expiry_date or not ticker:
            print(f"Missing fields in trade: {trade}")
            return True

        if isinstance(expiry_date, str):
            try:
                expiry_date = dt.datetime.strptime(expiry_date, "%Y-%m-%d").date()
            except ValueError as e:
                print(f"Failed to parse expiry_date '{expiry_date}': {e}")
                return False

        try:
            result = self.allows(entry_dt, expiry_date, ticker)
            if not result:
                print(f"Trade failed filter: entry_dt={entry_dt}, expiry_date={expiry_date}, ticker={ticker}, skip_weekdays={self.skip_weekdays}, days_before_expiry={self.days_before_expiry}, earnings_buffer={self.earnings_buffer}")
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return False
