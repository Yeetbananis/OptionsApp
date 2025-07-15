# =========================
# Standard Library Imports
# =========================
import sys
import os
import subprocess
import threading
import multiprocessing
import time  # For small delay in animation
import traceback  # For detailed error logging
import json
import warnings
import logging
import queue
import datetime as dt
from pathlib import Path

# Configure logging at the very beginning of the application
logging.basicConfig(
    level=logging.INFO, # Or logging.DEBUG for more verbosity
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout), # Log to console
        # logging.FileHandler("app_errors.log") # Optionally log to a file
    ]
)
# --- END Logging Configuration ---


# -----------------------------------------------------------------
# Ensure the project root (…/OptionPredictor) is on sys.path so that
# sibling packages like `ui`, `core`, `data` import cleanly even when
# you launch with:  python app/OptionsApp.py
# -----------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Suppress benign warnings
warnings.filterwarnings("ignore", category=UserWarning, module="mplfinance")
warnings.filterwarnings("ignore", message="Could not import cached_binomial_price")

# ==============================
# Third-Party Library Imports
# ==============================
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np  # Numeric operations, default values or checks
import pandas as pd

#External classes
from ui.dashboard                 import HomeDashboard
from data.home_data_manager       import HomeDataManager
from data.earnings_data_manager   import EarningsDataManager
from ui.DockingPlotWindow         import DockingPlotWindow
from app.AnalysisPersistence      import AnalysisPersistence
from ui.LoadAnalysisWindow        import LoadAnalysisWindow
from ui.LoadingScreen             import LoadingScreen
from ui.DebugConsoleWindow        import DebugConsoleWindow

# ====================
# Local Module Imports
# ====================
from core.engine.idea_engine        import IdeaEngine
from core.models.idea_models        import Idea
from ui.idea_suite_view             import IdeaSuiteView
from app.llm_helper                 import LLMHelper
from ui.StockChartWindow            import StockChartWindow
from ui.TokenTracker                import TokenUsageTracker
from core.engine.strategy_builder   import StrategyBuilderWindow 


import sys
from pathlib import Path
try:
    # This works when running from source code
    project_root = Path(__file__).resolve().parent.parent
except NameError:
    # This is a fallback for some bundled environments where __file__ is not defined
    project_root = Path(os.path.abspath(".")).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))



def configure_global_styles(theme: str):
    """
    Apply *every* ttk style rule for light vs dark.
    Must be called *before* you re-skin each window.
    """
    style = ttk.Style()
    style.theme_use('clam')

    if theme == 'dark':
        bg, fg           = "#0f0f0f", '#ffffff'
        entry_bg         = '#0f0f0f'
        button_bg        = "#3B3939"
        header_bg        = "#0f0f0f"
        combobox_bg      = entry_bg
        notebook_sel_bg  = "#0f0f0f"
        tree_bg, field_bg= entry_bg, entry_bg
        calendar_bg      = "#0f0f0f"
        calendar_fg      = "#ffffff"
        calendar_select  = "#2e7d32"
        progressbar_trough_color = "#3c3c3c"
        progressbar_bar_color = "#138317" # Example green
        #profit_bg        = "#2e7d32"  # Trade log profit color
        #loss_bg          = "#c62828"  # Trade log loss color
    else:
        bg, fg           = '#f0f0f0', '#000000'
        entry_bg         = '#ffffff'
        button_bg        = '#e0e0e0'
        header_bg        = '#d9d9d9'
        combobox_bg      = entry_bg
        notebook_sel_bg  = '#ffffff'
        tree_bg, field_bg= entry_bg, entry_bg
        calendar_bg      = "#ffffff"
        calendar_fg      = "#000000"
        calendar_select  = "#1976d2"
        progressbar_trough_color = "#e0e0e0"
        progressbar_bar_color = "#4caf50" # Example green
        #profit_bg        = "#a5d6a7"  # Trade log profit color
        #loss_bg          = "#ef9a9a"  # Trade log loss color

    # Base
    style.configure('.', background=bg, foreground=fg, font=('Segoe UI', 9))

    # Frames & Labelframes
    style.configure('TFrame', background=bg)
    style.configure('TLabelframe', background=bg, foreground=fg)
    style.configure('TLabelframe.Label', background=bg, foreground=fg)

    # Labels
    style.configure('TLabel', background=bg, foreground=fg)

    # Buttons
    style.configure('TButton', background=button_bg, foreground=fg)
    style.map('TButton', background=[('active', header_bg)])

    # Checkbuttons & Radiobuttons
    style.configure('TCheckbutton', background=bg, foreground=fg)
    style.configure('TRadiobutton', background=bg, foreground=fg)

    style.configure(".", background=bg, foreground=fg) # Sets default for all ttk
    style.configure("TFrame", background=bg)
    style.configure("TLabelframe", background=bg, foreground=fg)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)

    # Entries
    style.configure('TEntry', fieldbackground=entry_bg, foreground=fg)

    # Comboboxes
    style.configure('TCombobox', fieldbackground=combobox_bg, foreground=fg, arrowcolor=fg)
    style.map('TCombobox',
              fieldbackground=[('readonly', combobox_bg)],
              foreground=[('readonly', fg)])

    # Notebook tabs
    style.configure('TNotebook', background=bg)
    style.configure('TNotebook.Tab', background=bg, foreground=fg)
    style.map('TNotebook.Tab',
              background=[('selected', notebook_sel_bg)],
              foreground=[('selected', fg)])

    # Treeview
    style.configure('Treeview', background=tree_bg, fieldbackground=field_bg, foreground=fg)
    style.configure('Treeview.Heading', background=header_bg, foreground=fg)
    style.map('Treeview.Heading', background=[('active', header_bg)])
    style.map('Treeview', background=[('selected', '#007acc')], foreground=[('selected', '#ffffff')])
    # Trade log profit/loss tags
    #style.configure('profit.Treeview', background=profit_bg)
    #style.configure('loss.Treeview', background=loss_bg)

    # Calendar (tkcalendar)
    style.configure('Calendar', background=calendar_bg, foreground=calendar_fg)
    style.configure('Calendar.Month', background=calendar_bg, foreground=calendar_fg)
    style.configure('Calendar.Selected', background=calendar_select, foreground=fg)
    style.map('Calendar', selectbackground=[('selected', calendar_select)])

    
    # --- TProgressbar (or modify if you have it) ---
    style.configure("TProgressbar",
                troughcolor=progressbar_trough_color,
                bordercolor=progressbar_trough_color,
                background=progressbar_bar_color
               )
    # -----------------------------------------------------------

    style.configure(  # Invisible frame for hitbox
        "Hitbox.TFrame",
        background=style.lookup("TFrame", "background")  # invisible
    )



def calculate_binomial_greeks(S, K, T, r, sigma, option_type='call', N=500):
    # --- Safe import for cached_binomial_price -----------------------------------
    try:
        from core.engine.MonteCarloSimulation import cached_binomial_price          
    except Exception:                                                   
        # minimal Black-Scholes fallback so the rest of the app still runs
        from math import exp, log, sqrt
        from scipy.stats import norm
        def cached_binomial_price(S, K, T, r, sigma, *_, option_type="call", **__):
            if T <= 0 or sigma <= 0:
                return max(0.0, S-K) if option_type=="call" else max(0.0, K-S)
            d1 = (log(S/K)+(r+0.5*sigma**2)*T)/(sigma*sqrt(T))
            d2 = d1 - sigma*sqrt(T)
            if option_type=="call":
                return S*norm.cdf(d1)-K*exp(-r*T)*norm.cdf(d2)
            return K*exp(-r*T)*norm.cdf(-d2)-S*norm.cdf(-d1)

    
    # Adjust N based on T to avoid tiny dt
    N = min(N, max(50, int(T * 365 * 10)))  # At least 50 steps, scale with T
    eps = 0.01 * S           # small change in price
    eps_vol = 0.01           # small change in volatility
    eps_rate = 0.0001        # small change in rate
    eps_time = min(1 / 365, T / 10)  # Dynamic eps_time to avoid negative T
    
    # Clear cache to prevent stale results
    cached_binomial_price.cache_clear()
    
    def price(s, k, t, r_, sig):
        t = max(t, 1e-3)  # Larger minimum time to avoid numerical issues
        print(f"Calling cached_binomial_price(s={s:.6f}, k={k:.6f}, t={t:.6f}, r={r_:.6f}, sig={sig:.6f}, N={N}, option_type={option_type}, american=True)")
        result = cached_binomial_price(s, k, t, r_, sig, N=N, option_type=option_type, american=True)
        if np.isnan(result):
            print("Warning: NaN result from cached_binomial_price")
        return result

    base = price(S, K, T, r, sigma)
    print(f"Base Price: {base:.6f}")

    price_up = price(S + eps, K, T, r, sigma)
    price_down = price(S - eps, K, T, r, sigma)
    delta = (price_up - price_down) / (2 * eps)
    print(f"Delta Calculation: ({price_up:.6f} - {price_down:.6f}) / (2*{eps:.4f}) = {delta:.6f}")

    gamma = (price_up - 2 * base + price_down) / (eps ** 2)
    print(f"Gamma Calculation: ({price_up:.6f} - 2*{base:.6f} + {price_down:.6f}) / ({eps:.4f}^2) = {gamma:.6f}")

    price_vega_up = price(S, K, T, r, sigma + eps_vol)
    price_vega_down = price(S, K, T, r, sigma - eps_vol)
    vega = (price_vega_up - price_vega_down) / (2 * eps_vol) / 100
    print(f"Vega Calculation: ({price_vega_up:.6f} - {price_vega_down:.6f}) / (2*{eps_vol:.4f}) = {vega:.6f}")

    price_theta = price(S, K, T - eps_time, r, sigma)
    theta = (price_theta - base) / eps_time / 100
    print(f"Theta Calculation: ({price_theta:.6f} - {base:.6f}) / ({eps_time:.6f}) = {theta:.6f}")

    price_rho_up = price(S, K, T, r + eps_rate, sigma)
    price_rho_down = price(S, K, T, r - eps_rate, sigma)
    rho = (price_rho_up - price_rho_down) / (2 * eps_rate) 
    print(f"Rho Calculation: ({price_rho_up:.6f} - {price_rho_down:.6f}) / (2*{eps_rate:.6f}) = {rho:.6f}")

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 4),
        "vega": round(vega, 4),
        "theta": round(theta, 4),
        "rho": round(rho / 100, 4)  # scaled to per 1% rate move
    }


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT,
            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
            font=("Helvetica", 9), wraplength=220
        )
        label.pack(ipadx=6, ipady=3)

    def update(self, text: str):
        self.text = text
        # if the tip is showing, refresh it
        if self.tipwindow:
            self.hide_tooltip()
            self.show_tooltip()

    def hide_tooltip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None



class SettingsManager:
    """Tiny JSON persistence for user prefs across app restarts."""
    from pathlib import Path
    _FILE = Path.home() / ".option_analyzer_settings.json"

    _DEFAULTS = {
        "user_name": "Trader",
        "theme": "dark",
        "timezone": "America/Vancouver",
        "default_ticker": "SPY",
        "watchlist": "AAPL|MSFT|AMZN|NVDA|GOOGL|TSLA|META|BBAI",
        "marquee_speed": 0.5,
        "refresh_interval": 30,
        "enable_bounce_overlay": False,
         "earnings_data": {}
    }


    def __init__(self):
        self.data = self._DEFAULTS.copy()
        if self._FILE.exists():
            try:
                # Load existing settings
                loaded_data = json.loads(self._FILE.read_text())
                # Only update specific known keys to avoid stale/corrupt data affecting new defaults
                for key, default_val in self._DEFAULTS.items():
                    if key in loaded_data:
                        self.data[key] = loaded_data[key]
                # Special handling for earnings_data: ensure it's a dict
                if not isinstance(self.data.get("earnings_data"), dict):
                    self.data["earnings_data"] = {}
            except Exception:
                logging.warning("Corrupt settings file, falling back to defaults.")
                self.data = self._DEFAULTS.copy() # Fallback to defaults on corruption

    def save(self):
        try:
            self._FILE.write_text(json.dumps(self.data))
        except Exception:
            print("⚠ Could not write settings file.")

    # convenient shortcuts
    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        self.data[k] = v
        self.save()


