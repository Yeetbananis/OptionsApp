# backtester.py
# Robust, event-driven options backtester supporting customizable strategies.

from __future__ import annotations
import math
import logging
import datetime as _dt
import numpy as np
import pandas as pd
from typing import Optional

from position import Position, Leg
from data_loader import get_prices
from metrics import summary as perf_summary, get_benchmark_equity
from filters import FilterConfig

logger = logging.getLogger(__name__)

# Constants
DAYS_PER_YEAR = 365.25
TRADING_DAYS_PER_YEAR = 252


def realized_vol(prices: pd.Series, window: int = 21) -> pd.Series:
    """Annualized rolling realized vol from underlying returns."""
    logret = np.log(prices / prices.shift(1))
    return logret.rolling(window, min_periods=window//2).std() * np.sqrt(TRADING_DAYS_PER_YEAR)


def skewed_vol(S: float, K: float, base_vol: float, skew_factor: float = 0.4) -> float:
    """Simple moneyness-based skew."""
    moneyness = (K - S) / S
    return base_vol * (1 + skew_factor * moneyness)


def _black_scholes(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
    """Black-Scholes price for European option."""
    if sigma < 1e-8 or T < 1e-8:
        if option_type == 'P':
            return max(0.0, K * math.exp(-r * T) - S)
        return max(0.0, S - K * math.exp(-r * T))

    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    nd = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))

    if option_type == 'P':
        price = K * math.exp(-r * T) * nd(-d2) - S * nd(-d1)
    elif option_type == 'C':
        price = S * nd(d1) - K * math.exp(-r * T) * nd(d2)
    else:
        raise ValueError("option_type must be 'P' or 'C'")

    return max(0.0, price)


def select_short_put_strike(S: float, short_pct: float) -> float:
    return round(S * (1 - short_pct), 2)


def select_put_spread_strikes(S: float, short_pct: float, width_pct: float) -> tuple[float, float]:
    short_k = select_short_put_strike(S, short_pct)
    long_k = round(short_k - (S * width_pct), 2)
    return short_k, min(long_k, short_k - 0.01)


