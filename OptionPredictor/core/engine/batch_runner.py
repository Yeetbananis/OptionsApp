import itertools
import threading
import pandas as pd
from core.engine.backtestengine import BacktestEngine
from app.config import StrategyConfig

class BatchRunner:
    """
    Runs a grid-search over sweep_params, reporting progress and live trades
    via callbacks, with support for cancellation, pause and resume.
    Tracks the best run's trades for separate display.
    """
    def __init__(
        self,
        base_cfg: StrategyConfig,
        sweep_params: dict,
        price_data=None,
        vol_data=None,
        benchmark_data=None,
        progress_callback=None,
        trade_callback=None,
    ):
        self.base_cfg       = base_cfg
        self.sweep_params   = sweep_params
        self.price_data     = price_data
        self.vol_data       = vol_data
        self.benchmark_data = benchmark_data
        self.progress_callback = progress_callback
        self.trade_callback    = trade_callback

        self._results = pd.DataFrame()
        self._all_trades = []
        self._best_run_trades = []
        self._best_return_pct = float("-inf")

        self._cancelled   = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # start in "running" state
        self.is_paused     = False

    def cancel(self):
        self._cancelled = True
        self._pause_event.set()

    def pause(self):
        self.is_paused = True
        self._pause_event.clear()

    def resume(self):
        self.is_paused = False
        self._pause_event.set()

    def best_run_trades(self) -> list:
        """Returns trade list of the best-performing run."""
        return self._best_run_trades

    def run(self):
        keys, lists = zip(*self.sweep_params.items())
        total = 1
        for lst in lists:
            total *= len(lst)

        rows = []
        for idx, combo in enumerate(itertools.product(*lists), start=1):
            self._pause_event.wait()
            if self._cancelled:
                break

            overrides = dict(zip(keys, combo))
            cfg = self.base_cfg.with_overrides(**overrides)

            # inject shared price & benchmark data here
            engine = BacktestEngine(cfg)
            engine.run(
                price_data=self.price_data,
                benchmark_data=self.benchmark_data
            )
            res = engine.result()

            trades = res.trade_list()
            for trade in trades:
                self._pause_event.wait()
                if self._cancelled:
                    break
                if self.trade_callback:
                    self.trade_callback(trade)
                self._all_trades.append(trade)

            summary = res.summary()
            rows.append({**overrides, **summary})

            return_pct = summary.get("total_return_pct", float("-inf"))
            if pd.notna(return_pct) and return_pct > self._best_return_pct:
                self._best_return_pct = return_pct
                self._best_run_trades = trades

            if self.progress_callback:
                self.progress_callback(idx, total, overrides)

        self._results = pd.DataFrame(rows)

    def results_df(self) -> pd.DataFrame:
        return self._results

    def all_trades(self) -> list:
        return self._all_trades
