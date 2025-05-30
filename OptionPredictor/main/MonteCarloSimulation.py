# MonteCarloSimulation.py
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
# Removed MplButton import as it wasn't used
import pandas as pd
import io
import yfinance as yf
from yfinance.exceptions import YFRateLimitError
import requests
import datetime as dt
import math
from scipy.stats import norm
from mpl_toolkits.mplot3d import Axes3D
import seaborn as sns
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import tkinter as tk # Needed for embedding canvas/toolbar
from numpy.polynomial.laguerre import lagval
from functools import lru_cache
import time # Make sure time is imported 
from matplotlib.lines import Line2D # Needed for Line2D used in educational mode
from matplotlib.animation import FuncAnimation
from numpy.fft import fft, ifft

  

# Apply the dark theme globally for matplotlib plots (optional)
# plt.style.use('dark_background')
# Consider setting style within plotting functions if you want more control
# or if the global style interferes with Tkinter themes.

MAX_PATHS_TO_PLOT = 50  # Default
dark_mode = False  # Global theme flag used by plot functions

def set_max_paths(n):
    global MAX_PATHS_TO_PLOT
    MAX_PATHS_TO_PLOT = n


def fetch_ticker_data(ticker: str, days: int) -> pd.Series:
    """
    Fetches daily closing prices for a ticker over the last `days` days, 
    with the end date set to 7 days before the current date to ensure data availability.
    
    Attempt 1: Tries Stooq first.
    Attempt 2: Falls back to yfinance with retries if Stooq fails.
    Raises ValueError with detailed message if neither source works.
    """
    import datetime as dt
    import time
    import pandas as pd
    import yfinance as yf
    import requests
    import io

    # Calculate date range
    current_date = dt.datetime.today()
    end_date = current_date - dt.timedelta(days=7)  # 7 days before today b/c error before was it couldn't fetch tdy's data
    start_date = end_date - dt.timedelta(days=int(days))
    
    if start_date >= end_date:
        raise ValueError(f"Invalid date range: start_date ({start_date.strftime('%Y-%m-%d')}) "
                         f"is on or after end_date ({end_date.strftime('%Y-%m-%d')}).")
    
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    print(f"Fetching data for {ticker} from {start_str} to {end_str}")

    def clean_close(df: pd.DataFrame) -> pd.Series:
        if 'Close' not in df.columns:
            raise ValueError(f"'Close' column missing for {ticker}")
        s = df['Close'].ffill().dropna()
        if s.empty:
            raise ValueError(f"No valid 'Close' prices for {ticker}")
        return s

    # Attempt 1: Fetch data from Stooq
    symbol = ticker.lower()
    if '.' not in symbol:
        symbol += '.us'
    url = (
        f"https://stooq.com/q/d/l/"
        f"?s={symbol}"
        f"&d1={start_str.replace('-', '')}&d2={end_str.replace('-', '')}"
        f"&i=d"
    )
    print(f"Attempt 1: Fetching Stooq data from URL: {url}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()

        df = pd.read_csv(
            io.StringIO(resp.text),
            parse_dates=[0],
            index_col=0
        ).sort_index()
        return clean_close(df)

    except requests.exceptions.RequestException as e:
        print(f"Attempt 1 (Stooq) failed for '{ticker}' due to network/HTTP error: {e}")
    except Exception as e:
        print(f"Attempt 1 (Stooq) failed for '{ticker}': {e}")
        if 'resp' in locals():
            print(f"Problematic Stooq data: {resp.text[:500]}")

    # Attempt 2: Fetch data from yfinance with retries
    print(f"Attempt 2: Falling back to yfinance for '{ticker}'")
    max_retries = 3
    for attempt in range(max_retries):
        try:
            df = yf.download(
                ticker,
                start=start_str,
                end=end_str,
                progress=False,
                threads=False
            )
            if df is not None and not df.empty:
                return clean_close(df)
            else:
                print(f"yfinance returned empty data on retry {attempt + 1}/{max_retries}")
        except Exception as e:
            print(f"yfinance retry {attempt + 1}/{max_retries} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(5 * (attempt + 1))  # Exponential backoff
                continue
            print(f"Attempt 2 (yfinance) failed after {max_retries} retries")
            break

    # Both attempts failed
    raise ValueError(
        f"Failed to fetch data for '{ticker}'.\n"
        f"- Attempt 1 (Stooq): Failed.\n"
        f"- Attempt 2 (yfinance): Failed after {max_retries} retries.\n"
        f"Date range: {start_str} to {end_str}. Check ticker or network."
    )

def calculate_drift_and_volatility(prices):
    """Calculates annualized drift and realized volatility."""
    # Ensure input is a Series
    if isinstance(prices, pd.DataFrame):
        if 'Close' in prices.columns:
            prices = prices['Close']
        else:
            prices = prices.iloc[:, 0]  # Fallback to the first column

    elif not isinstance(prices, pd.Series):
        prices = pd.Series(prices)

    prices = prices.dropna()

    if len(prices) < 2:
        print("Warning: Less than 2 data points for volatility calculation. Returning zeros.")
        return 0.0, 0.0, 0.0

    log_returns = np.log(prices / prices.shift(1)).dropna()

    if log_returns.empty or len(log_returns) < 2:
        print("Warning: Not enough log returns for volatility calculation after dropping NaNs. Returning zeros.")
        return 0.0, 0.0, 0.0

    if np.isinf(log_returns).any():
        print("Warning: Infinite values detected in log returns. Replacing with NaN.")
        log_returns.replace([np.inf, -np.inf], np.nan, inplace=True)
        log_returns.dropna(inplace=True)
        if log_returns.empty or len(log_returns) < 2:
            print("Warning: Not enough valid log returns after removing infinities. Returning zeros.")
            return 0.0, 0.0, 0.0

    drift = float(log_returns.mean()) * 252
    realized_vol = float(log_returns.std()) * np.sqrt(252)
    n_returns = len(log_returns)
    # Chi-square–based stderr for sample standard deviation:
    # Var(s) ≈ σ² / [2*(n_returns-1)] ⇒ stderr = realized_vol / sqrt(2*(n_returns-1))
    stderr = (realized_vol / np.sqrt(2 * max(n_returns - 1, 1))) if n_returns > 1 else 0.0


    return drift, realized_vol, stderr

def black_scholes_price(S, K, T, r, sigma, option_type="call"):
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)
    
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    
    if option_type == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    else:
        return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


# --- Hybrid FFT-based rough Bergomi simulator (Bayer–Friz–Gatheral) ---
def simulate_rbergomi_hybrid(
    S0: float,
    xi0: callable,
    r: float,
    eta: float,
    H: float,
    rho: float,
    T: float,
    N: int,
    n_paths: int,
    m_cutoff: int = None
) -> tuple[np.ndarray, np.ndarray]:
    """
    Simulate the rBergomi model via an O(N log N) hybrid FFT scheme.

    Returns:
      t (N+1,) time grid
      paths (n_paths, N+1) simulated price paths
    """
    dt = T / N
    t = np.linspace(0, T, N+1)

    # default cutoff if not provided
    if m_cutoff is None:
        m_cutoff = max(1, N // 10)

    # 1) build kernel weights a[k] = ∫_{k dt}^{(k+1) dt}(t_i - s)^{H-1/2} ds
    prefac = dt**(H + 0.5) / (H + 0.5)
    a = np.array([((i+1)**(H+0.5) - i**(H+0.5)) for i in range(N)]) * prefac

    # split into exact part and tail
    a_exact = a[:m_cutoff]
    a_tail  = a[m_cutoff:]

    # prepare circulant embedding for FFT convolution of tail
    circ = np.concatenate([a_tail, np.zeros(N - len(a_tail))])
    fft_circ = fft(np.concatenate([circ, circ]))

    paths = np.zeros((n_paths, N+1))
    paths[:,0] = S0

    for p in range(n_paths):
        # draw correlated Brownian increments
        Z1 = np.random.standard_normal(N)
        Z2 = np.random.standard_normal(N)
        dW1 = Z1 * np.sqrt(dt)
        dW2 = (rho * Z1 + np.sqrt(1 - rho**2) * Z2) * np.sqrt(dt)

        # build fractional driver F
        F = np.convolve(Z2, a_exact, mode='full')[:N]
        z2_pad = np.concatenate([Z2, np.zeros(N)])
        conv  = ifft(fft(z2_pad) * fft_circ)
        F    += np.real(conv[:N])

        # Euler–Maruyama for log-S
        logS = np.log(S0)
        for i in range(N):
            var_i = xi0(t[i]) * np.exp(eta * F[i] - 0.5 * eta**2 * (t[i]**(2*H)))
            logS += (r - 0.5 * var_i) * dt + np.sqrt(var_i) * dW1[i]
            paths[p, i+1] = np.exp(logS)

    return t, paths


# --- Binomial Option Pricing ---

def binomial_tree_option_price(S, K, T, r, sigma, N, option_type='call', american=True):
    """Prices an option using the Binomial Tree model (Cox-Ross-Rubinstein)."""
    # Validate inputs
    if N <= 0:
        print("Warning: Number of steps N must be positive for Binomial Tree.")
        return np.nan # Cannot compute
    if T < 0:
        print("Warning: Time to expiry T cannot be negative.")
        return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S) # Intrinsic at T=0 maybe?
    if sigma < 0:
        print("Warning: Volatility sigma cannot be negative. Using sigma=0.")
        sigma = 0.0

    # If T is effectively zero, return intrinsic value
    if T < 1e-9: # Use a small threshold instead of == 0 for float comparison
       return max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)

    dt = T / N
    u = np.exp(sigma * np.sqrt(dt))

    # Prevent division by zero or u becoming invalid if sigma or dt are extreme or zero
    if u == 0 or np.isinf(u) or np.isnan(u) or u == 1.0:
         # If u is 1 (sigma=0 or dt=0), tree doesn't branch. Value is discounted payoff at S.
         if u == 1.0:
              payoff = max(0.0, S - K) if option_type == 'call' else max(0.0, K - S)
              return np.exp(-r * T) * payoff # European value if sigma=0
         else:
            print(f"Warning: Binomial parameter 'u' became invalid ({u}). Check sigma/T/N. Returning NaN.")
            return np.nan

    d = 1.0 / u
    a = np.exp(r * dt) # Pre-calculate growth factor

    # Risk-neutral probability
    # Handle potential division by zero if u=d (should be caught by u=1 check)
    if (u - d) == 0:
         print("Warning: Binomial parameters u and d are equal. Cannot calculate probability. Returning NaN.")
         return np.nan

    p = (a - d) / (u - d)

    # Check if p is valid (between 0 and 1) - indicates potential arbitrage or model breakdown
    # Allow small tolerance due to floating point math
    if not (-1e-9 <= p <= 1.0 + 1e-9):
        print(f"Warning: Risk-neutral probability p={p:.4f} is outside [0, 1]. May indicate arbitrage or model issues. Clamping p.")
        p = max(min(p, 1.0), 0.0) # Clamp p to [0, 1] to proceed


    q = 1.0 - p # Probability of down move
    disc = np.exp(-r * dt) # Discount factor for one step

    # Initialize option values at maturity (N steps) using vectorization
    j = np.arange(N + 1) # 0 to N
    ST = S * (u ** (N - j)) * (d ** j) # Stock prices at maturity (N down moves for j=N)

    if option_type == 'call':
        option_values = np.maximum(0.0, ST - K)
    else: # put
        option_values = np.maximum(0.0, K - ST)

    # Step backwards through the tree
    for i in range(N - 1, -1, -1):
        # Option values from the next step (i+1)
        # Size of option_values reduces by 1 each step
        # option_values_prev had size i+2

        # Calculate European option value component for step i
        option_values = disc * (p * option_values[0 : i + 1] + q * option_values[1 : i + 2])

        if american:
            # Calculate stock prices and intrinsic values at the current node step i
            j_curr = np.arange(i + 1) # 0 to i
            ST_curr = S * (u ** (i - j_curr)) * (d ** j_curr)
            if option_type == 'call':
                intrinsic = np.maximum(0.0, ST_curr - K)
            else: # put
                intrinsic = np.maximum(0.0, K - ST_curr)
            # Choose the maximum of exercising now (intrinsic) or holding (European component)
            option_values = np.maximum(option_values, intrinsic)

    # Final option value at time 0
    if np.isnan(option_values[0]):
         print("Warning: Final binomial option value is NaN.")
    return option_values[0]