# Import logic functions from the separate file
try:
    from core.engine.MonteCarloSimulation import (
        fetch_ticker_data, calculate_drift_and_volatility,
        calculate_simulation_data, plot_simulation_paths,
        #binomial_tree_option_price,
        plot_distribution,
        generate_profit_heatmap_data, plot_profit_heatmap, 
        generate_option_surface_data, plot_option_surface_3d,
        calculate_trigger_stats_correctly as recalculate_trigger_price_correctly,
        set_max_paths, cached_binomial_price, 
        generate_volatility_surface_data,
        plot_volatility_surface_3d,   
        #cached_lsm_price

    )
except ImportError:
    messagebox.showerror("Import Error", "Could not find 'MonteCarloSimulation.py'. Make sure it's in the same directory as this script.")
    exit()

class OptionAnalyzerApp:
    def __init__(self, root):
        # 1. PRIMARY SETUP (Settings must be first)
        self.settings = SettingsManager()
        self.current_theme = self.settings.get("theme", "light")
        self.is_dark_mode_var = tk.BooleanVar(value=(self.current_theme == "dark"))

        # 2. ROOT WINDOW CONFIGURATION
        self.root = root
        self.root.title("Option Analyzer")
        self.root.geometry("1200x800") # Use a larger default size
        self.root.minsize(900, 700)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 3. CORE COMPONENTS INITIALIZATION
        self.data_mgr = HomeDataManager()
        self.earnings_data_mgr = EarningsDataManager()
        # Create a single token tracker for the entire application session
        self.token_tracker = TokenUsageTracker()
        # Pass the tracker to the LLMHelper
        self.llm = LLMHelper(token_tracker=self.token_tracker)
        self.idea_engine = IdeaEngine()
        self.user_name = self.settings.get("user_name", "Trader")




        # --- Debug Console Initialization (NEW) ---
        self.debug_console_window = DebugConsoleWindow(self.root, theme=self.current_theme)
        self.debug_console_window.hide_window() # Start hidden
        self.debug_console_window.start_redirection() # Start redirecting output early
        # --- END NEW --

        # 4. STATE AND WINDOW MANAGEMENT
        self.input_data = {}
        self.child_windows = []
        self.theme_callbacks = []
        self.strategy_tester_instance = None
        self.docking_window_instance = None
        self.strategy_testers = []
        self.analysis_persistence = AnalysisPersistence()
        self.initial_load_tasks = ['indices', 'watchlist', 'news', 'fng', 'earnings'] # NEW: Add 'earnings'
        self.loading_screen = None
        self.loading_complete = False
        self._strat_builder_win = None

        # Earnings fetching queue and state
        self._earnings_fetch_queue = queue.Queue()
        self._earnings_fetch_thread = None
        self._fetching_earnings = False
        self._pending_earnings_symbols = set() # NEW: Track symbols to fetch

        # Animation state
        self._loading_job = None
        self.is_loading = False
        self.animation_chars = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]
        self.animation_step = 0

        # 5. APPLY GLOBAL STYLES (Crucial step)
        # This function should contain ALL style configurations for the app
        configure_global_styles(self.current_theme)

        # --- Main Layout ---
        self.main_frame = ttk.Frame(root)
        self.main_frame.pack(expand=True, fill=tk.BOTH)

        # Instead of creating the dashboard directly, start the loading sequence.
        # The loading sequence will create and reveal the dashboard when ready.
        self.root.after(100, self.start_loading_sequence)

        # NEW: Start polling the earnings queue
        self.root.after(200, self._poll_earnings_queue)

        # 7. STATUS BAR
        self.status_label = ttk.Label(self.root, text="Ready.", style="Status.TLabel", anchor="center")
        self.status_label.pack(fill="x", pady=4, padx=5)

        # 8. EXPOSE HELPERS (Optional but good practice)
        self.root.apply_theme_to_window = self.apply_theme_to_window


    def theme_settings(self):
        return {
            "light": {
                "bg": "#f0f0f0",
                "fg": "#000000",
                "entry_bg": "#ffffff"
            },
            "dark": {
                "bg": "#0f0f0f",
                "fg": "#ffffff",
                "entry_bg": "#3c3c3c"
            }
        }[self.current_theme]


    def apply_theme_to_window(self, window):
        """Central recursive theming for every widget in `window`."""
        try:
            if not window.winfo_exists():
                return
        except:
            return

        # derive our colors from the current_theme
        bg       = "#0f0f0f" if self.current_theme == 'dark' else "#f0f0f0"
        fg       = "#ffffff" if self.current_theme == 'dark' else "#000000"
        entry_bg = "#3c3c3c" if self.current_theme == 'dark' else "#ffffff"

        # theme this container
        try:
            window.configure(bg=bg)
        except:
            pass

        # walk all children
        for w in window.winfo_children():
            # ttk widgets respond to style → (we already set that globally)
            # raw tk widgets need explicit bg/fg
            if isinstance(w, (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton)):
                try: w.configure(bg=bg, fg=fg)
                except: pass
            if isinstance(w, tk.Entry):
                try: w.configure(bg=entry_bg, fg=fg)
                except: pass
            if isinstance(w, tk.Text):
                try: w.configure(bg=entry_bg, fg=fg)
                except: pass

            # recurse into frames & toplevels
            if hasattr(w, 'winfo_children'):
                self.apply_theme_to_window(w)

        # Call apply_custom_theme if the window supports it
        try:
            if hasattr(window, 'apply_custom_theme'):
                window.apply_custom_theme()
        except:
            pass


    def start_loading_sequence(self):
        """Shows the loading screen and starts the two independent loops."""
        self.loading_screen = LoadingScreen(self.root, self.user_name, theme=self.current_theme)
        self.root.withdraw()
        
        # Create the dashboard in the background
        self.dashboard = HomeDashboard(self.main_frame, self)
        
        # Start the two loops
        self._candle_animation_loop()
        self._loading_status_monitor()

    def _candle_animation_loop(self):
        """
        A simple, robust loop that ONLY draws candles. It checks the finale
        flag on the loading screen to know when to stop permanently.
        """
        if not self.loading_screen or not self.loading_screen.winfo_exists():
            return
        
        # **FIX**: Check the "kill switch" flag before drawing a new candle.
        if self.loading_screen.is_finale_triggered:
            return # Stop the loop permanently.

        self.loading_screen.add_new_candle()
        self.root.after(1, self._candle_animation_loop)

    def _loading_status_monitor(self):
        """
        Checks for data loading progress OR proceeds after a timeout
        to ensure the app always loads, even when offline.
        """
        # Set a total timeout for the initial load (e.g., 12 seconds)
        MAX_LOAD_TIME = 12000 # milliseconds
        
        start_time = getattr(self, "_loading_start_time", time.time())
        if not hasattr(self, "_loading_start_time"):
            self._loading_start_time = start_time
        
        elapsed_time = (time.time() - start_time) * 1000

           # --- Check for completion or timeout ---
        if not self.initial_load_tasks or elapsed_time > MAX_LOAD_TIME:
            if not self.loading_complete:
                self.loading_complete = True
                
                # When loading finishes, call the single, reliable final sequence method.
                self._trigger_final_sequence()

            return # Stop this monitoring loop
        else:
            # --- Still loading ---
            total_tasks = 4.0
            progress = (total_tasks - len(self.initial_load_tasks)) / total_tasks
            if self.loading_screen and self.loading_screen.winfo_exists():
                self.loading_screen.update_progress_bar(progress)
            
            # Check again soon
            self.root.after(100, self._loading_status_monitor)

    def _trigger_final_sequence(self):
        """Forces dashboard render, then runs the finale animation and reveals the app."""
        if not (self.loading_screen and self.loading_screen.winfo_exists()):
            self.show_main_window()
            return

        # 1. Force the dashboard to process all pending geometry and drawing tasks.
        #    This is the key step that happens invisibly behind the loading screen.
        self.dashboard.update_idletasks()

        # 2. Now that the dashboard UI is ready, run the finale on the loading screen.
        self.loading_screen.update_progress_bar(1.0)
        self.loading_screen.trigger_pre_climax_dip()
        self.loading_screen.animate_take_profit()

        # 3. Schedule the reveal of the main window *after* the animation is complete.
        #    The animation takes about 1.2s, so 1500ms is a safe delay.
        self.root.after(1200, self.loading_screen.fade_out_and_close)
        self.root.after(1500, self.show_main_window)


    def on_initial_load_complete(self, task_name):
        """Called by dashboard components when they finish their first data fetch."""
        if task_name in self.initial_load_tasks:
            self.initial_load_tasks.remove(task_name)
            
    def show_main_window(self):
        """Makes the main application window visible and places the dashboard."""
        self.dashboard.pack(expand=True, fill=tk.BOTH)
        self.root.deiconify() # Reveal the main window

    def set_status(self, text, color=None):
        """Updates the status label. Uses default label foreground if color is None."""
        try:
            if color:
                self.status_label.config(text=text, foreground=color)
            else:
                # Reset to default foreground color
                default_fg = ttk.Style().lookup('Status.TLabel', 'foreground')
                self.status_label.config(text=text, foreground=default_fg)
            self.root.update_idletasks() # Ensure GUI updates
        except tk.TclError:
             # Handle case where window might be destroyed during update
             print(f"Status update skipped (window closed?): {text}")


    # ------------------ spinner ------------------
    def animate_loading(self):
        if not self.is_loading or not self.root.winfo_exists():
            return                         # bail out if window already gone
        char = self.animation_chars[self.animation_step % len(self.animation_chars)]
        self.set_status(f"Running analysis {char}", "orange")
        self.animation_step += 1
        # store id so we can cancel it later
        self._loading_job = self.root.after(150, self.animate_loading)


    
    # ---------------------------------------------
    def _cancel_loading_animation(self):
        if self._loading_job is not None:
            try:
                self.root.after_cancel(self._loading_job)
            except Exception:
                pass
            self._loading_job = None
        self.is_loading = False

    def _configure_styles(self):
            """Defines all custom ttk styles for the application."""
            style = ttk.Style(self.root)
            
            # This style is for the section headers in the settings window.
            # Defining it here, once, prevents the "Layout not found" error.
            default_bg = style.lookup('TFrame', 'background')
            default_fg = style.lookup('TLabel', 'foreground')
            style.configure("Settings.TLabelFrame", background=default_bg)
            style.configure("Settings.TLabelFrame.Label", font=("Segoe UI Semibold", 10), background=default_bg, foreground=default_fg)
            
            # Define other custom styles used in the settings window
            style.configure("Pill.TButton", borderwidth=0)
            style.configure("Card.TFrame", relief='solid', borderwidth=1)
            style.configure("Accent.TButton", font=("Segoe UI", 9, "bold"))

 # ---------------- SETTINGS (Corrected & Cleaned) ----------------
    def open_settings_window(self):
        """
        Opens a settings window with a professional and organized layout.
        This version relies on globally pre-configured styles to prevent errors.
        """
        win = tk.Toplevel(self.root)
        win.title("⚙️ Settings")
        win.geometry("820x640")
        win.transient(self.root)
        win.grab_set()
        self.apply_theme_to_window(win)

        # --- Get theme colors ---
        style = ttk.Style(win)
        accent_color = "#0078d4"
        default_bg = style.lookup('TFrame', 'background')
        default_fg = style.lookup('TLabel', 'foreground')

        # --- Main Layout ---
        main_pane = ttk.PanedWindow(win, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        # --- Left: Category List ---
        category_list = tk.Listbox(main_pane, width=22, exportselection=False, relief=tk.FLAT, highlightthickness=0, font=("Segoe UI", 11))
        category_list.pack(fill=tk.Y, side=tk.LEFT)
        main_pane.add(category_list, weight=1)
        category_list.configure(background=default_bg, foreground=default_fg, selectbackground=accent_color, selectforeground="white")

        settings_area = ttk.Frame(main_pane, padding=(15, 5))
        main_pane.add(settings_area, weight=4)

        # --- Variables ---
        name_var = tk.StringVar(value=self.user_name)
        theme_var = tk.StringVar(value=self.current_theme)
        tz_var = tk.StringVar(value=self.settings.get("timezone"))
        ticker_var = tk.StringVar(value=self.settings.get("default_ticker"))
        interval_var = tk.IntVar(value=self.settings.get("refresh_interval"))
        speed_var = tk.DoubleVar(value=self.settings.get("marquee_speed", 1.5))
        bounce_enabled_var = tk.BooleanVar(value=self.settings.get('enable_bounce_overlay', False))
        
        frames = {}
        def show_frame(name):
            for f_widget in frames.values(): f_widget.pack_forget()
            frames[name].pack(fill=tk.BOTH, expand=True)
            for i, item in enumerate(category_list.get(0, tk.END)):
                if name in item:
                    category_list.selection_clear(0, tk.END)
                    category_list.selection_set(i)
                    category_list.activate(i)
                    break
        category_list.bind('<<ListboxSelect>>', lambda e: show_frame(category_list.get(category_list.curselection())))

        # ======================================================================
        #  PANEL 1: GENERAL SETTINGS
        # ======================================================================
        general_frame = ttk.Frame(settings_area)
        frames["👤 General"] = general_frame
        # **FIX**: Removed the problematic 'style' argument
        prefs_frame = ttk.LabelFrame(general_frame, text="User Preferences", padding=15)
        prefs_frame.pack(fill="x", padx=5, pady=5)
        prefs_frame.columnconfigure(1, weight=1)

        ttk.Label(prefs_frame, text="Display Name:").grid(row=0, column=0, sticky="w", pady=8, padx=5)
        ttk.Entry(prefs_frame, textvariable=name_var).grid(row=0, column=1, sticky="ew", pady=8)
        ttk.Label(prefs_frame, text="Theme:").grid(row=1, column=0, sticky="w", pady=8, padx=5)
        theme_buttons = ttk.Frame(prefs_frame)
        theme_buttons.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(theme_buttons, text="Light", variable=theme_var, value="light").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(theme_buttons, text="Dark", variable=theme_var, value="dark").pack(side="left")
        ttk.Label(prefs_frame, text="Timezone:").grid(row=2, column=0, sticky="w", pady=8, padx=5)
        tz_list = ["America/Vancouver", "America/New_York", "Europe/London", "Asia/Tokyo", "Australia/Sydney"]
        ttk.Combobox(prefs_frame, textvariable=tz_var, values=tz_list, state="readonly").grid(row=2, column=1, sticky="ew", pady=8)

        # ======================================================================
        #  PANEL 2: DASHBOARD SETTINGS
        # ======================================================================
        dashboard_frame = ttk.Frame(settings_area)
        frames["📊 Dashboard"] = dashboard_frame
        # **FIX**: Removed the problematic 'style' argument
        defaults_frame = ttk.LabelFrame(dashboard_frame, text="Dashboard & Animation", padding=15)
        defaults_frame.pack(fill="x", padx=5, pady=5)
        defaults_frame.columnconfigure(1, weight=1)
        
        def create_slider(parent, text, var, from_, to, format_str, row):
            ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=8, padx=5)
            slider_frame = ttk.Frame(parent)
            slider_frame.grid(row=row, column=1, sticky="ew", pady=8)
            slider_frame.columnconfigure(0, weight=1)
            val_label = ttk.Label(slider_frame, text=format_str.format(var.get()), width=4)
            val_label.grid(row=0, column=1, sticky="w", padx=(10, 0))
            ttk.Scale(slider_frame, from_=from_, to=to, orient="horizontal", variable=var, command=lambda v: val_label.config(text=format_str.format(float(v)))).grid(row=0, column=0, sticky="ew")

        ttk.Label(defaults_frame, text="Default Chart Ticker:").grid(row=0, column=0, sticky="w", pady=8, padx=5)
        ttk.Entry(defaults_frame, textvariable=ticker_var).grid(row=0, column=1, sticky="ew", pady=8)
        create_slider(defaults_frame, "Data Refresh (sec):", interval_var, 5, 300, "{:.0f}", 1)
        create_slider(defaults_frame, "Marquee Speed:", speed_var, 0.5, 8.0, "{:.1f}", 2)
        def _on_toggle_bouncer(): self.settings.set('enable_bounce_overlay', bounce_enabled_var.get()); self.dashboard.toggle_bounce_overlay()
        ttk.Checkbutton(defaults_frame, text="Enable 'Boredom Ball' Overlay", variable=bounce_enabled_var, command=_on_toggle_bouncer).grid(row=3, column=0, columnspan=2, sticky="w", pady=(15, 5), padx=5)

        # ======================================================================
        #  PANEL 3: WATCHLIST EDITOR
        # ======================================================================
        watchlist_panel = ttk.Frame(settings_area)
        frames["⭐ Watchlist"] = watchlist_panel
        # **FIX**: Removed the problematic 'style' argument
        watchlist_outer_frame = ttk.LabelFrame(watchlist_panel, text="Drag Tickers to Reorder", padding=15)
        watchlist_outer_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        canvas = tk.Canvas(watchlist_outer_frame, highlightthickness=0, bg=default_bg)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(watchlist_outer_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=scrollbar.set)
        watchlist_frame = ttk.Frame(canvas, padding=(0, 0, 15, 0))
        canvas.create_window((0, 0), window=watchlist_frame, anchor="nw")
        watchlist_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        watchlist_frame.columnconfigure(0, weight=1)

        chips, chip_frames = [], []
        drag_data = {"ghost": None, "placeholder": None, "widget": None}

        def on_drag_start(event, widget):
            widget.focus_force()
            ghost = tk.Toplevel(win)
            ghost.overrideredirect(True)
            ghost.attributes('-alpha', 0.85)
            # Use a default style that is guaranteed to exist
            ghost_label = ttk.Label(ghost, text=f"  {chips[chip_frames.index(widget)].get()}  ", style="TButton") 
            ghost_label.pack()
            ghost.geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
            
            placeholder = ttk.Frame(watchlist_frame, height=widget.winfo_height(), style="Card.TFrame")
            
            drag_data.update({"ghost": ghost, "placeholder": placeholder, "widget": widget})
            widget.grid_forget()
            placeholder.grid(row=chip_frames.index(widget), column=0, sticky="ew", pady=3)

        def on_drag_motion(event, widget):
            if not drag_data["ghost"]: return
            drag_data["ghost"].geometry(f"+{event.x_root + 15}+{event.y_root + 10}")

            y_target = watchlist_frame.winfo_pointery() - watchlist_frame.winfo_rooty()
            current_placeholder_row = drag_data["placeholder"].grid_info().get("row", 0)
            
            best_index = current_placeholder_row
            min_dist = float('inf')

            for i, child in enumerate(chip_frames):
                if child is drag_data["widget"]: continue
                dist = abs(child.winfo_y() + child.winfo_height() / 2 - y_target)
                if dist < min_dist:
                    min_dist = dist
                    insertion_point = child.winfo_y() + child.winfo_height() / 2
                    best_index = i if y_target < insertion_point else i + 1

            if best_index != current_placeholder_row:
                drag_data["placeholder"].grid(row=best_index)

        def on_drag_release(event, widget):
            if not drag_data["ghost"]: return
            drag_data["ghost"].destroy()
            
            new_index = drag_data["placeholder"].grid_info()["row"]
            drag_data["placeholder"].destroy()
            
            original_index = chip_frames.index(widget)
            chip_frames.pop(original_index)
            chip_frames.insert(new_index, widget)
            original_chip_var = chips.pop(original_index)
            chips.insert(new_index, original_chip_var)
            
            for i, f in enumerate(chip_frames): f.grid(row=i, column=0, sticky="ew", pady=3)
            drag_data.update({"ghost": None, "placeholder": None, "widget": None})

        def remove_chip(frame):
            idx = chip_frames.index(frame)
            removed_ticker = chips[idx].get().strip().upper() # Get ticker before popping
            chips.pop(idx); chip_frames.pop(idx)
            frame.destroy()
            for i, f in enumerate(chip_frames): f.grid(row=i, column=0, sticky="ew", pady=3)
            #Trigger earnings update on ticker removal
            self.settings.data["earnings_data"].pop(removed_ticker, None) # Remove from stored data
            self.dashboard.update_earnings_events() # Update dashboard's calendar

        # In OptionsApp.py

        def add_watchlist_chip(ticker=""):
            var = tk.StringVar(value=ticker)
            frame = ttk.Frame(watchlist_frame, style="Card.TFrame")
            frame.grid(row=len(chip_frames), column=0, sticky="ew", pady=3)
            
            handle = ttk.Label(frame, text="⠿", cursor="hand2", font=("Segoe UI", 12))
            handle.pack(side="left", padx=(8, 12), pady=8)
            entry = ttk.Entry(frame, textvariable=var) # Keep a reference to the entry
            entry.pack(side="left", fill='x', expand=True, pady=8)
            ttk.Button(frame, text="✕", width=2, style='Toolbutton', command=lambda f=frame: remove_chip(f)).pack(side="left", padx=(8, 8), pady=8)

            def on_ticker_entry_change(*args):
                updated_ticker = var.get().strip().upper()
                if updated_ticker:
                    self._add_to_pending_earnings_fetch(updated_ticker)
            var.trace_add("write", on_ticker_entry_change)

            # --- DEFINITIVE FIX: The first append call was removed from here ---

            # If a new empty chip is added, immediately mark for fetch if text is entered later
            if not ticker:
                self._add_to_pending_earnings_fetch(var.get().strip().upper())
                
                handle.bind("<ButtonPress-1>", lambda e, w=frame: on_drag_start(e, w))
                handle.bind("<B1-Motion>", lambda e, w=frame: on_drag_motion(e, w))
                handle.bind("<ButtonRelease-1>", lambda e, w=frame: on_drag_release(e, w))
                
            # The append now happens only once, outside the if block.
            chip_frames.append(frame)
            chips.append(var)

        for t in filter(None, (x.strip() for x in self.settings.get("watchlist", "").split("|"))): add_watchlist_chip(t)
        ttk.Button(watchlist_panel, text="＋ Add Ticker", style="Pill.TButton", command=lambda: add_watchlist_chip()).pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(10, 5))

        # --- Final Assembly ---
        for name in frames.keys(): category_list.insert(tk.END, name)
        show_frame("👤 General")

        # --- Bottom Action Buttons ---
        button_frame = ttk.Frame(win)
        button_frame.pack(side=tk.BOTTOM, fill='x', padx=15, pady=(5, 15))
        button_frame.columnconfigure(0, weight=1)
        ttk.Button(button_frame, text="⟳ Reset App", command=self.reset_app).grid(row=0, column=1, padx=5)
        
        def save_and_close():
            self.settings.set("user_name", name_var.get().strip() or "Trader")
            new_theme = theme_var.get()
            
            # Persist all other settings
            self.settings.set("timezone", tz_var.get())
            self.settings.set("default_ticker", ticker_var.get().strip().upper() or "SPY")
            self.settings.set("marquee_speed", float(speed_var.get()))
            self.settings.set("refresh_interval", interval_var.get())
            
            old_watchlist = set(filter(None, (x.strip().upper() for x in self.settings.get("watchlist", "").split("|"))))
            valid_tickers = [var.get().strip().upper() for var in chips if var.get().strip()]
            new_watchlist = set(valid_tickers)
            self.settings.set("watchlist", "|".join(valid_tickers) if valid_tickers else "SPY|^VIX")

            # Identify added/removed tickers to update earnings data
            added_tickers = new_watchlist - old_watchlist
            removed_tickers = old_watchlist - new_watchlist

            for ticker in removed_tickers:
                self.settings.data["earnings_data"].pop(ticker, None) # Remove from stored data

            for ticker in added_tickers:
                self._add_to_pending_earnings_fetch(ticker) # Schedule fetch for new tickers

            #  Destroy the settings window *before* applying the theme change
            win.destroy()
                
            # Now, apply theme change if needed, which will redraw the main app
            if new_theme != self.current_theme:
                self.is_dark_mode_var.set(new_theme == "dark")
                self.toggle_theme()
            
            # Refresh dashboard with potentially new settings
            if hasattr(self, "dashboard"):
                self.dashboard.update_refresh_interval(interval_var.get())
                self.dashboard._update_marquee_speed()
                self.dashboard._refresh()
                self.dashboard.update_earnings_events() # Force update earnings calendar

        ttk.Button(button_frame, text="Save & Close", command=save_and_close, style="Accent.TButton").grid(row=0, column=2, padx=5)
        win.bind("<Return>", lambda event: save_and_close())
        win.bind("<Escape>", lambda event: win.destroy())

    def save_settings(self):
        """Persist any changes in self.settings to disk."""
        try:
            self.settings.save()
        except Exception as e:
            print(f"⚠️ Failed to save settings: {e}")

    # NEW: Earnings fetching methods
    def _add_to_pending_earnings_fetch(self, symbol: str):
        """Adds a symbol to the queue for earnings data fetching."""
        symbol = symbol.upper()
        if symbol and symbol not in self.settings.get("earnings_data", {}) and symbol not in self._pending_earnings_symbols:
            self._pending_earnings_symbols.add(symbol)
            self._earnings_fetch_queue.put(symbol)
            self._start_earnings_fetch_thread_if_needed()

    def _start_earnings_fetch_thread_if_needed(self):
        """Starts the background thread for fetching earnings if it's not already running."""
        if not self._fetching_earnings:
            self._fetching_earnings = True
            self._earnings_fetch_thread = threading.Thread(target=self._earnings_fetch_worker, daemon=True)
            self._earnings_fetch_thread.start()
            logging.info("Started earnings fetch worker thread.")

    def _earnings_fetch_worker(self):
        """Worker function for fetching earnings data in a background thread."""
        while self._fetching_earnings:
            try:
                symbol = self._earnings_fetch_queue.get(timeout=1) # Wait for symbols for 1 second
                if symbol is None: # Sentinel value to stop thread
                    break

                # Check if we already have it from a previous launch and it's not too old
                stored_earnings = self.settings.get("earnings_data", {}).get(symbol)
                if stored_earnings:
                    next_date_str = stored_earnings.get("next_earnings_date")
                    if next_date_str:
                        next_date = dt.datetime.strptime(next_date_str, "%Y-%m-%d").date()
                        # If the stored date is in the future, and not older than, say, 30 days old from current date, consider it fresh
                        if next_date >= dt.date.today() and (dt.date.today() - next_date).days < 30:
                            logging.info(f"Using cached earnings data for {symbol} (next date {next_date_str}).")
                            self.root.after(0, self.dashboard.update_earnings_events) # Trigger UI update
                            self._pending_earnings_symbols.discard(symbol)
                            continue # Skip fetching if data is fresh

                logging.info(f"Fetching earnings for {symbol}...")
                data = self.earnings_data_mgr.get_earnings_data(symbol)
                if data:
                    current_earnings_data = self.settings.get("earnings_data", {})
                    current_earnings_data[symbol] = data
                    self.settings.set("earnings_data", current_earnings_data)
                    logging.info(f"Successfully fetched earnings for {symbol}. Next: {data.get('next_earnings_date')}")
                else:
                    logging.warning(f"Failed to fetch earnings for {symbol}.")
                    # Optionally store a placeholder for failed fetches to avoid constant retries
                    current_earnings_data = self.settings.get("earnings_data", {})
                    current_earnings_data[symbol] = {"next_earnings_date": None}
                    self.settings.set("earnings_data", current_earnings_data)

                self._pending_earnings_symbols.discard(symbol)
                self.root.after(0, self.dashboard.update_earnings_events) # Trigger UI update after each fetch
                self.root.after(0, lambda: self.on_initial_load_complete('earnings'))

            except queue.Empty:
                if not self._pending_earnings_symbols: # No more symbols to fetch
                    self._fetching_earnings = False
                    logging.info("Earnings fetch worker finished.")
                    break
            except Exception as e:
                logging.error(f"Error in earnings fetch worker: {e}")
                traceback.print_exc()
                self._pending_earnings_symbols.discard(symbol) # Ensure symbol is removed even on error
                self.root.after(0, self.dashboard.update_earnings_events) # Try to update UI even on error

    def _poll_earnings_queue(self):
        """Polls the earnings queue for any pending fetch requests."""
        if not self.root.winfo_exists():
            return

        # Trigger initial fetch for all watchlist items on app start
        if not self._fetching_earnings and not self._pending_earnings_symbols:
            watchlist_symbols = filter(None, (x.strip().upper() for x in self.settings.get("watchlist", "").split("|")))
            for sym in watchlist_symbols:
                self._add_to_pending_earnings_fetch(sym)

        self.root.after(1000, self._poll_earnings_queue) # Continue polling



    # ---------------- RESET ----------------
    def reset_app(self):
        ok = messagebox.askyesno("Reset App", "This will clear saved settings and restart the application.\nContinue?", parent=self.root)
        if not ok: return
        # 1. Clear settings file
        try:
            SettingsManager._FILE.unlink(missing_ok=True)
        except Exception:
            pass
        # 2. Relaunch self
        python = self._get_python_executable()
        os.execl(python, python, *sys.argv)

    def _toggle_fullscreen_input(self, window):
            is_full = window.attributes('-fullscreen')
            window.attributes('-fullscreen', not is_full)
            window.bind("<Escape>", lambda e: self._toggle_fullscreen_input(window))


    def launch_strategy_tester(self):
        """Launches the Strategy Tester window, ensuring only one instance is active."""
        if self.strategy_tester_instance and self.strategy_tester_instance.win.winfo_exists():
            self.strategy_tester_instance.win.lift()
            self.strategy_tester_instance.win.focus_force()
            return

        try:
            from core.engine.strategy_tester import StrategyTesterWindow # Keep import local
        except ImportError:
            messagebox.showerror("Error", "strategy_tester.py not found.")
            return

        try:
            tester = StrategyTesterWindow(self.root, self)
            self.strategy_tester_instance = tester # Store the current instance
            self.strategy_testers.append(tester)   # Keep for theme updates
            self.apply_theme_to_window(tester.win)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Strategy Tester:\n{e}")
            import traceback
            traceback.print_exc()

    def remove_strategy_tester(self, tester_instance):
        """Removes a closed tester window from the tracking list."""
        if tester_instance in self.strategy_testers:
            self.strategy_testers.remove(tester_instance)
        if self.strategy_tester_instance == tester_instance: 
            self.strategy_tester_instance = None

    def launch_stock_research_suite(self):
        """Launches the new Stock Research Suite window."""
        try:
            # Import the new suite locally to keep startup fast
            from ui.StockResearchSuite import StockResearchSuite
            
            # Check if an instance already exists
            if hasattr(self, "_research_suite_win") and self._research_suite_win.winfo_exists():
                self._research_suite_win.lift()
                self._research_suite_win.focus_force()
                return

            # Pass the theme and any necessary API keys from settings
            finnhub_key = "d114k6hr01qse6lf8c1gd114k6hr01qse6lf8c20" # You should ideally load this from settings
            suite = StockResearchSuite(parent=self.root, app_controller=self, theme=self.current_theme, finnhub_key=finnhub_key)
            self._research_suite_win = suite # Store a reference
            self.child_windows.append(suite) # For theme updates

        except ImportError:
            messagebox.showerror("Error", "StockResearchSuite.py not found.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Stock Research Suite:\n{e}")
            import traceback
            traceback.print_exc()


    def _get_python_executable(self):
        """
        Finds the correct Python executable, prioritizing the one used to run the app.
        This is important for when the app is bundled into an executable.
        """
        if getattr(sys, 'frozen', False):
            # The application is frozen
            return sys.executable
        return sys.executable # In a normal environment, this is python.exe or python

    # ─────────────────────────────────────────────────────────────
    #  Chat-bot launcher
    # ─────────────────────────────────────────────────────────────
    from pathlib import Path

    # In class OptionAnalyzerApp:

    def launch_chatbot(self):
        # --- REPLACEMENT START ---
        """
        Intelligently launches the chatbot.
        - If the app is a bundled executable, it runs Chatbot.exe.
        - If running from source code, it runs Chatbot.py.
        This ensures portability and that the latest code is always used
        in the appropriate environment.
        """
        try:
            # Use getattr(sys, 'frozen', False) to check if running as a bundled .exe
            is_bundled = getattr(sys, 'frozen', False)

            if is_bundled:
                # --- PRODUCTION MODE (.exe) ---
                # The base path is the directory of the main executable
                base_path = Path(sys.executable).parent
                target_path = base_path / "Chatbot.exe"
                cmd = [str(target_path)]
            else:
                # --- DEVELOPMENT MODE (.py) ---
                # Build a robust relative path to the Python script
                target_path = Path(__file__).resolve().parent.parent / "ui" / "Chatbot.py"
                python_exe = sys.executable
                cmd = [python_exe, str(target_path)]

            # Check if the target file actually exists before trying to run it
            if not target_path.exists():
                messagebox.showerror(
                    "File Not Found",
                    f"Could not find the required chatbot file at:\n{target_path}",
                    parent=self.root
                )
                return

            # Add the current theme as an argument for the chatbot process
            cmd.append(self.current_theme)
            
            # Launch the chatbot as a new, independent process
            subprocess.Popen(cmd)

        except Exception as exc:
            logging.exception("Failed to launch chatbot")
            self.show_copyable_error("Chatbot Launch Error", f"Unable to start chatbot:\n{exc}")
       
                    
    def open_input_window(self):
        """Opens a Toplevel window for user inputs."""

        tooltips = {
            "Ticker": "The stock symbol (e.g., AAPL for Apple).",
            "Current Price (S0)": "The stock's price right now, in dollars.",
            "Barrier Price (H)": "Your target price or safety level to watch.",
            "Implied Volatility": "How much the market expects the stock to move.",
            "Risk-Free Rate": "A baseline interest rate, like from treasury bonds.",
            "Days to Expiry": "How many days left before the option expires.",
            "Strike Price (K)": "The price at which you can buy or sell the stock.",
            "Option Type": "'Call' if you're betting it goes up, 'Put' if down.",
            "Paths to Display": "How many simulated price paths to visualize (1–500)."
        }

        if self.is_loading:
            messagebox.showwarning("Busy", "Analysis is already in progress.", parent=self.root)
            return


        input_win = tk.Toplevel(self.root)
        input_win.title("Input Parameters")
        input_win.geometry("760x900")
        input_win.transient(self.root)

        self.apply_theme_to_window(input_win)

        # Create canvas + scrollbar wrapper
        canvas = tk.Canvas(input_win, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(input_win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Actual input frame inside the canvas
        input_frame = ttk.Frame(canvas)
        input_frame_id = canvas.create_window((0, 0), window=input_frame, anchor="nw")

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        input_frame.bind("<Configure>", on_frame_configure)

        # Resize canvas when window resized
        def on_canvas_resize(event):
            canvas.itemconfig(input_frame_id, width=event.width)

        canvas.bind("<Configure>", on_canvas_resize)

        # Enable mouse scrolling
        def _on_mousewheel(event):
            try:
                if event.num == 4 or event.delta > 0:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5 or event.delta < 0:
                    canvas.yview_scroll(1, "units")
            except tk.TclError:
                pass  # Ignore scroll after widget is destroyed

        canvas.bind_all("<MouseWheel>", _on_mousewheel)       # Windows & most trackpads
        canvas.bind_all("<Button-4>", _on_mousewheel)         # Linux scroll up
        canvas.bind_all("<Button-5>", _on_mousewheel)         # Linux scroll down


        # --- Top bar with fullscreen + close ---
        topbar = ttk.Frame(input_win, padding=(0, 5))
        topbar.place(relx=1.0, y=0, anchor="ne")

        fs_button = ttk.Button(topbar, text="⛶", width=3, command=lambda: self._toggle_fullscreen_input(input_win))
        fs_button.pack(side=tk.RIGHT)

        close_button = ttk.Button(topbar, text="✖", width=3, command=input_win.destroy)
        close_button.pack(side=tk.RIGHT, padx=(0, 5))

        self.educational_mode = tk.BooleanVar(value=False)
        edu_check = ttk.Checkbutton(
            input_frame,
            text="Educational Mode",
            variable=self.educational_mode,
            command=lambda: self._refresh_tooltips(self.tooltip_labels, tooltips)
        )
        edu_check.grid(row=0, column=0, columnspan=2, sticky='w', padx=5, pady=10)

        labels_hints_defaults = {
            "Ticker:": ("(e.g., AAPL)", "AAPL"),
            "Current Price (S0):": ("(e.g., 170.5)", "170.5"),
            "Barrier Price (H):": ("(Target/Floor, e.g., 180)", "180.0"),
            "Implied Volatility:": ("(Decimal, e.g., 0.25)", "0.25"),
            "Risk-Free Rate:": ("(Decimal, e.g., 0.04)", "0.04"),
            "Days to Expiry:": ("(e.g., 90)", "90"),
            "Strike Price (K):": ("(e.g., 175)", "175.0"),
            "Option Type:": ("(call or put)", "call"),
            "Paths to Display:": ("(1 to 500)", "30")
        }

        self.entries = {}
        self.tooltip_labels = {}

        for i, (label_text, (hint, default_val)) in enumerate(labels_hints_defaults.items(), start=1):
            clean_key = label_text.replace(":", "")
            label = ttk.Label(input_frame, text=f"{label_text} {hint}")
            label.grid(row=i, column=0, sticky='w', padx=5, pady=6)
            self.tooltip_labels[clean_key] = label

            entry = ttk.Entry(input_frame, width=18)
            entry.grid(row=i, column=1, sticky='ew', padx=5, pady=6)
            entry.insert(0, default_val)
            self.entries[clean_key] = entry

            if self.educational_mode.get() and clean_key in tooltips:
                Tooltip(label, tooltips[clean_key])

        self.greeks_mode = tk.StringVar(value="manual")
        mode_frame = ttk.Frame(input_frame)
        mode_frame.grid(row=i+1, column=0, columnspan=2, pady=(10, 5), sticky='w')
        ttk.Label(mode_frame, text="Greek Mode:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="Manual", variable=self.greeks_mode, value="manual").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Model (Binomial)", variable=self.greeks_mode, value="model").pack(side=tk.LEFT, padx=5)

        # --- Model choice section with config buttons ---
        self.model_choice = tk.StringVar(value="black_scholes")
        model_frame = ttk.LabelFrame(input_frame, text="Simulation Model", padding=(10,5))
        model_frame.grid(row=i+8, column=0, columnspan=2, sticky='ew', pady=(20,5))

        def ask_model_params(model_name, parent):
            win = tk.Toplevel(parent)
            win.title(f"{model_name.title()} Parameters")
            win.geometry("320x300")
            param_entries = {}

            def add_entry(label, default):
                row = ttk.Frame(win)
                row.pack(pady=3, fill='x')
                ttk.Label(row, text=label, width=18).pack(side='left')
                ent = ttk.Entry(row)
                ent.insert(0, str(default))
                ent.pack(side='left', fill='x', expand=True)
                param_entries[label] = ent

            if model_name == 'jump_diffusion':
                add_entry('λ (Jump Intensity)', 0.1)
                add_entry('μ (Jump Mean)', -0.1)
                add_entry('σ (Jump Volatility)', 0.2)
            elif model_name == 'heston':
                add_entry('κ (Mean Reversion)',    2.0)
                add_entry('θ (Long-run Var)',      0.04)
                add_entry('ξ (Vol of Vol)',        0.10)
                add_entry('v₀ (Initial Var)',      0.04)
                add_entry('ρ (Corr)',             -0.70)   
            elif model_name == 'rough_bergomi':
                add_entry('H (Hurst Exponent)',     0.10)
                add_entry('η (Vol of Vol)',         1.50)
                add_entry('ρ (Corr)',               0.00)   
            def save_and_close():
                self.input_data.setdefault("model_params", {})
                for key, entry in param_entries.items():
                    val = float(entry.get())
                    self.input_data["model_params"][key] = val

                win.destroy()

            ttk.Button(win, text="Save", command=save_and_close).pack(pady=10)
            win.bind("<Return>", lambda e: save_and_close())

        def add_model_row(text, value):
            row = ttk.Frame(model_frame)
            row.pack(anchor='w', fill='x', pady=2)
            ttk.Radiobutton(row, text=text, variable=self.model_choice, value=value).pack(side='left')
            if value != 'black_scholes':
                ttk.Button(row, text="⚙", width=2, command=lambda v=value: ask_model_params(v, input_win)).pack(side='left', padx=4)

        add_model_row("Black-Scholes", "black_scholes")
        add_model_row("Jump Diffusion", "jump_diffusion")
        add_model_row("Heston (Mean-Reverting Vol)", "heston")
        add_model_row("Rough Bergomi (Fractal Vol)", "rough_bergomi")

        # Greeks Input
        ttk.Label(input_frame, text="(Optional) Input Greeks:").grid(row=i+2, column=0, columnspan=2, pady=(20, 5))

        greek_defaults = {
            "Delta": "0.6",
            "Gamma": "0.05",
            "Vega": "-0.44",
            "Theta": "-0.18",
            "Rho": "0.2"
        }
        self.greeks_entries = {}
        for j, (greek, default) in enumerate(greek_defaults.items()):
            ttk.Label(input_frame, text=f"{greek}:").grid(row=i+3+j, column=0, sticky='w', padx=5)
            entry = ttk.Entry(input_frame, width=18)
            entry.grid(row=i+3+j, column=1, sticky='ew', padx=5, pady=3)
            entry.insert(0, default)
            self.greeks_entries[greek.lower()] = entry

        def update_greek_input_state():
            state = 'normal' if self.greeks_mode.get() == "manual" else 'disabled'
            for entry in self.greeks_entries.values():
                entry.config(state=state)

        self.greeks_mode.trace_add("write", lambda *args: update_greek_input_state())
        update_greek_input_state()

        # Submit
        submit_btn = ttk.Button(input_frame, text="Run Analysis",
                                command=lambda win=input_win: self.submit_inputs(win))
        submit_btn.grid(row=i+1, column=0, columnspan=2, pady=25)

        input_frame.columnconfigure(1, weight=1)

        if self.educational_mode.get():
            self._refresh_tooltips(self.tooltip_labels, tooltips)




    def submit_inputs(self, window):
        """Validates inputs and starts the analysis thread + animation."""
        if self.is_loading: return # Prevent multiple submissions

        try:
            # Retrieve and validate inputs
            input_values = {}
            input_values['ticker'] = self.entries["Ticker"].get().strip().upper()
            input_values['S0'] = float(self.entries["Current Price (S0)"].get())
            input_values['H'] = float(self.entries["Barrier Price (H)"].get())
            input_values['sigma'] = float(self.entries["Implied Volatility"].get())
            input_values['r'] = float(self.entries["Risk-Free Rate"].get())
            input_values['T_days'] = int(self.entries["Days to Expiry"].get())
            input_values['strike'] = float(self.entries["Strike Price (K)"].get())
            input_values['option_type'] = self.entries["Option Type"].get().strip().lower()
            input_values['paths_to_display'] = int(self.entries["Paths to Display"].get())
            #input_values['style'] = self.entries["Option Style"].get().strip().lower()
            input_values['educational_mode'] = self.educational_mode.get()
            # Collect Greeks if provided, else use 0
            greek_inputs = {}
            for greek in ['delta', 'gamma', 'vega', 'theta', 'rho']:
                try:
                    val = self.greeks_entries[greek].get()
                    greek_inputs[greek] = float(val) if val.strip() else 0.0
                except ValueError:
                    greek_inputs[greek] = 0.0  # Default fallback
            input_values['greek_inputs'] = greek_inputs
            input_values['greek_mode'] = self.greeks_mode.get()
            input_values['simulation_model'] = self.model_choice.get()
            input_values['model_params'] = self.input_data.get("model_params", {})




            # Basic Validation Checks
            if not input_values['ticker']: raise ValueError("Ticker symbol cannot be empty.")
            if input_values['S0'] <= 0: raise ValueError("Current Price must be positive.")
            if input_values['sigma'] < 0: raise ValueError("Implied Volatility cannot be negative.")
            # Allow r=0, but maybe warn if negative? For now, allow negative rates.
            if input_values['T_days'] <= 0: raise ValueError("Days to Expiry must be positive.")
            if input_values['strike'] <= 0: raise ValueError("Strike Price must be positive.")
            if input_values['option_type'] not in ['call', 'put']: raise ValueError("Option Type must be 'call' or 'put'.")
            if not (1 <= input_values['paths_to_display'] <= 500):
                raise ValueError("Paths to Display must be between 1 and 500.")
            #if input_values['style'] not in ['american', 'european']:
                #raise ValueError("Option Style must be 'american' or 'european'.")
            if input_values['greek_mode'] == "model":
                greeks = calculate_binomial_greeks(
                    input_values['S0'], input_values['strike'], input_values['T_days']/365,
                    input_values['r'], input_values['sigma'], option_type=input_values['option_type']
                )
                input_values['greek_inputs'] = greeks



            # If inputs are valid, close input window and start analysis
            window.destroy()

            # 3) Start the spinner *after* the window is gone
            self.is_loading = True
            self.animation_step = 0
            self.animate_loading()

            # 4) Spawn the analysis thread
            analysis_thread = threading.Thread(
                target=self.run_analysis_thread,
                args=(input_values,),
                daemon=True
            )
            analysis_thread.start()

        except ValueError as e:
            messagebox.showerror("Input Error", str(e), parent=self.root) # Show error on main window
            # Stop animation if it started (though likely didn't in case of validation error)
            self.is_loading = False
            self.set_status("Input validation failed", "red")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred during input: {e}", parent=self.root)
            self.is_loading = False
            self.set_status("An unexpected error occurred", "red")
            print(f"Input Submission Error Traceback:\n{traceback.format_exc()}")


    def run_analysis_thread(self, inputs):
        """The function executed in the background thread."""
        try:
            T = inputs['T_days'] / 365.0
            self.input_data = inputs.copy()
            sigma = inputs['sigma']
            self.input_data['T'] = T
            jump_params = None
            heston_params = None
            rough_params = None


            # 1. Fetch historical data
            prices = fetch_ticker_data(inputs['ticker'], inputs['T_days'] + 180)
            drift, realized_vol, stderr = calculate_drift_and_volatility(prices)
            self.input_data['drift'] = drift
            self.input_data['realized_vol'] = realized_vol
            self.input_data['vol_stderr'] = stderr

            set_max_paths(inputs['paths_to_display'])

            # 2. Detect simulation model
            model = inputs.get("simulation_model", "black_scholes")
            model_params = inputs.get("model_params", {})
            self.input_data["simulation_model"] = model  # For use in summary

            if model == "jump_diffusion":
                jump_params = {
                    'lambda': model_params.get('λ (Jump Intensity)', 0.1),
                    'mu': model_params.get('μ (Jump Mean)', -0.1),
                    'sigma': model_params.get('σ (Jump Volatility)', 0.2)
                }
                heston_params = rough_params = None

            if model == "heston":
                heston_params = {
                    'kappa': model_params.get('κ (Mean Reversion)',    2.0),
                    'theta': model_params.get('θ (Long-run Var)',      sigma**2),
                    'xi':    model_params.get('ξ (Vol of Vol)',        0.10),
                    'v0':    model_params.get('v₀ (Initial Var)',      sigma**2),
                    'rho':   model_params.get('ρ (Corr)',             -0.70)
                }
                jump_params = rough_params = None

            elif model == "rough_bergomi":
                rough_params = {
                    'H':   model_params.get('H (Hurst Exponent)',    0.10),
                    'eta': model_params.get('η (Vol of Vol)',        1.50),
                    'rho': model_params.get('ρ (Corr)',              0.00)
                }
                jump_params = heston_params = None

            # 3. Monte Carlo Simulation
            sim_results = calculate_simulation_data(
                inputs['S0'], inputs['H'], inputs['sigma'], drift, T, inputs['r'],
                n_simulations=10000, option_type=inputs['option_type'],
                model=model,
                jump_params=jump_params,
                heston_params=heston_params,
                rough_params=rough_params
            )
            (prob, avg_trig, std_trig, trig_prices, paths, days) = sim_results

            self.input_data['probability'] = prob
            self.input_data['avg_trigger'] = avg_trig
            self.input_data['std_trigger'] = std_trig
            self.input_data['trigger_prices'] = trig_prices
            self.input_data['sample_paths'] = paths
            self.input_data['sim_days'] = days

            # 4. Corrected trigger price calc
            correct_avg_trig, correct_std_trig, _ = recalculate_trigger_price_correctly(
                inputs['S0'], inputs['sigma'], T, inputs['r'],
                n_simulations=10000, option_type=inputs['option_type']
            )
            self.input_data['correct_avg_trigger'] = correct_avg_trig
            self.input_data['correct_std_trigger'] = correct_std_trig

            if model == "black_scholes":
                from core.engine.MonteCarloSimulation import black_scholes_price
                bs_price = black_scholes_price(
                    inputs['S0'], inputs['strike'], T,
                    inputs['r'], inputs['sigma'], inputs['option_type']
                )
                self.input_data['bs_price'] = bs_price


            # 5. Binomial Fair Price
            fair_price = cached_binomial_price(
                inputs['S0'], inputs['strike'], T, inputs['r'], inputs['sigma'],
                N=500, option_type=inputs['option_type'], american=False
            )
            self.input_data['fair_price'] = fair_price
            self.input_data['educational_mode'] = inputs['educational_mode']

            # 6. Heatmap + Surface
            self.input_data['heatmap_data'] = generate_profit_heatmap_data(
                inputs['S0'], inputs['strike'], T, inputs['r'], inputs['sigma'],
                inputs['option_type'], initial_option_price=fair_price,
                low_pct_factor=0.5, high_pct_factor=2.0
            )

            # 7. Option Surface Data
            self.input_data['surface_data'] = generate_option_surface_data(
                inputs['S0'], inputs['strike'], T, inputs['r'], inputs['sigma'],
                inputs['option_type'], low_pct_factor=0.5, high_pct_factor=2.0
            )

            # 8. Volatility Surface Data
            self.input_data['vol_surface_data'] = generate_volatility_surface_data(
                 inputs['S0'], inputs['strike'], T, inputs['sigma']
            )

            # 7. Done → schedule UI update
            self.root.after(0, self.analysis_complete)

        except Exception as e:
            self.root.after(0, lambda err=e: self.analysis_failed(err))


    def analysis_complete(self):
        """Updates GUI after successful analysis."""
        self._cancel_loading_animation()
        self.is_loading = False # Stop animation flag
        time.sleep(0.1) # Small delay to ensure last animation frame clears
        self.set_status("Analysis complete. Launching results...", color="green")
        self.launch_analysis_results_window()    # NEW → pop up results window

    def analysis_failed(self, error):
        """Handles errors occurring during the analysis thread."""
        self._cancel_loading_animation()
        self.is_loading = False
        # Short delay might prevent status update race condition if analysis fails instantly
        time.sleep(0.1)
        self.set_status("Analysis failed!", color="red")

        # Log the full traceback to the console for debugging
        traceback_str = traceback.format_exception(type(error), error, error.__traceback__)
        print("=== ANALYSIS THREAD ERROR TRACEBACK ===")
        print("".join(traceback_str))
        print("======================================")

        # Show a user-friendly error message
        tk.messagebox.showerror("Analysis Error",
                                f"Failed to complete analysis:\n{error}\n\n(Check console for detailed traceback)",
                                parent=self.root)

    def launch_docking_station(self):
        """Creates or focuses the single instance of the docking window."""
        if self.docking_window_instance and self.docking_window_instance.winfo_exists():
            self.docking_window_instance.lift()
        else:
            self.docking_window_instance = DockingPlotWindow(self.root, self)
        return self.docking_window_instance

    def plot_in_dock(self, pane_side: str, plot_type: str):
        """A helper method to send a plot command to the docking window."""
        if not self.input_data:
            messagebox.showwarning("No Data", "Please run an analysis first.", parent=self.root)
            return

        dock_window = self.launch_docking_station()
        if dock_window:
            dock_window.plot_in_pane(pane_side, plot_type, self.input_data)

    def launch_analysis_results_window(self):
        """
        Shows a clean window with options to view, save, or load analyses.
        """
        win = tk.Toplevel(self.root)
        win.title("Analysis Results")
        win.transient(self.root)
        win.geometry("450x600") # Increased height for new buttons
        win.minsize(450, 500)
        self.apply_theme_to_window(win)

        main_frame = ttk.Frame(win, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.rowconfigure(3, weight=1) # Allow plot frame to expand
        main_frame.columnconfigure(0, weight=1)

        # --- (Plotting button creation logic remains the same) ---
        def create_plot_row(parent, text, plot_key):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, padx=5, pady=4)
            ttk.Label(row, text=text).pack(side=tk.LEFT, expand=True, anchor='w')
            ttk.Button(row, text="Dock", style="Pill.TButton", command=lambda: self.dock_plot(plot_key)).pack(side=tk.RIGHT, padx=(0,5))
            ttk.Button(row, text="New Window", style="Pill.TButton", command=lambda: self._launch_standalone_plot(plot_key)).pack(side=tk.RIGHT, padx=5)

        # --- Sections ---
        info_frame = ttk.LabelFrame(main_frame, text="Summary & Chart", padding=10)
        info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(info_frame, text="Show Summary Info", command=self.show_summary_popup).pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(info_frame, text="📈 View Stock Chart", command=self.show_stock_chart_window).pack(fill=tk.X, padx=5, pady=5)
        
        plot_frame = ttk.LabelFrame(main_frame, text="Generate Plots", padding=10)
        plot_frame.grid(row=1, column=0, sticky="ew", pady=5)
        create_plot_row(plot_frame, "Simulation Paths", 'simulation_paths')
        create_plot_row(plot_frame, "Trigger Distribution", 'distribution')
        create_plot_row(plot_frame, "Profit Heatmap", 'heatmap')
        create_plot_row(plot_frame, "3D Volatility Surface", 'vol_surface')
        
        advanced_frame = ttk.LabelFrame(main_frame, text="Advanced Analysis", padding=10)
        advanced_frame.grid(row=2, column=0, sticky="ew", pady=10)
        ttk.Button(advanced_frame, text="📉 Analyze Greeks", command=self.show_greek_analysis).pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(advanced_frame, text="Explain Position (LLM)", command=self.show_llm_explanation).pack(fill=tk.X, padx=5, pady=5)

        # --- NEW: Action Buttons at the Bottom ---
        action_frame = ttk.Frame(main_frame, padding=(0, 15, 0, 0))
        action_frame.grid(row=4, column=0, sticky="ew")
        action_frame.columnconfigure(0, weight=1) # Spacer

        ttk.Button(action_frame, text="Load Analysis", command=self._launch_load_window).grid(row=0, column=1, padx=5)
        ttk.Button(action_frame, text="Save Analysis", style="Accent.TButton", command=self._prompt_save_analysis).grid(row=0, column=2, padx=5)
        ttk.Button(action_frame, text="Close", command=win.destroy).grid(row=0, column=3, padx=5)

    def _launch_standalone_plot(self, plot_type: str):
        """Launches a plot in its own dedicated, single-pane window."""
        if not self.input_data:
            messagebox.showwarning("No Data", "Please run an analysis first.", parent=self.root)
            return

        try:
            win = tk.Toplevel(self.root)
            win.geometry("800x600")
            self.apply_theme_to_window(win)
            plot_frame = ttk.Frame(win, padding=10)
            plot_frame.pack(expand=True, fill=tk.BOTH)

            is_dark_mode = self.current_theme == 'dark'
            plot_map = {
                'simulation_paths': (plot_simulation_paths, "Simulation Paths"),
                'distribution': (plot_distribution, "Trigger Price Distribution"),
                'heatmap': (plot_profit_heatmap, "Profit/Loss Heatmap"),
                'vol_surface': (plot_volatility_surface_3d, "3D Implied Volatility Surface")
            }

            if plot_type not in plot_map:
                raise ValueError(f"Unknown plot type: {plot_type}")

            plot_function, title = plot_map[plot_type]
            win.title(title)
            
            args, kwargs = [], {}
            if plot_type == 'simulation_paths':
                args = [self.input_data['sim_days'], self.input_data['sample_paths'], self.input_data['S0'], self.input_data['H'], self.input_data['option_type'], self.input_data['sigma'], self.input_data['probability'], len(self.input_data['sample_paths']), self.input_data['paths_to_display']]
                kwargs = {'dark_mode': is_dark_mode, 'title': f"{self.input_data['ticker']} {title}"}
            elif plot_type == 'distribution':
                args = [self.input_data['trigger_prices'], self.input_data['H'], self.input_data['probability'], self.input_data['option_type'], self.input_data['S0'], self.input_data['correct_avg_trigger'], self.input_data['correct_std_trigger']]
                kwargs = {'dark_mode': is_dark_mode}
            elif plot_type == 'heatmap':
                prices, times, profit_m, percent_m, day_lbls, price_lbls, premium = self.input_data['heatmap_data']
                args = [prices, times, profit_m, percent_m, day_lbls, price_lbls, premium, self.input_data['option_type'], self.input_data['strike']]
                # **FIX**: The 'probability' keyword argument has been removed from this line.
                kwargs = {'title': "Profit/Loss Heatmap", 'dark_mode': is_dark_mode}
            elif plot_type == 'vol_surface':
                p_grid, t_grid, iv_grid = self.input_data['vol_surface_data']
                args = [p_grid, t_grid, iv_grid]
                kwargs = {'title': title, 'dark_mode': is_dark_mode}

            plot_function(plot_frame, *args, **kwargs)

        except Exception as e:
            messagebox.showerror("Plot Error", f"Failed to generate plot:\n{e}", parent=self.root)
            traceback.print_exc()

    def dock_plot(self, plot_type: str):
        """A helper method to send a plot to the next available dock pane."""
        if not self.input_data:
            messagebox.showwarning("No Data", "Please run an analysis first.", parent=self.root)
            return

        dock_window = self.launch_docking_station()
        if dock_window:
            dock_window.add_plot(plot_type, self.input_data)

    def _prompt_save_analysis(self, prefill_notes=""):
        # --- REPLACEMENT START ---
        """Opens a dialog to get a name and notes, with optional pre-filled text."""
        if not self.input_data:
            messagebox.showerror("No Data", "There is no analysis data to save.", parent=self.root)
            return

        win = tk.Toplevel(self.root)
        win.title("Save Analysis")
        win.geometry("450x350") # Increased height for notes
        win.transient(self.root)
        win.grab_set()
        self.apply_theme_to_window(win)

        frame = ttk.Frame(win, padding=15)
        frame.pack(expand=True, fill=tk.BOTH)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1) # Allow notes Text widget to expand

        ttk.Label(frame, text="Analysis Name:", anchor='w').grid(row=0, column=0, sticky='ew', pady=(0, 2))
        name_var = tk.StringVar()
        ttk.Entry(frame, textvariable=name_var).grid(row=1, column=0, sticky='ew')
        
        ticker = self.input_data.get('ticker', 'TICKER')
        otype = self.input_data.get('option_type', 'option').capitalize()
        strike = self.input_data.get('strike', 'K')
        name_var.set(f"{ticker} ${strike} {otype} Analysis")

        ttk.Label(frame, text="Notes:", anchor='w').grid(row=2, column=0, sticky='ew', pady=(10, 2))
        notes_text = tk.Text(frame, height=8, wrap='word', relief='solid', borderwidth=1)
        notes_text.grid(row=3, column=0, sticky='nsew')
        
        # Pre-fill the notes with the LLM explanation if provided
        if prefill_notes:
            notes_text.insert("1.0", prefill_notes)
        
        btn_frame = ttk.Frame(frame, padding=(0, 15, 0, 0))
        btn_frame.grid(row=4, column=0, sticky="e")

        def on_save():
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("Name Required", "Please provide a name for the analysis.", parent=win)
                return
            notes = notes_text.get("1.0", tk.END).strip()
            self.analysis_persistence.save_analysis(name, notes, self.input_data)
            messagebox.showinfo("Success", f"Analysis '{name}' saved successfully.", parent=self.root)
            win.destroy()

        ttk.Button(btn_frame, text="Save", style="Accent.TButton", command=on_save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(side=tk.LEFT)
        # --- REPLACEMENT END ---
        
    def _launch_load_window(self):
        """Launches the window to load saved analyses."""
        LoadAnalysisWindow(self.root, self, self.analysis_persistence, self._on_analysis_loaded)
        
    def _on_analysis_loaded(self, loaded_data):
        """Callback function for when an analysis is loaded."""
        self.input_data = loaded_data
        self.set_status(f"Loaded analysis for {self.input_data.get('ticker')}.", "green")
        # Relaunch the results window with the newly loaded data
        self.launch_analysis_results_window()

    def display_results_summary_console(self):
         """Prints a simple text summary to the console (optional)."""
         if not self.input_data: return # Should not happen if called from analysis_complete


         fair_price_str = f"${self.input_data['fair_price']:.2f}" if not np.isnan(self.input_data['fair_price']) else "N/A (Calculation Error?)"
         prob_str = f"{self.input_data['probability']*100:.2f}%" if not np.isnan(self.input_data['probability']) else "N/A"
         avg_trig_str = f"${self.input_data['avg_trigger']:.2f}" if not np.isnan(self.input_data['avg_trigger']) else "N/A"
         real_vol_str = f"{self.input_data.get('realized_vol', np.nan)*100:.1f}%" # Use .get for safety
         stderr_str = f"{self.input_data.get('vol_stderr', np.nan)*100:.1f}%"

         summary = (
             f"\n--- Analysis Summary for {self.input_data['ticker']} ---\n"
             f"Option Type: {self.input_data['option_type'].capitalize()}, Strike: ${self.input_data['strike']:.2f}, Expiry: {self.input_data['T_days']} days\n"
             f"Current Price (S0): ${self.input_data['S0']:.2f}, Barrier (H): ${self.input_data['H']:.2f}\n"
             f"Input IV: {self.input_data['sigma']*100:.1f}%, Risk-Free Rate: {self.input_data['r']*100:.1f}%\n"
             f"Realized Volatility (hist.): {real_vol_str} (±{stderr_str})\n"
             f"--------------------------------------\n"
             f"{self.input_data['style'].capitalize()} Fair Value: {fair_price_str}\n"
             f"MC Probability of Hitting Barrier: {prob_str}\n"
             f"Avg. {'Max' if self.input_data['option_type']=='call' else 'Min'} Price in MC: {avg_trig_str}\n"
             f"--------------------------------------\n"
         )
         print(summary)


    def show_summary_popup(self):
        """Shows an enhanced summary window with key analysis metrics."""
        if not self.input_data:
            messagebox.showwarning("No Data", "Run an analysis first.", parent=self.root)
            return

        win = tk.Toplevel(self.root)
        win.title("Detailed Analysis Summary")
        win.geometry("920x960")
        win.transient(self.root)
        win.grab_set()

        self.apply_theme_to_window(win)
        win.grab_set()

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        def fmt_val(val, fmt, default="N/A"):
            return fmt.format(val) if pd.notna(val) else default

        iv_val = self.input_data.get('sigma', 0)
        rv_val = self.input_data.get('realized_vol', 0)
        fair_price = fmt_val(self.input_data.get('fair_price'), "${:.4f}")
        prob = fmt_val(self.input_data.get('probability', 0) * 100, "{:.2f}%")
        avg_trig = fmt_val(self.input_data.get('avg_trigger'), "${:.2f}")
        vol = fmt_val(rv_val * 100, "{:.1f}%")
        stderr = fmt_val(self.input_data.get('vol_stderr', 0) * 100, "{:.1f}%")

        sim_count = 10000
        hits = int(self.input_data.get('probability', 0.0) * sim_count)
        trigger_type = "Maximum" if self.input_data.get('option_type') == 'call' else "Minimum"
        iv_pct = iv_val * 100

        # Volatility comparison
        if iv_val > rv_val + self.input_data.get('vol_stderr', 0):
            vol_status = f"Overpriced (IV = {iv_pct:.1f}%, Realized = {rv_val*100:.1f}%)"
        elif iv_val < rv_val - self.input_data.get('vol_stderr', 0):
            vol_status = f"Underpriced (IV = {iv_pct:.1f}%, Realized = {rv_val*100:.1f}%)"
        else:
            vol_status = f"Fairly Priced (IV = {iv_pct:.1f}%, Realized = {rv_val*100:.1f}%)"

        # Build Simulation Settings section with model-specific logic
        model = self.input_data.get('simulation_model', 'black_scholes')
        param_map = self.input_data.get("model_params", {})
        bs_price = self.input_data.get('bs_price', None)
        fair_price = self.input_data.get('fair_price', None)
        fair_price = fmt_val(fair_price, "${:.4f}")

        simulation_settings = [("Model Used", model.replace('_', ' ').title())]

        # Add model-generated price line
        if model == "black_scholes" and bs_price is not None:
            simulation_settings.append(("Black-Scholes Price", f"${bs_price:.4f}"))
        elif model != "black_scholes" and fair_price is not None:
            simulation_settings.append(
                ("Model-Based Estimate", f"${float(self.input_data['fair_price']):.4f}")
            )


        if model == "jump_diffusion":
            for key in ['λ (Jump Intensity)', 'μ (Jump Mean)', 'σ (Jump Volatility)']:
                if key in param_map:
                    simulation_settings.append((key, str(round(param_map[key], 6))))
        elif model == "heston":
            for key in ['κ (Mean Reversion)', 'θ (Long-run Var)', 'ξ (Vol of Vol)', 'v₀ (Initial Var)']:
                if key in param_map:
                    simulation_settings.append((key, str(round(param_map[key], 6))))
        elif model == "rough_bergomi":
            for key in ['H (Hurst Exponent)', 'η (Vol of Vol)']:
                if key in param_map:
                    simulation_settings.append((key, str(round(param_map[key], 6))))

        sections = [
            ("Underlying Info", [
                ("Ticker", self.input_data.get('ticker', 'N/A')),
                ("Option Type", self.input_data.get('option_type', '').capitalize()),
                ("Strike Price", f"${self.input_data.get('strike', 0):.2f}"),
                ("Barrier Price (H)", f"${self.input_data.get('H', 0):.2f}"),
                ("Current Price (S₀)", f"${self.input_data.get('S0', 0):.2f}"),
                ("Days to Expiry", str(self.input_data.get('T_days', 0)))
            ]),
            ("Inputs", [
                ("Implied Volatility", f"{iv_pct:.1f}%"),
                ("Risk-Free Rate", fmt_val(self.input_data.get('r', 0) * 100, "{:.2f}%"))
            ]),
            ("Monte Carlo Results", [
                ("Simulations Run", f"{sim_count:,}"),
                (f"Paths that hit barrier", f"{hits:,} ({prob})"),
                (f"Avg. {trigger_type} Price", avg_trig)
            ]),
            ("Simulation Settings", simulation_settings),
            ("Binomial Estimate", [
                ("Fair Option Value", fair_price),
                ("Realized Volatility", f"{vol} (±{stderr})"),
                ("Volatility Status", vol_status)
            ])
        ]

        for section_title, items in sections:
            title = ttk.Label(frame, text=section_title, font=("Helvetica", 11, "bold"))
            title.pack(anchor='w', pady=(10, 2))

            for label, val in items:
                row = ttk.Frame(frame)
                row.pack(fill=tk.X, pady=2)
                ttk.Label(row, text=f"{label}:", width=24).pack(side=tk.LEFT)
                ttk.Label(row, text=val).pack(side=tk.LEFT)

        ttk.Button(frame, text="Close", command=win.destroy).pack(pady=15)




    # --- Plotting Window Launchers ---

    def _launch_plot_window(self, plot_function, *args, **kwargs):
        """Launches a new window to display a plot."""
        try:
            popup = tk.Toplevel(self.root)
            # Use pop to get title but also remove it from kwargs if present
            # We use 'plot_title' to avoid potential conflicts with a 'title' kwarg
            # that the plot_function itself might need.
            popup.title(kwargs.pop('plot_title', "Plot Window"))
            popup.geometry("800x600")
            self.apply_theme_to_window(popup)

            plot_frame = ttk.Frame(popup, padding=10)
            plot_frame.pack(expand=True, fill=tk.BOTH)

            # Call the actual plotting function, passing the frame and all args/kwargs
            plot_function(plot_frame, *args, **kwargs)

        except Exception as e:
            traceback.print_exc()  # Log the full traceback
            messagebox.showerror("Plot Error", f"Failed to generate plot: {e}", parent=self.root)
        finally:
            self.set_status("")


    # Wrapper functions to call _launch_plot_window for each plot type
    def show_simulation_plot(self):
        if not self.input_data or 'sim_days' not in self.input_data or 'sample_paths' not in self.input_data:
            messagebox.showwarning("Missing Data", "Simulation path data is missing. Please run analysis.", parent=self.root)
            return
        self.set_status("Generating Simulation Path plot...")
        self._launch_plot_window(plot_simulation_paths,
            self.input_data['sim_days'],
            self.input_data['sample_paths'],
            self.input_data['S0'],
            self.input_data['H'],
            self.input_data['option_type'],
            self.input_data['sigma'],
            self.input_data['probability'],
            len(self.input_data['sample_paths']), # use the total number of simulations.
            self.input_data['paths_to_display'], # send the user inputed value.
            title=f"{self.input_data['ticker']} Simulation Paths",
            educational_mode=self.input_data.get('educational_mode', False),
            dark_mode=(self.current_theme == 'dark'))

        self.set_status("") # Clear status after plot launched (or failed)


    def show_distribution_plot(self):
        if not self.input_data or 'trigger_prices' not in self.input_data:
            messagebox.showwarning("Missing Data", "Trigger price data is missing. Please run analysis.", parent=self.root)
            return
        self.set_status("Generating Distribution plot...")
        self._launch_plot_window(plot_distribution,
                                 self.input_data['trigger_prices'],
                                 self.input_data['H'],
                                 self.input_data['probability'],
                                 self.input_data['option_type'],
                                 self.input_data['S0'],
                                 self.input_data['correct_avg_trigger'],
                                 self.input_data['correct_std_trigger'],
                                 dark_mode=(self.current_theme == 'dark'))
        self.set_status("")


    def show_heatmap_plot(self):
        if not self.input_data or 'heatmap_data' not in self.input_data or not self.input_data['heatmap_data']:
            messagebox.showwarning("Missing Data", "Heatmap data is not available. Please run analysis.", parent=self.root)
            return
        self.set_status("Generating Heatmap plot...")
        # Unpack heatmap data
        try:
            prices, times, profit_m, percent_m, day_lbls, price_lbls, premium = self.input_data['heatmap_data']
            self._launch_plot_window(plot_profit_heatmap,
                         prices, times, profit_m, percent_m, day_lbls, price_lbls, premium,
                         self.input_data['option_type'], self.input_data['strike'],
                         "Profit/Loss Heatmap",
                         self.input_data.get('probability'),
                          dark_mode=(self.current_theme == 'dark'))
        except Exception as e: # Catch potential errors during unpacking or plotting call
             messagebox.showerror("Plot Error", f"Failed to display heatmap:\n{e}", parent=self.root)
             print(f"Heatmap display error: {traceback.format_exc()}")
        finally:
            self.set_status("")


    def show_3d_volatility_plot(self):
        """
        Launch a 3D implied volatility surface plot.
        """
        if not self.input_data or 'vol_surface_data' not in self.input_data or not self.input_data['vol_surface_data']:
            messagebox.showwarning(
                "Missing Data",
                "Volatility surface data is not available. Please run analysis first.",
                parent=self.root
            )
            return

        self.set_status("Generating 3D Volatility Surface plot...")

        try:
            # Import the new plotting function here or ensure it's imported at the top
            from core.engine.MonteCarloSimulation import plot_volatility_surface_3d

            p_grid, t_grid, iv_grid = self.input_data['vol_surface_data']
            self._launch_plot_window(
                plot_volatility_surface_3d, # <--- Use the NEW plot function
                p_grid,
                t_grid,
                iv_grid,
                plot_title="3D Implied Volatility Surface", # <-- Window Title
                title="3D Implied Volatility Surface",    # <-- Plot Title
                dark_mode=(self.current_theme == 'dark')
            )
        except Exception as e:
            messagebox.showerror(
                "Plot Error",
                f"Failed to display 3D volatility surface:\n{e}",
                parent=self.root
            )
            logging.error(f"3D Volatility Surface display error: {e}")
            traceback.print_exc() # Print detailed error
        finally:
            self.set_status("")


    def show_stock_chart_window(self):
            ticker = self.input_data.get("ticker", "")
            if not ticker:
                messagebox.showerror("Missing Ticker", "No stock ticker found.")
                return
            StockChartWindow(self.root, ticker, theme=self.current_theme)


    def toggle_theme(self):
        bounce_overlay = getattr(self.dashboard, 'bounce_overlay', None)
        # Check the bouncer's state BEFORE the theme change to know if we need to stop it.
        was_bouncing = bounce_overlay and getattr(bounce_overlay, '_bouncing', False)

        # --- Stop the overlay if it was running to prevent visual glitches ---
        if was_bouncing:
            bounce_overlay.stop()

        # --- APPLY ALL THEME CHANGES (Existing Logic) ---
        new_theme = 'dark' if self.is_dark_mode_var.get() else 'light'
        self.current_theme = new_theme

        import core.engine.MonteCarloSimulation as sim
        sim.dark_mode = (new_theme == 'dark')

        configure_global_styles(new_theme)
        self.apply_theme_to_window(self.root)

        for tester in self.strategy_testers[:]:
            if tester.win.winfo_exists():
                tester.update_theme(self.current_theme)
            else:
                self.remove_strategy_tester(tester)

        if hasattr(self, 'dashboard'):
            self.dashboard.update_theme()

        live_children = []
        for win in self.child_windows:
            try:
                if win.winfo_exists():
                    self.apply_theme_to_window(win)
                    live_children.append(win)
            except:
                continue
        self.child_windows = live_children
        self.settings.set("theme", self.current_theme)

        # --- Restart the overlay ONLY if the setting is enabled ---
        # This reads the setting that was just saved from the settings window.
        should_be_bouncing = self.settings.get('enable_bounce_overlay', False)

        if should_be_bouncing:
            bounce_overlay.start()



    def _on_close(self) -> None:
        """
        Handles the window close event (the 'X' button).
        Ensures all threads and child windows are properly shut down.
        """
        if getattr(self, "_is_closing", False):
            return  # Shutdown already in progress
        self._is_closing = True

        print("Initiating application shutdown sequence...")

        # 1. Stop console redirection FIRST. This ensures any errors from
        #    thread cleanup are printed to the actual console, not a dead window.
        if hasattr(self, 'debug_console_window') and self.debug_console_window:
            try:
                self.debug_console_window.stop_redirection()
                print("Debug console redirection stopped.")
            except Exception as e:
                print(f"Error stopping debug console redirection: {e}")

        # 2. Signal all components and threads to stop their work.
        if hasattr(self, "dashboard") and self.dashboard:
            try:
                self.dashboard.shutdown()
                print("Dashboard shutdown initiated.")
            except Exception as e:
                print(f"Error during dashboard shutdown: {e}")

        self._cancel_loading_animation()
        print("Loading animation cancelled.")

        # Ensure earnings fetch thread is stopped gracefully
        if self._fetching_earnings and self._earnings_fetch_thread and self._earnings_fetch_thread.is_alive():
            try:
                print("Signaling earnings fetch thread to stop...")
                self._earnings_fetch_queue.put(None) # Send sentinel to stop the worker
                self._earnings_fetch_thread.join(timeout=3) # Give it some time to finish
                if self._earnings_fetch_thread.is_alive():
                    print("Warning: Earnings fetch thread did not terminate gracefully after 3 seconds.")
            except Exception as e:
                print(f"Error during earnings thread shutdown: {e}")
        self._fetching_earnings = False # Ensure flag is reset

        # 3. Terminate any external processes (like chatbot if launched via Popen).
        if hasattr(self, "_chatbot_proc") and self._chatbot_proc.poll() is None:
            try:
                print("Terminating chatbot process...")
                self._chatbot_proc.terminate()
                self._chatbot_proc.wait(timeout=2) # Give it a moment to terminate
                if self._chatbot_proc.poll() is None:
                    print("Warning: Chatbot process did not terminate gracefully, killing it.")
                    self._chatbot_proc.kill()
            except Exception as e:
                print(f"Error terminating chatbot process: {e}")

        # 4. Destroy child windows explicitly (they should already have protocol handlers, but as a fallback)
        for win in self.child_windows[:]: # Iterate over a copy as list might be modified
            if win and win.winfo_exists():
                try:
                    win.destroy()
                    print(f"Destroyed child window: {win.title()}")
                except Exception as e:
                    print(f"Error destroying child window {win}: {e}")
        self.child_windows = [] # Clear the list

        # 5. Destroy the console window after its redirection is stopped.
        if hasattr(self, 'debug_console_window') and self.debug_console_window:
            try:
                self.debug_console_window.destroy()
                print("Debug console window destroyed.")
            except Exception as e:
                print(f"Error destroying debug console window: {e}")

        print("Application shutdown complete. Exiting mainloop.")
        # 6. Tell the main event loop to exit.
        self.root.quit()
        # No need for sys.exit() here, as root.mainloop() will exit after root.quit()
        # and the __main__ block will handle sys.exit().

    def launch_idea_suite(self):
        """
        Open or refocus the Idea-Suite window, now with a robust,
        guaranteed refresh on first launch.
        """
        # If window exists, just bring it to the front
        if getattr(self, "_idea_suite_win", None) and self._idea_suite_win.winfo_exists():
            self._idea_suite_win.deiconify()
            self._idea_suite_win.lift()
            self._idea_suite_win.focus_force()
            return

        # --- Create a new window and all its components ---
        win = tk.Toplevel(self.root)
        win.title("💡 Idea Suite")
        win.geometry("1400x900")
        self._idea_suite_win = win
        self.child_windows.append(win)
        
        # Create a notebook widget to hold the view
        notebook = ttk.Notebook(win)
        notebook.pack(expand=True, fill="both")
        
        # Create the controller and view here, linking them properly
        from core.engine.idea_suite_controller import IdeaSuiteController
        
        # 1. The view now creates its own queue to receive ideas
        suite_view = IdeaSuiteView(notebook, app=self)
        suite_view.pack(expand=True, fill="both")

        # 2. The controller is given the view's queue to push data into
        controller = IdeaSuiteController(self.idea_engine, suite_view.queue)
        
        # 3. The view is given a reference to the controller to request refreshes
        suite_view.set_controller(controller)
        
        # 4. Kick off the initial, guaranteed refresh
        suite_view.refresh_ideas()
        
        self.apply_theme_to_window(win)



    # In class OptionAnalyzerApp:

    def launch_portfolio(self):
        """
        Launches the professional Portfolio application in a new, separate process
        to ensure complete UI isolation.
        """
        try:
            # Check if the process object exists and if the process is still running
            if hasattr(self, 'portfolio_process') and self.portfolio_process.is_alive():
                print("Portfolio window is already open.")
                # Note: We can't easily force-focus a window in another process.
                # This check simply prevents launching a second instance.
                return

            # This helper function must be in the global scope of your portfolio_view.py
            from ui.portfolio_view import launch_portfolio_window

            # Create and start the new process
            self.portfolio_process = multiprocessing.Process(target=launch_portfolio_window, daemon=True)
            self.portfolio_process.start()
            print("Launched portfolio window in a new process.")

        except ImportError:
            messagebox.showerror("File Not Found", "Could not find 'portfolio_view.py'.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open the Portfolio application: {e}")
            traceback.print_exc()

    # The _on_portfolio_close method is no longer needed.
    # The separate process handles its own lifecycle.


    def launch_strategy_builder(self, idea_data: dict | None = None):
        """
        Launches the Strategy Builder window using a singleton pattern.
        It creates the window once and then hides/shows it to prevent
        resource-related crashes in the bundled .exe.
        """
        # Check if the window variable exists and if the window hasn't been destroyed
        if self._strat_builder_win and self._strat_builder_win.winfo_exists():
            # If it exists, just show it and bring it to the front
            self._strat_builder_win.deiconify()
            self._strat_builder_win.lift()
            self._strat_builder_win.focus_force()
        else:
            # If it doesn't exist or was destroyed, create it for the first time
            self._strat_builder_win = StrategyBuilderWindow(self.root, self, None) # Create without data first
            if self._strat_builder_win not in self.child_windows:
                self.child_windows.append(self._strat_builder_win)
            self.apply_theme_to_window(self._strat_builder_win)

        # Whether showing an old window or creating a new one, if new idea data
        # is provided, pre-fill the form.
        if idea_data and self._strat_builder_win.winfo_exists():
            # Schedule the prefill to run after the window is fully visible and ready.
            self._strat_builder_win.after(50, lambda: self._strat_builder_win._prefill_from_idea(idea_data))

    def _toggle_fullscreen(self):
        is_full = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not is_full)
        self.root.bind("<Escape>", lambda e: self._toggle_fullscreen())


    def _refresh_tooltips(self, label_dict, tooltip_dict):
        # Add tooltips only if educational mode is ON
        if self.educational_mode.get():
            for key, label in label_dict.items():
                if key in tooltip_dict:
                    Tooltip(label, tooltip_dict[key])

    def show_greek_analysis(self):
        if not self.input_data or 'greek_inputs' not in self.input_data:
            messagebox.showwarning("No Greeks", "Please run an analysis first and input Greek values.", parent=self.root)
            return
        from core.models.Greeks import Greeks
        Greeks(self.root, self.input_data['greek_inputs'], self.input_data['S0'], self.input_data['T_days'], dark_mode=(self.current_theme == 'dark'))

    def show_copyable_error(self, title: str, message: str):
            """Displays a custom error dialog with a visible 'Copy to Clipboard' button."""
            win = tk.Toplevel(self.root)
            win.title(title)
            win.geometry("600x400")
            win.transient(self.root)
            win.grab_set()
            self.apply_theme_to_window(win)

            main_frame = ttk.Frame(win, padding=15)
            main_frame.pack(expand=True, fill=tk.BOTH)

            # --- Button Frame (Packed to the bottom first) ---
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

            def _copy_to_clipboard():
                self.root.clipboard_clear()
                self.root.clipboard_append(message)
                copy_btn.config(text="✓ Copied!")
                copy_btn.after(2000, lambda: copy_btn.config(text="Copy to Clipboard"))

            # Pack buttons from the right side of the button_frame
            close_btn = ttk.Button(button_frame, text="Close", command=win.destroy)
            close_btn.pack(side=tk.RIGHT)
            
            copy_btn = ttk.Button(button_frame, text="Copy to Clipboard", command=_copy_to_clipboard)
            copy_btn.pack(side=tk.RIGHT, padx=(0, 10))

            # --- Text Frame (Fills all remaining space) ---
            text_frame = ttk.LabelFrame(main_frame, text="Error Details")
            text_frame.pack(expand=True, fill=tk.BOTH)
            text_frame.rowconfigure(0, weight=1)
            text_frame.columnconfigure(0, weight=1)

            text_box = tk.Text(text_frame, wrap=tk.WORD, relief="flat", padx=10, pady=5)
            text_box.grid(row=0, column=0, sticky="nsew")
            text_box.insert(tk.END, message)
            text_box.config(state=tk.DISABLED)

            vsb = ttk.Scrollbar(text_frame, orient="vertical", command=text_box.yview)
            vsb.grid(row=0, column=1, sticky="ns")
            text_box.configure(yscrollcommand=vsb.set)
            
            # Apply theme to the text box
            theme_settings = self.theme_settings()
            text_box.config(background=theme_settings['entry_bg'], foreground=theme_settings['fg'])




    # In class OptionAnalyzerApp:

    def show_llm_explanation(self, idea: Idea | None = None):
        # --- REPLACEMENT START ---
        """
        Shows an LLM explanation for the current analysis and provides an
        option to save it directly into the analysis notes.
        """
        if not self.input_data:
            messagebox.showwarning("No Data", "Please run an analysis first.", parent=self.root)
            return

        # This feature is now specifically for the main analysis data.
        prompt_data = {
            "ticker": self.input_data.get('ticker'),
            "option_type": self.input_data.get('option_type'),
            "strike": self.input_data.get('strike'),
            "S0": self.input_data.get('S0'),
            "premium": self.input_data.get('fair_price'),
            "T_days": self.input_data.get('T_days'),
            "prob": self.input_data.get('probability'),
            "title": "Custom Analysis",
            "description": f"A {self.input_data.get('option_type')} option with a strike of ${self.input_data.get('strike')}",
            "sigma": self.input_data.get('sigma'),
            "realized_vol": self.input_data.get('realized_vol'),
            "fair_price": self.input_data.get('fair_price'),
            "greek_inputs": self.input_data.get('greek_inputs')
        }
        popup_title = f"📘 LLM Analysis: {prompt_data['ticker']}"

        self.set_status("Asking the LLM for an explanation...", color="orange")

        def llm_thread_worker():
            try:
                explanation = self.llm.explain_option_strategy(**prompt_data)
                self.root.after(0, show_popup, explanation)
            except (ConnectionError, PermissionError) as e:
                self.root.after(0, lambda err_msg=str(e): messagebox.showerror("LLM Error", err_msg, parent=self.root))
            except Exception as e:
                self.root.after(0, lambda: self.show_copyable_error("LLM Error", f"An unexpected error occurred:\n{traceback.format_exc()}"))
            finally:
                self.root.after(0, self.set_status, "Ready.")

        def show_popup(explanation):
            popup = tk.Toplevel(self.root)
            popup.title(popup_title)
            popup.geometry("700x600")
            self.apply_theme_to_window(popup)

            text_frame = ttk.Frame(popup, padding=5)
            text_frame.pack(expand=True, fill=tk.BOTH)
            text_box = tk.Text(text_frame, wrap=tk.WORD, relief="flat", padx=15, pady=15, font=("Segoe UI", 10))
            text_box.pack(expand=True, fill=tk.BOTH)
            text_box.insert(tk.END, explanation)
            text_box.config(state=tk.DISABLED)

            theme_settings = self.theme_settings()
            text_box.config(background=theme_settings['entry_bg'], foreground=theme_settings['fg'])
            
            button_frame = ttk.Frame(popup, padding=(10, 0, 10, 10))
            button_frame.pack(fill=tk.X)
            
            def save_and_close_action():
                # Call the save dialog, pre-filling it with the explanation
                self._prompt_save_analysis(prefill_notes=explanation)
                # Close the explanation popup after opening the save dialog
                popup.destroy()

            ttk.Button(button_frame, text="💾 Save Analysis w/ Notes", command=save_and_close_action).pack(side=tk.RIGHT)
            ttk.Button(button_frame, text="Close", command=popup.destroy).pack(side=tk.RIGHT, padx=(0, 10))

        threading.Thread(target=llm_thread_worker, daemon=True).start()
       
# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    # Hide the main window immediately to prevent the flash
    root.withdraw()
    
    app = OptionAnalyzerApp(root)
    
    try:
        root.mainloop()
    except tk.TclError:
        print("GUI closed by user.")
    except KeyboardInterrupt:
        print("Application interrupted by user.")
    finally:
        sys.exit()