class Backtester:
    DEFAULT_RISK_FREE_RATE = 0.03

    @classmethod
    def run(cls, cfg: dict, price_data: Optional[pd.Series] = None) -> dict:
        logger.info(f"Starting backtest with config: {cfg}")
        # Unpack
        sym = cfg["underlying"].upper()
        start = pd.to_datetime(cfg["start"])
        end   = pd.to_datetime(cfg["end"])
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

        # Use preloaded prices if provided, otherwise load
        if price_data is not None and isinstance(price_data, pd.Series):
            prices = price_data
            # Ensure prices cover the required range, otherwise raise an error or log a warning
            if prices.index.min() > start or prices.index.max() < end:
                 logger.warning("Preloaded price data does not cover the full backtest period.")
                 # Optionally fall back to loading full data if partial is insufficient
                 prices = cls._load_prices(sym, start, end)
            else:
                 # Slice the preloaded data to the exact range required by this backtest
                 prices = prices.loc[start:end].copy()
                 if prices.empty:
                      raise ValueError("Preloaded price data is empty for the specified range.")

        else:
            prices = cls._load_prices(sym, start, end)

        rolling_vol = realized_vol(prices).ffill().bfill().clip(lower=0.05)

        eq_series, trades = cls._simulate(
            prices, rolling_vol, capital, alloc_pct,
            pt_pct, sl_mult, dte_target,
            commission, rf, strat_params
        )

        stats = perf_summary(eq_series, trades, rf=rf) if trades else {}

        # Skip benchmark if disabled
        benchmark = {}
        if cfg.get("use_benchmark", True):
            try:
                benchmark = get_benchmark_equity(
                    start_date=cfg["start"],
                    end_date=cfg["end"],
                    initial_value=eq_series.iloc[0],
                    ticker=cfg.get("benchmark_ticker", "SPY")
                )
            except Exception as e:
                logger.warning(f"Benchmark load failed: {e}")
                benchmark = pd.Series(dtype=float)

        return {
            "equity":    eq_series,
            "trades":    trades,
            "stats":     stats,
            "config":    cfg,
            "benchmark": benchmark
        }

    @staticmethod
    def _load_prices(sym: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
        try:
            ps = get_prices(sym, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if ps.empty:
                raise ValueError("Empty price series")

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
        prices = prices[~prices.index.duplicated(keep='first')]
        vols = vols[~vols.index.duplicated(keep='first')]
        dates = prices.index

        equity = [init_cap]
        trades = []
        positions: list[Position] = []

        # ─── daily entries: every trading date ───────────────────────
        valid_entries = dates
        # ───────────────────────────────────────────────────────────────

        for i, today in enumerate(dates):
            cap = equity[-1]
            val = prices.loc[today]
            S = float(val.iloc[0] if isinstance(val, pd.Series) else val)

            val_sigma = vols.loc[today]
            sigma = float(val_sigma.iloc[0] if isinstance(val_sigma, pd.Series) else val_sigma)


            # Update exits
            to_close = []
            for pos in positions:
                pos.update_and_maybe_close(S, today.date(), rf, sigma)
                if pos.closed:
                    pnl = pos.pnl - commission * sum(l.qty for l in pos.legs)
                    pos.pnl = pnl
                    trades.append(pos.dict_summary())
                    cap += pnl
                    to_close.append(pos)
            for pos in to_close:
                positions.remove(pos)
            equity.append(cap)

            # Reset weekly flag
            if i > 0:
                prev_week = dates[i-1].to_period('W')
                if today.to_period('W') != prev_week:
                    active_week = False

            # Entry logic: every valid day
            if today in valid_entries:
                expiry = cls._find_expiry(dates, today, dte_target)

                # build our legs and compute gross credit
                legs, credit = cls._build_legs(S, sigma, rf, strat_params, dte_target, commission)
                # subtract entry commissions for ALL legs
                total_comm = commission * sum(l.qty for l in legs)
                net_credit = credit - total_comm
                logger.debug(f"{today.date()}: gross={credit:.4f}, comm={total_comm:.4f}, net={net_credit:.4f}")

                # skip only if net credit is *really* negative
                if net_credit < -1e-6:
                    continue

                # otherwise size and open the position:
                size = cls._size_position(cap, alloc_pct, net_credit, legs, strat_params)
                for leg in legs:
                    leg.qty = size
                pos = Position(
                    open_date=today.date(),
                    expiry_date=expiry,
                    legs=legs,
                    profit_target_pct=pt_pct,
                    stop_loss_mult=sl_mult,
                    entry_S=S,
                    entry_sigma=sigma,
                    entry_r=rf
                )
                positions.append(pos)
                active_week = True


        # Build equity series
        eq_idx = [dates[0] - pd.Timedelta(days=1)] + list(dates)
        eq_vals= [init_cap] + equity[1:]
        eq = pd.Series(eq_vals, index=eq_idx, name="Equity").reindex(dates, method='ffill')
        return eq, trades

    @staticmethod
    def _find_expiry(dates: pd.DatetimeIndex, today: pd.Timestamp, dte: int) -> _dt.date:
        approx = today + pd.Timedelta(days=dte)
        pos = dates.get_indexer([approx], method='bfill')[0]
        return dates[pos].date() if pos >= 0 else today.date()

    @staticmethod
    def _build_legs(
        S: float, sigma: float, r: float, params: dict,
        dte: int, commission: float
    ) -> tuple[list[Leg], float]:
        ty = params.get("strategy_type")
        T = max(1e-6, dte / DAYS_PER_YEAR)
        legs: list[Leg] = []
        credit = 0.0

        if ty == "custom_manual":
            for ld in params["custom_legs"]:
                prem = _black_scholes(S, ld["strike"], T, r, sigma, ld["type"])
                credit -= ld["dir"] * prem
                legs.append(Leg(
                    strike=ld["strike"], option_type=ld["type"],
                    direction=ld["dir"], qty=ld["qty"], entry_price=prem
                ))

        else:
            short_pct = params.get("short_put_pct_otm", 0.07)
            if ty == "put_spread":
                K1, K2 = select_put_spread_strikes(S, short_pct, params.get("spread_width_pct",0.05))
            else:
                K1, K2 = (select_short_put_strike(S, short_pct), None)

            # sell short put
            p1 = _black_scholes(S, K1, T, r, sigma, 'P')
            legs.append(Leg(strike=K1, option_type='P', direction=-1, qty=1, entry_price=p1))
            credit += p1

            # buy long put (if spread)
            if K2:
                p2 = _black_scholes(S, K2, T, r, sigma, 'P')
                legs.append(Leg(strike=K2, option_type='P', direction=+1, qty=1, entry_price=p2))
                credit -= p2

        # **no** immediate commission subtraction here
        return legs, credit

    @staticmethod
    def _size_position(cap: float, alloc_pct: float, credit: float, legs: list[Leg], params: dict) -> int:
        target = cap * alloc_pct
        if any(l.direction == -1 for l in legs if l.option_type == 'P'):
            K_short = max(l.strike for l in legs if l.direction == -1)
            risk_est = K_short * 100
        else:
            risk_est = 1000
        max_by_risk = int(target / risk_est)
        max_by_credit = int(target / (abs(credit) * 100 + 1e-9))
        return max(1, min(max_by_risk, max_by_credit))
