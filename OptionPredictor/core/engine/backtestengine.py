# backtestengine.py

import logging
import datetime as dt
from typing import Callable, Optional

import pandas as pd

from app.config import StrategyConfig
from core.models.filters import FilterConfig
import core.engine.backtester as BT
from tools.earningscalendar import fetch_earnings_calendar

# configure module-level logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class BacktestResult:
    """
    Wraps raw backtester output in a clean object.
    Provides methods for summary, equity curve access, trade list, and CSV export.
    """
    def __init__(
        self,
        equity: pd.Series,
        trades: list[dict],
        stats: dict,
        config: dict,
        benchmark: pd.Series
    ):
        self._equity    = equity
        self._trades    = trades
        self._stats     = stats
        self._config    = config
        self._benchmark = benchmark

    def summary(self) -> dict:
        """Return performance statistics dict."""
        return self._stats

    def equity_curve(self) -> pd.Series:
        """Return full equity‐curve series."""
        return self._equity

    def trade_list(self) -> list[dict]:
        """Return list of executed trades (after filtering)."""
        return list(self._trades)

    def export_csv(self, path: str):
        """
        Write equity and trade data to CSV files.
        Files: <path>_equity.csv and <path>_trades.csv
        """
        df_eq = self._equity.to_frame(name="equity").reset_index().rename(columns={'index': 'date'})
        df_tr = pd.DataFrame(self._trades)
        df_eq.to_csv(f"{path}_equity.csv", index=False)
        df_tr.to_csv(f"{path}_trades.csv",  index=False)
        logging.info(f"Exported equity → {path}_equity.csv and trades → {path}_trades.csv")


class BacktestEngine:
    """
    Pure engine: takes a StrategyConfig, runs the backtester,
    applies entry/exit filters, streams progress & trades via callbacks,
    and packages results as a BacktestResult.
    """

    def __init__(
        self,
        config: StrategyConfig,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        trade_callback:    Optional[Callable[[dict], None]] = None,
    ):
        self.config            = config
        self.progress_callback = progress_callback
        self.trade_callback    = trade_callback
        self._result: Optional[BacktestResult] = None

    @staticmethod
    def estimate_steps(cfg: StrategyConfig) -> int:
        """
        Cheap estimate of total steps for progress bar.
        Here: number of calendar days between start/end.
        """
        start = pd.to_datetime(cfg.start)
        end   = pd.to_datetime(cfg.end)
        return max(1, (end - start).days)

    def run(self, chunk_size=50, price_data: Optional[pd.Series] = None, benchmark_data: Optional[pd.Series] = None):
        cfg_dict = self.config.to_dict()
        logging.info("Starting Backtester.run()")
        # Pass the price_data to the Backtester.run method
        raw = BT.Backtester.run(cfg_dict, price_data=price_data)

        all_trades = raw["trades"]
        fcfg = self.config.filters
        if isinstance(fcfg, dict):
            fcfg = FilterConfig(**fcfg)


        allowed = []
        for trade in all_trades:
            entry_dt = trade["open"]
            expiry = trade.get("expiry", entry_dt)
            # Ensure expiry is a date object for comparison
            expiry_dt = expiry.date() if hasattr(expiry, "date") else pd.to_datetime(expiry).date()


            if fcfg.allows(entry_dt, expiry_dt, self.config.underlying):
                allowed.append(trade)


        total = len(allowed)
        logging.info(f"Filtered trades: {total} / {len(all_trades)} allowed")


        benchmark = raw.get("benchmark")
        if not cfg_dict.get("use_benchmark", True):
            benchmark = None
        elif benchmark_data is not None:
            benchmark = benchmark_data
        self._result = BacktestResult(
            equity=raw["equity"],
            trades=[], # Trades are added via callback
            stats=raw["stats"],
            config=raw["config"],
            benchmark=benchmark,
        )


        buffer = []
        for idx, trade in enumerate(allowed, start=1):
            # Optimization/BatchRunner will handle trade logging via callback
            # self._result._trades.append(trade)
            buffer.append(trade)


            if len(buffer) >= chunk_size:
                if self.trade_callback:
                    try:
                        self.trade_callback(list(buffer))  # Send chunk
                    except Exception:
                        logging.exception("Error in trade_callback")
                buffer.clear()


            if self.progress_callback:
                try:
                    self.progress_callback(idx, total)
                except Exception:
                    logging.exception("Error in progress_callback")


        if buffer and self.trade_callback:
            try:
                self.trade_callback(list(buffer))  # Final flush
            except Exception:
                logging.exception("Error in trade_callback (final flush)")

        # After all trades are processed and sent via callback, update the result's trade list
        # This ensures the result object has the final filtered list for summary/export
        self._result._trades = allowed

        logging.info("BacktestEngine run complete.")


    def result(self) -> BacktestResult:
        """
        Return the BacktestResult.  Must call .run() first.
        """
        if self._result is None:
            raise RuntimeError("BacktestEngine.run() must be called before result()")
        return self._result


# Example usage when run directly
if __name__ == "__main__":
    # simple smoke test
    cfg = StrategyConfig(
        underlying="SPY",
        start="2022-01-01",
        end="2022-12-31",
        strategy_type="short_put",
        capital=100_000,
        allocation_pct=5,
        profit_target_pct=50,
        stop_loss_mult=2,
        dte_target=30,
        commission_per_contract=0.65,
        risk_free_rate=0.03,
    )
    engine = BacktestEngine(cfg,
        progress_callback=lambda done, total: print(f"{done}/{total}"),
        trade_callback=lambda t: print("TRD", t)
    )
    engine.run()
    res = engine.result()
    print("\nFinal equity:", res.equity_curve().iloc[-1])
    print("Trades:", len(res.trade_list()))
    print("Stats:", res.summary())
