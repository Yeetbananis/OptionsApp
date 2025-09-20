"""
utils/metrics.py
───────────────────────────────────────────────────────────────────────────
Corrected and robust functions for calculating financial performance metrics,
including a focused set of advanced risk metrics.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import logging
import yfinance as yf

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - METRICS - %(message)s')

# Constants
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_DEFAULT = 0.03

def _validate_series(series: pd.Series) -> pd.Series | None:
    """Basic validation for equity series."""
    if not isinstance(series, pd.Series) or series.empty or len(series) < 2 or series.isnull().all():
        return None
    if not pd.api.types.is_numeric_dtype(series.dtype):
        series = pd.to_numeric(series, errors='coerce')
    return series.dropna()

def summary(
    equity: pd.Series,
    trades: list[dict] | pd.DataFrame,
    rf: float = RISK_FREE_RATE_DEFAULT,
    strat_type: str = ""
) -> dict:
    """
    Generates a consolidated, corrected dictionary of performance metrics.
    """
    logging.info("Calculating performance summary...")
    eq_series = _validate_series(equity)
    metrics = {}

    # --- Equity-Based Metrics ---
    if eq_series is not None and len(eq_series) >= 2:
        metrics['start_value'] = eq_series.iloc[0]
        metrics['end_value'] = eq_series.iloc[-1]
        metrics['total_return'] = metrics['end_value'] - metrics['start_value']
        metrics['total_return_pct'] = (metrics['end_value'] / metrics['start_value'] - 1) * 100 if metrics['start_value'] != 0 else 0.0

        duration_days = (eq_series.index[-1] - eq_series.index[0]).days
        duration_years = max(1.0, duration_days) / 365.25
        metrics['cagr'] = ((metrics['end_value'] / metrics['start_value']) ** (1 / duration_years) - 1) * 100 if metrics['start_value'] != 0 else 0.0

        daily_rets = eq_series.pct_change().dropna()
        if len(daily_rets) > 1:
            annualized_std = daily_rets.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
            cagr_decimal = metrics['cagr'] / 100
            metrics['sharpe'] = (cagr_decimal - rf) / annualized_std if annualized_std > 0 else np.nan
            downside_rets = daily_rets[daily_rets < 0]
            downside_std = downside_rets.std() * np.sqrt(TRADING_DAYS_PER_YEAR)
            metrics['sortino'] = (cagr_decimal - rf) / downside_std if downside_std > 0 else np.inf

        cumulative_max = eq_series.cummax()
        drawdown = eq_series - cumulative_max
        metrics['max_drawdown'] = drawdown.min()
        
        # Calculate Ulcer Index
        drawdown_pct = (drawdown / cumulative_max).dropna()
        metrics['ulcer_index'] = np.sqrt(np.sum(drawdown_pct**2) / len(drawdown_pct)) if len(drawdown_pct) > 0 else 0.0

    # --- Trade-Based Metrics ---
    if trades is not None and len(trades) > 0:
        df_trades = pd.DataFrame(trades)
        if 'pnl' in df_trades.columns:
            pnl = df_trades['pnl']
            metrics['total_trades'] = len(df_trades)
            wins = pnl[pnl > 0]
            losses = pnl[pnl <= 0]
            metrics['win_rate'] = (len(wins) / metrics['total_trades']) * 100 if metrics['total_trades'] > 0 else 0
            metrics['avg_win'] = wins.mean()
            metrics['avg_loss'] = losses.mean()
            metrics['gross_profit'] = wins.sum()
            metrics['gross_loss'] = losses.sum()
            metrics['profit_factor'] = metrics['gross_profit'] / abs(metrics['gross_loss']) if abs(metrics['gross_loss']) > 0 else np.inf
            metrics['expectancy'] = pnl.mean()

    # Check for theoretically unlimited risk
    unlimited_risk_strategies = ["short_put", "short_call", "custom_manual"]
    metrics['unlimited_risk'] = "Yes" if strat_type in unlimited_risk_strategies else "No"

    final_metrics = {k: (v if pd.notna(v) else 0) for k, v in metrics.items()}
    logging.info("Performance summary calculated successfully.")
    return final_metrics

def get_benchmark_equity(start_date: str, end_date: str, initial_value: float = 100000, ticker: str = "SPY") -> pd.Series:
    try:
        data = yf.download(ticker, start=start_date, end=end_date, auto_adjust=True, progress=False)
        if data.empty or "Close" not in data.columns:
            return pd.Series(dtype=float)
        prices = data["Close"].dropna()
        if prices.empty:
            return pd.Series(dtype=float)
        normalized_equity = (prices / prices.iloc[0]) * initial_value
        return normalized_equity
    except Exception as e:
        logging.error(f"Failed to get benchmark data for {ticker}: {e}")
        return pd.Series(dtype=float)