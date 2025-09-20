from __future__ import annotations
import math
import logging
import datetime as _dt
import numpy as np
import pandas as pd
from typing import Optional
from numba import njit

from core.models.position import Position, Leg
from core.storage.data_loader import get_prices
from core.models.metrics import summary as perf_summary

logger = logging.getLogger(__name__)

# Constants
DAYS_PER_YEAR = 365.25
TRADING_DAYS_PER_YEAR = 252

def realized_vol(prices: pd.Series, window: int = 21) -> pd.Series:
    logret = np.log(prices / prices.shift(1))
    return logret.rolling(window, min_periods=window//2).std() * np.sqrt(TRADING_DAYS_PER_YEAR)

@njit(fastmath=True, cache=True)
def _black_scholes(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    if sigma < 1e-8 or T < 1e-8:
        if option_type == 'P': return max(0.0, K * math.exp(-r * T) - S)
        return max(0.0, S - K * math.exp(-r * T))
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nd = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
    if option_type == 'P': price = K * math.exp(-r * T) * nd(-d2) - S * nd(-d1)
    elif option_type == 'C': price = S * nd(d1) - K * math.exp(-r * T) * nd(d2)
    else: price = 0.0
    return max(0.0, price)

def select_short_put_strike(S: float, short_pct: float) -> float:
    return round(S * (1 - short_pct), 2)

def select_put_spread_strikes(S: float, short_pct: float, width_pct: float) -> tuple[float, float]:
    short_k = select_short_put_strike(S, short_pct)
    long_k = round(short_k - (S * width_pct), 2)
    return short_k, min(long_k, short_k - 0.01)

class Backtester:
    DEFAULT_RISK_FREE_RATE = 0.03
    DEFAULT_SPREAD_PCT = 0.05
    DEFAULT_SLIPPAGE_PER_CONTRACT = 0.01
    DEFAULT_VOL_PREMIUM = 1.15

    @classmethod
    def run(
        cls, 
        cfg: dict, 
        price_data: Optional[pd.Series] = None,
        vol_data: Optional[pd.Series] = None,
        spy_prices: Optional[pd.Series] = None
    ) -> dict:
        logger.info(f"Starting backtest with config: {cfg}")
        sym = cfg["underlying"].upper()
        start = pd.to_datetime(cfg["start"])
        end = pd.to_datetime(cfg["end"])
        capital = float(cfg["capital"])
        alloc_pct = float(cfg["allocation_pct"]) / 100.0
        pt_pct    = float(cfg["profit_target_pct"]) / 100.0
        sl_mult   = float(cfg["stop_loss_mult"])
        dte_target= int(cfg["dte_target"])
        commission= float(cfg["commission_per_contract"])
        rf        = float(cfg.get("risk_free_rate", cls.DEFAULT_RISK_FREE_RATE))
        strat_type= cfg["strategy_type"]
        strat_params = cfg.get("strategy_params", {})
        strat_params["strategy_type"] = strat_type
        if strat_type == "custom_manual":
            strat_params["custom_legs"] = cfg["custom_legs"]
        
        if price_data is None or vol_data is None:
            prices = cls._load_prices(sym, start, end)
            rolling_vol = realized_vol(prices).ffill().bfill().clip(lower=0.05)
        else:
            prices = price_data.loc[start:end].copy()
            rolling_vol = vol_data.loc[start:end].copy()
            if prices.empty or rolling_vol.empty:
                raise ValueError("Preloaded data is empty for the specified backtest range.")

        eq_series, trades = cls._simulate(
            prices, rolling_vol, capital, alloc_pct,
            pt_pct, sl_mult, dte_target,
            commission, rf, strat_params
        )
        
        # <<< FIX: Pass the strategy_type to perf_summary so the risk warning works correctly. >>>
        stats = perf_summary(eq_series, trades, rf=rf, strat_type=cfg["strategy_type"]) if not eq_series.empty else {}
        
        benchmark = pd.Series(dtype=float)
        if cfg.get("use_benchmark", True):
            try:
                ticker = cfg.get("benchmark_ticker", "SPY")
                bench_prices = spy_prices if ticker == "SPY" else cls._load_prices(ticker, start, end)
                if not bench_prices.empty:
                    bench_prices = bench_prices.loc[start:end]
                    benchmark = eq_series.iloc[0] * (bench_prices / bench_prices.iloc[0])
            except Exception as e:
                logger.warning(f"Benchmark computation failed: {e}")

        return {
            "equity": eq_series, "trades": trades,
            "stats": stats, "config": cfg, "benchmark": benchmark
        }

    @staticmethod
    def _load_prices(sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        try:
            ps = get_prices(sym, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if ps.empty: raise ValueError("Empty price series")
            ps = ps.squeeze()
            ps = ps.loc[start:end].copy()
            ps = ps[~ps.index.duplicated(keep='first')]
            return ps
        except Exception as e:
            logger.error(f"Price load failed for {sym}: {e}")
            raise

    @classmethod
    def _simulate(
        cls, prices: pd.Series, vols: pd.Series,
        init_cap, alloc_pct, pt_pct, sl_mult, dte_target,
        commission, rf, strat_params
    ) -> tuple[pd.Series, list[dict]]:
        
        dates = prices.index
        prices_np = prices.to_numpy()
        vols_np = vols.to_numpy()
        equity = [init_cap]
        trades = []
        positions: list[Position] = []
        
        for i in range(len(dates)):
            today = dates[i]
            cap = equity[-1]
            S = prices_np[i]
            sigma = vols_np[i] * cls.DEFAULT_VOL_PREMIUM

            if positions:
                to_close = []
                for pos in positions:
                    pos.update_and_maybe_close(S, today.date(), rf, sigma)
                    if pos.closed:
                        num_contracts = sum(l.qty for l in pos.legs)
                        commission_cost = commission * num_contracts
                        slippage_cost = cls.DEFAULT_SLIPPAGE_PER_CONTRACT * num_contracts
                        pnl = pos.pnl - commission_cost - slippage_cost
                        pos.pnl = pnl
                        trades.append(pos.dict_summary())
                        cap += pnl
                        to_close.append(pos)
                if to_close:
                    positions = [p for p in positions if not p.closed]

            equity.append(cap)
            
            expiry = cls._find_expiry(dates, today, dte_target)
            legs, credit = cls._build_legs(S, sigma, rf, strat_params, dte_target)
            
            if credit <= 0: continue

            size = cls._size_position(cap, alloc_pct, legs)
            if size > 0:
                for leg in legs: leg.qty = size
                pos = Position(
                    open_date=today.date(), expiry_date=expiry, legs=legs,
                    profit_target_pct=pt_pct, stop_loss_mult=sl_mult,
                    entry_S=S, entry_sigma=sigma, entry_r=rf
                )
                positions.append(pos)

        eq_idx = [dates[0] - pd.Timedelta(days=1)] + list(dates) if dates.size > 0 else []
        eq_vals= [init_cap] + equity[1:]
        return pd.Series(eq_vals, index=eq_idx, name="Equity").reindex(prices.index, method='ffill'), trades

    @staticmethod
    def _find_expiry(dates: pd.DatetimeIndex, today: pd.Timestamp, dte: int) -> _dt.date:
        approx = today + pd.Timedelta(days=dte)
        pos = dates.searchsorted(approx, side='left')
        if pos < len(dates): return dates[pos].date()
        return dates[-1].date()

    @classmethod
    def _build_legs(
        cls, S: float, sigma: float, r: float, params: dict, dte: int
    ) -> tuple[list[Leg], float]:
        ty = params.get("strategy_type")
        T = max(1e-6, dte / DAYS_PER_YEAR)
        legs: list[Leg] = []
        credit = 0.0
        spread = cls.DEFAULT_SPREAD_PCT / 2.0

        if ty == "custom_manual":
            for ld in params["custom_legs"]:
                prem = _black_scholes(S, ld["strike"], T, r, sigma, ld["type"])
                if ld["dir"] == -1: prem *= (1.0 - spread)
                else: prem *= (1.0 + spread)
                credit -= ld["dir"] * prem
                legs.append(Leg(strike=ld["strike"], option_type=ld["type"], direction=ld["dir"], qty=ld["qty"], entry_price=prem))
        else:
            short_pct = params.get("short_put_pct_otm", 0.07)
            K1, K2 = (select_short_put_strike(S, short_pct), None)
            if ty == "put_spread":
                K1, K2 = select_put_spread_strikes(S, short_pct, params.get("spread_width_pct", 0.05))
            
            p1 = _black_scholes(S, K1, T, r, sigma, 'P') * (1.0 - spread)
            legs.append(Leg(strike=K1, option_type='P', direction=-1, qty=1, entry_price=p1))
            credit += p1
            if K2:
                p2 = _black_scholes(S, K2, T, r, sigma, 'P') * (1.0 + spread)
                legs.append(Leg(strike=K2, option_type='P', direction=+1, qty=1, entry_price=p2))
                credit -= p2

        return legs, credit

    @staticmethod
    def _size_position(cap: float, alloc_pct: float, legs: list[Leg]) -> int:
        target = cap * alloc_pct
        if not legs: return 0
        short_put_strikes = [l.strike for l in legs if l.direction == -1 and l.option_type == 'P']
        risk_est = (max(short_put_strikes) * 100) if short_put_strikes else 1000
        if risk_est <= 0: return 0
        return max(1, int(target / risk_est))