@lru_cache(maxsize=128) # Cache results for efficiency
def cached_binomial_price(S, K, T, r, sigma, N, option_type, american):
    return binomial_tree_option_price(S, K, T, r, sigma, N, option_type, american)


# --- Monte Carlo Simulation ---

def calculate_simulation_data(S0, H, sigma, drift, T, r, n_simulations=100000, option_type='call',
                              model='black_scholes', jump_params=None, heston_params=None, rough_params=None):
    """Runs Monte Carlo simulation using selected model. Returns simulated data but not the plot."""
    import numpy as np

    if T <= 0:
        print("Warning: Time to expiry T must be positive for MC simulation. Using T=1/365.")
        T = 1/365
    if sigma < 0:
        print("Warning: Volatility sigma cannot be negative. Using sigma=0.")
        sigma = 0
    if n_simulations <= 0:
        print("Warning: Number of simulations must be positive. Using 1.")
        n_simulations = 1

    n_steps = int(T * 365 * 24)
    n_steps = max(1, min(n_steps, 100000))  # Cap steps
    dt = T / n_steps

    np.random.seed(42)
    time_points = np.linspace(0, T, n_steps + 1)
    sample_paths_for_plot = []
    hits = 0

    # --- Black-Scholes ---
    if model == 'black_scholes':
        rn_drift = (r - 0.5 * sigma ** 2) * dt
        vol_term = sigma * np.sqrt(dt)
        log_returns = rn_drift + vol_term * np.random.standard_normal((n_simulations, n_steps))
        log_paths = np.log(S0) + np.cumsum(log_returns, axis=1)
        log_paths = np.hstack((np.full((n_simulations, 1), np.log(S0)), log_paths))
        price_paths_matrix = np.exp(log_paths)

    elif model == 'jump_diffusion':
        λ      = jump_params.get('lambda', 0.1)
        mu_j   = jump_params.get('mu', -0.1)
        sigma_j= jump_params.get('sigma', 0.2)
        vol_term = sigma * np.sqrt(dt)

        # Gaussian shocks
        Z = np.random.standard_normal((n_simulations, n_steps))
        # Poisson counts
        N = np.random.poisson(λ * dt, (n_simulations, n_steps))
        # Sum of N jumps ~ Normal(N*mu_j, sqrt(N)*sigma_j)
        J_sum = np.random.normal(loc=mu_j * N,
                                 scale=sigma_j * np.sqrt(N))

        # log‐return with jump compensation
        log_returns = (
            (r
             - 0.5 * sigma**2
             - λ * (np.exp(mu_j + 0.5 * sigma_j**2) - 1)
            ) * dt
            + vol_term * Z
            + J_sum
        )

        # build price paths
        log_paths = np.log(S0) + np.cumsum(log_returns, axis=1)
        log_paths = np.hstack((np.full((n_simulations, 1), np.log(S0)),
                               log_paths))
        price_paths_matrix = np.exp(log_paths)


    # --- Heston Model ---
    elif model == 'heston':
        kappa = heston_params.get('kappa', 2.0)
        theta = heston_params.get('theta', sigma ** 2)
        xi    = heston_params.get('xi', 0.1)
        v0    = heston_params.get('v0', sigma ** 2)
        rho   = heston_params.get('rho', -0.7)  
        dt_sqrt = np.sqrt(dt)

        v = np.full((n_simulations,), v0)
        log_S = np.full((n_simulations,), np.log(S0))
        log_path_matrix = np.zeros((n_simulations, n_steps + 1))
        log_path_matrix[:, 0] = log_S

        for t in range(n_steps):
            Z1 = np.random.standard_normal(n_simulations)
            Z2 = rho * Z1 + np.sqrt(1 - rho ** 2) * np.random.standard_normal(n_simulations)

            v = np.maximum(v + kappa * (theta - v) * dt + xi * np.sqrt(np.maximum(v, 0)) * Z2 * dt_sqrt, 1e-8)
            log_S += (r - 0.5 * v) * dt + np.sqrt(v) * Z1 * dt_sqrt
            log_path_matrix[:, t + 1] = log_S

        price_paths_matrix = np.exp(log_path_matrix)

    # --- Rough Bergomi Model (Hybrid FFT) ---
    elif model == 'rough_bergomi':
        # fractional parameters
        H_param   = rough_params.get('H', 0.1)
        eta_param = rough_params.get('eta', 1.5)
        rho_param = rough_params.get('rho', 0.0)
        m_cut     = rough_params.get('m_cutoff', n_steps // 10)

        # flat forward‐variance curve
        xi0 = lambda τ: sigma**2

        # simulate
        time_points, price_paths_matrix = simulate_rbergomi_hybrid(
            S0=S0,
            xi0=xi0,
            r=r,
            eta=eta_param,
            H=H_param,
            rho=rho_param,
            T=T,
            N=n_steps,
            n_paths=n_simulations,
            m_cutoff=m_cut
        )

        # expiry prices & barrier hits
        final_prices = price_paths_matrix[:, -1]
        if option_type == 'call':
            hits = np.sum(np.any(price_paths_matrix >= H, axis=1))
            payoff = np.maximum(final_prices - H, 0)
        else:
            hits = np.sum(np.any(price_paths_matrix <= H, axis=1))
            payoff = np.maximum(H - final_prices, 0)

        probability        = hits / n_simulations
        avg_expiry_price   = np.mean(final_prices)
        std_expiry_price   = np.std(final_prices)
        sample_paths_for_plot = price_paths_matrix[:MAX_PATHS_TO_PLOT, :]

        return (
            probability,
            avg_expiry_price,
            std_expiry_price,
            final_prices,
            sample_paths_for_plot,
            time_points
        )


    else:
        raise ValueError(f"Unknown model type: {model}")

    # --- Barrier check ---
    for i in range(n_simulations):
        path = price_paths_matrix[i, :]
        if option_type == 'call' and np.any(path >= H):
            hits += 1
        elif option_type == 'put' and np.any(path <= H):
            hits += 1

    simulated_prices_at_expiry = price_paths_matrix[:, -1]
    sample_paths_for_plot = price_paths_matrix[:MAX_PATHS_TO_PLOT, :]
    probability = hits / n_simulations if n_simulations > 0 else 0.0
    avg_expiry_price = np.mean(simulated_prices_at_expiry)
    std_expiry_price = np.std(simulated_prices_at_expiry)

    return probability, avg_expiry_price, std_expiry_price, simulated_prices_at_expiry, sample_paths_for_plot, time_points


#def least_squares_mc_american_option(S0, K, T, r, sigma, n_paths=100000, n_steps=100, option_type='call', degree=2):
    dt = T / n_steps
    discount = np.exp(-r * dt)
    S = np.zeros((n_paths, n_steps + 1))
    S[:, 0] = S0

    np.random.seed(42)

    for t in range(1, n_steps + 1):
        z = np.random.standard_normal(n_paths)
        S[:, t] = S[:, t - 1] * np.exp((r - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z)

    if option_type == 'call':
        payoff = np.maximum(S - K, 0)
    else:
        payoff = np.maximum(K - S, 0)

    V = payoff[:, -1]  # Initialize with terminal payoff

    for t in range(n_steps - 1, 0, -1):
        itm = payoff[:, t] > 0
        if np.any(itm):
            X = S[itm, t]
            Y = V[itm]  # No discount yet
            A = np.column_stack([X**d for d in range(degree + 1)])
            coeffs = np.linalg.lstsq(A, Y, rcond=None)[0]
            continuation = A @ coeffs

            exercise = payoff[itm, t] > continuation
            V[itm] = np.where(exercise, payoff[itm, t], V[itm])

        # Then discount everyone
        V *= discount
    
    # Check for immediate exercise at t=0
    immediate_exercise = payoff[:, 0]
    V = np.maximum(V, immediate_exercise)

    return np.mean(V)

#@lru_cache(maxsize=128)
#def cached_lsm_price(S, K, T, r, sigma, n_paths, n_steps, option_type):
    #return least_squares_mc_american_option(S, K, T, r, sigma, n_paths, n_steps, option_type)




def calculate_trigger_stats_correctly(S0, sigma, T, r, n_simulations=100000, option_type='call'):
    """Runs corrected Monte Carlo simulation to compute trigger (max/min) statistics."""
    n_steps = int(T * 365 * 24)
    n_steps = max(1, min(n_steps, 100000))
    dt = T / n_steps

    drift_term = (r - 0.5 * sigma**2) * dt
    vol_term = sigma * np.sqrt(dt)

    np.random.seed(42)  # For consistency

    # Generate log returns matrix
    log_returns = drift_term + vol_term * np.random.standard_normal((n_simulations, n_steps))

    # Initialize log price matrix
    initial_log_price = np.log(S0)
    log_price_paths = initial_log_price + np.cumsum(log_returns, axis=1)
    log_price_paths = np.hstack((np.full((n_simulations, 1), initial_log_price), log_price_paths))
    price_paths = np.exp(log_price_paths)

    # Exclude initial price (column 0) so trigger is strictly > S₀ or < S₀
    if option_type == 'call':
        trigger_values = np.max(price_paths[:, 1:], axis=1)
    else:
        trigger_values = np.min(price_paths[:, 1:], axis=1)

    avg_trigger = np.mean(trigger_values)
    std_trigger = np.std(trigger_values)

    return avg_trigger, std_trigger, trigger_values

# --- Plotting Functions ---

def _setup_plot_embedding(parent_window, fig_size=(8, 6)):
    """Creates a figure, canvas, and toolbar for embedding in Tkinter."""
   
    # Use a specific style for plots if desired, otherwise default or global style applies
    # plt.style.use('seaborn-v0_8-darkgrid') # Example
    fig = plt.Figure(figsize=fig_size, dpi=100) # Use plt.Figure for embedding
    canvas = FigureCanvasTkAgg(fig, master=parent_window)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # Add the Matplotlib navigation toolbar
    toolbar_frame = tk.Frame(parent_window) # Create a frame for the toolbar
    toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
    toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
    toolbar.update()

    if dark_mode:
        toolbar.configure(background="#1e1e1e")
        for child in toolbar.winfo_children():
            try:
                child.configure(background="#1e1e1e", foreground="#f0f0f0")
            except:
                pass


    return fig, canvas # Return fig to add axes/plots, canvas to draw


def plot_simulation_paths(parent_window, time_points, sample_paths, S0, H, option_type, sigma, probability,
                          n_simulations, num_paths_to_plot, title="Simulated Stock Paths", educational_mode=False, dark_mode=False):

    if dark_mode:
        plt.style.use('dark_background')
    else:
        plt.style.use('default')

     # --- Description label above the graph ---
    info_text = (
        "🔍 What You're Watching – Monte Carlo Simulation\n"
        "Each line shows a possible future stock price path until option expiry.\n"
        "The blue dashed line = current price. The red line = barrier.\n"
        "Paths that cross the barrier represent 'hits' (where the option is in the money).\n"
        "This simulation helps estimate the probability of your option ending up in profit based on how many hits happen."
    )
    bg_color = "#1e1e1e" if dark_mode else "#f0f0f0"
    fg_color = "#f0f0f0" if dark_mode else "#000000"
    info_label = tk.Label(parent_window, text=info_text, justify='left', font=("Helvetica", 9),
                      anchor='w', bg=bg_color, fg=fg_color)

    info_label.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(5, 0))


    fig = plt.Figure(figsize=(8, 6))
    canvas = FigureCanvasTkAgg(fig, master=parent_window)
    canvas_widget = canvas.get_tk_widget()
    canvas_widget.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    ax = fig.add_subplot(111)

    days = time_points * 365
    frames = len(days)
    num_paths_to_plot = min(num_paths_to_plot, len(sample_paths))

    if num_paths_to_plot == 0 or frames == 0:
        ax.text(0.5, 0.5, "No simulation data to plot.", ha='center', va='center')
        fig.tight_layout()
        canvas.draw()
        return

    # Set common plot formatting
    ax.axhline(S0, color='blue', linestyle='--', linewidth=1.2, label=f"Start Price (S₀ = ${S0:.2f})")
    barrier_color = 'red' if option_type == 'call' else 'green'
    ax.axhline(H, color=barrier_color, linestyle='-', linewidth=1.5, label=f"Barrier (H = ${H:.2f})")
    ax.set_xlim(days[0], days[-1])

    all_prices = [p for p in sample_paths[:num_paths_to_plot] if p is not None and len(p) == len(days)]
    y_min = min(np.nanmin(np.concatenate(all_prices)), S0, H) * 0.95
    y_max = max(np.nanmax(np.concatenate(all_prices)), S0, H) * 1.05
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("Days to Expiry")
    ax.set_ylabel("Simulated Price")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(loc='upper right', fontsize='small')

    if not educational_mode:
        for i in range(num_paths_to_plot):
            path = sample_paths[i]
            if path is not None and len(path) == len(days):
                ax.plot(days, path, lw=0.7, alpha=0.6)
        hit_count = int(round(probability * n_simulations))
        ax.set_title(
            f"{title}\n(Monte Carlo | Barrier: {H:.2f} | Vol: {sigma:.2%} | Showing {num_paths_to_plot} paths | "
            f"Hit Rate: {probability * 100:.1f}% ({hit_count}/{n_simulations}))",
            fontsize=12
        )
        fig.tight_layout()
        canvas.draw()
        return

    # --- EDUCATIONAL MODE ---
    lines = [ax.plot([], [], lw=1.5, alpha=0.85)[0] for _ in range(num_paths_to_plot)]
    frame_idx = [0]
    paused = [False]
   # speed = [1.0]
   

    def init():
        for line in lines:
            line.set_data([], [])
        return lines

    def update(frame):
        if paused[0]:
            return lines
        idx = frame_idx[0]
        if idx >= frames:
            ani.event_source.stop()
            switch_to_static_view()
            return lines
        for i in range(num_paths_to_plot):
            path = sample_paths[i]
            if path is not None and len(path) == len(days):
                lines[i].set_data(days[:idx + 1], path[:idx + 1])
        frame_idx[0] += 1
        return lines

    ani = FuncAnimation(fig, update, init_func=init, frames=frames, blit=True, interval=10, repeat=False)


    def check_animation_end():
        if frame_idx[0] >= frames:
            switch_to_static_view()
        else:
            parent_window.after(50, check_animation_end)

    parent_window.after(50, check_animation_end)


    #def on_speed_change(val):
        #try:
         #   speed[0] = float(val)
         #   ani.event_source.interval = max(1, int(1000 / (60 * speed[0])))
       # except Exception as e:
       #     print(f"[Speed Slider Error] {e}")

    def toggle_pause():
        paused[0] = not paused[0]
        pause_btn.config(text="Resume" if paused[0] else "Pause")

    def jump_to(fraction):
        idx = int(frames * fraction)
        frame_idx[0] = min(idx, frames - 2)

    def on_close():
        try:
            if ani and ani.event_source:
                ani.event_source.stop()
        except:
            pass
        parent_window.destroy()

    def switch_to_static_view():
        ax.clear()
        ax.axhline(S0, color='blue', linestyle='--', linewidth=1.2, label=f"Start Price (S₀ = ${S0:.2f})")
        ax.axhline(H, color=barrier_color, linestyle='-', linewidth=1.5, label=f"Barrier (H = ${H:.2f})")
        ax.set_xlim(days[0], days[-1])
        ax.set_ylim(y_min, y_max)
        ax.grid(True, linestyle=":", alpha=0.6)
        for path in sample_paths[:num_paths_to_plot]:
            if path is not None and len(path) == len(days):
                ax.plot(days, path, lw=0.7, alpha=0.6)
        hit_count = int(round(probability * n_simulations))
        ax.set_title(
            f"{title}\n(Monte Carlo | Barrier: {H:.2f} | Vol: {sigma:.2%} | Showing {num_paths_to_plot} paths | "
            f"Hit Rate: {probability * 100:.1f}% ({hit_count}/{n_simulations}))",
            fontsize=12
        )
        ax.legend(loc='upper right', fontsize='small')
        fig.tight_layout()
        canvas.draw()

    # --- UI Controls ---
    control_frame = tk.Frame(parent_window)
    control_frame.pack(fill=tk.X)
    #tk.Label(control_frame, text="Speed:").pack(side=tk.LEFT)

    #speed_slider = tk.Scale(control_frame, from_=0.1, to=5.0, resolution=0.1,
                            #orient=tk.HORIZONTAL, command=on_speed_change)
    #speed_slider.set(1.0)
    #speed_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

    pause_btn = tk.Button(control_frame, text="Pause", command=toggle_pause)
    pause_btn.pack(side=tk.RIGHT)

    jump_frame = tk.Frame(parent_window)
    jump_frame.pack(fill=tk.X)
    for frac, label in zip([0.0, 0.25, 0.5, 0.75, 0.96], ["0/4", "1/4", "2/4", "3/4", "4/4"]):
        tk.Button(jump_frame, text=label, command=lambda f=frac: jump_to(f)).pack(side=tk.LEFT)

    canvas.get_tk_widget().winfo_toplevel().protocol("WM_DELETE_WINDOW", on_close)
    canvas.draw()


def plot_distribution(parent, simulated_prices_at_expiry, H, probability, option_type, S0, avg_trigger, std_trigger, dark_mode=False):
    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns
    import matplotlib.backends.backend_tkagg as tkagg
    if dark_mode:
        plt.style.use('dark_background')
    else:
        plt.style.use('default')
    fig, ax = plt.subplots(figsize=(10, 5))

    sns.histplot(simulated_prices_at_expiry, kde=True, stat='percent', bins=40, color='skyblue', edgecolor='white', ax=ax)

    ax.axvline(avg_trigger, color='orange', linestyle='--', linewidth=2,
           label=f"Avg. Trigger = ${avg_trigger:.2f}")
    ax.axvline(avg_trigger + std_trigger, color='gray', linestyle='--', linewidth=1.5,
           label=f"+1 Std = ${avg_trigger + std_trigger:.2f}")
    ax.axvline(avg_trigger - std_trigger, color='gray', linestyle='--', linewidth=1.5,
           label=f"-1 Std = ${avg_trigger - std_trigger:.2f}")



    ax.axvline(H, color='red', linestyle='--', linewidth=2, label=f"Barrier (H = ${H:.0f})")

    min_price = np.min(simulated_prices_at_expiry)
    max_price = np.max(simulated_prices_at_expiry)
    buffer = (max_price - min_price) * 0.1
    ax.set_xlim(min_price - buffer, max_price + buffer)

    text_y_pos = ax.get_ylim()[1] * 0.6
    text_x_offset = std_trigger / 2
    text_x_pos = H + text_x_offset
    ax.text(text_x_pos, text_y_pos, f"Prob. Hitting Barrier: {probability * 100:.2f}%",
            color='red', fontsize=10, va='top')

    ax.set_title("Monte Carlo Simulation: Trigger Price Distribution", fontsize=14, weight='bold')
    ax.set_xlabel("Trigger Price Reached During Simulation")
    ax.set_ylabel("Percentage of Simulations (%)")
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, linestyle='--', alpha=0.3)

    canvas = tkagg.FigureCanvasTkAgg(fig, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

# --- Heatmap and 3D Surface Data Generation ---

def generate_profit_heatmap_data(S0, K, T, r, sigma, option_type, style='american', initial_option_price=None,
                                 low_pct_factor=0.7, high_pct_factor=1.3, price_steps=20, time_steps=15):

    """Generates data for the profit/loss heatmap."""
    # If initial price isn't provided, calculate it
    if initial_option_price is None or np.isnan(initial_option_price):
        print("Heatmap: Calculating initial fair value as premium...")
        initial_option_price = binomial_tree_option_price(S0, K, T, r, sigma, N=200, # Use moderate N here
                                                           option_type=option_type, american=True)
        if np.isnan(initial_option_price):
             print("Error: Cannot calculate initial premium for heatmap. Aborting heatmap data generation.")
             return None # Indicate failure

    premium = initial_option_price
    print(f"Heatmap using premium: {premium:.4f}")

    # Define ranges for underlying price and time
    price_range = np.linspace(S0 * low_pct_factor, S0 * high_pct_factor, price_steps)
    # Time goes from T down to 0 (expiry)
    time_range = np.linspace(T, 1e-6, time_steps) # Avoid T=0 exactly

    profit_matrix = np.zeros((time_steps, price_steps))
    percent_profit_matrix = np.zeros((time_steps, price_steps))

    for i, t_remain in enumerate(time_range):
        for j, current_S in enumerate(price_range):
            # Calculate option value at this S and time remaining t_remain
            #if style == 'american':
                #current_option_value = cached_lsm_price(current_S, K, t_remain, r, sigma, 10000, 100, option_type)
            #else:
            current_option_value = cached_binomial_price(current_S, K, t_remain, r, sigma, 100, option_type, False)



            if np.isnan(current_option_value): # Handle potential calculation errors
                profit = np.nan
                percent_profit = np.nan
            else:
                # Profit = Current Value - Initial Cost (Premium)
                profit = current_option_value - premium
                # Percent profit relative to initial cost
                percent_profit = (profit / premium) * 100 if premium > 1e-6 else np.nan # Avoid div by zero

            profit_matrix[i, j] = profit
            percent_profit_matrix[i, j] = percent_profit

    # Labels for axes
    day_labels = [f"{int(t*365)}" for t in time_range]
    price_labels = [f"{p:.1f}" for p in price_range]

    return price_range, time_range, profit_matrix, percent_profit_matrix, day_labels, price_labels, premium


def generate_option_surface_data(S0, K, T, r, sigma, option_type, style='american',
                                 low_pct_factor=0.5, high_pct_factor=2.0, price_steps=30, time_steps=30):
    """Generates data for the 3D option value surface."""
    # Define ranges
    price_grid = np.linspace(S0 * low_pct_factor, S0 * high_pct_factor, price_steps)
    time_grid = np.linspace(T, 1e-6, time_steps) # Time remaining
    # Create meshgrid
    P_grid, T_grid = np.meshgrid(price_grid, time_grid)
    # Initialize value grid
    V_grid = np.full_like(P_grid, np.nan) # Use NaN for initial values

    # Calculate option value for each point on the grid
    for i in range(time_steps):
        for j in range(price_steps):
            # Get S and T_remain from the meshgrid for this point
            current_S = P_grid[i, j]
            t_remain = T_grid[i, j]
            # Calculate value using binomial tree (adjust N for performance vs accuracy)
            V_grid[i, j] = binomial_tree_option_price(current_S, K, t_remain, r, sigma, N=100,
                                          option_type=option_type, american=(style == 'american'))

    return P_grid, T_grid, V_grid

def generate_volatility_surface_data(S0, K, T, base_sigma, price_steps=30, time_steps=30):
    """Generates artificial data for a 3D volatility surface."""
    price_range = np.linspace(S0 * 0.75, S0 * 1.25, price_steps) # Range of strikes
    time_range = np.linspace(max(T / 20, 0.01), T * 1.2, time_steps) # Range of times (avoiding zero)
    P_grid, T_grid = np.meshgrid(price_range, time_range)
    IV_grid = np.zeros_like(P_grid)

    for i in range(time_steps):
        for j in range(price_steps):
            s = P_grid[i, j]
            t = T_grid[i, j]
            moneyness = np.log(s / K) # Log-moneyness

            # --- Artificial Volatility Components ---
            # 1. Smile: Quadratic, higher IV away from ATM, steeper for shorter T
            smile = 0.5 * (moneyness**2) / np.sqrt(t + 0.1)
            # 2. Skew: Linear, lower IV for higher strikes (common in equity options)
            skew = -0.25 * moneyness
            # 3. Term Structure: Slightly lower IV for longer T (can be adjusted)
            term = 0.03 * np.exp(-t * 2)
            # 4. Base Level
            iv = base_sigma + smile + skew + term

            # Ensure IV is within a reasonable range (e.g., 5% to 150%)
            IV_grid[i, j] = max(0.05, min(iv, 1.50))

    return P_grid, T_grid, IV_grid


# --- Plotting Functions for Heatmap and 3D Surface ---


def plot_profit_heatmap(parent_window, prices, times, profit_m, percent_m, day_lbls, price_lbls, premium,
                        option_type, strike, title="Profit/Loss Heatmap", chance_of_profit=None, dark_mode=False):
    """Plots the Profit/Loss heatmap with toggles, metrics, full screen, and contract multiplier."""
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import seaborn as sns
    import tkinter as tk
    from tkinter import ttk
    import numpy as np

    bg_color = "#1e1e1e" if dark_mode else "#f0f0f0"
    fg_color = "#ffffff" if dark_mode else "#000000"

    if dark_mode:
        plt.style.use('dark_background')
    else:
        plt.style.use('default')

    root_window = parent_window.winfo_toplevel()
    frame = tk.Frame(parent_window, bg=bg_color)
    frame.pack(fill=tk.BOTH, expand=True)

    contract_multiplier = tk.DoubleVar(value=1.0)
    view_state = {"view": "dollar", "canvas": None, "fig": None, "fullscreen": False}

    def update_heatmap():
        if view_state["canvas"]:
            view_state["canvas"].get_tk_widget().destroy()

        fig, ax = plt.subplots(figsize=(10, 8))

        multiplier = contract_multiplier.get() * 100
        data = profit_m * multiplier if view_state["view"] == "dollar" else percent_m
        label = 'Profit ($)' if view_state["view"] == "dollar" else 'Profit (%)'
        fmt = ".2f" if view_state["view"] == "dollar" else ".1f"

        if view_state["view"] == "dollar":
            vmin, vmax = -premium * multiplier, np.nanmax(data)
        else:
            vmin, vmax = -100.0, np.nanmax(data)

        sns.heatmap(data, cmap='RdYlGn', ax=ax, annot=True, fmt=fmt,
                    xticklabels=price_lbls, yticklabels=day_lbls,
                    linewidths=0.5, linecolor='black',
                    cbar_kws={'label': label}, vmin=vmin, vmax=vmax)

        ax.set_title(f"{option_type.capitalize()} Option Profitability | Strike=${strike:.2f}")
        ax.set_xlabel("Underlying Price")
        ax.set_ylabel("Days Remaining")
        ax.tick_params(axis='x', rotation=45, labelsize='small')
        ax.tick_params(axis='y', labelsize='small')

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        view_state["canvas"] = canvas
        view_state["fig"] = fig

    def toggle_view():
        view_state["view"] = "percent" if view_state["view"] == "dollar" else "dollar"
        toggle_btn.config(text="Switch to $ View" if view_state["view"] == "percent" else "Switch to % View")
        update_heatmap()

    def toggle_fullscreen():
        view_state["fullscreen"] = not view_state["fullscreen"]
        root_window.attributes("-fullscreen", view_state["fullscreen"])
        fullscreen_btn.config(text="Exit Full Screen" if view_state["fullscreen"] else "Full Screen")

    def apply_contracts(event=None):
        update_heatmap()
        update_metrics()

    def update_metrics():
        for widget in metrics_frame.winfo_children():
            widget.destroy()

        contracts = contract_multiplier.get()
        multiplier = contracts * 100

        net_debit = premium * multiplier
        max_loss = net_debit
        max_profit = "Infinite"
        breakeven_price = strike + premium if option_type == 'call' else strike - premium
        breakeven_text = f"Above ${breakeven_price:.2f}" if option_type == 'call' else f"Below ${breakeven_price:.2f}"

        prob_text = f"{chance_of_profit*100:.1f}%" if isinstance(chance_of_profit, (float, int)) else "--%"

        metrics = [
            ("CONTRACTS:", f"{contracts:.2f}"),
            ("NET DEBIT:", f"${net_debit:.2f}  (${premium:.2f} × {int(multiplier)} shares)"),
            ("MAX LOSS:", f"${max_loss:.2f}"),
            ("MAX PROFIT:", max_profit),
            ("CHANCE OF PROFIT:", prob_text),
            ("BREAKEVEN:", breakeven_text)
        ]

        for label, value in metrics:
            row = tk.Frame(metrics_frame)
            row.pack(side=tk.LEFT, padx=10)
            tk.Label(row, text=label, font=("Helvetica", 10, "bold"), anchor="w").pack()
            tk.Label(row, text=value, font=("Helvetica", 10), anchor="w").pack()

    # --- Metrics + Input ---
    input_row = tk.Frame(frame)
    input_row.pack(pady=(10, 5))

    tk.Label(input_row, text="Contracts (can be fractional): ").pack(side=tk.LEFT)
    entry = ttk.Entry(input_row, textvariable=contract_multiplier, width=7)
    entry.pack(side=tk.LEFT)
    entry.bind("<Return>", apply_contracts)

    metrics_frame = tk.Frame(frame)
    metrics_frame.pack(pady=5)

    # --- Button Frame ---
    button_frame = tk.Frame(frame)
    button_frame.pack(pady=5)

    toggle_btn = ttk.Button(button_frame, text="Switch to % View", command=toggle_view)
    toggle_btn.pack(side=tk.LEFT, padx=5)

    fullscreen_btn = ttk.Button(button_frame, text="Full Screen", command=toggle_fullscreen)
    fullscreen_btn.pack(side=tk.LEFT, padx=5)

    update_metrics()
    update_heatmap()

def plot_option_surface_3d(parent_window, P_grid, T_grid, V_grid, option_type, strike, title="3D Option Value Surface", educational_mode=False, dark_mode=False):

    if dark_mode:
        plt.style.use('dark_background')
    else:
        plt.style.use('default')
    """Plots the 3D Option Value surface in the provided Tkinter window/frame."""
    fig, canvas = _setup_plot_embedding(parent_window, fig_size=(9, 7))
    ax = fig.add_subplot(111, projection='3d')

    # Convert time remaining (years) to days remaining for the axis label
    T_days_grid = T_grid * 365

    # Check if V_grid contains valid data
    if np.isnan(V_grid).all():
        ax.text2D(0.5, 0.5, "No valid surface data to display.", transform=ax.transAxes, ha='center', va='center')
    else:
        # Plot the surface, handling potential NaNs in V_grid
        surf = ax.plot_surface(P_grid, T_days_grid, V_grid, cmap='viridis', edgecolor='none', antialiased=True, alpha=0.9, rcount=100, ccount=100) # Increased count for smoothness

        # Add a color bar which maps values to colors
        # fig.colorbar(surf, shrink=0.5, aspect=5, label='Option Value ($)') # Causes issues with TkAgg sometimes

        # Formatting
        ax.set_title(f'{option_type.capitalize()} Option Value | Strike=${strike:.2f}')
        ax.set_xlabel('Underlying Price ($)')
        ax.set_ylabel('Days Remaining')
        ax.set_zlabel('Option Value ($)')

        # Improve view angle and axis limits
        ax.view_init(elev=25., azim=-65) # Adjust elevation and azimuth
        ax.dist = 11 # Zoom level

        # Set limits based on data range, handling potential NaNs
        if not np.isnan(V_grid).all():
            valid_V = V_grid[np.isfinite(V_grid)]
            z_min = np.min(valid_V) if len(valid_V) > 0 else 0
            z_max = np.max(valid_V) if len(valid_V) > 0 else 1
            ax.set_zlim(z_min, z_max * 1.05) # Set Z limit based on calculated values

        if educational_mode:
            ax.text2D(0.05, 0.92, "📉 Time Decay: Value drops as expiry nears", transform=ax.transAxes, fontsize=10, color='black')
            ax.text2D(0.05, 0.88, "⚡ Volatility lifts value: More movement = more potential profit", transform=ax.transAxes, fontsize=10, color='black')
            ax.text2D(0.05, 0.84, "📈 Moneyness: Deep ITM options have high intrinsic value", transform=ax.transAxes, fontsize=10, color='black')
            

        # Add grid lines for better perception
        ax.xaxis._axinfo["grid"]['linestyle'] = ":"
        ax.yaxis._axinfo["grid"]['linestyle'] = ":"
        ax.zaxis._axinfo["grid"]['linestyle'] = ":"

    fig.tight_layout()
    canvas.draw()

def plot_volatility_surface_3d(plot_frame, P_grid, T_grid, IV_grid, title="3D Volatility Surface", dark_mode=False):
    """Plots the 3D Implied Volatility surface in the provided Tkinter frame."""
    if dark_mode:
        plt.style.use('dark_background')
        fig_bg = '#1e1e1e'
        text_fg = '#ffffff'
    else:
        plt.style.use('default')
        fig_bg = '#f0f0f0'
        text_fg = '#000000'

    fig = plt.Figure(figsize=(9, 7), dpi=100, facecolor=fig_bg)
    ax = fig.add_subplot(111, projection='3d', facecolor=fig_bg)

    T_days_grid = T_grid * 365 # Convert time to days for the axis

    # Check if V_grid contains valid data
    if np.isnan(IV_grid).all():
        ax.text2D(0.5, 0.5, "No valid surface data to display.", transform=ax.transAxes, ha='center', va='center', color=text_fg)
    else:
        # Plot the surface using coolwarm colormap (Blue=Low, Red=High)
        surf = ax.plot_surface(P_grid, T_days_grid, IV_grid * 100, cmap='jet', edgecolor='none', antialiased=True)

        # Add a color bar
        cbar = fig.colorbar(surf, shrink=0.5, aspect=5, label='Implied Volatility (%)')
        cbar.ax.yaxis.label.set_color(text_fg)
        cbar.ax.tick_params(axis='y', colors=text_fg)

        # Formatting
        ax.set_title(title, color=text_fg)
        ax.set_xlabel('Strike Price ($)', color=text_fg)
        ax.set_ylabel('Days Remaining', color=text_fg)
        ax.set_zlabel('Implied Volatility (%)', color=text_fg)
        ax.tick_params(axis='x', colors=text_fg)
        ax.tick_params(axis='y', colors=text_fg)
        ax.tick_params(axis='z', colors=text_fg)

        # Make panes transparent and set edge color
        ax.xaxis.pane.fill = False
        ax.yaxis.pane.fill = False
        ax.zaxis.pane.fill = False
        ax.xaxis.pane.set_edgecolor('grey' if dark_mode else '#dddddd')
        ax.yaxis.pane.set_edgecolor('grey' if dark_mode else '#dddddd')
        ax.zaxis.pane.set_edgecolor('grey' if dark_mode else '#dddddd')

        # Set view angle and zoom
        ax.view_init(elev=28., azim=-125) # Adjust for a good view
        ax.dist = 11

    # Create Tkinter canvas and add toolbar
    canvas = FigureCanvasTkAgg(fig, master=plot_frame)
    canvas.draw()
    canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

    toolbar_frame = tk.Frame(plot_frame, bg=fig_bg) # Match background
    toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)
    toolbar = NavigationToolbar2Tk(canvas, toolbar_frame)
    toolbar.update()

    # Apply theme to toolbar
    if dark_mode:
        toolbar.configure(background="#1e1e1e")
        for child in toolbar.winfo_children():
            try: child.configure(background="#1e1e1e", foreground="#f0f0f0")
            except: pass
    else:
         toolbar.configure(background="#f0f0f0")
         for child in toolbar.winfo_children():
            try: child.configure(background="#f0f0f0", foreground="#000000")
            except: pass
# --- End of MonteCarloSimulation.py ---