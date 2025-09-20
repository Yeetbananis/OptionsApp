# ── Standard library imports ──────────────────────
import threading
import logging
import time
from pathlib import Path
import datetime as _dt
from typing import Any

# ── Third-party libraries ─────────────────────────
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkcalendar import DateEntry
import matplotlib.dates as mdates
from PIL import Image, ImageTk

# ── Local modules ─────────────────────────────────
from ui.filter_dialog import FilterDialog
from core.models.filters import FilterConfig
from ui.bounceoverlay import BounceOverlay
from app.config import StrategyConfig
from core.engine.backtestengine import BacktestEngine
from core.engine.batch_runner import BatchRunner
from core.storage.data_loader import get_prices
from core.engine.backtester import realized_vol


ICON_DIR = Path(__file__).parent.parent.parent / "data" / "icons"

# Configure logging for the GUI part
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - GUI - %(message)s')

# --- SPY Backup (deferred) ----------------------------------
def ensure_spy_backup():
    from pathlib import Path
    import datetime as _dt, requests, io
    import yfinance as yf
    import logging
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    backup = data_dir / "SPY_backup.csv"
    if backup.exists():
        return
    today = _dt.datetime.today().strftime("%Y-%m-%d")
    try:
        df = yf.download("SPY", start="2000-01-01", end=today, progress=False)
        if df.empty:
            raise ValueError("yfinance returned empty DataFrame")
    except Exception as e:
        logging.warning(f"SPY backup via yfinance failed: {e}, falling back to Stooq.")
        d1 = "20000101"
        d2 = _dt.datetime.today().strftime("%Y%m%d")
        url = f"https://stooq.com/q/d/l/?s=spy.us&d1={d1}&d2={d2}&i=d"
        resp = requests.get(url, timeout=10); resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"], index_col="Date").sort_index()
    df.to_csv(backup)

_icon_cache = {}
def load_icon(path, tint_color=None, tint_black=False, size=(24, 24)):
    """
    Load an icon, tint it, and cache the result to avoid redundant file I/O.
    """
    cache_key = (path, tint_color, tint_black, size)
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]
    
    try:
        img = Image.open(path).convert("RGBA").resize(size, Image.LANCZOS)
        if tint_black:
            tint = (0, 0, 0, 255)
        elif tint_color:
            if isinstance(tint_color, str) and tint_color.startswith('#'):
                rgb = tuple(int(tint_color.lstrip('#')[i:i+2], 16) for i in (0,2,4))
                tint = (*rgb, 255)
            elif isinstance(tint_color, tuple):
                tint = tint_color if len(tint_color)==4 else (*tint_color,255)
            else:
                tint = (0, 0, 0, 255)
        else:
            photo_image = ImageTk.PhotoImage(img)
            _icon_cache[cache_key] = photo_image
            return photo_image

        r, g, b, a = img.split()
        colored = Image.new("RGBA", img.size, tint)
        colored.putalpha(a)
        photo_image = ImageTk.PhotoImage(colored)
        _icon_cache[cache_key] = photo_image
        return photo_image
    except Exception as e:
        logging.error(f"Failed to load icon {path}: {e}")
        return None



