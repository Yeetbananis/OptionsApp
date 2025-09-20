# File: core/engine/worker_tasks.py

import logging
import multiprocessing as mp
from app.config import StrategyConfig
from core.engine.backtestengine import BacktestEngine

logger = logging.getLogger(__name__)

# --- Global variables for worker processes (unchanged) ---
_worker_price_data = None
_worker_vol_data = None
_worker_benchmark_data = None
_worker_spy_prices = None
_worker_base_cfg = None

def init_worker(price_data, vol_data, benchmark_data, spy_prices, base_cfg):
    """Initializer function (unchanged)."""
    global _worker_price_data, _worker_vol_data, _worker_benchmark_data
    global _worker_spy_prices, _worker_base_cfg
    
    _worker_price_data = price_data
    _worker_vol_data = vol_data
    _worker_benchmark_data = benchmark_data
    _worker_spy_prices = spy_prices
    _worker_base_cfg = base_cfg
    logger.info(f"Worker process {mp.current_process().pid} initialized with data.")

# --- MODIFICATION START ---
# The worker now accepts an index along with the parameters.
def run_single_backtest(index, overrides):
    """
    The core task for the worker. It performs the backtest and returns the
    original index along with the results.
    """
    try:
        cfg = _worker_base_cfg.with_overrides(**overrides)
        engine = BacktestEngine(cfg)
        
        engine.run(
            price_data=_worker_price_data,
            vol_data=_worker_vol_data,
            benchmark_data=_worker_benchmark_data,
            spy_prices=_worker_spy_prices
        )
        res = engine.result()
        stats = res.summary()
        # It now returns a tuple with the index as the first element.
        return (index, overrides, stats, res.trade_list())
    except Exception as e:
        logger.error(f"Backtest failed for parameters {overrides}: {e}", exc_info=False)
        # On failure, it still returns the index so the main process can track completion.
        return (index, overrides, None, None)
# --- MODIFICATION END ---