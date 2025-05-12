"""utils/metrics.py
───────────────────────────────────────────────────────────────────────────
Functions for calculating common performance metrics for financial strategies.

Provides calculations for:
- Returns (daily)
- CAGR (Compound Annual Growth Rate)
- Max Drawdown
- Sharpe Ratio
- Sortino Ratio
- Various trade statistics (win rate, profit factor, expectancy, etc.)

Designed to work with pandas Series (for equity curves) and lists of trade
dictionaries or pandas DataFrames (for trade logs).
"""

from __future__ import annotations
import numpy as np
import pandas as pd
import logging
import yfinance as yf


# Configure logging for metrics calculation
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - METRICS - %(message)s')

# Constants
TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_DEFAULT = 0.0 # Default to 0 if not provided

# ═══════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════

def _to_series(data, name="equity") -> pd.Series:
    """Converts input data (list, numpy array, Series) to a pandas Series."""
    if isinstance(data, pd.Series):
        return data.rename(name) # Ensure consistent naming
    elif isinstance(data, (list, np.ndarray)):
        return pd.Series(data, name=name)
    else:
        raise TypeError(f"Input data must be a pandas Series, list, or numpy array. Got: {type(data)}")

def _validate_series(series: pd.Series) -> pd.Series | None:
     """Basic validation for equity or return series."""
     if not isinstance(series, pd.Series):
         logging.error(f"Input must be a pandas Series, got {type(series)}")
         return None
     if series.empty:
         logging.warning("Input Series is empty. Cannot calculate metrics.")
         return None
     if series.isnull().all():
         logging.warning("Input Series contains only NaNs. Cannot calculate metrics.")
         return None
     # Check for non-numeric types if possible, though pandas usually handles this
     if not pd.api.types.is_numeric_dtype(series.dtype):
          try:
               series = pd.to_numeric(series, errors='coerce')
               if series.isnull().all():
                    logging.warning("Input Series could not be converted to numeric.")
                    return None
          except Exception:
                logging.warning(f"Input Series has non-numeric dtype {series.dtype} and conversion failed.")
                return None

     return series.dropna() # Drop NaNs for calculations


# ═══════════════════════════════════════════════════════════════════════════
# Core Metric Calculations
# ═══════════════════════════════════════════════════════════════════════════

def daily_returns(equity: pd.Series | list | np.ndarray) -> pd.Series:
    """Calculates daily percentage returns from an equity curve."""
    s = _to_series(equity)
    s = _validate_series(s)
    if s is None or len(s) < 2:
        return pd.Series(dtype=float) # Return empty series
    return s.pct_change().dropna()

