import itertools
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import pandas as pd
import numpy as np
import os
import tempfile
import psutil
import gc
import math
import time
import pickle
from typing import Iterable, Tuple, Dict, Any

from core.engine.backtestengine import BacktestEngine
from app.config import StrategyConfig
from core.models.metrics import summary as perf_summary

logger = logging.getLogger(__name__)

# -------------------------
# Worker-side globals (loaded once per worker by initializer)
# -------------------------
_worker_price = None
_worker_vol = None
_worker_benchmark = None
_worker_spy = None
_worker_base_cfg = None


def _worker_initializer(price_path, vol_path, bench_path, spy_path, base_cfg_bytes):
    """
    Runs once per process at pool-start. Loads memory-mapped arrays (numpy.memmap)
    and unpickles the base config to _worker_base_cfg. Keeps one copy per process.
    This avoids sending big pandas objects via pickling per-task.
    """
    global _worker_price, _worker_vol, _worker_benchmark, _worker_spy, _worker_base_cfg

    # Load numpy memmaps if provided
    try:
        _worker_price = np.load(price_path, allow_pickle=True) if price_path else None
    except Exception as e:
        logger.exception("Failed loading price memmap in worker: %s", e)
        _worker_price = None

    try:
        _worker_vol = np.load(vol_path, allow_pickle=True) if vol_path else None
    except Exception:
        _worker_vol = None

    try:
        _worker_benchmark = np.load(bench_path, allow_pickle=True) if bench_path else None
    except Exception:
        _worker_benchmark = None

    try:
        _worker_spy = np.load(spy_path, allow_pickle=True) if spy_path else None
    except Exception:
        _worker_spy = None

    try:
        _worker_base_cfg = pickle.loads(base_cfg_bytes)
    except Exception as e:
        logger.exception("Failed to unpickle base config in worker: %s", e)
        _worker_base_cfg = None

    # reduce memory pressure immediately after loading
    gc.collect()


def _run_single_core_light(overrides: dict) -> Tuple[dict, dict, float]:
    """
    Worker function that expects global data to be loaded in worker initializer.
    Only receives 'overrides' (lightweight) to avoid pickling big data each time.
    Returns (overrides, stats, return_pct)
    """
    global _worker_price, _worker_vol, _worker_benchmark, _worker_spy, _worker_base_cfg
    try:
        # Convert base cfg into a worker-local config with overrides
        # NOTE: with_overrides must be cheap (should not re-load big data)
        cfg = _worker_base_cfg.with_overrides(**overrides)

        # Build engine and run. Pass in the worker-local data; BacktestEngine must accept numpy or None.
        engine = BacktestEngine(cfg)
        engine.run(
            price_data=_worker_price if _worker_price is not None else None,
            vol_data=_worker_vol if _worker_vol is not None else None,
            benchmark_data=_worker_benchmark if _worker_benchmark is not None else None,
            spy_prices=_worker_spy if _worker_spy is not None else None
        )
        res = engine.result()
        rf_rate = cfg.risk_free_rate
        strat_type = cfg.strategy_type

        equity = res.equity_curve()
        trades = res.trade_list()
        stats = perf_summary(equity, trades, rf=rf_rate, strat_type=strat_type) if trades else {}
        return_pct = stats.get("total_return_pct", float("-inf"))

        # Prefer explicit deletion of heavy refs before returning
        del engine, res, equity, trades
        gc.collect()
        return (overrides, stats, return_pct)

    except MemoryError:
        logger.error("MemoryError in worker for overrides %s", overrides)
        gc.collect()
        return (overrides, {}, float("-inf"))
    except Exception as e:
        logger.exception("Worker failed for overrides %s: %s", overrides, e)
        return (overrides, {}, float("-inf"))



