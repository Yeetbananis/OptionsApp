import logging
from typing import Callable, Optional

import pandas as pd

from app.config import StrategyConfig
from core.models.filters import FilterConfig
import core.engine.backtester as BT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class BacktestResult:
    """Wraps raw backtester output in a clean object."""
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
        return self._stats

    def equity_curve(self) -> pd.Series:
        return self._equity

    def trade_list(self) -> list[dict]:
        return list(self._trades)

    def export_csv(self, path: str):
        df_eq = self._equity.to_frame(name="equity").reset_index().rename(columns={'index': 'date'})
        df_tr = pd.DataFrame(self._trades)
        df_eq.to_csv(f"{path}_equity.csv", index=False)
        df_tr.to_csv(f"{path}_trades.csv",  index=False)
        logging.info(f"Exported equity → {path}_equity.csv and trades → {path}_trades.csv")

class BacktestEngine:
    """
    Takes a StrategyConfig, runs the backtester, applies filters, 
    and packages results as a BacktestResult.
    """

    def __init__(
        self,
        config: StrategyConfig,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        trade_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.config            = config
        self.progress_callback = progress_callback
        self.trade_callback    = trade_callback
        self._result: Optional[BacktestResult] = None

    @staticmethod
    def estimate_steps(cfg: StrategyConfig) -> int:
        start = pd.to_datetime(cfg.start)
        end   = pd.to_datetime(cfg.end)
        return max(1, (end - start).days)
    
    def run(
        self,
        chunk_size=50,
        price_data: Optional[pd.Series] = None,
        vol_data: Optional[pd.Series] = None,
        benchmark_data: Optional[pd.Series] = None,
        spy_prices: Optional[pd.Series] = None
    ):
        cfg_dict = self.config.to_dict()
        logging.info("Starting Backtester.run()")
        
        raw = BT.Backtester.run(cfg_dict, price_data=price_data, vol_data=vol_data, spy_prices=spy_prices)

        all_trades = raw["trades"]
        fcfg = self.config.filters
        if isinstance(fcfg, dict):
            fcfg = FilterConfig(**fcfg)

        allowed = []
        for trade in all_trades:
            entry_dt = trade["open"]
            expiry = trade.get("expiry", entry_dt)
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
            trades=[],
            stats=raw["stats"],
            config=raw["config"],
            benchmark=benchmark,
        )

        buffer = []
        for idx, trade in enumerate(allowed, start=1):
            buffer.append(trade)

            if len(buffer) >= chunk_size:
                if self.trade_callback:
                    try:
                        self.trade_callback(list(buffer))
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
                self.trade_callback(list(buffer))
            except Exception:
                logging.exception("Error in trade_callback (final flush)")

        self._result._trades = allowed
        logging.info("BacktestEngine run complete.")

    def result(self) -> BacktestResult:
        if self._result is None:
            raise RuntimeError("BacktestEngine.run() must be called before result()")
        return self._result