def cagr(equity: pd.Series | list | np.ndarray, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Calculates Compound Annual Growth Rate (CAGR)."""
    s = _to_series(equity)
    s = _validate_series(s)
    if s is None or len(s) < 2:
        return 0.0

    start_value = s.iloc[0]
    end_value = s.iloc[-1]

    if start_value <= 0: # Avoid math errors with zero or negative start
        logging.warning("CAGR calculation skipped: Initial equity is non-positive.")
        return 0.0

    num_periods = len(s) - 1
    if num_periods == 0: # Handle single data point case
        return 0.0

    years = num_periods / periods_per_year
    if years <= 0: # Should not happen if num_periods > 0, but safety check
        return 0.0

    cagr_value = (end_value / start_value) ** (1 / years) - 1
    return float(cagr_value)


def max_drawdown(equity: pd.Series | list | np.ndarray) -> float:
    """
    Calculates the maximum drawdown from peak equity.
    Returns the drawdown as a negative value (e.g., -0.25 for -25%).
    If you want the peak-to-trough value, use peak_to_trough_drawdown.
    """
    s = _to_series(equity)
    s = _validate_series(s)
    if s is None or len(s) < 2:
        return 0.0

    cumulative_max = s.cummax()
    drawdown = s - cumulative_max # Drawdown in $ amounts (negative)
    max_dd_value = float(drawdown.min()) # The largest drop in $

    # Find the peak value *before* the max drawdown occurred
    peak_at_max_dd = cumulative_max[drawdown.idxmin()] if not drawdown.empty else s.iloc[0]

    # Calculate drawdown percentage relative to the peak before the drop
    if peak_at_max_dd <= 0: # Avoid division by zero
         max_dd_pct = 0.0
    else:
         # max_dd_value is negative, so this calculates the drop percentage
         max_dd_pct = max_dd_value / peak_at_max_dd

    # return max_dd_value # Return the absolute $ drawdown
    return float(max_dd_pct) # Return the percentage drawdown


def peak_to_trough_drawdown(equity: pd.Series | list | np.ndarray) -> float:
     """Calculates the maximum peak-to-trough drawdown value (absolute $)."""
     s = _to_series(equity)
     s = _validate_series(s)
     if s is None or len(s) < 2:
         return 0.0

     cumulative_max = s.cummax()
     drawdown = s - cumulative_max # Drawdown in $ amounts (negative)
     return float(drawdown.min()) # Returns the largest negative difference


def annualized_volatility(equity: pd.Series | list | np.ndarray, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
     """Calculates annualized volatility of daily returns."""
     rets = daily_returns(equity)
     if rets.empty:
         return 0.0
     vol = rets.std(ddof=1) # Use sample standard deviation
     return float(vol * np.sqrt(periods_per_year))


def sharpe_ratio(equity: pd.Series | list | np.ndarray, rf: float = RISK_FREE_RATE_DEFAULT, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Calculates the annualized Sharpe Ratio."""
    rets = daily_returns(equity)
    if rets.empty:
        return 0.0

    excess_returns = rets - (rf / periods_per_year)
    mean_excess_return = excess_returns.mean()
    std_dev = excess_returns.std(ddof=1) # Use sample standard deviation

    if std_dev == 0 or np.isnan(std_dev):
        # Handle cases with zero volatility (e.g., flat equity) or NaN std dev
        return 0.0 if abs(mean_excess_return) < 1e-9 else np.inf * np.sign(mean_excess_return)

    sharpe = (mean_excess_return / std_dev) * np.sqrt(periods_per_year)
    return float(sharpe)


def sortino_ratio(equity: pd.Series | list | np.ndarray, rf: float = RISK_FREE_RATE_DEFAULT, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Calculates the annualized Sortino Ratio."""
    rets = daily_returns(equity)
    if rets.empty:
        return 0.0

    target_return = rf / periods_per_year
    excess_returns = rets - target_return
    mean_excess_return = excess_returns.mean()

    # Calculate downside deviation (std dev of returns below target)
    downside_returns = excess_returns[excess_returns < 0]
    if downside_returns.empty:
        # No returns below target, downside deviation is 0
        # Handle depending on mean return: if positive -> infinite Sortino, if zero/negative -> zero Sortino
        return 0.0 if mean_excess_return <= 1e-9 else np.inf

    # Calculate downside deviation using population standard deviation (N) as common practice
    downside_deviation = np.sqrt(np.mean(downside_returns**2)) # Equivalent to std(ddof=0) on downside returns

    if downside_deviation == 0 or np.isnan(downside_deviation):
        # Similar handling to Sharpe for zero deviation cases
        return 0.0 if mean_excess_return <= 1e-9 else np.inf

    sortino = (mean_excess_return / downside_deviation) * np.sqrt(periods_per_year)
    return float(sortino)

def calmar_ratio(equity: pd.Series | list | np.ndarray, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
     """Calculates the Calmar Ratio (CAGR / Absolute Max Drawdown %)."""
     cagr_val = cagr(equity, periods_per_year)
     max_dd_pct = max_drawdown(equity) # Returns negative percentage e.g. -0.25

     if max_dd_pct == 0 or np.isnan(max_dd_pct):
          return 0.0 if cagr_val <= 0 else np.inf # Or should return 0? Debatable. Let's use 0.

     # Use absolute value of drawdown for the ratio
     calmar = cagr_val / abs(max_dd_pct)
     return float(calmar)


# ═══════════════════════════════════════════════════════════════════════════
# Trade Analysis Metrics
# ═══════════════════════════════════════════════════════════════════════════

def trade_metrics(trades: list[dict] | pd.DataFrame) -> dict:
    """
    Calculates various statistics based on a list or DataFrame of trades.
    Requires a 'pnl' column/key for each trade.

    Parameters:
        trades: List of dictionaries or pandas DataFrame. Each element/row must
                contain at least a 'pnl' field/column with the trade's profit/loss.

    Returns:
        dict: A dictionary containing trade statistics.
    """
    if isinstance(trades, pd.DataFrame):
        if 'pnl' not in trades.columns:
             logging.error("Trade DataFrame must contain a 'pnl' column.")
             return {}
        pnl = trades["pnl"].astype(float).dropna()
    elif isinstance(trades, list):
        if not trades: # Handle empty list
             pnl = np.array([])
        else:
             try:
                  pnl = np.array([float(t["pnl"]) for t in trades if "pnl" in t])
             except (KeyError, TypeError, ValueError) as e:
                  logging.error(f"Error processing trade list: Ensure each dict has a numeric 'pnl' key. Details: {e}")
                  return {}
    else:
        raise TypeError("Input 'trades' must be a list of dicts or a pandas DataFrame.")

    if pnl.size == 0:
        logging.warning("No valid PnL values found in trades. Returning default trade metrics.")
        # Return default structure with zeros/Nones
        return dict(
            total_trades=0, win_rate=0.0, avg_win=0.0, avg_loss=0.0,
            profit_factor=np.nan, expectancy=0.0, gross_profit=0.0, gross_loss=0.0,
            avg_trade_pnl=0.0, std_dev_pnl=0.0
        )

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    num_trades = int(pnl.size)
    num_wins = int(wins.size)
    num_losses = int(losses.size)

    win_rate = (num_wins / num_trades * 100) if num_trades > 0 else 0.0
    avg_win = float(wins.mean()) if num_wins > 0 else 0.0
    avg_loss = float(losses.mean()) if num_losses > 0 else 0.0 # avg_loss will be negative
    gross_profit = float(wins.sum())
    gross_loss = float(losses.sum()) # gross_loss will be negative

    # Profit Factor: Gross Profit / Absolute Gross Loss
    if gross_loss == 0:
         profit_factor = np.inf if gross_profit > 0 else 0.0 # Or NaN? inf seems standard
    else:
         profit_factor = abs(gross_profit / gross_loss)

    # Expectancy: Average PnL per trade
    expectancy = float(pnl.mean())

    # Standard deviation of PnL
    std_dev_pnl = float(pnl.std(ddof=0)) # Use population std dev for expectancy context

    return dict(
        total_trades=num_trades,
        win_rate=float(win_rate),
        avg_win=avg_win,
        avg_loss=avg_loss, # Keep as negative
        profit_factor=float(profit_factor),
        expectancy=expectancy,
        gross_profit=gross_profit,
        gross_loss=gross_loss, # Keep as negative
        avg_trade_pnl=expectancy, # Redundant but maybe clearer label
        std_dev_pnl=std_dev_pnl
    )


# ═══════════════════════════════════════════════════════════════════════════
# Consolidated Summary Function
# ═══════════════════════════════════════════════════════════════════════════

def summary(
    equity: pd.Series | list | np.ndarray,
    trades: list[dict] | pd.DataFrame,
    rf: float = RISK_FREE_RATE_DEFAULT,
    periods_per_year: int = TRADING_DAYS_PER_YEAR
) -> dict:
    """
    Generates a consolidated dictionary of performance and trade metrics.

    Parameters:
        equity: Equity curve data (pandas Series, list, or numpy array).
        trades: Trade log data (list of dicts or pandas DataFrame with 'pnl').
        rf (float): Risk-free rate (annualized) for ratio calculations.
        periods_per_year (int): Number of trading periods in a year (e.g., 252 for daily).

    Returns:
        dict: A dictionary containing key performance indicators.
    """
    logging.info("Calculating performance summary...")
    eq_series = _to_series(equity)
    eq_series = _validate_series(eq_series)

    if eq_series is None or eq_series.empty:
        logging.error("Equity series is invalid or empty. Cannot generate summary.")
        # Return structure with NaNs/zeros?
        metrics = {k: 0.0 for k in [
             'start_value', 'end_value', 'total_return_abs', 'total_return_pct',
             'cagr', 'annualized_volatility', 'sharpe', 'sortino', 'calmar',
             'max_drawdown_pct', 'max_drawdown_abs'
             ]}
    else:
         metrics = dict(
             start_value=float(eq_series.iloc[0]),
             end_value=float(eq_series.iloc[-1]),
             total_return_abs=float(eq_series.iloc[-1] - eq_series.iloc[0]),
             total_return_pct=float((eq_series.iloc[-1] / eq_series.iloc[0] - 1) * 100) if eq_series.iloc[0] != 0 else 0.0,
             cagr=float(cagr(eq_series, periods_per_year)),
             annualized_volatility=float(annualized_volatility(eq_series, periods_per_year)),
             sharpe=float(sharpe_ratio(eq_series, rf, periods_per_year)),
             sortino=float(sortino_ratio(eq_series, rf, periods_per_year)),
             calmar=float(calmar_ratio(eq_series, periods_per_year)),
             max_drawdown_pct=float(max_drawdown(eq_series)), # Returns negative %
             max_drawdown_abs=float(peak_to_trough_drawdown(eq_series)) # Returns negative $ amount
         )

    trade_stats = trade_metrics(trades)
    metrics.update(trade_stats) # Combine equity metrics with trade metrics

    logging.info("Performance summary calculated successfully.")
    return metrics


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("--- Testing Metrics Module ---")

    # Create sample data
    np.random.seed(42)
    initial_equity = 100000
    daily_rets = np.random.normal(0.0005, 0.01, TRADING_DAYS_PER_YEAR * 2) # 2 years of data
    sample_equity = pd.Series(initial_equity * (1 + daily_rets).cumprod())
    sample_equity.index = pd.date_range(start="2022-01-01", periods=len(sample_equity), freq='B') # Business day freq

    sample_trades = []
    current_capital = initial_equity
    for i in range(100): # Simulate 100 trades
        pnl = np.random.normal(200, 800) # Random PnL
        sample_trades.append({
            "pnl": pnl,
            "open": sample_equity.index[i*5].date(), # Example open/close dates
            "close": sample_equity.index[min(i*5+10, len(sample_equity)-1)].date()
        })
        current_capital += pnl # Simple PnL addition for trade stats
        # Note: This trade generation doesn't perfectly match the equity curve above

    print("\n--- Calculating Summary Stats ---")
    summary_stats = summary(sample_equity, sample_trades, rf=0.02)

    print("Summary Results:")
    for key, val in summary_stats.items():
        print(f"  {key:<25}: {val:.4f}" if isinstance(val, float) else f"  {key:<25}: {val}")

    # Test edge cases
    print("\n--- Testing Edge Cases ---")
    empty_equity = pd.Series([], dtype=float)
    empty_trades = []
    print("Empty Data Summary:", summary(empty_equity, empty_trades))

    flat_equity = pd.Series([100000] * 10)
    print("Flat Equity Summary:", summary(flat_equity, empty_trades))

    single_trade = [{"pnl": 500}]
    print("Single Trade Metrics:", trade_metrics(single_trade))


def get_benchmark_equity(start_date: str, end_date: str, initial_value: float = 100000, ticker: str = "SPY") -> pd.Series:
    """
    Fetches benchmark equity curve using adjusted close prices.
    Returns Series aligned to business days, scaled to match initial_value.
    """
    try:
        ticker = ticker.upper()
        data = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            auto_adjust=False,
            progress=False
        )
        if data.empty or "Adj Close" not in data.columns:
            logging.warning(f"No data fetched for benchmark {ticker}.")
            return pd.Series(dtype=float)

        prices = data["Adj Close"].dropna()
        if prices.empty:
            logging.warning(f"Adjusted Close data is empty for benchmark {ticker}.")
            return pd.Series(dtype=float)

        returns = prices.pct_change().dropna()
        equity = (1 + returns).cumprod() * initial_value
        equity.name = ticker

        # Align to business days if needed
        equity = equity.asfreq("B", method="pad")
        return equity

    except Exception as e:
        logging.error(f"Failed to get benchmark data for {ticker}: {e}")
        return pd.Series(dtype=float)