# -------------------------
# Utility functions to prepare data for worker initializer
# -------------------------
def _save_to_temp_np(obj, suffix="npz"):
    """Save picklable object to temporary .npy/.npz and return the path (string)."""
    if obj is None:
        return None
    fd, path = tempfile.mkstemp(suffix=f".{suffix}")
    os.close(fd)
    try:
        # Use numpy.save for arrays or pickled objects
        # We allow pickled objects to preserve pandas objects if needed, but we aim for smaller numpy structures.
        np.save(path, obj, allow_pickle=True)
        return path
    except Exception:
        # fallback: use pickle file
        ppath = path + ".pkl"
        with open(ppath, "wb") as f:
            pickle.dump(obj, f, protocol=pickle.HIGHEST_PROTOCOL)
        return ppath


def _iter_chunks(iterable: Iterable, chunk_size: int):
    """Yield lists of length up to chunk_size from iterable (generator-safe)."""
    it = iter(iterable)
    while True:
        chunk = list(itertools.islice(it, chunk_size))
        if not chunk:
            break
        yield chunk


class BatchRunner:
    """
    Faster and more robust BatchRunner:
      - converts large inputs to temp files and loads them once per worker (initializer)
      - uses a persistent ProcessPoolExecutor with executor.map (lower overhead)
      - streams combinations via chunks to avoid materializing the whole grid
      - adaptive but conservative worker selection to avoid OOM
    """
    def __init__(self, base_cfg: StrategyConfig, sweep_params: dict,
                 price_data=None, vol_data=None, benchmark_data=None, spy_prices=None,
                 progress_callback=None, trade_callback=None):
        if not isinstance(base_cfg, StrategyConfig):
            raise ValueError("base_cfg must be StrategyConfig")
        if not isinstance(sweep_params, dict) or not all(isinstance(k, str) and isinstance(v, list) for k, v in sweep_params.items()):
            raise ValueError("sweep_params must be dict[str, list]")

        self.base_cfg = base_cfg
        self.sweep_params = sweep_params
        self.price_data = price_data
        self.vol_data = vol_data
        self.benchmark_data = benchmark_data
        self.spy_prices = spy_prices
        self.progress_callback = progress_callback
        self.trade_callback = trade_callback

        self._results = pd.DataFrame()
        self._best_run_trades = []
        self._cancel_event = mp.Event()
        self._pause = mp.Event()
        self._pause.set()

    def cancel(self):
        self._cancel_event.set()
        self._pause.set()

    def pause(self):
        self._pause.clear()

    def resume(self):
        self._pause.set()

    def _estimate_worker_count(self, data_mem_estimate):
        """
        Conservative worker count: leave 1 CPU and ensure per-worker memory fits.
        """
        avail_mem = psutil.virtual_memory().available
        cpu_avail = max(1, mp.cpu_count() - 1)
        # Reserve some headroom (15% of available memory)
        usable_mem = max(int(avail_mem * 0.80), 200 * 1024 * 1024)

        per_worker_mem = max(int(data_mem_estimate * 1.5), 450 * 1024 * 1024)  # Increased base overhead for library imports (e.g., scipy)
        max_workers_by_mem = max(1, usable_mem // per_worker_mem)
        n_workers = min(cpu_avail, max_workers_by_mem)
        return max(1, n_workers)

    def run(self):
        # Create combination generator (do NOT materialize entire list for large grids)
        keys = list(self.sweep_params.keys())
        lists = [self.sweep_params[k] for k in keys]
        combos_iter = (dict(zip(keys, combo)) for combo in itertools.product(*lists))
        total = 1
        for l in lists:
            total *= len(l)
        if total == 0:
            logger.info("No combinations to run.")
            return

        if total > 200000:
            logger.warning("Very large grid: %d combos", total)

        # Estimate memory footprint of data (rough)
        data_mem = 0
        for d in [self.price_data, self.vol_data, self.benchmark_data, self.spy_prices]:
            if d is None:
                continue
            # prefer using numpy if possible; if pandas, estimate memory_usage
            if isinstance(d, (pd.Series, pd.DataFrame)):
                try:
                    data_mem += int(d.memory_usage(deep=True).sum())
                except Exception:
                    try:
                        data_mem += d.values.nbytes
                    except Exception:
                        data_mem += 50 * 1024 * 1024
            elif isinstance(d, np.ndarray):
                data_mem += d.nbytes
            else:
                data_mem += 50 * 1024 * 1024

        # Serialize large objects once to temp files for worker initializer
        price_path = _save_to_temp_np(self.price_data)
        vol_path = _save_to_temp_np(self.vol_data)
        bench_path = _save_to_temp_np(self.benchmark_data)
        spy_path = _save_to_temp_np(self.spy_prices)

        # Serialize base config into bytes to pass cheaply to initializer
        base_cfg_bytes = pickle.dumps(self.base_cfg, protocol=pickle.HIGHEST_PROTOCOL)

        # Determine safe worker count
        n_workers = self._estimate_worker_count(data_mem)
        logger.info("BatchRunner2 starting with %d workers; estimated data size %.2f MB; total combos %d",
                    n_workers, data_mem / 1024 / 1024.0, total)

        # chunk size heuristics: larger chunks reduce IPC but increase per-chunk memory spikes
        chunksize = max(4, min(512, math.ceil(total / (n_workers * 4))))


        rows = []
        completed = 0
        best_return = float("-inf")
        best_overrides = None

        # We'll use a persistent pool with initializer that loads the data once per process.
        with ProcessPoolExecutor(max_workers=n_workers,
                                 initializer=_worker_initializer,
                                 initargs=(price_path, vol_path, bench_path, spy_path, base_cfg_bytes)) as exe:
            # executor.map is slightly faster than submit/await per-task overhead for many small tasks
            # We'll stream combos in chunks to avoid huge task queue memory
            # Build a generator of overrides; we'll map _run_single_core_light over it
            def combo_chunks():
                it = itertools.product(*lists)
                # yield chunk lists of overrides
                while True:
                    chunk = list(itertools.islice(it, chunksize))
                    if not chunk:
                        break
                    yield [dict(zip(keys, c)) for c in chunk]

            # Use map over flattened generator to ensure tasks are submitted in small batches.
            try:
                for chunk in combo_chunks():
                    if self._cancel_event.is_set():
                        break
                    # For each chunk, map the worker function with executor.map (returns iterator)
                    futures_iter = exe.map(_run_single_core_light, chunk, chunksize=1)
                    for result in futures_iter:
                        if self._cancel_event.is_set():
                            break
                        self._pause.wait()
                        overrides, stats, return_pct = result
                        row = {**overrides, **stats}
                        rows.append(row)

                        if pd.notna(return_pct) and return_pct > best_return:
                            best_return = return_pct
                            best_overrides = overrides

                        completed += 1
                        if self.progress_callback:
                            try:
                                self.progress_callback(completed, total, overrides)
                            except Exception:
                                pass

                    # light cleanup each chunk
                    gc.collect()
            except Exception as e:
                logger.exception("Batch run failed: %s", e)
            finally:
                # best-effort cleanup of temp files
                for p in (price_path, vol_path, bench_path, spy_path):
                    try:
                        if p and os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass

        # Final results DataFrame
        self._results = pd.DataFrame(rows)

        # Capture full best run (equity + trades) immediately, no recomputation in UI
        self._best_run_equity = None
        if best_overrides is not None:
            try:
                cfg = self.base_cfg.with_overrides(**best_overrides)
                engine = BacktestEngine(cfg)
                engine.run(price_data=self.price_data,
                           vol_data=self.vol_data,
                           benchmark_data=self.benchmark_data,
                           spy_prices=self.spy_prices)
                result = engine.result()
                self._best_run_trades = result.trade_list()
                self._best_run_equity = result.equity_curve()
            except Exception:
                logger.exception("Failed to capture best configuration results in main process")
                self._best_run_trades, self._best_run_equity = [], None


        if self.trade_callback and self._best_run_trades:
            try:
                self.trade_callback(self._best_run_trades)
            except Exception:
                logger.exception("trade_callback failed")

    def results_df(self) -> pd.DataFrame:
        return self._results

    def all_trades(self) -> list:
        return self._best_run_trades

    def best_run_trades(self) -> list:
        return self._best_run_trades

    def best_run_equity(self) -> pd.Series | None:
        return self._best_run_equity