class StrategyTesterWindow:
    def __init__(self, parent, app_instance):
        self.app = app_instance
        self.theme = self.app.current_theme
        self.copy_perf_btn = None
        self.log_tree = None
        self.history_tree = None
        self.wifi_label = None
        self.fullscreen_button = None
        self.fig = None
        self.ax = None
        self.canvas = None

        theme_settings = self.app.theme_settings()
        self.current_theme_settings = theme_settings
        self.summary_txt_fg = theme_settings.get("fg", "#ffffff" if self.theme == "dark" else "#000000")

        self.win = tk.Toplevel(parent)
        self.win.title("Options Strategy Backtester")
        self.win.geometry("1400x900")
        self.win.protocol("WM_DELETE_WINDOW", self.on_close)

        self.filters = FilterConfig()
        self.current_wifi_status = "down"
        self._next_trade_iid = 1
        self._last_progress_ts = 0.0
        self.is_graph_fullscreen = False
        self.graph_original_parent = None
        self._pending_trades = []
        self._flush_scheduled = False
        self.selected_trade_iid = None
        self.trade_marker = None
        self.bounce = BounceOverlay(self.win)
        self.custom_legs = []

        self._end_early = False
        self.stat_labels = {}
        self.optimization_runs_data = {}

        icon_fg_color = self.summary_txt_fg
        self.icons = {
            "down": load_icon(ICON_DIR/"wifi_disconnected.png", tint_color=icon_fg_color),
            "weak": load_icon(ICON_DIR/"wifi_weak.png", tint_color=icon_fg_color),
            "medium": load_icon(ICON_DIR/"wifi_medium.png", tint_color=icon_fg_color),
            "strong": load_icon(ICON_DIR/"wifi_strong.png", tint_color=icon_fg_color),
            "secure": load_icon(ICON_DIR/"wifi_secure.png", tint_color=icon_fg_color),
        }
        self.fullscreen_icon = load_icon(ICON_DIR / "fullscreen.png", tint_color=icon_fg_color, size=(16, 16))
        self.minimize_icon = load_icon(ICON_DIR / "minimize.png", tint_color=icon_fg_color, size=(16, 16))

        self._create_widgets() # Create all GUI elements

        # Get theme colors for manually styling the context menus
        theme_settings = self.app.theme_settings()
        menu_fg = theme_settings.get("fg", "black")
        menu_bg = theme_settings.get("bg", "white")
        
        # Create a themed menu for the "Trade Log" table
        self._log_tree_menu = tk.Menu(self.win, tearoff=0, background=menu_bg, foreground=menu_fg)
        self._log_tree_menu.add_command(label="Copy", command=self._copy_tree_selection)

        # Create a themed menu for the "Optimization Results" table with the extra option
        self._history_tree_menu = tk.Menu(self.win, tearoff=0, background=menu_bg, foreground=menu_fg)
        self._history_tree_menu.add_command(label="Load Trades for Selected Run", command=self._load_selected_run_trades)
        self._history_tree_menu.add_separator()
        self._history_tree_menu.add_command(label="Copy", command=self._copy_tree_selection)

        # Bind the right-click event to our intelligent handler for both trees
        if self.log_tree: self.log_tree.bind("<Button-3>", self._show_tree_context_menu)
        if self.history_tree: self.history_tree.bind("<Button-3>", self._show_tree_context_menu)
        
        # <<< FIX: Removed the old TextHandler logging setup which is no longer used >>>
        self._setup_default_values()
        logging.info("Strategy Tester window initialized.")

        self.app.apply_theme_to_window(self.win)
        self.update_theme(self.theme)


    def _show_text_context_menu(self, event):
        # only show if there is a selection
        try:
            sel = self.summary_txt.selection_get()
        except tk.TclError:
            return
        self._text_menu.tk_popup(event.x_root, event.y_root)

    def _copy_text_selection(self):
        try:
            text = self.summary_txt.selection_get()
        except tk.TclError:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(text)

    def _show_tree_context_menu(self, event):
        """Intelligently shows the correct context menu based on the treeview clicked."""
        widget = event.widget
        iid = widget.identify_row(event.y)
        if not iid:
            return
        
        widget.selection_set(iid)
        self._last_tree = widget # Remember which tree for the 'Copy' command

        # Display the correct menu for the specific tree
        if widget == self.history_tree:
            self._history_tree_menu.tk_popup(event.x_root, event.y_root)
        else:
            self._log_tree_menu.tk_popup(event.x_root, event.y_root)

    def _copy_tree_selection(self):
        widget = getattr(self, "_last_tree", None)
        if not widget:
            return
        sel = widget.selection()
        if not sel:
            return
        vals = widget.item(sel[0], "values")
        text = "\t".join(str(v) for v in vals)
        self.win.clipboard_clear()
        self.win.clipboard_append(text)


    def _create_widgets(self):
        self.HEADER_NORMAL_HEIGHT = 275
        self.HEADER_EXPANDED_HEIGHT = 325 # Give it more space for the progress bar

        self.main_pane = tk.PanedWindow(self.win, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Header with custom legs display
        hdr = ttk.LabelFrame(self.main_pane, text="Backtest Configuration", padding=15)
        self.main_pane.add(hdr, stretch="never")

        # Add custom legs display label
        self.custom_legs_label = ttk.Label(
            hdr, text="Custom Strategy: None", font=('Segoe UI', 9, 'italic')
        )
        self.custom_legs_label.pack(anchor="nw", padx=10, pady=5)

        # Content frame with inputs
        content_frame = ttk.Frame(hdr)
        content_frame.pack(fill="both", expand=True)

        # Left: inputs organized in a grid layout
        inputs_frame = ttk.Frame(content_frame)
        inputs_frame.pack(side="left", fill="both", expand=True)

        # Row 0: First row of parameters
        ttk.Label(inputs_frame, text="Underlying:").grid(row=0, column=0, sticky="e", padx=(5, 2), pady=8)
        self.symbol_ent = ttk.Entry(inputs_frame, width=8)
        self.symbol_ent.grid(row=0, column=1, sticky="w", padx=(2, 10), pady=8)


        ttk.Label(inputs_frame, text="Start Date:").grid(row=0, column=2, sticky="e", padx=(5, 2), pady=8)
        # Get theme settings from the parent app for DateEntry initialization
        th_init = self.app.theme_settings() if hasattr(self.app, 'theme_settings') else {}
        if not th_init:  # Fallback if theme_settings doesn't exist or returns empty
            th_init = {"entry_bg": "#25a37e", "fg": "#E30303", "bg": "#e68e12ac"} #should not be hit
        date_kwargs_init = {
            'background': th_init["entry_bg"],
            'foreground': th_init["fg"],
            'bordercolor': th_init["bg"],
            'headersbackground': th_init["bg"],
            'headersforeground': th_init["fg"],
        }
        self.start_ent = DateEntry(
            inputs_frame,
            width=10,
            date_pattern="yyyy-MM-dd",
            **date_kwargs_init # Apply the detailed styling
        )
        self.start_ent.grid(row=0, column=3, sticky='w', padx=5, pady=2)
        self.start_ent.set_date(_dt.date.today() - _dt.timedelta(days=365*2))

        ttk.Label(inputs_frame, text="End Date:").grid(row=0, column=4, sticky="e", padx=(5, 2), pady=8)
        self.end_ent = DateEntry(
            inputs_frame,
            width=10,
            date_pattern="yyyy-MM-dd",
            **date_kwargs_init  # Apply the same detailed styling as start_ent
        )
        self.end_ent.grid(row=0, column=5, sticky="w", padx=(2, 10), pady=8)
        self.end_ent.set_date(_dt.date.today() - _dt.timedelta(days=7))  # Default to one week ago
        
        ttk.Label(inputs_frame, text="DTE:").grid(row=0, column=6, sticky="e", padx=(5, 2), pady=8)
        self.dte_ent = ttk.Entry(inputs_frame, width=5)
        self._add_numeric_validation(self.dte_ent, float, min_val=0.01)
        self.dte_ent.grid(row=0, column=7, sticky="w", padx=(2, 10), pady=8)
        
        ttk.Label(inputs_frame, text="Capital $:").grid(row=0, column=8, sticky="e", padx=(5, 2), pady=8)
        self.cap_ent = ttk.Entry(inputs_frame, width=10)
        self._add_numeric_validation(self.cap_ent, float, min_val=0.01)
        self.cap_ent.grid(row=0, column=9, sticky="w", padx=(2, 5), pady=8)

        # Row 1: Second row of parameters
        ttk.Label(inputs_frame, text="Strategy:").grid(row=1, column=0, sticky="e", padx=(5, 2), pady=8)
        self.strat_cbo = ttk.Combobox(inputs_frame, values=["Short Put", "Put Credit Spread", "Custom Strategy"], state="readonly", width=18)
        self.strat_cbo.grid(row=1, column=1, columnspan=2, sticky="w", padx=(2, 10), pady=8)
        self.strat_cbo.bind("<<ComboboxSelected>>", self._toggle_builder_visibility)
        
        ttk.Label(inputs_frame, text="Alloc %:").grid(row=1, column=3, sticky="e", padx=(5, 2), pady=8)
        self.alloc_ent = ttk.Entry(inputs_frame, width=5)
        self._add_numeric_validation(self.alloc_ent, float, min_val=0.01)
        self.alloc_ent.grid(row=1, column=4, sticky="w", padx=(2, 10), pady=8)
        
        ttk.Label(inputs_frame, text="Profit Tgt %:").grid(row=1, column=5, sticky="e", padx=(5, 2), pady=8)
        self.pt_ent = ttk.Entry(inputs_frame, width=5)
        self._add_numeric_validation(self.pt_ent, float, min_val=0.01)
        self.pt_ent.grid(row=1, column=6, sticky="w", padx=(2, 10), pady=8)
        
        ttk.Label(inputs_frame, text="Stop xCr:").grid(row=1, column=7, sticky="e", padx=(5, 2), pady=8)
        self.sl_ent = ttk.Entry(inputs_frame, width=5)
        self._add_numeric_validation(self.sl_ent, float, min_val=0.01)
        self.sl_ent.grid(row=1, column=8, sticky="w", padx=(2, 10), pady=8)
        
        ttk.Label(inputs_frame, text="Comm $/ct:").grid(row=1, column=9, sticky="e", padx=(5, 2), pady=8)
        self.comm_ent = ttk.Entry(inputs_frame, width=6)
        self._add_numeric_validation(self.comm_ent, float, min_val=0.01)
        self.comm_ent.grid(row=1, column=10, sticky="w", padx=(2, 5), pady=8)

        ttk.Label(inputs_frame, text="Benchmark:").grid(row=2, column=0, sticky="e", padx=(5,2), pady=8)
        self.benchmark_cbo = ttk.Combobox(inputs_frame, values=["SPY", "QQQ", "TLT"], state="readonly", width=8)
        self.benchmark_cbo.grid(row=2, column=1, sticky="w", padx=(2, 10), pady=8)
        self.benchmark_cbo.current(0)

        self.benchmark_var = tk.BooleanVar(value=True)
        self.benchmark_chk = ttk.Checkbutton(inputs_frame, text="Compare to Benchmark", variable=self.benchmark_var)
        self.benchmark_chk.grid(row=2, column=2, columnspan=2, sticky="w", padx=(2, 10), pady=8)

        ttk.Label(inputs_frame, text="Filters:").grid(row=3, column=0, sticky="e", padx=(5,2), pady=8)
        self.filter_btn = ttk.Button(inputs_frame, text="⚙ Filters…", command=self._open_filter_dialog, width=12)
        self.filter_btn.grid(row=3, column=1, columnspan=2, sticky="w", pady=8)

        # Right: button frame
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(side="right", fill="y", padx=15)

        # ─── tiny “WiFi status:” label above the icon ───
        self.wifi_text = ttk.Label(
            hdr,
            text="WiFi status:",
            font=('Segoe UI', 8),               # very small
        )
        # place it just above the icon
        self.wifi_text.place(relx=1.0, rely=0.0, anchor="ne", x=0, y=-16)

        # now the actual icon
        self.wifi_label = ttk.Label(
            hdr,
            image=self.icons["down"],
            style='Wifi.TLabel'
        )
        self.wifi_label.place(relx=1.0, rely=0.0, anchor="ne", x=-5, y=0)
        self.check_wifi()


        self.run_btn = ttk.Button(button_frame, text="▶ Run Backtest", command=self._start_backtest, width=16)
        self.run_btn.pack(pady=10)

        self.build_btn = ttk.Button(button_frame, text="🔧 Build Legs", command=self._open_custom_builder, width=16)
        self.build_btn.pack(pady=5)
        self.build_btn.pack_forget()

        self.optimize_btn = ttk.Button(button_frame, text="⚙ Optimize", command=self._open_optimize_dialog, width=16)
        self.optimize_btn.pack(pady=5)

        self.opt_toolbar = ttk.Frame(button_frame)
        self.pause_opt_btn = ttk.Button(self.opt_toolbar, text="⏸ Pause", command=self._toggle_pause_opt, state='disabled')
        self.pause_opt_btn.pack(side='left', padx=4)
        self.end_early_btn = ttk.Button(self.opt_toolbar, text="⏹ End Early", command=self._end_early_optimization, state='disabled')
        self.end_early_btn.pack(side='left', padx=4)
        self.cancel_opt_btn = ttk.Button(self.opt_toolbar, text="✖ Cancel", command=self._cancel_optimization, state='disabled')
        self.cancel_opt_btn.pack(side='left', padx=4)

        # Create the new label for status text animations
        self.status_label = ttk.Label(button_frame, text="", font=('Segoe UI', 9, 'italic'))


        self.opt_combo_lbl = ttk.Label(button_frame, text="", font=('Segoe UI', 9, 'italic'), foreground='#888888', width=65, anchor='w')
        self.opt_combo_lbl.pack(fill='x', padx=4, pady=(2,0))
        self.opt_progress_lbl = ttk.Label(button_frame, text="", font=('Segoe UI', 9))
        self.opt_progress_lbl.pack(fill='x', padx=4)

        #style progress

        self.progress = ttk.Progressbar(button_frame, mode="determinate", maximum=1, value=0)
        self.progress.pack(fill='x', padx=4, pady=(2,10))
        # Configure progress bar colors based on theme
        progress_style = ttk.Style()
        # Configure progress bar colors based on theme
        if hasattr(self.app, 'progress_style'):
            self.progress.configure(style=self.app.progress_style)
        else:
            # Fallback in case the parent app doesn't have a progress style defined
            progress_style = ttk.Style()
            theme = self.theme
            progress_style.configure("TProgressbar", 
                background="#187808" if theme == "dark" else "#4caf50",
                troughcolor="#2e2e2e" if theme == "dark" else "#e0e0e0")
            self.progress.configure(style="TProgressbar")

        self.opt_toolbar.pack_forget()
        self.opt_combo_lbl.pack_forget()
        self.opt_progress_lbl.pack_forget()
        self.progress.pack_forget()

        results_pane = tk.PanedWindow(self.main_pane, orient=tk.HORIZONTAL, sashrelief=tk.RAISED)
        self.main_pane.add(results_pane, stretch="always")


         # <<< FIX: Create a resizable VERTICAL pane for the left side >>>
        left_vertical_pane = tk.PanedWindow(results_pane, orient=tk.VERTICAL, sashrelief=tk.RAISED)
        results_pane.add(left_vertical_pane, stretch="always")

        # Create the summary frame that will go in the TOP of the vertical pane
        summary_frame = ttk.LabelFrame(left_vertical_pane, text="Performance Summary", padding=10)
        left_vertical_pane.add(summary_frame, stretch="never") # Add to the pane


        # <<< FIX: This frame now uses a grid to place metric sections horizontally >>>
        summary_content_frame = ttk.Frame(summary_frame)
        summary_content_frame.pack(fill='x', expand=True)
        
        # Create a frame for each horizontal section
        perf_frame = ttk.Frame(summary_content_frame)
        perf_frame.grid(row=0, column=0, sticky='nw', padx=(0, 10))
        
        sep1 = ttk.Separator(summary_content_frame, orient='vertical')
        sep1.grid(row=0, column=1, sticky='ns', padx=10, pady=5)

        risk_frame = ttk.Frame(summary_content_frame)
        risk_frame.grid(row=0, column=2, sticky='nw', padx=10)

        sep2 = ttk.Separator(summary_content_frame, orient='vertical')
        sep2.grid(row=0, column=3, sticky='ns', padx=10, pady=5)

        trade_frame = ttk.Frame(summary_content_frame)
        trade_frame.grid(row=0, column=4, sticky='nw', padx=(10, 0))

        # Helper function to create a metric row in a specific parent frame
        def create_metric_row(parent, row, key, label_text):
            label = ttk.Label(parent, text=label_text + ":")
            label.grid(row=row, column=0, sticky='e', padx=(0, 10))
            value_label = ttk.Label(parent, text="N-A", font=('Segoe UI', 9, 'bold'), anchor='w')
            value_label.grid(row=row, column=1, sticky='w')
            self.stat_labels[key] = value_label
        
        # -- Populate Performance Section --
        ttk.Label(perf_frame, text="Overall Performance", font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        create_metric_row(perf_frame, 1, 'start_value', 'Start Equity')
        create_metric_row(perf_frame, 2, 'end_value', 'End Equity')
        create_metric_row(perf_frame, 3, 'total_return', 'Total Return ($)')
        create_metric_row(perf_frame, 4, 'total_return_pct', 'Total Return (%)')
        create_metric_row(perf_frame, 5, 'cagr', 'CAGR (%)')

        # -- Populate Risk Section --
        ttk.Label(risk_frame, text="Risk Analysis", font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        create_metric_row(risk_frame, 1, 'unlimited_risk', 'Unlimited Risk')
        create_metric_row(risk_frame, 2, 'sharpe', 'Sharpe Ratio')
        create_metric_row(risk_frame, 3, 'sortino', 'Sortino Ratio')
        create_metric_row(risk_frame, 4, 'max_drawdown', 'Max Drawdown ($)')
        create_metric_row(risk_frame, 5, 'ulcer_index', 'Ulcer Index')

        # -- Populate Trade Stats Section --
        ttk.Label(trade_frame, text="Trade Statistics", font=('Segoe UI', 9, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        create_metric_row(trade_frame, 1, 'total_trades', 'Total Trades')
        create_metric_row(trade_frame, 2, 'win_rate', 'Win Rate (%)')
        create_metric_row(trade_frame, 3, 'profit_factor', 'Profit Factor')
        create_metric_row(trade_frame, 4, 'expectancy', 'Expectancy ($)')
        self.beat_spy_label = ttk.Label(trade_frame, text="")
        self.beat_spy_label.grid(row=5, column=0, columnspan=2, sticky='w', pady=(5,0))
        

        self.copy_perf_btn = ttk.Button(summary_frame, text="📋 Copy Metrics", command=self._copy_performance_metrics)
        self.copy_perf_btn.pack(anchor="ne", side='bottom', pady=(10, 0))

        # Create the plot frame that will go in the BOTTOM of the vertical pane
        plot_frame = ttk.LabelFrame(left_vertical_pane, text="Equity Curve", padding=5)
        left_vertical_pane.add(plot_frame, stretch="always") # Add to the pane

        fig_bg = "#0f0f0f" if self.theme == "dark" else "#f0f0f0"
        self.fig, self.ax = plt.subplots(facecolor=fig_bg)
        self.ax.set_facecolor("#0f0f0f" if self.theme == "dark" else "#ffffff")
        self.ax.tick_params(colors=self.summary_txt_fg)
        self.ax.xaxis.label.set_color(self.summary_txt_fg)
        self.ax.yaxis.label.set_color(self.summary_txt_fg)
        self.ax.title.set_color(self.summary_txt_fg)
        for s in self.ax.spines.values(): s.set_color(self.summary_txt_fg)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.fig.tight_layout()

        # --- Add Fullscreen Button ---
        try:
            # Get foreground color based on the theme from the parent app
            fg_color = self.summary_txt_fg  # Already defined based on theme in __init__
            
            self.fullscreen_icon = load_icon(
                ICON_DIR / "fullscreen.png",
                tint_color=fg_color,
                size=(16, 16)
            )
            self.minimize_icon = load_icon(
                ICON_DIR / "minimize.png",
                tint_color=fg_color,
                size=(16, 16)
            )

            # Create and place the button using these tinted icons:
            button_container = ttk.Frame(plot_frame)
            button_container.place(relx=1.0, rely=0.0, anchor='ne', x=-5, y=5)
            self.fullscreen_button = ttk.Button(
                button_container,
                image=self.fullscreen_icon,
                command=self._toggle_fullscreen_graph
            )
            self.fullscreen_button.image_ref = self.fullscreen_icon
            self.fullscreen_button.pack()


        except Exception as e:
            logging.error(f"Could not load fullscreen/minimize icons: {e}")
            # Fallback to minimal text button
            button_container = ttk.Frame(plot_frame)
            button_container.place(relx=0.99, rely=0.01, anchor='ne', x=-2, y=2)

            self.fullscreen_button = ttk.Button(
                button_container,
                text="FS",
                command=self._toggle_fullscreen_graph,
                style='Transparent.TButton'
            )
            self.fullscreen_button.pack()
        # --- End Add Fullscreen Button ---

        # Initialize tooltip for equity curve
        self._setup_tooltip()

        if hasattr(self, 'canvas'):
            self.canvas.mpl_connect('button_press_event', self._on_plot_click)

        log_frame = ttk.LabelFrame(results_pane, text="Trade Logs", padding=10)
        results_pane.add(log_frame, stretch="always")

        tabs = ttk.Notebook(log_frame)
        best_tab = ttk.Frame(tabs)
        hist_tab = ttk.Frame(tabs)
        tabs.add(best_tab, text="Trade Log")
        tabs.add(hist_tab, text="Optimization Results")
        tabs.pack(fill="both", expand=True)

        cols = ("Trade #","Open Date","Close Date","K Short","K Long","Contracts","Credit ($)","PnL ($)")
        widths = (60, 90, 90, 70, 70, 70, 80, 90)

        # --- Filter Entry Box ---
        filter_frame = tk.Frame(best_tab)
        filter_frame.pack(fill="x", padx=10, pady=(10, 0))

        self.filter_var = tk.StringVar()
        self.filter_entry = tk.Entry(filter_frame, textvariable=self.filter_var)
        self.filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.filter_button = tk.Button(filter_frame, text="Filter Trades", command=self._filter_trades)
        self.filter_button.pack(side="left")

        # Create a frame for the Treeview and scrollbars to avoid mixing pack and grid
        tree_frame = ttk.Frame(best_tab)
        tree_frame.pack(fill="both", expand=True)

        self.log_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=15)
        for i, c in enumerate(cols):
            self.log_tree.heading(c, text=c, command=lambda cc=c: self._sort_treeview(self.log_tree, cc, False))
            self.log_tree.column(c, width=widths[i], anchor="c", stretch=True)
        self.log_tree.tag_configure('oddrow')
        self.log_tree.tag_configure('evenrow')


        vsb_best = ttk.Scrollbar(tree_frame, orient="vertical", command=self.log_tree.yview)
        hsb_best = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.log_tree.xview)
        self.log_tree.configure(yscrollcommand=vsb_best.set, xscrollcommand=hsb_best.set)

        # Use grid within the tree_frame
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.log_tree.grid(row=0, column=0, sticky="nsew")
        vsb_best.grid(row=0, column=1, sticky="ns")
        hsb_best.grid(row=1, column=0, sticky="ew")
        self.export_btn = tk.Button(best_tab, text="💾 Export Trades", command=self._export_trades_to_csv)
        self.export_btn.pack(anchor="ne", pady=5, padx=10)
        self.log_tree.bind('<<TreeviewSelect>>', self._on_trade_select)
        self.log_tree.bind("<Button-3>", self._show_trade_right_click)

        # REPLACE THE OLD history_tree SETUP WITH THIS
        opt_cols = {
            "Return %": 80, "CAGR %": 80, "Sharpe": 70, "Win Rate %": 80,
            "Trades": 60, "DTE": 50, "Alloc %": 60, "PT %": 50, "SL xCr": 50
        }
        self.history_tree = ttk.Treeview(hist_tab, columns=list(opt_cols.keys()), show="headings", height=15)
        for col, width in opt_cols.items():
            self.history_tree.heading(col, text=col)
            self.history_tree.column(col, width=width, anchor="c")
        self.history_tree.tag_configure('oddrow')
        self.history_tree.tag_configure('evenrow')

        vsb_hist = ttk.Scrollbar(hist_tab, orient="vertical", command=self.history_tree.yview)
        hsb_hist = ttk.Scrollbar(hist_tab, orient="horizontal", command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=vsb_hist.set, xscrollcommand=hsb_hist.set)
        hist_tab.rowconfigure(0, weight=1)
        hist_tab.columnconfigure(0, weight=1)
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        vsb_hist.grid(row=0, column=1, sticky="ns")
        hsb_hist.grid(row=1, column=0, sticky="ew")

        # --- Set initial pane sizes ---
        self.win.update_idletasks()
        self.main_pane.sash_place(0, 0, self.HEADER_NORMAL_HEIGHT)
        results_pane.sash_place(0, 850, 0)
        
        # Dynamically set the summary pane height to fit its content cleanly
        summary_frame.update_idletasks()
        required_height = summary_frame.winfo_reqheight()
        left_vertical_pane.sash_place(0, 0, required_height + 20) # Add padding


    def check_wifi(self):
        def worker():
            import time, requests
            host = "https://www.google.com"
            try:
                start = time.time()
                resp  = requests.get(host, timeout=1.0)
                latency = (time.time() - start) * 1000  # ms
                if not resp.ok:
                    icon_key = "down"
                elif latency < 100:
                    icon_key = "strong"
                elif latency < 300:
                    icon_key = "medium"
                else:
                    icon_key = "weak"
                if resp.url.startswith("https://"):
                    icon_key = "secure"
            except Exception:
                icon_key = "down"

            if self.win.winfo_exists():
                # update on main thread
                self.current_wifi_status = icon_key
                self.win.after(0, lambda: self.wifi_label.configure(image=self.icons[icon_key]))

        # fire off the worker thread
        threading.Thread(target=worker, daemon=True).start()
        # schedule next poll in 5s
        if self.win.winfo_exists():
            self.win.after(5000, self.check_wifi)


    def on_close(self):
            """Handles window closing and notifies the parent app."""
            self.app.remove_strategy_tester(self)
            self.win.destroy()

    def recreate_date_entries(self): #destroy and recreate calendar fields (only fix found for improper theme switch)
        th = self.app.theme_settings()

        date_kwargs = {
            'background': th["entry_bg"],
            'foreground': th["fg"],
            'bordercolor': th["bg"],
            'headersbackground': th["bg"],
            'headersforeground': th["fg"],
            'selectbackground': th["entry_bg"],
            'selectforeground': th["fg"]
        }

        # Save current dates
        start_date = self.start_ent.get_date()
        end_date = self.end_ent.get_date()

        # Destroy existing widgets
        self.start_ent.destroy()
        self.end_ent.destroy()

        # Recreate start_ent
        self.start_ent = DateEntry(
            self.start_ent.master,
            width=10,
            date_pattern="yyyy-MM-dd",
            **date_kwargs
        )
        self.start_ent.grid(row=0, column=3, sticky='w', padx=5, pady=2)
        self.start_ent.set_date(start_date)

        # Recreate end_ent
        self.end_ent = DateEntry(
            self.end_ent.master,
            width=10,
            date_pattern="yyyy-MM-dd",
            **date_kwargs
        )
        self.end_ent.grid(row=0, column=5, sticky="w", padx=(2, 10), pady=8)
        self.end_ent.set_date(end_date)


    def update_theme(self, new_theme):
        """Updates the window's theme-dependent elements."""
        self.theme = new_theme
        th = self.app.theme_settings()
        if not th:
            logging.error("StrategyTester: No theme settings found from app, cannot update theme.")
            return

        self.summary_txt_bg = th.get("entry_bg", "#3c3c3c" if self.theme == "dark" else "#ffffff")
        self.summary_txt_fg = th.get("fg", "#ffffff" if self.theme == "dark" else "#000000")
        fg_color = self.summary_txt_fg
        bg_color = th.get("bg", "#2e2e2e" if self.theme == "dark" else "#f0f0f0")

        print(f"StrategyTester: Updating theme to {self.theme}")

        # 1. Update Plot Colors
        if self.fig and self.ax and self.canvas: # Check if plot elements exist
            self.fig.patch.set_facecolor(bg_color)
            self.ax.set_facecolor(self.summary_txt_bg)
            self.ax.tick_params(colors=self.summary_txt_fg, which='both')
            if hasattr(self.ax.xaxis, 'label'): self.ax.xaxis.label.set_color(self.summary_txt_fg)
            if hasattr(self.ax.yaxis, 'label'): self.ax.yaxis.label.set_color(self.summary_txt_fg)
            if hasattr(self.ax, 'title'): self.ax.title.set_color(self.summary_txt_fg)
            for s in self.ax.spines.values(): s.set_edgecolor(self.summary_txt_fg)
            self.ax.grid(True, linestyle='--', linewidth=0.5, color=self.summary_txt_fg, alpha=0.3)
            self.canvas.draw_idle()

        # 2. Update Calendar (DateEntry) - both popup and entry field   
        self.recreate_date_entries()

        # 3. Update Treeview Tags
        if self.log_tree and self.history_tree: # Check if trees exist
            profit_color, loss_color = ("#006400", "#8B0000") if self.theme == "dark" else ("#d0f0c0", "#f0d0d0")
            self.log_tree.tag_configure('profit', background=profit_color, foreground=self.summary_txt_fg)
            self.log_tree.tag_configure('loss', background=loss_color, foreground=self.summary_txt_fg)
            self.history_tree.tag_configure('profit', background=profit_color, foreground=self.summary_txt_fg)
            self.history_tree.tag_configure('loss', background=loss_color, foreground=self.summary_txt_fg)
        
        # 4. Update Icons
        icon_fg_color = self.summary_txt_fg
        self.icons = { # Re-load icons with new tint color
            "down": load_icon(ICON_DIR/"wifi_disconnected.png", tint_color=icon_fg_color),
            "weak": load_icon(ICON_DIR/"wifi_weak.png", tint_color=icon_fg_color),
            "medium": load_icon(ICON_DIR/"wifi_medium.png", tint_color=icon_fg_color),
            "strong": load_icon(ICON_DIR/"wifi_strong.png", tint_color=icon_fg_color),
            "secure": load_icon(ICON_DIR/"wifi_secure.png", tint_color=icon_fg_color),
        }
        self.fullscreen_icon = load_icon(ICON_DIR / "fullscreen.png", tint_color=icon_fg_color, size=(16, 16))
        self.minimize_icon = load_icon(ICON_DIR / "minimize.png", tint_color=icon_fg_color, size=(16, 16))
        
        if self.wifi_label: self.wifi_label.config(image=self.icons.get(self.current_wifi_status, self.icons["down"]))
        if self.fullscreen_button: self.fullscreen_button.config(image=self.fullscreen_icon if not self.is_graph_fullscreen else self.minimize_icon)


        # 5. Update tk Widgets
        btn_bg_color = "#555555" if self.theme == "dark" else "#e0e0e0" # Example for tk.Button
        if self.filter_button: self.filter_button.config(bg=btn_bg_color, fg=fg_color) # tk.Button
        if self.export_btn: self.export_btn.config(bg=btn_bg_color, fg=fg_color)     # tk.Button
        if self.filter_entry: self.filter_entry.config(bg=self.summary_txt_bg, fg=fg_color, insertbackground=fg_color) # tk.Entry

        if hasattr(self, 'log_text') and self.log_text:
            self.log_text.config(bg=self.summary_txt_bg, fg=fg_color)

        # 6. Re-apply general theme from OptionsApp
        self.app.apply_theme_to_window(self.win)


    def _setup_tooltip(self):
        self.tooltip = None
        self.tooltip_line = None
        self.plot_data = {'dates': [], 'pnl': []}  # Store plot data for tooltip

    def _on_trade_select(self, event):
        """Handle trade selection in log_tree to mark/unmark trade on equity curve."""
        selection = self.log_tree.selection()

        # If nothing is selected, just hide any existing marker
        if not selection:
            if self.trade_marker is not None:
                self.trade_marker.set_visible(False)
                self.trade_marker = None
                self.canvas.draw_idle()
            self.selected_trade_iid = None
            return

        iid = selection[0]

        # If you clicked the same trade again, toggle it off
        if iid == self.selected_trade_iid:
            if self.trade_marker is not None:
                self.trade_marker.set_visible(False)
                self.trade_marker = None
                self.canvas.draw_idle()
            self.selected_trade_iid = None
            return

        # New trade selected
        self.selected_trade_iid = iid
        vals = self.log_tree.item(iid, 'values')
        close_date_str = vals[2]  # Close Date column

        try:
            close_date = pd.to_datetime(close_date_str).date()
        except Exception:
            return  # invalid date

        # find index in your plot_data
        date_list = [d.date() for d in self.plot_data['dates']]
        if close_date not in date_list:
            return
        idx = date_list.index(close_date)

        # Hide any old marker
        if self.trade_marker is not None:
            self.trade_marker.set_visible(False)

        # Plot a new red marker and keep a reference
        x = self.plot_data['dates'][idx]
        y = self.plot_data['pnl'][idx]
        # note: store the Line2D instance directly
        (self.trade_marker,) = self.ax.plot(
            x, y,
            marker='o',
            color='red',
            markersize=8,
            zorder=10,
        )
        self.canvas.draw_idle()


    def _on_plot_click(self, event):
        """Select & scroll the trade log if you click near a plotted equity‐curve point."""
        if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return

        # Convert dates & PnL to display coordinates
        date_nums = mdates.date2num(self.plot_data['dates'])
        pnl_vals  = self.plot_data['pnl']
        data = np.column_stack([date_nums, pnl_vals])
        trans = self.ax.transData
        disp_pts = trans.transform(data)      # Nx2 array of [x_disp, y_disp]
        click_pt = np.array([event.x, event.y])

        # Compute pixel distances to all points
        dists = np.hypot(disp_pts[:,0] - click_pt[0], disp_pts[:,1] - click_pt[1])
        idx = np.argmin(dists)

        # Tolerance in pixels – increase to make easier
        tol = 20
        if dists[idx] > tol:
            return

        # We clicked close enough to plot_data['dates'][idx]
        target_date = self.plot_data['dates'][idx].strftime('%Y-%m-%d')

        # Select & scroll in the tree
        for iid in self.log_tree.get_children():
            vals = self.log_tree.item(iid, 'values')
            if vals[2] == target_date:  # Close Date column
                self.log_tree.selection_set(iid)
                self.log_tree.see(iid)
                self._on_trade_select(None)
                break


        

    def _toggle_builder_visibility(self, *args):
        # Only manage Build Legs button visibility
        if self.strat_cbo.get() == "Custom Strategy":
            if not self.build_btn.winfo_ismapped():
                self.build_btn.pack(pady=5)
        else:
            self.build_btn.pack_forget()
            self.custom_legs = []
            self.custom_legs_label.configure(text="Custom Strategy: None")

    def _open_custom_builder(self):
        dlg = CustomLegBuilder(self.win, existing_legs=self.custom_legs.copy(), controller=self)
        # You MUST ensure OptionsApp applies its theme to 'dlg' after creation
        if hasattr(self.win.master, 'apply_theme_to_window'):
             self.win.master.apply_theme_to_window(dlg)
        self.win.wait_window(dlg)
        self.custom_legs = dlg.legs
        if dlg.legs is not None:
            if self.custom_legs:
                legs_display = ", ".join(
                    f"{leg['qty']}× {'Long' if leg['dir'] == 1 else 'Short'} {leg['type']} @ {leg['strike']}"
                    for leg in self.custom_legs
                )
                self.custom_legs_label.configure(text=f"Custom Strategy: {legs_display}")
                messagebox.showinfo("Custom strategy saved", f"{len(self.custom_legs)} leg(s) recorded.", parent=self.win)
            else:
                self.custom_legs_label.configure(text="Custom Strategy: None")
                messagebox.showinfo("Custom strategy saved", "No legs in strategy.", parent=self.win)


    def _open_optimize_dialog(self):
        dlg = OptimizeDialog(self.win, controller=self)
        # You MUST ensure OptionsApp applies its theme to 'dlg' after creation
        if hasattr(self.win.master, 'apply_theme_to_window'):
             self.win.master.apply_theme_to_window(dlg)

    def _start_optimization(self, param_grid: dict):
        """Kick off a batch run over our param grid with live progress."""
        base_cfg = self._validate_inputs()
        if base_cfg is None:
            return
        
        self._start_status_animation("Assembling Timelines & Pre-computing Volatility")

        if isinstance(base_cfg.get("filters"), dict):
            base_cfg["filters"] = FilterConfig(**base_cfg["filters"])

        self.win.update_idletasks()
        self.main_pane.sash_place(0, 0, self.HEADER_EXPANDED_HEIGHT)

        try:
            template = StrategyConfig(**base_cfg)
        except Exception as e:
            messagebox.showerror("Config Error", str(e), parent=self.win)
            return

        # Prepare UI for optimization
        self.run_btn.configure(state="disabled")
        self.optimize_btn.configure(state="disabled")
        self.build_btn.configure(state="disabled")
        self.opt_toolbar.pack(fill='x', pady=5)
        self.pause_opt_btn.configure(state='normal', text='⏸ Pause')
        self.end_early_btn.configure(state='normal')
        self.cancel_opt_btn.configure(state='normal')
        self.opt_combo_lbl.pack(fill='x', padx=4, pady=(2,0))
        self.opt_progress_lbl.pack(fill='x', padx=4)
        self.progress.pack(fill='x', padx=4, pady=(2,10))

        total = 1
        for vals in param_grid.values():
            total *= len(vals)
        self.progress.configure(maximum=total, value=0, mode='determinate')
        self.opt_start_time = time.monotonic() # Use monotonic for accurate duration
        self.opt_combo_lbl.config(text="Initializing...")

        # --- Variables for the "Steady-State" ETA Calibration ---
        self._eta_calibrated = False
        self._locked_in_eta = 0
        self._eta_start_time = 0          # Timestamp when the final countdown begins
        self._calibration_start_time = 0  # Timestamp when the measurement window opens
        self.CALIBRATION_START_TASK = 3   # Start measuring after 2 tasks
        self.CALIBRATION_END_TASK = 10     # Stop measuring after 10 tasks

        price_data = get_prices(template.underlying, template.start, template.end)
        vol_data = realized_vol(price_data).ffill().bfill().clip(lower=0.05)
        benchmark_data = None
        if template.use_benchmark:
            benchmark_data = get_prices(template.benchmark_ticker, template.start, template.end)

        # Create and store the BatchRunner with shared data
        self.runner = BatchRunner(
            base_cfg=template,
            sweep_params=param_grid,
            price_data=price_data,
            vol_data=vol_data,
            benchmark_data=benchmark_data,
            progress_callback=self._update_opt_progress,
            # FIX: This callback is disabled to prevent the premature trade log population.
            # The final results function is now solely responsible for all UI updates.
            trade_callback=None
        )

        # Run in background
        threading.Thread(target=self._run_optimization_thread, daemon=True).start()




    def _run_optimization_thread(self):
        """Executes the BatchRunner and schedules UI updates based on how it finished."""
        try:
            self.runner.run()
            # After the run is complete (normally or via cancellation):
            # 1. If 'End Early' was clicked, always show the partial results.
            # 2. If it finished normally (not cancelled), show the full results.
            # 3. If it was just cancelled, do nothing.
            if self._end_early or not self.runner._cancel_event.is_set():
                self.win.after(0, self._populate_optimization_results)
        except Exception as e:
            logging.exception("A critical error occurred during the optimization batch run:")
            self.win.after(0, lambda exc=e: messagebox.showerror(
                "Optimization Error", f"A critical error stopped the process:\n{exc}", parent=self.win))
        finally:
            # Always reset the flag and the UI after the thread is done.
            self._end_early = False
            self.win.after(0, self._finalize_backtest_ui)

    def _populate_optimization_results(self):
        """
        After grid-search, populates the Optimization Results table,
        applies the best settings to the UI, and shows the best run's trades.
        """
        if not hasattr(self, 'runner') or self.runner.results_df().empty:
            logging.warning("Optimization ended with no results to populate.")
            self._finalize_backtest_ui()
            return

        df = self.runner.results_df()
        if df.empty:
            messagebox.showinfo("No Results", "Optimization did not produce any valid results.", parent=self.win)
            self._finalize_backtest_ui()
            return
            
        # 1. Populate the "Optimization Results" summary table
        self.history_tree.delete(*self.history_tree.get_children())
        self.optimization_runs_data.clear()
        
        df_sorted = df.sort_values("total_return_pct", ascending=False).reset_index(drop=True)
        
        for index, row in df_sorted.iterrows():
            try:
                # Prepare values for display in the treeview
                display_values = (
                    f"{row.get('total_return_pct', 0):.2f}",
                    f"{row.get('cagr', 0):.2f}",
                    f"{row.get('sharpe', 0):.3f}",
                    f"{row.get('win_rate', 0):.2f}",
                    f"{row.get('total_trades', 0)}",
                    f"{int(row.get('dte_target', 0))}",
                    f"{row.get('allocation_pct', 0):.1f}",
                    f"{row.get('profit_target_pct', 0):.1f}",
                    f"{row.get('stop_loss_mult', 0):.1f}"
                )
                iid = self.history_tree.insert("", "end", values=display_values)
                # Store the full data for this run so we can re-run it later
                self.optimization_runs_data[iid] = row.to_dict()
            except Exception:
                continue # Skip any row that fails to format

        # 2. Get the best run from the top of our sorted dataframe
        best = df_sorted.iloc[0]

        # 3. Apply best settings to inputs (UI)
        try:
            self.dte_ent.delete(0, tk.END); self.dte_ent.insert(0, str(int(best["dte_target"])))
            self.alloc_ent.delete(0, tk.END); self.alloc_ent.insert(0, f"{best['allocation_pct']}")
            self.pt_ent.delete(0, tk.END); self.pt_ent.insert(0, f"{best['profit_target_pct']}")
            self.sl_ent.delete(0, tk.END); self.sl_ent.insert(0, f"{best['stop_loss_mult']}")
        except Exception as e:
            logging.warning(f"Could not apply best settings to UI inputs: {e}")

        # 4. Show the notification message
        msg = (
            "🎉 Optimization Complete! 🎉\n\n"
            "The best settings have been applied to the input fields.\n"
            "The 'Trade Log' shows the trades for this best run.\n\n"
            "Click any run in the 'Optimization Results' tab to see its trades."
        )
        messagebox.showinfo("Optimization Complete", msg, parent=self.win)

        # 5. Populate all other UI elements with the best run's data
        self._display_best_run_results(best)
        self._finalize_backtest_ui()


    def _display_best_run_results(self, best: pd.Series):
        """
        Handles populating all UI elements with the data from a single, specific run
        (e.g., the best run after an optimization).
        """
        # --- 1. Regenerate full results for the selected run ---
        # This ensures we have the definitive trade list and equity curve.
        from core.engine.backtestengine import BacktestEngine
        from app.config import StrategyConfig
        try:
            base_cfg = self._validate_inputs()
            best_config_dict = {
                **base_cfg,
                "dte_target": int(best["dte_target"]),
                "allocation_pct": best["allocation_pct"],
                "profit_target_pct": best["profit_target_pct"],
                "stop_loss_mult": best["stop_loss_mult"],
            }
            config = StrategyConfig(**best_config_dict)
            engine = BacktestEngine(config)
            engine.run(
                price_data=getattr(self.runner, "price_data", None),
                vol_data=getattr(self.runner, "vol_data", None),
                benchmark_data=getattr(self.runner, "benchmark_data", None),
                spy_prices=getattr(self.runner, "spy_prices", None)
            )
            result = engine.result()
            self._best_trades = result.trade_list() # This is used to populate the Trade Log
            self._best_equity = result.equity_curve()

        except Exception as e:
            logging.error(f"Failed to generate final results for the best run: {e}")
            messagebox.showerror("Result Error", f"Could not generate the final report:\n{e}", parent=self.win)
            self._best_equity, self._best_trades = None, []

        # --- 2. Populate the "Trade Log" tab ---
        # NOTE: We no longer touch self.history_tree here.
        self._populate_log_tree(self._best_trades)

        # --- 3. Plot Equity Curve and Benchmark ---
        try:
            self.ax.clear()
            benchmark_final_value = None
            if self._best_equity is not None and not self._best_equity.empty:
                eq = self._best_equity
                self.ax.plot(eq.index, eq.values, label="Strategy", linewidth=1.25)
                self.plot_data['dates'], self.plot_data['pnl'] = list(eq.index), list(eq.values)

                benchmark_data = getattr(self.runner, "benchmark_data", None)
                if benchmark_data is not None and self.benchmark_var.get():
                    bench_aligned = pd.Series(benchmark_data).reindex(eq.index, method='ffill').fillna(method='bfill')
                    if not bench_aligned.empty:
                        bench_norm = bench_aligned / float(bench_aligned.iloc[0]) * float(eq.iloc[0])
                        self.ax.plot(bench_norm.index, bench_norm.values, label="Benchmark", linestyle='--', linewidth=1.0)
                        benchmark_final_value = bench_norm.iloc[-1]
                self.ax.legend()
            else:
                self.ax.text(0.5, 0.5, "No equity data", ha='center', va='center', transform=self.ax.transAxes)

            self.ax.set_xlabel("Date"); self.ax.set_ylabel("Equity ($)")
            self.canvas.draw_idle()

        except Exception as e:
            logging.exception(f"Failed to draw equity plot: {e}")

        # --- 4. Populate Performance Metrics Table ---
        try:
            for key, label_widget in self.stat_labels.items():
                if key in best and pd.notna(best[key]):
                    label_widget.config(text=self._format_stat(key, best[key]))
                else:
                    label_widget.config(text="N/A")
            
            if benchmark_final_value is not None and self._best_equity is not None and not self._best_equity.empty:
                beat_bench = "Yes" if self._best_equity.iloc[-1] >= benchmark_final_value else "No"
                self.beat_spy_label.config(text=f"Beat {self.benchmark_cbo.get()}: {beat_bench}")
            else:
                self.beat_spy_label.config(text="")
        except Exception as e:
            logging.exception(f"Failed to populate performance metrics: {e}")


    def _handle_trade(self, trades):
        """
        trades will be either a dict (one trade) or a list of dicts.
        We normalize to a list and insert each immediately.
        """
        batch = trades if isinstance(trades, list) else [trades]
        for t in batch:
            pnl = t.get('pnl', 0.0)
            tag = 'profit' if pnl >= 0 else 'loss'
            i = self._next_trade_iid
            self._next_trade_iid += 1

            k_short = t.get('K_short')
            k_long  = t.get('K_long')

            vals = (
                i,
                t['open'].strftime('%Y-%m-%d'),
                t['close'].strftime('%Y-%m-%d'),
                f"{k_short:.2f}" if isinstance(k_short, (int, float)) else "",
                f"{k_long:.2f}"  if isinstance(k_long, (int, float))  else "",
                t.get('contracts', 0),
                f"{t.get('credit', 0):.2f}",
                f"{pnl:.2f}"
            )
            self.log_tree.insert("", "end", values=vals, tags=(tag,))
            # immediately scroll into view
            self.log_tree.see(self.log_tree.get_children()[-1])




    def _update_opt_progress(self, done: int, total: int, overrides: dict[str, Any]):
        # hop to GUI thread
        self.win.after(0, lambda d=done, t=total, o=overrides:
                    self._update_opt_gui(d, t, o))


    def _update_opt_gui(self, done: int, total: int, overrides: dict[str, Any]):
        # Stop the initial "loading" animation
        if hasattr(self, '_animation_job') and self._animation_job:
            self._stop_status_animation()
            
        # Update progress bar
        self.progress['maximum'] = total
        self.progress['value'] = done

        now = time.monotonic()
        percent_done = (done / total) * 100 if total > 0 else 0
        
        # --- New "Steady-State" ETA Logic ---
        if not self._eta_calibrated:
            # --- Phase 1 & 2: Pre-Calibration and Calibration Window ---
            self.opt_progress_lbl.config(text=f"{done}/{total} ({percent_done:.1f}%) — Calibrating ETA...")

            # Record the start time exactly when the 3rd task completes
            if done == self.CALIBRATION_START_TASK:
                self._calibration_start_time = now

            # When the 6th task completes, perform the one-time calculation
            if done == self.CALIBRATION_END_TASK:
                calibration_duration = now - self._calibration_start_time
                tasks_in_window = self.CALIBRATION_END_TASK - self.CALIBRATION_START_TASK

                if tasks_in_window > 0 and calibration_duration > 0:
                    avg_time_per_task = calibration_duration / tasks_in_window
                    remaining_tasks = total - done
                    self._locked_in_eta = avg_time_per_task * remaining_tasks
                    self._eta_calibrated = True
                    self._eta_start_time = now  # The moment the final countdown begins
        
        if self._eta_calibrated:
            # --- Phase 3: Linear Countdown ---
            elapsed_since_lock = now - self._eta_start_time
            current_eta = self._locked_in_eta - elapsed_since_lock
            current_eta = max(0, current_eta)
            
            eta_str = f" — ETA {self._format_eta(current_eta)}"
            self.opt_progress_lbl.config(text=f"{done}/{total} ({percent_done:.1f}%){eta_str}")

        # Update the line showing the current combination being tested
        if overrides:
            dte = int(overrides['dte_target'])
            alloc = overrides['allocation_pct']
            pt = overrides['profit_target_pct']
            sl = overrides['stop_loss_mult']
            self.opt_combo_lbl.config(
                text=(f"Testing: DTE={dte:<3d}  Alloc={alloc:4.1f}%  "
                      f"ProfitTgt={pt:4.1f}%  Stop×={sl:4.1f}")
            )

        # Force the UI to repaint immediately
        self.progress.update_idletasks()

    def _log_trade(self, trade):
        """
        Called from the worker thread (BacktestEngine.trade_callback).
        Buffers trades and schedules a GUI-thread flush via after_idle().
        """
        # Flatten: _handle_trade expects a dict, but BacktestEngine may
        # send a list of dicts when batch-mode is on.
        if isinstance(trade, list):
            self._pending_trades.extend(trade)
        else:
            self._pending_trades.append(trade)

        if not self._flush_scheduled:
            self._flush_scheduled = True
            self.win.after_idle(self._flush_trade_log)


    def _flush_trade_log(self):
        """Runs on the Tk main loop; safe to touch widgets."""
        self._flush_scheduled = False
        if not self._pending_trades:
            return

        # <<< FIX: Process all pending trades in a batch for much faster UI updates >>>
        # Instead of inserting one-by-one, prepare all data first.
        batch, self._pending_trades[:] = self._pending_trades[:], []

        for t in batch:
            pnl = t.get('pnl', 0.0)
            tag = 'profit' if pnl >= 0 else 'loss'
            i = self._next_trade_iid
            self._next_trade_iid += 1

            k_short = t.get('K_short')
            k_long  = t.get('K_long')

            vals = (
                i,
                t['open'].strftime('%Y-%m-%d'),
                t['close'].strftime('%Y-%m-%d'),
                f"{k_short:.2f}" if isinstance(k_short, (int, float)) else "",
                f"{k_long:.2f}"  if isinstance(k_long, (int, float))  else "",
                t.get('contracts', 0),
                f"{t.get('credit', 0):.2f}",
                f"{pnl:.2f}"
            )
            # Insert into the treeview. This is still done one-by-one, but without
            # calling the legacy _handle_trade wrapper, it's cleaner.
            # True batch insertion in Tkinter is complex, but this is a major improvement.
            self.log_tree.insert("", "end", values=vals, tags=(tag,))

        # After inserting all trades in the batch, scroll to the last one just once.
        children = self.log_tree.get_children()
        if children:
            self.log_tree.see(children[-1])


    def _see_last(self):
        children = self.log_tree.get_children()
        if children:
            # scroll to the very last item
            self.log_tree.see(children[-1])
        self._see_scheduled = False

    def _rebuild_trade_log_from_last_run(self):
        visible_trades = 0
        if not hasattr(self, "engine"):
            return  # no backtest yet

        trades = self.engine.result().trade_list()
        self.log_tree.delete(*self.log_tree.get_children())

        for i, t in enumerate(trades):
            if not self.filters.passes(t):  # Apply current filters
                continue
            visible_trades += 1
            pnl = t.get('pnl', 0.0)
            tag = 'profit' if pnl > 0 else 'loss' if pnl < 0 else ('evenrow' if i % 2 == 0 else 'oddrow')
            vals = (
                i + 1,
                t['open'].strftime('%Y-%m-%d'),
                t['close'].strftime('%Y-%m-%d'),
                f"{t.get('K_short', ''):.2f}" if t.get('K_short') is not None else "",
                f"{t.get('K_long', ''):.2f}" if t.get('K_long') is not None else "",
                t.get('contracts', 0),
                f"{t.get('credit', 0):.2f}",
                f"{pnl:.2f}"
            )
            self.log_tree.insert("", "end", values=vals, tags=(tag,))
        if visible_trades == 0:
            messagebox.showinfo("No Trades Match Filter", "Your filter settings excluded all trades.")



    def _update_backtest_progress(self, done: int, total: int):
        # Worker thread → hop to GUI thread
        self.win.after(0, lambda d=done, t=total: self._update_bt_gui(d, t))

    def _update_bt_gui(self, done: int, total: int):
         # Stop the initial "loading" animation when the progress bar starts moving.
        if hasattr(self, '_animation_job') and self._animation_job:
            self._stop_status_animation()

        self.progress['maximum'] = total
        self.progress['value']   = done
        self.progress.update_idletasks()   # immediate repaint




    def _cancel_optimization(self):
        """Cancels the optimization and resets the UI without displaying results."""
        if hasattr(self, 'runner'):
            self._end_early = False # Ensure we don't process results
            self.runner.cancel()
        
        self._finalize_backtest_ui()
        self.opt_progress_lbl.config(text="") # Clear status labels
        self.opt_combo_lbl.config(text="")
        messagebox.showinfo("Cancelled", "The optimization has been cancelled.", parent=self.win)

    def _toggle_pause_opt(self):
        """Pauses or resumes the running optimization."""
        if not hasattr(self, 'runner'):
            return

        # Check the state of the multiprocessing Event to determine if paused
        if self.runner._pause.is_set():
            # Is currently running -> Pause it
            self.runner.pause()
            self.pause_opt_btn.configure(text="▶ Resume")
            self.opt_progress_lbl.config(text="Paused — Click Resume to continue")
        else:
            # Is currently paused -> Resume it
            self.runner.resume()
            self.pause_opt_btn.configure(text="⏸ Pause")
            # The progress updater will overwrite the status label, so no need to clear it here.

    def _end_early_optimization(self):
        """Signals the runner to stop and process the best results found so far."""
        if hasattr(self, 'runner'):
            self._end_early = True
            self.runner.cancel()
        
        self.opt_progress_lbl.config(text="Finishing up current tasks...")
        # Disable buttons to prevent further clicks while shutting down
        self.pause_opt_btn.config(state='disabled')
        self.end_early_btn.config(state='disabled')
        self.cancel_opt_btn.config(state='disabled')



    def _open_filter_dialog(self):
        dlg = FilterDialog(self.win, controller=self)
        self.win.wait_window(dlg)
        self.filters = dlg.filter_config
        self._rebuild_trade_log_from_last_run()

    def _show_optimization_context_menu(self, event):
        """Shows a context menu on right-click in the optimization results table."""
        widget = event.widget
        iid = widget.identify_row(event.y)
        if not iid:
            return
        
        # Programmatically select the row that was right-clicked
        widget.selection_set(iid)
        
        # Display the context menu at the cursor's location
        self.opt_results_menu.tk_popup(event.x_root, event.y_root)

    def _load_selected_run_trades(self):
        """
        When a user selects a run in the Optimization Results table,
        this runs a backtest for that specific configuration on-demand.
        """
        selection = self.history_tree.selection()
        if not selection:
            return
        
        iid = selection[0]
        params_to_run = self.optimization_runs_data.get(iid)
        if not params_to_run:
            return
        
        # Give immediate feedback to the user
        self.log_tree.delete(*self.log_tree.get_children())
        self.log_tree.insert("", "end", values=("", "", "Loading trades for selected run...", ""))
        
        # Run the single backtest in a background thread to keep the UI responsive
        threading.Thread(
            target=self._run_single_backtest_thread,
            args=(params_to_run,),
            daemon=True
        ).start()

    def _run_single_backtest_thread(self, params: dict):
        """
        Worker thread function to run a single backtest configuration.
        """
        try:
            base_cfg = self._validate_inputs()
            
            # Define the specific optimization parameters we expect to override from the selected run.
            # This prevents passing unexpected metric keys (like 'sharpe', 'start_value') to the config.
            override_keys = ['dte_target', 'allocation_pct', 'profit_target_pct', 'stop_loss_mult']
            overrides = {key: params[key] for key in override_keys if key in params}
            
            # Ensure DTE is an integer
            if 'dte_target' in overrides:
                overrides['dte_target'] = int(overrides['dte_target'])
            
            # Combine the base config from the UI with the clean overrides
            full_config_dict = {**base_cfg, **overrides}
            
            config = StrategyConfig(**full_config_dict)
            engine = BacktestEngine(config)
            
            # Use the price/vol data already loaded by the BatchRunner
            engine.run(
                price_data=getattr(self.runner, "price_data", None),
                vol_data=getattr(self.runner, "vol_data", None),
                benchmark_data=getattr(self.runner, "benchmark_data", None),
                spy_prices=getattr(self.runner, "spy_prices", None)
            )
            
            trades = engine.result().trade_list()
            # Schedule the UI update on the main thread
            self.win.after(0, lambda: self._populate_log_tree(trades))
        except Exception as e:
            logging.exception("Failed to run on-demand backtest for drill-down.")
            # FIX: Capture the exception 'e' in the lambda to prevent NameError in newer Python versions
            self.win.after(0, lambda e=e: messagebox.showerror(
                "Drill-Down Error", f"Could not load trades for the selected run:\n{e}", parent=self.win))

    def _populate_log_tree(self, trades: list):
        """
        Clears and populates the main trade log with a given list of trades.
        """
        self.log_tree.delete(*self.log_tree.get_children())
        if not trades:
            self.log_tree.insert("", "end", values=("", "", "No trades generated for this run.", ""))
            return

        for i, t in enumerate(trades):
            try:
                pnl = t.get('pnl', 0.0)
                tag = 'profit' if pnl > 0 else 'loss' if pnl < 0 else ('evenrow' if i % 2 == 0 else 'oddrow')
                k_short = t.get('K_short')
                k_long  = t.get('K_long')
                vals = (
                    i + 1,
                    t['open'].strftime('%Y-%m-%d'),
                    t['close'].strftime('%Y-%m-%d'),
                    f"{k_short:.2f}" if isinstance(k_short, (int, float)) else "",
                    f"{k_long:.2f}" if isinstance(k_long, (int, float)) else "",
                    t.get('contracts', 0),
                    f"{t.get('credit', 0):.2f}",
                    f"{pnl:.2f}"
                )
                self.log_tree.insert("", "end", values=vals, tags=(tag,))
            except Exception:
                continue


    def _setup_default_values(self):
        """Populate input fields with default values."""
        self.symbol_ent.insert(0, "SPY")
        two_years_ago = _dt.date.today() - _dt.timedelta(days=2*365)
        one_week_ago  = _dt.date.today() - _dt.timedelta(days=7)
        self.start_ent.set_date(two_years_ago)
        self.end_ent.set_date(one_week_ago)
        self.strat_cbo.current(0)
        self.cap_ent.insert(0, "100000")
        self.alloc_ent.insert(0, "5")
        self.pt_ent.insert(0, "50")
        self.sl_ent.insert(0, "2")
        self.dte_ent.insert(0, "30")
        self.comm_ent.insert(0, "0.65")
        self._toggle_builder_visibility()

    def _validate_inputs(self) -> dict | None:
        """Validate user inputs and return config dict or None if invalid."""
        cfg = {}
        try:
            cfg["underlying"] = self.symbol_ent.get().strip().upper()
            if not cfg["underlying"]:
                raise ValueError("Underlying symbol cannot be empty.")

            cfg["start"] = _dt.datetime.strptime(self.start_ent.get(), "%Y-%m-%d").strftime("%Y-%m-%d")
            cfg["end"] = _dt.datetime.strptime(self.end_ent.get(), "%Y-%m-%d").strftime("%Y-%m-%d")
            if cfg["start"] >= cfg["end"]:
                raise ValueError("Start date must be before end date.")

            strat_map = {"Short Put": "short_put", "Put Credit Spread": "put_spread", "Custom Strategy": "custom_manual"}
            cfg["strategy_type"] = strat_map[self.strat_cbo.get()]

            cfg["capital"] = float(self.cap_ent.get())
            if cfg["capital"] <= 0:
                raise ValueError("Capital must be positive.")

            cfg["allocation_pct"] = float(self.alloc_ent.get())
            if not (0 < cfg["allocation_pct"] <= 100):
                raise ValueError("Allocation % must be between 0 and 100.")

            cfg["profit_target_pct"] = float(self.pt_ent.get())
            if cfg["profit_target_pct"] <= 0:
                raise ValueError("Profit Target % must be positive.")

            cfg["stop_loss_mult"] = float(self.sl_ent.get())
            if cfg["stop_loss_mult"] <= 0:
                raise ValueError("Stop Loss Multiplier must be positive.")

            cfg["dte_target"] = int(self.dte_ent.get())
            if cfg["dte_target"] <= 0:
                raise ValueError("DTE Target must be positive.")

            cfg["commission_per_contract"] = float(self.comm_ent.get())
            if cfg["commission_per_contract"] < 0:
                raise ValueError("Commission cannot be negative.")

            cfg["strategy_params"] = {
                "short_put_pct_otm": 0.07,
                "spread_width_pct": 0.05,
            }

            if cfg["strategy_type"] == "custom_manual":
                if not self.custom_legs:
                    raise ValueError("Click 'Build Legs' and add at least one leg for a Custom Strategy.")
                cfg["custom_legs"] = self.custom_legs

            cfg["benchmark_ticker"] = self.benchmark_cbo.get()
            cfg["use_benchmark"] = self.benchmark_var.get()
            cfg["filters"] = getattr(self, "filters", FilterConfig())

            return cfg
        
        

        except ValueError as e:
            messagebox.showerror("Input Error", f"Invalid input: {e}", parent=self.win)
            return None
        except Exception as e:
            messagebox.showerror("Input Error", f"Please check input formats.\nDetails: {e}", parent=self.win)
            return None      


    


    def _start_backtest(self):
        """Validate inputs, build StrategyConfig, and start the backtest engine in a thread."""
        
        ensure_spy_backup() # Ensure SPY backup is available
        # 1) pull & validate everything from the form
        gui_cfg = self._validate_inputs()
        if gui_cfg is None:
            return
        
        self._start_status_animation("Initializing Engine & Loading Data")

        if isinstance(gui_cfg.get("filters"), dict):
            gui_cfg["filters"] = FilterConfig(**gui_cfg["filters"])

        self.log_tree.delete(*self.log_tree.get_children())
        self._next_trade_iid = 1
        self._pending_trades.clear()
        self._flush_scheduled = False


        # 2) load (cached) earnings calendar for this ticker
        #cfg_filters = gui_cfg["filters"]
        #cfg_filters.earnings_calendar = {
         #   gui_cfg["underlying"]: fetch_earnings_calendar(gui_cfg["underlying"])
        #}
        #self.filters = cfg_filters

        # 3) build and run
        try:
            cfg = StrategyConfig(**gui_cfg)
        except Exception as e:
            messagebox.showerror("Config Error", str(e), parent=self.win)
            return
        
        # Clear UI
        for iid in self.log_tree.get_children():
            self.log_tree.delete(iid)
        
        logging.info("Running backtest…")
        self.canvas.draw()
        self.run_btn.configure(state="disabled")

        

        # ─── determinate progress bar setup ────────────────────────────────────
        # 1) ask engine how many steps it plans (we’ll assume it exposes estimate_steps())
        # Launch estimate in background to avoid UI freeze
        def set_steps():
            try:
                total = BacktestEngine.estimate_steps(cfg)
                self.win.after(0, lambda: self.progress.configure(maximum=total))
            except:
                pass
        threading.Thread(target=set_steps, daemon=True).start()
        # 2) make sure it’s visible
        self.progress.pack(fill="x", pady=(15,2))
        # ────────────────────────────────────────────────────────────────────────

        # create engine with our new callback
        self.engine = BacktestEngine(
            cfg,
            progress_callback=self._update_backtest_progress,
            trade_callback   =self._log_trade        # ← safe wrapper
        )


        # run it
        threading.Thread(target=self._run_backtest_thread, daemon=True).start()


    def _run_backtest_thread(self):
            """Run BacktestEngine and schedule UI update when done."""
            try:
                self.engine.run(chunk_size=1)
                logging.info("Backtest complete — populating results…")
                self.win.after(0, self._populate_results)
            except Exception as e:
                logging.exception("Error during backtest execution:")
                # capture 'e' into the lambda so it's in scope
                self.win.after(0, lambda exc=e: messagebox.showerror(
                    "Backtest Error", f"An error occurred:\n{exc}", parent=self.win))
            finally:
                self.win.after(0, self._finalize_backtest_ui)


    def _calculate_equity_stats(self, equity_series: pd.Series) -> dict:
        """
        Calculates total return and max drawdown directly from the equity curve.
        """
        stats = {
            'total_return': None,
            'total_return_pct': None,
            'max_drawdown': None
        }
        if equity_series is None or len(equity_series) < 2:
            return stats

        # Total Return Calculation
        start_equity = equity_series.iloc[0]
        end_equity = equity_series.iloc[-1]
        stats['total_return'] = end_equity - start_equity
        if start_equity != 0:
            stats['total_return_pct'] = (end_equity / start_equity - 1) * 100

        # Max Drawdown Calculation
        cumulative_max = equity_series.cummax()
        drawdown = equity_series - cumulative_max
        stats['max_drawdown'] = drawdown.min()

        return stats

    def _finalize_backtest_ui(self):
        """Stop progress bar and re-enable Run/Optimize buttons."""
        # stop any running animation
        try:
            self.progress.stop()
        except tk.TclError:
            pass

        self.run_btn.configure(state="normal")
        self.optimize_btn.configure(state="normal")
        self.build_btn.configure(state="normal")

        # hide the entire optimize toolbar & status
        self.opt_toolbar.pack_forget()
        self.opt_combo_lbl.pack_forget()
        self.opt_progress_lbl.pack_forget()
        self.progress.pack_forget()

        # disable the secondary buttons so they'll start 'grayed out' next time
        self.pause_opt_btn.configure(state="disabled", text="⏸ Pause")
        self.end_early_btn.configure(state="disabled")
        self.cancel_opt_btn.configure(state="disabled")

        # <<< FIX: Return the header to its normal height >>>
        self.main_pane.sash_place(0, 0, self.HEADER_NORMAL_HEIGHT)


    def _format_stat(self, key, value):
        """Format statistic value for display."""
        if isinstance(value, (int, float)):
            if 'pct' in key or 'rate' in key or key in ['cagr', 'sharpe', 'sortino']:
                return f"{value:.2f}%" if 'pct' in key or 'rate' in key or key == 'cagr' else f"{value:.3f}"
            elif key in ['ulcer_index', 'trade_pnl_skewness', 'daily_return_skewness']:
                # Format Ulcer Index and Skewness to 4 decimal places for precision
                return f"{value:.4f}"
            elif key in ['gross_profit', 'gross_loss', 'total_return', 'start_value', 'end_value', 'avg_win', 'avg_loss', 'max_drawdown']:
                prefix = "-$" if key == 'max_drawdown' and value < 0 else "$"
                return f"{prefix}{abs(value):,.2f}"
            elif key == 'profit_factor':
                return f"{value:.2f}" if pd.notna(value) and np.isfinite(value) else "inf"
            elif key == 'expectancy':
                return f"${value:.2f}"
            else:
                return f"{value:,}"
        return str(value)
    
    def _format_eta(self, seconds: float) -> str:
        if seconds < 60:
            return f"~ {int(seconds)} seconds"
        minutes, sec = divmod(seconds, 60)
        if minutes < 60:
            return f"~ {int(minutes)} min {int(sec)} sec"
        hours, minutes = divmod(minutes, 60)
        return f"~ {int(hours)} hr {int(minutes)} min"
    
    def _add_numeric_validation(self, widget, cast_type, min_val=None, max_val=None):
        """Attach realtime validation to highlight widget red if cast_type(value) fails or out of bounds."""
        def on_key(event):
            val = widget.get().strip()
            try:
                num = cast_type(val)
                if (min_val is not None and num < min_val) or (max_val is not None and num > max_val):
                    raise ValueError
                # Use the theme's foreground color for valid text
                widget.configure(foreground=self.summary_txt_fg)
            except:
                widget.configure(foreground='red')
        widget.bind("<KeyRelease>", on_key)

    def _start_status_animation(self, text_base):
        """Starts a recurring animation for a status label (e.g., 'Loading...')."""
        if hasattr(self, '_animation_job') and self._animation_job:
            self.win.after_cancel(self._animation_job)
        
        # Ensure header is expanded to show the status area
        self.main_pane.sash_place(0, 0, self.HEADER_EXPANDED_HEIGHT)
        self.status_label.pack(fill='x', padx=4, pady=(10, 0))
        
        self._animation_text_base = text_base
        self._animation_dots = 0

        def _update():
            dots = "." * (self._animation_dots % 4)
            self.status_label.config(text=f"{self._animation_text_base}{dots}")
            self._animation_dots += 1
            self._animation_job = self.win.after(400, _update)
        _update()

    def _stop_status_animation(self):
        """Stops any running status animation and hides the label."""
        if hasattr(self, '_animation_job') and self._animation_job:
            self.win.after_cancel(self._animation_job)
            self._animation_job = None
        self.status_label.pack_forget()


    def _populate_results(self):
        """Pulls results, populates the UI, and plots the equity curve with all interactive features."""
        import matplotlib.pyplot as plt
        import pandas as pd
        import io
        import requests

        # --- 1. Clear all previous results from the UI ---
        for label_widget in self.stat_labels.values():
            label_widget.config(text="N/A")
        if hasattr(self, 'beat_spy_label'):
            self.beat_spy_label.config(text="")
        self.ax.clear()
        
        # Reset data for tooltips and plot markers
        self.plot_data = {'dates': [], 'pnl': [], 'trades': []}
        if self.trade_marker:
            self.trade_marker.set_visible(False)
            self.trade_marker = None

        # --- 2. Get new results from the backtest engine ---
        result = self.engine.result()
        stats = result.summary()
        equity = result.equity_curve()
        trades = result.trade_list()

        # --- 3. Calculate Total Return and Max Drawdown directly from equity curve ---
        if stats:
            for key, label_widget in self.stat_labels.items():
                if key in stats:
                    value = stats.get(key)
                    formatted_value = self._format_stat(key, value)
                    label_widget.config(text=formatted_value)
        
        # --- 4. Trade Log is now populated live, so this block is no longer needed. ---
        # The log is cleared automatically when the next backtest starts.

        # --- 5. & 6. Plot Equity Curve and Benchmark using OLD RELIABLE LOGIC ---
        benchmark_series = None # Initialize benchmark series

        # --- Plot strategy equity first ---
        if not equity.empty:
            dates = equity.index
            values = equity.to_numpy()
            
            # Preserve data for interactive features
            self.plot_data['dates'] = dates.tolist()
            self.plot_data['pnl'] = values.tolist()
            self.plot_data['trades'] = trades

            # Plot strategy equity curve
            self.ax.plot(dates, values, lw=1.5, color="#3498db", label="Strategy")

            # --- Fetch and process benchmark data from Stooq (from old code) ---
            if self.benchmark_var.get():
                ticker = self.benchmark_cbo.get().lower()
                s_str = equity.index[0].strftime("%Y%m%d")
                e_str = equity.index[-1].strftime("%Y%m%d")
                url = f"https://stooq.com/q/d/l/?s={ticker}.us&d1={s_str}&d2={e_str}&i=d"
                try:
                    resp = requests.get(url, timeout=10)
                    resp.raise_for_status()
                    df2 = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"], index_col="Date")
                    series = df2["Adj Close"] if "Adj Close" in df2.columns else df2["Close"]
                    series = series.reindex(equity.index).ffill().bfill()
                    
                    # Normalize to strategy start value
                    strat_start = float(equity.iloc[0])
                    benchmark_series = series / series.iloc[0] * strat_start

                    # --- Update the "Beat Benchmark" label ---
                    last_strat = float(equity.iloc[-1])
                    last_bench = float(benchmark_series.iloc[-1])
                    beat = "Yes" if last_strat >= last_bench else "No"
                    self.beat_spy_label.config(text=f"Beat {ticker.upper()}: {beat}")
                    
                except Exception as e:
                    logging.error(f"Failed to fetch or process benchmark data: {e}")
                    self.beat_spy_label.config(text=f"Beat {ticker.upper()}: N/A")

            # --- Plot the benchmark if it was successfully created ---
            if benchmark_series is not None and not benchmark_series.empty:
                self.ax.plot(
                    benchmark_series.index,
                    benchmark_series.to_numpy(),
                    lw=1.2,
                    linestyle="--",
                    color="#ffaa00",
                    label=self.benchmark_cbo.get()
                )
            
            # --- Display the legend for all plotted items ---
            self.ax.legend()
        
         # --- Finalize Plot ---
        self.ax.set_title("Equity Curve", color=self.summary_txt_fg)
        self.ax.set_xlabel("Date")
        self.ax.set_ylabel("Equity ($)")
        
        # Format Y-axis with dollar signs and commas
        fmt = plt.FuncFormatter(lambda x, p: f'${x:,.0f}')
        self.ax.yaxis.set_major_formatter(fmt)
        
        self.fig.tight_layout()
        self.canvas.draw()

    def _on_plot_motion(self, event):
        """Handle mouse motion over plot for tooltip."""
        canvas = event.canvas # Get the canvas that triggered the event
        ax = self.ax

        # --- Ensure 'mdates' is imported: Add 'import matplotlib.dates as mdates' at the top of your file ---
        import matplotlib.dates as mdates
        import numpy as np
        import pandas as pd


        if event.inaxes != ax or event.xdata is None or event.ydata is None:
            if hasattr(self, 'tooltip') and self.tooltip and self.tooltip.get_visible():
                self.tooltip.set_visible(False)
                if hasattr(self, 'tooltip_line') and self.tooltip_line:
                    self.tooltip_line.set_visible(False)
                canvas.draw_idle()
            return

        x, y = event.xdata, event.ydata
        dates, pnl = self.plot_data['dates'], self.plot_data['pnl']
        if not dates: return

        date_nums = mdates.date2num(dates) # Convert dates to numbers
        idx = np.argmin(np.abs(date_nums - x)) # Find nearest index
        nd, npnl = dates[idx], pnl[idx] # Get the actual date and pnl

        date_str = pd.Timestamp(nd).strftime('%Y-%m-%d')
        pnl_str  = f"${npnl:,.2f}" if npnl >= 0 else f"-${-npnl:,.2f}"
        txt = f"Results on {date_str}\nEquity: {pnl_str}"

        fig_w, fig_h = canvas.get_width_height()
        # Use mdates.date2num(nd) for transformation, but nd (datetime) for plotting
        disp_x, disp_y = ax.transData.transform((mdates.date2num(nd), npnl))

        margin = 200
        offset, ha = (10, 10), 'left'
        # Check if plot is near right edge
        if disp_x > fig_w - margin:
            offset, ha = (-10, 10), 'right'

        if not hasattr(self, 'tooltip') or not self.tooltip:
            self.tooltip = ax.annotate(
                txt, xy=(nd, npnl), xytext=offset, textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.5", fc="green", alpha=0.8),
                arrowprops=dict(arrowstyle="->"), ha=ha, va='bottom', zorder=20
            )
            self.tooltip_line, = ax.plot([nd, nd], [ax.get_ylim()[0], npnl], 'k--', lw=1, visible=False, zorder=20)
        else:
            self.tooltip.set_text(txt)
            self.tooltip.xy = (nd, npnl)
            self.tooltip.set_ha(ha)
            self.tooltip.set_position(offset)
            self.tooltip_line.set_xdata([nd, nd])
            self.tooltip_line.set_ydata([ax.get_ylim()[0], npnl])

        self.tooltip.set_visible(True)
        self.tooltip_line.set_visible(True)
        canvas.draw_idle()



    def _sort_treeview(self, tv, col, reverse):
        """Sort treeview by column while preserving profit/loss coloring."""
        try:
            data = [(float(tv.set(i, col)), i) for i in tv.get_children()]
        except ValueError:
            data = [(tv.set(i, col),    i) for i in tv.get_children()]

        data.sort(reverse=reverse)
        for idx, (_, item) in enumerate(data):
            tv.move(item, '', idx)
            pnl_str = tv.set(item, "PnL ($)")
            try:
                pnl = float(pnl_str)
            except:
                pnl = 0.0
            tag = 'profit' if pnl > 0 else 'loss' if pnl < 0 else ('oddrow' if idx%2 else 'evenrow')
            tv.item(item, tags=(tag,))

        # re-bind header click for toggling
        tv.heading(col, command=lambda c=col: self._sort_treeview(tv, c, not reverse))

    def _filter_trades(self):
        keyword = self.filter_var.get().lower().strip()
        # Clear the current trade log
        self.log_tree.delete(*self.log_tree.get_children())
        
        # Get all trades from the engine
        if not hasattr(self, 'engine') or not self.engine.result():
            return
        
        trades = self.engine.result().trade_list()
        
        # Populate trades based on filter
        for i, t in enumerate(trades):
            # Format trade values
            pnl = t.get('pnl', 0.0)
            tag = 'profit' if pnl > 0 else 'loss' if pnl < 0 else ('evenrow' if i % 2 == 0 else 'oddrow')
            vals = (
                i + 1,
                t['open'].strftime('%Y-%m-%d'),
                t['close'].strftime('%Y-%m-%d'),
                f"{t.get('K_short', ''):.2f}" if t.get('K_short') is not None else "",
                f"{t.get('K_long', ''):.2f}" if t.get('K_long') is not None else "",
                t.get('contracts', 0),
                f"{t.get('credit', 0):.2f}",
                f"{pnl:.2f}"
            )
            combined_text = " ".join(str(v).lower() for v in vals)
            
            # Insert trade if filter is empty or trade matches keyword
            if not keyword or keyword in combined_text:
                self.log_tree.insert("", "end", values=vals, tags=(tag,))

    
    def _copy_performance_metrics(self):
        # <<< FIX: Rebuild the summary text from the labels for copying >>>
        lines = []
        # Re-create the display order to build the text block
        display_order = [
            ('start_value', 'Start Equity'), ('end_value', 'End Equity'),
            ('total_return', 'Total Return ($)'), ('total_return_pct', 'Total Return (%)'),
            ('cagr', 'CAGR (%)'),
            ('unlimited_risk', 'Unlimited Risk'), ('sharpe', 'Sharpe Ratio'),
            ('sortino', 'Sortino Ratio'), ('max_drawdown', 'Max Drawdown ($)'),
            ('ulcer_index', 'Ulcer Index'),
            ('total_trades', 'Total Trades'), ('win_rate', 'Win Rate (%)'),
            ('profit_factor', 'Profit Factor'), ('expectancy', 'Expectancy ($)'),
        ]
        max_label_len = max(len(lbl) for _, lbl in display_order) + 1

        for key, text in display_order:
            if key in self.stat_labels:
                value = self.stat_labels[key].cget("text")
                lines.append(f"{text:<{max_label_len}}: {value}")
        
        # Add benchmark separately
        if self.beat_spy_label.cget("text"):
            lines.append(self.beat_spy_label.cget("text"))

        summary_text = "\n".join(lines)
        if not summary_text:
            messagebox.showwarning("No Metrics", "No performance metrics to copy.", parent=self.win)
            return

        self.win.clipboard_clear()
        self.win.clipboard_append(summary_text)


        messagebox.showinfo("Copied", "Performance metrics copied to clipboard.", parent=self.win)


    def _show_trade_right_click(self, event):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Export Trade Log", command=self._export_trades_to_csv)
        menu.post(event.x_root, event.y_root)

    def _export_trades_to_csv(self):
        import pandas as pd
        trades = [self.log_tree.item(child, "values") for child in self.log_tree.get_children()]
        if not trades:
            return
        cols = self.log_tree["columns"]
        df = pd.DataFrame(trades, columns=cols)
        file_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                                filetypes=[("CSV files", "*.csv")],
                                                title="Save Trade Log As")
        if file_path:
            df.to_csv(file_path, index=False)



    
    
    def _toggle_fullscreen_graph(self):
        embedded = self.canvas.get_tk_widget()

        # → ENTER fullscreen
        if not hasattr(self, '_fs_window') or not self._fs_window or not self._fs_window.winfo_exists():
            # 1) Remember original parent and FIGURE properties
            self._orig_parent = embedded.master
            self._orig_size = self.fig.get_size_inches()
            self._orig_dpi = self.fig.get_dpi()

            # 2) Hide the original embedded canvas
            embedded.pack_forget()

            # 3) Create the fullscreen Toplevel window
            self._fs_window = tk.Toplevel(self.win)
            self._fs_window.attributes('-fullscreen', True)
            self._fs_window.protocol("WM_DELETE_WINDOW", self._toggle_fullscreen_graph)

            # 4) Create a NEW canvas for the fullscreen window
            self._fs_canvas = FigureCanvasTkAgg(self.fig, master=self._fs_window)
            fs_widget = self._fs_canvas.get_tk_widget()
            fs_widget.pack(fill=tk.BOTH, expand=True)

            # 5) Bind to <Configure> for dynamic resize
            self._fs_window.bind("<Configure>", self._resize_fullscreen_fig)

            # 6) Schedule initial resize after window mapping
            self._fs_window.after(100, self._resize_fullscreen_fig, None)

            # 7) Connect the tooltip handler
            self._fs_tooltip_cid = self._fs_canvas.mpl_connect('motion_notify_event', self._on_plot_motion)

            # 8) Create close button
            try:
                self.minimize_icon = load_icon(
                    ICON_DIR / "minimize.png",
                    tint_color=self.summary_txt_fg,
                    size=(16, 16)
                )
                self._fs_close_btn = ttk.Button(
                    self._fs_window,
                    image=self.minimize_icon,
                    command=self._toggle_fullscreen_graph,
                )
                self._fs_close_btn.image_ref = self.minimize_icon
                self._fs_close_btn.place(relx=1.0, rely=0.0, anchor='ne', x=-20, y=20)
            except Exception as e:
                logging.error(f"Could not load minimize icon: {e}")
                # Fallback text button
                self._fs_close_btn = ttk.Button(
                    self._fs_window,
                    text="Exit FS",
                    command=self._toggle_fullscreen_graph,
                )
                self._fs_close_btn.place(relx=1.0, rely=0.0, anchor='ne', x=-10, y=10)

            # 9) Update main button icon
            self.fullscreen_button.configure(image=self.minimize_icon)
            self.fullscreen_button.image_ref = self.minimize_icon

            self.is_graph_fullscreen = True

        # → EXIT fullscreen
        else:
            # 1) Disconnect tooltip and unbind <Configure>
            if hasattr(self, '_fs_canvas') and self._fs_canvas:
                try:
                    self._fs_canvas.mpl_disconnect(self._fs_tooltip_cid)
                except:
                    pass
            if self._fs_window:
                try:
                    self._fs_window.unbind("<Configure>")
                except:
                    pass

            # 2) Destroy the fullscreen widgets and window
            if hasattr(self, '_fs_canvas'):
                self._fs_canvas.get_tk_widget().destroy()
            if hasattr(self, '_fs_close_btn'):
                self._fs_close_btn.destroy()
            if hasattr(self, '_fs_window'):
                self._fs_window.destroy()

            # 3) Clear references
            self._fs_window = None
            self._fs_canvas = None
            self._fs_close_btn = None
            self._fs_tooltip_cid = None

            # 4) Restore original FIGURE properties
            if hasattr(self, '_orig_size'):
                self.fig.set_size_inches(self._orig_size)
            if hasattr(self, '_orig_dpi'):
                self.fig.set_dpi(self._orig_dpi)

            # 5) Repack the *original* embedded canvas
            embedded.pack(in_=self._orig_parent, fill=tk.BOTH, expand=True)

            # 6) Update the main button icon
            self.fullscreen_button.configure(image=self.fullscreen_icon)
            self.fullscreen_button.image_ref = self.fullscreen_icon

            # 7) Re-connect the handler to the original canvas
            if hasattr(self, '_on_plot_motion'):
                if hasattr(self, 'tooltip_cid') and self.tooltip_cid:
                    try:
                        self.canvas.mpl_disconnect(self.tooltip_cid)
                    except:
                        pass
                self.tooltip_cid = self.canvas.mpl_connect(
                    'motion_notify_event', self._on_plot_motion)

            # 8) Adjust layout & redraw for original view
            self.fig.tight_layout(pad=0.5)
            self.canvas.draw_idle()
            self.is_graph_fullscreen = False

    def _resize_fullscreen_fig(self, event):
        if not hasattr(self, '_fs_canvas') or not self._fs_canvas:
            return
        widget = self._fs_canvas.get_tk_widget()
        self._fs_window.update_idletasks()  # Ensure sizes are current
        w = widget.winfo_width()
        h = widget.winfo_height()
        if w <= 1 or h <= 1:
            return
        # Get actual DPI from widget
        dpi = widget.winfo_fpixels('1i')
        self.fig.set_dpi(dpi)
        # Set figure size exactly to widget size in inches
        self.fig.set_size_inches(w / dpi, h / dpi)
        # Adjust subplot margins to minimize cutoff
        self.fig.subplots_adjust(left=0.05, right=0.95, bottom=0.1, top=0.95)
        # Apply tight layout with small padding
        self.fig.tight_layout(pad=0.1)
        self._fs_canvas.draw_idle()
   
# Example Usage
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Main Application")
    root.geometry("300x100")

    def open_tester():
        try:
            bg = root.cget('bg')
            theme = "dark" if sum(root.winfo_rgb(bg)) / 3 < 32768 else "light"
        except:
            theme = "light"
        StrategyTesterWindow(root)

    ttk.Button(root, text="Open Strategy Tester", command=open_tester).pack(pady=20)
    root.mainloop()


class CustomLegBuilder(tk.Toplevel):
    """Modal window for adding custom strategy legs with a modern UI."""
    def __init__(self, master, existing_legs=None, controller=None):
        super().__init__(master)
        self.title("Build Custom Strategy")
        self.geometry("600x450")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.legs = existing_legs or []
        self.controller = controller  # Reference to StrategyTesterWindow instance
        self._make_widgets()

    def _make_widgets(self):
        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        # Input frame
        input_frm = ttk.Frame(frm)
        input_frm.pack(fill="x", pady=(0, 10))

        ttk.Label(input_frm, text="Strike").grid(row=0, column=0, padx=5, pady=5)
        self.strike_e = ttk.Entry(input_frm, width=10)
        self.strike_e.grid(row=1, column=0, padx=5, pady=5)

        ttk.Label(input_frm, text="Type").grid(row=0, column=1, padx=5, pady=5)
        self.type_c = ttk.Combobox(input_frm, values=["Call", "Put"], width=8, state="readonly")
        self.type_c.grid(row=1, column=1, padx=5, pady=5)
        self.type_c.current(0)

        ttk.Label(input_frm, text="Long/Short").grid(row=0, column=2, padx=5, pady=5)
        self.dir_c = ttk.Combobox(input_frm, values=["Long (+1)", "Short (-1)"], width=12, state="readonly")
        self.dir_c.grid(row=1, column=2, padx=5, pady=5)
        self.dir_c.current(1)

        ttk.Label(input_frm, text="Quantity").grid(row=0, column=3, padx=5, pady=5)
        self.qty_e = ttk.Entry(input_frm, width=8, style='CustomLeg.TEntry')
        self.qty_e.grid(row=1, column=3, padx=5, pady=5)
        self.qty_e.insert(0, "1")

        ttk.Button(input_frm, text="➕ Add", command=self._add_leg).grid(row=1, column=4, padx=10, pady=5)

        # Legs table
        table_frm = ttk.Frame(frm)
        table_frm.pack(fill="both", expand=True, pady=10)
        cols = ("Strike", "Type", "Direction", "Quantity")
        self.legs_tree = ttk.Treeview(table_frm, columns=cols, show="headings", height=10)
        for col in cols:
            self.legs_tree.heading(col, text=col)
            self.legs_tree.column(col, width=120, anchor="center")
        self.legs_tree.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(table_frm, orient="vertical", command=self.legs_tree.yview)
        vsb.pack(side="right", fill="y")
        self.legs_tree.configure(yscrollcommand=vsb.set)

        # Populate existing legs
        for leg in self.legs:
            self.legs_tree.insert("", "end", values=(
                f"{leg['strike']:.2f}", leg['type'], "Long" if leg['dir'] == 1 else "Short", leg['qty']
            ))

        # Remove and Confirm buttons
        action_frm = ttk.Frame(frm)
        action_frm.pack(fill="x", pady=5)
        ttk.Button(action_frm, text="🗑 Remove Selected", command=self._remove_leg).pack(side="left", padx=5)
        ttk.Button(action_frm, text="✔ Confirm Strategy", command=self._confirm).pack(side="left", padx=5)

        # Control buttons
        btn_frm = ttk.Frame(frm)
        btn_frm.pack(fill="x", pady=15)
        ttk.Button(btn_frm, text="Done", command=self._finish).pack(side="right", padx=5)
        ttk.Button(btn_frm, text="Cancel", command=self._cancel).pack(side="right", padx=5)

    def _add_leg(self):
        try:
            strike = float(self.strike_e.get())
            qty = int(self.qty_e.get())
            opt_t = 'C' if self.type_c.get() == "Call" else 'P'
            direc = +1 if "Long" in self.dir_c.get() else -1
            if strike <= 0 or qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Input Error", "Enter valid numeric strike / qty.", parent=self)
            return

        leg = dict(strike=strike, type=opt_t, dir=direc, qty=qty)
        self.legs.append(leg)
        self.legs_tree.insert("", "end", values=(
            f"{strike:.2f}", opt_t, "Long" if direc == 1 else "Short", qty
        ))
        self.strike_e.delete(0, tk.END)
        self.qty_e.delete(0, tk.END)
        self.qty_e.insert(0, "1")

    def _remove_leg(self):
        selected = self.legs_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a leg to remove.", parent=self)
            return
        index = self.legs_tree.index(selected[0])
        self.legs.pop(index)
        self.legs_tree.delete(selected[0])

    def _confirm(self):
        self.controller.custom_legs = self.legs.copy()
        if self.legs:
            legs_display = ", ".join(
                f"{leg['qty']}× {'Long' if leg['dir'] == 1 else 'Short'} {leg['type']} @ {leg['strike']}"
                for leg in self.legs
            )
            self.controller.custom_legs_label.configure(text=f"Custom Strategy: {legs_display}")
        else:
            self.controller.custom_legs_label.configure(text="Custom Strategy: None")
        self.grab_release()
        self.destroy()

    def _finish(self):
        self.controller.custom_legs = self.legs.copy()
        if self.legs:
            legs_display = ", ".join(
                f"{leg['qty']}× {'Long' if leg['dir'] == 1 else 'Short'} {leg['type']} @ {leg['strike']}"
                for leg in self.legs
            )
            self.controller.custom_legs_label.configure(text=f"Custom Strategy: {legs_display}")
        else:
            self.controller.custom_legs_label.configure(text="Custom Strategy: None")
        self.grab_release()
        self.destroy()

    def _cancel(self):
        self.legs = []
        self.controller.custom_legs = []
        self.controller.custom_legs_label.configure(text="Custom Strategy: None")
        self.grab_release()
        self.destroy()


class ParameterRangeSelector(ttk.Frame):
    """A custom widget for selecting a parameter range with a slider for steps."""
    def __init__(self, master, text, range_from, range_to, default_from, default_to, is_int=False, update_callback=None):
        super().__init__(master, padding=(0, 5))
        self.is_int = is_int
        self.update_callback = update_callback

        self.var_from = tk.StringVar(value=str(default_from))
        self.var_to = tk.StringVar(value=str(default_to))
        self.var_steps = tk.IntVar(value=5)

        container = ttk.LabelFrame(self, text=text, padding=10)
        container.pack(fill='x', expand=True)

        # <<< FIX: Configure grid columns to create a stable, non-resizing layout >>>
        # Give weight to the column that contains the slider so it expands, not the inputs.
        container.columnconfigure(1, weight=1) # Slider column
        container.columnconfigure(3, weight=1) # Slider column
        
        # --- Row 0: Input Boxes ---
        ttk.Label(container, text="From:").grid(row=0, column=0, sticky='w')
        entry_from = ttk.Entry(container, textvariable=self.var_from, width=8)
        entry_from.grid(row=0, column=1, sticky='we', padx=(5, 15))

        ttk.Label(container, text="To:").grid(row=0, column=2, sticky='w')
        entry_to = ttk.Entry(container, textvariable=self.var_to, width=8)
        entry_to.grid(row=0, column=3, sticky='we', padx=5)

        # --- Row 1: Steps Slider ---
        ttk.Label(container, text="Steps:").grid(row=1, column=0, sticky='w', pady=(5,0))
        self.scale_steps = ttk.Scale(container, from_=1, to=20, orient='horizontal', variable=self.var_steps, command=self._update_feedback)
        # The slider now spans all columns to fill the space cleanly.
        self.scale_steps.grid(row=1, column=1, columnspan=3, sticky='we', pady=(5,0), padx=5)

        # --- Row 2: Feedback Label ---
        self.feedback_label = ttk.Label(container, text="", font=('Segoe UI', 8, 'italic'), foreground='#888888', justify='left')
        self.feedback_label.grid(row=2, column=0, columnspan=4, sticky='w', pady=(2,0))

        # Bind events
        entry_from.bind("<KeyRelease>", self._update_feedback)
        entry_to.bind("<KeyRelease>", self._update_feedback)
        self.var_steps.trace_add("write", self._update_feedback)

        self._update_feedback()

    def _update_feedback(self, *args):
        try:
            start = float(self.var_from.get())
            end = float(self.var_to.get())
            steps = self.var_steps.get()

            if start >= end:
                self.feedback_label.config(text="Error: 'From' must be less than 'To'")
                return
            
            if steps == 1:
                 values = [start]
            else:
                values = np.linspace(start, end, steps)

            if self.is_int:
                values = np.unique(np.round(values).astype(int))
                self.var_steps.set(len(values))
                formatted_values = f"[{', '.join(map(str, values))}]"
            else:
                formatted_values = f"[{', '.join([f'{v:.1f}' for v in values])}]"
            
            self.feedback_label.config(text=f"Testing {len(values)} values: {formatted_values}")

        except (ValueError, TypeError):
            self.feedback_label.config(text="Invalid number format")
        
        if self.update_callback:
            self.update_callback()

    def get_values(self):
        start = float(self.var_from.get())
        end = float(self.var_to.get())
        steps = self.var_steps.get()
        if steps == 1:
            values = [start]  # This is a standard list
        else:
            values = np.linspace(start, end, steps) # This is a NumPy array

        if self.is_int:
            # This branch works correctly for both lists and arrays
            return np.unique(np.round(values).astype(int)).tolist()
        
        # <<< FIX: Check if it's a NumPy array before calling .tolist() >>>
        if isinstance(values, np.ndarray):
            return values.tolist()
        else:
            # If it's not a NumPy array, it's already the list we need.
            return values
    

class OptimizeDialog(tk.Toplevel):
    """A modern dialog for setting up grid search parameters with sliders."""
    AVG_TIME_PER_COMBO = 0.25 

    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        self.transient(master)
        self.grab_set()
        self.title("Configure Optimization")
        # <<< FIX: Set a wider initial size and make the window resizable >>>
        self.geometry("550x750")
        self.resizable(True, True)
        self.minsize(550, 750)

        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)

        self.param_selectors = {}
        
        # Create all widgets that are used in callbacks FIRST.
        summary_frame = ttk.LabelFrame(frm, text="Optimization Summary", padding=10)
        summary_frame.columnconfigure(1, weight=1)
        ttk.Label(summary_frame, text="Total Combinations:").grid(row=0, column=0, sticky='w')
        self.totals_label = ttk.Label(summary_frame, text="0", font=('Segoe UI', 10, 'bold'))
        self.totals_label.grid(row=0, column=1, sticky='w', padx=5)

        btn_frm = ttk.Frame(frm)
        self.run_btn = ttk.Button(btn_frm, text="Run Optimization", command=self._on_run)
        
        # NOW, create the parameter selectors that trigger the callbacks.
        self.param_selectors['dte_target'] = ParameterRangeSelector(
            frm, "DTE Target", 1, 180, 30, 60, is_int=True, update_callback=self._update_totals
        )
        self.param_selectors['dte_target'].pack(fill='x')

        self.param_selectors['allocation_pct'] = ParameterRangeSelector(
            frm, "Allocation %", 1, 25, 3, 10, update_callback=self._update_totals
        )
        self.param_selectors['allocation_pct'].pack(fill='x')

        self.param_selectors['profit_target_pct'] = ParameterRangeSelector(
            frm, "Profit Target %", 10, 100, 25, 75, update_callback=self._update_totals
        )
        self.param_selectors['profit_target_pct'].pack(fill='x')
        
        self.param_selectors['stop_loss_mult'] = ParameterRangeSelector(
            frm, "Stop Loss Multiplier (xCredit)", 1, 5, 2, 3, update_callback=self._update_totals
        )
        self.param_selectors['stop_loss_mult'].pack(fill='x')

        # Finally, pack the summary and button widgets into the layout.
        summary_frame.pack(fill='x', pady=(15, 5))
        btn_frm.pack(side='bottom', fill='x', pady=(10, 0))
        self.run_btn.pack(side="right", padx=5)
        ttk.Button(btn_frm, text="Cancel", command=self.destroy).pack(side="right")

        self._update_totals() # Initial calculation



    def _update_totals(self):
        """Calculates and displays the total number of combinations."""
        total = 1
        try:
            for selector in self.param_selectors.values():
                steps = selector.var_steps.get()
                total *= steps if steps > 0 else 1

            self.totals_label.config(text=f"{total:,}")
            self.run_btn.config(state='normal')
        except (ValueError, tk.Toplevel):
            self.totals_label.config(text="Invalid input...")
            self.run_btn.config(state='disabled')

    def _on_run(self):
        try:
            grid = {
                key: selector.get_values()
                for key, selector in self.param_selectors.items()
            }
            grid = {k: v for k, v in grid.items() if v}

            if not grid:
                messagebox.showerror("Input Error", "At least one parameter must have a valid range.", parent=self)
                return

            self.controller._start_optimization(grid)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Input Error", f"Could not generate grid.\nDetails: {e}", parent=self)