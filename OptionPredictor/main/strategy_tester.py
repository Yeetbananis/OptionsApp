# ── Standard library imports ──────────────────────
import threading
import logging
import time
import requests
from pathlib import Path
import datetime as _dt

# ── Third-party libraries ─────────────────────────
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib import style as mpl_style
from tkcalendar import DateEntry
import matplotlib.dates as mdates
from PIL import Image, ImageTk

# ── Local modules ─────────────────────────────────
from filter_dialog import FilterDialog
from filters import FilterConfig
from earningscalendar import fetch_earnings_calendar
from bounceoverlay import BounceOverlay
from config import StrategyConfig
from backtestengine import BacktestEngine
from batch_runner import BatchRunner
from data_loader import get_prices
from backtester import realized_vol


ICON_DIR = Path(__file__).parent / "icons"

# Theme definitions
THEMES = {
    "dark": {"bg":"#2e2e2e", "fg":"#ffffff", "entry_bg":"#3c3c3c"},
    "light": {"bg":"#f0f0f0", "fg":"#000000", "entry_bg":"#ffffff"}
}


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

def load_icon(path, tint_color=None, tint_black=False, size=(24, 24)):
    """
    Load an icon and tint all non-transparent pixels to `tint_color` or black if `tint_black` is True.
    `tint_color` is a hex string like '#RRGGBB' or an (R,G,B) / (R,G,B,A) tuple.
    """
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
            return ImageTk.PhotoImage(img)
        r, g, b, a = img.split()
        colored = Image.new("RGBA", img.size, tint)
        colored.putalpha(a)
        img = colored
        return ImageTk.PhotoImage(img)
    except Exception as e:
        logging.error(f"Failed to load icon {path}: {e}")
        return None





class StrategyTesterWindow:
    def __init__(self, parent, current_theme: str = "light"):
        self.filters = FilterConfig()    # “no-op” filter by default
        self.theme = current_theme
        # initialize summary text colors from central THEMES
        self.summary_txt_bg = THEMES[self.theme]["entry_bg"]
        self.summary_txt_fg = THEMES[self.theme]["fg"]
        self.current_wifi_status = "down"  # Track current WiFi status

        self.win = tk.Toplevel(parent)
        self._next_trade_iid = 1  # Track next trade IID for treeview
        self._last_progress_ts = 0.0 # Track last progress update time
        self.is_graph_fullscreen = False
        self.graph_original_parent = None
        self.fullscreen_button = None # Initialize here
        

        self.win.title("Options Strategy Backtester")
        # buffer for trades waiting to be drawn
        self._pending_trades = []
        self._flush_scheduled = False
        self.selected_trade_iid = None  # Track selected trade IID
        self.trade_marker = None  # Track plotted marker
        self.bounce = BounceOverlay(self.win) # Bounce overlay for long-running tasks
        
        # --- Load Wi-Fi icons tinted to our fg color ---
        fg_color = THEMES[self.theme]['fg']
        self.icons = {
            "down":   load_icon(ICON_DIR/"wifi_disconnected.png", tint_color=fg_color),
            "weak":   load_icon(ICON_DIR/"wifi_weak.png",        tint_color=fg_color),
            "medium": load_icon(ICON_DIR/"wifi_medium.png",      tint_color=fg_color),
            "strong": load_icon(ICON_DIR/"wifi_strong.png",      tint_color=fg_color),
            "secure": load_icon(ICON_DIR/"wifi_secure.png",      tint_color=fg_color),
        }


        self.win.geometry("1050x780")
        self.custom_legs = []


        self.style = ttk.Style(self.win)
            # ─── use clam for richer styling, then define our “cool” progressbar ───
        self.style.theme_use('clam')
        self.style.configure(
                "Cool.Horizontal.TProgressbar",
                troughcolor="#2e2e2e",    # dark track
                bordercolor="#2e2e2e",
                background="#4caf50",     # bright green fill
                lightcolor="#81c784",     # highlight
                darkcolor="#388e3c",      # shadow
                thickness=20              # taller bar
            )
        self.style.map(
                "Cool.Horizontal.TProgressbar",
                background=[('active', '#66bb6a'), ('!active', '#4caf50')]
            )


        ## ─── Set up the main window ────────────────────────────────────────────────
        self._create_widgets()


        # ─── Enable right-click “Copy” on summary and trade logs ───
        # Text‐widget menu
        self.summary_txt.bind("<Button-3>", self._show_text_context_menu)
        self._text_menu = tk.Menu(self.win, tearoff=0)
        self._text_menu.add_command(label="Copy", command=self._copy_text_selection)



        # Treeview menu (applies to both Best Run and All History)
        for tree in (self.log_tree, self.history_tree):
            tree.bind("<Button-3>", self._show_tree_context_menu)
        self._tree_menu = tk.Menu(self.win, tearoff=0)
        self._tree_menu.add_command(label="Copy", command=self._copy_tree_selection)


         # ─── Live‐log handler for the summary pane ────────────────────────────────
        import logging

        class TextHandler(logging.Handler):
            """A logging.Handler that writes to a Tkinter Text widget."""
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget

            def emit(self, record):
                try:
                    # if widget was destroyed, do nothing
                    if not getattr(self.text_widget, "winfo_exists", lambda: False)():
                        return
                    msg = self.format(record)
                    # insert at end, scrolling as we go
                    self.text_widget.configure(state='normal')
                    self.text_widget.insert('end', msg + '\n')
                    self.text_widget.see('end')
                    self.text_widget.configure(state='disabled')
                except tk.TclError:
                    # widget dead or not writable
                    return

        # attach it to the root logger (or to a named one)
        text_handler = TextHandler(self.summary_txt)
        text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logging.getLogger().addHandler(text_handler)
        # ─────────────────────────────────────────────────────────────────────────

        
        self._setup_default_values()
        logging.info("Strategy Tester window initialized.")

        # apply central theme via the parent
        if hasattr(parent, 'apply_theme_to_window'):
            parent.apply_theme_to_window(self.win)


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
        # determine which tree was clicked
        widget = event.widget
        iid = widget.identify_row(event.y)
        if not iid:
            return
        widget.selection_set(iid)
        # remember which tree for the copy callback
        self._last_tree = widget
        self._tree_menu.tk_popup(event.x_root, event.y_root)

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
        main_pane = tk.PanedWindow(self.win, orient=tk.VERTICAL, sashrelief=tk.RAISED, bg=self.win.cget('bg'))
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Header with custom legs display
        hdr = ttk.LabelFrame(main_pane, text="Backtest Configuration", padding=15)
        main_pane.add(hdr, stretch="never")

        # Add custom legs display label
        self.custom_legs_label = ttk.Label(
            hdr, text="Custom Strategy: None", font=('Segoe UI', 9, 'italic'),
            foreground='#888888' if self.theme == 'dark' else '#666666'
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

        th = THEMES[self.theme]  # pull in theme‐aware colors

        ttk.Label(inputs_frame, text="Start Date:").grid(row=0, column=2, sticky="e", padx=(5, 2), pady=8)
        self.start_ent = DateEntry(
            inputs_frame,
            width=10,
            date_pattern="yyyy-MM-dd",
            background=th["entry_bg"],
            foreground=th["fg"],
            borderwidth=1
        )
        self.start_ent.grid(row=0, column=3, sticky="w", padx=(2, 10), pady=8)

        ttk.Label(inputs_frame, text="End Date:").grid(row=0, column=4, sticky="e", padx=(5, 2), pady=8)
        self.end_ent = DateEntry(
            inputs_frame,
            width=10,
            date_pattern="yyyy-MM-dd",
            background=th["entry_bg"],
            foreground=th["fg"],
            borderwidth=1
        )
        self.end_ent.grid(row=0, column=5, sticky="w", padx=(2, 10), pady=8)
        
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

        # get the labelframe background so our text blends in
        bf = self.style.lookup('TLabelframe', 'background')
        # ─── tiny “WiFi status:” label above the icon ───
        self.wifi_text = ttk.Label(
            hdr,
            text="WiFi status:",
            font=('Segoe UI', 8),               # very small
            foreground=self.summary_txt_fg       # white in dark mode
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

        # define the style Wifi.TLabel to use the same background:
        self.style.configure('Wifi.TLabel', background=bf)
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

        self.opt_combo_lbl = ttk.Label(button_frame, text="", font=('Segoe UI', 9, 'italic'), foreground='#888888')
        self.opt_combo_lbl.pack(fill='x', padx=4, pady=(2,0))
        self.opt_progress_lbl = ttk.Label(button_frame, text="", font=('Segoe UI', 9))
        self.opt_progress_lbl.pack(fill='x', padx=4)
        self.progress = ttk.Progressbar(button_frame, style="Cool.Horizontal.TProgressbar", mode="determinate", maximum=1, value=0)
        self.progress.pack(fill='x', padx=4, pady=(2,10))

        self.opt_toolbar.pack_forget()
        self.opt_combo_lbl.pack_forget()
        self.opt_progress_lbl.pack_forget()
        self.progress.pack_forget()

        results_pane = tk.PanedWindow(main_pane, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, bg=self.win.cget('bg'))
        main_pane.add(results_pane, stretch="always")

        self.win.update_idletasks()
        main_pane.sash_place(0, 0, 250)

        left_frame = ttk.Frame(results_pane, padding=10)
        results_pane.add(left_frame, stretch="always")
        summary_frame = ttk.LabelFrame(left_frame, text="Performance Summary", padding=10)
        self.summary_txt = tk.Text(summary_frame, height=10, width=42, bg=self.summary_txt_bg, fg=self.summary_txt_fg, relief=tk.FLAT, wrap="word", font=('Consolas', 10))
        self.summary_txt.pack(fill="both", expand=True)
        summary_frame.pack(fill="x", expand=False, pady=(0,5))
        copy_perf_btn = tk.Button(summary_frame, text="📋 Copy Metrics", command=self._copy_performance_metrics,
                          bg="#555555" if self.theme == "dark" else "#e0e0e0", fg=THEMES[self.theme]["fg"])
        copy_perf_btn.pack(anchor="ne", pady=(0, 5))
        plot_frame = ttk.LabelFrame(left_frame, text="Equity Curve", padding=5)
        plot_frame.pack(fill="both", expand=True)

        fig_bg = "#2e2e2e" if self.theme == "dark" else "#f0f0f0"
        self.fig, self.ax = plt.subplots(facecolor=fig_bg)
        self.ax.set_facecolor(self.summary_txt_bg)
        self.ax.tick_params(colors=self.summary_txt_fg)
        self.ax.xaxis.label.set_color(self.summary_txt_fg)
        self.ax.yaxis.label.set_color(self.summary_txt_fg)
        self.ax.title.set_color(self.summary_txt_fg)
        for s in self.ax.spines.values(): s.set_edgecolor(self.summary_txt_fg)
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.fig.tight_layout()

        # --- Add Fullscreen Button ---
        try:
           # tint the fullscreen/minimize icons to match our fg color
            fg_color = THEMES[self.theme]['fg']
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
            self.style.configure('Transparent.TButton', background=self.win.cget('bg'), borderwidth=0)
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
        tabs.add(best_tab, text="Best Run")
        tabs.add(hist_tab, text="All History")
        tabs.pack(fill="both", expand=True)

        cols = ("Trade #","Open Date","Close Date","K Short","K Long","Contracts","Credit ($)","PnL ($)")
        widths = (60, 90, 90, 70, 70, 70, 80, 90)

        # --- Filter Entry Box ---
        filter_frame = tk.Frame(best_tab, bg=self.win.cget('bg'))
        filter_frame.pack(fill="x", padx=10, pady=(10, 0))

        self.filter_var = tk.StringVar()
        filter_entry = tk.Entry(filter_frame, textvariable=self.filter_var, bg=THEMES[self.theme]["entry_bg"], fg=THEMES[self.theme]["fg"], insertbackground=THEMES[self.theme]["fg"])
        filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        filter_button = tk.Button(filter_frame, text="Filter Trades", command=self._filter_trades, bg="#555555" if self.theme == "dark" else "#e0e0e0", fg=THEMES[self.theme]["fg"])
        filter_button.pack(side="left")

        # Create a frame for the Treeview and scrollbars to avoid mixing pack and grid
        tree_frame = ttk.Frame(best_tab)
        tree_frame.pack(fill="both", expand=True)

        self.log_tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=15)
        for i, c in enumerate(cols):
            self.log_tree.heading(c, text=c, command=lambda cc=c: self._sort_treeview(self.log_tree, cc, False))
            self.log_tree.column(c, width=widths[i], anchor="c", stretch=True)
        self.log_tree.tag_configure('oddrow', background=self.summary_txt_bg)
        self.log_tree.tag_configure('evenrow', background=self.summary_txt_bg)

        profit_color, loss_color = ("#264d26", "#4d2626") if self.theme == "dark" else ("#d0f0c0", "#f0d0d0")
        self.log_tree.tag_configure('profit', background=profit_color, foreground=self.summary_txt_fg)
        self.log_tree.tag_configure('loss', background=loss_color, foreground=self.summary_txt_fg)

        vsb_best = ttk.Scrollbar(tree_frame, orient="vertical", command=self.log_tree.yview)
        hsb_best = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.log_tree.xview)
        self.log_tree.configure(yscrollcommand=vsb_best.set, xscrollcommand=hsb_best.set)

        # Use grid within the tree_frame
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.log_tree.grid(row=0, column=0, sticky="nsew")
        vsb_best.grid(row=0, column=1, sticky="ns")
        hsb_best.grid(row=1, column=0, sticky="ew")
        export_btn = tk.Button(best_tab, text="💾 Export Trades", command=self._export_trades_to_csv,
                       bg="#555555" if self.theme == "dark" else "#e0e0e0", fg=THEMES[self.theme]["fg"])
        export_btn.pack(anchor="ne", pady=5, padx=10)
        self.log_tree.bind('<<TreeviewSelect>>', self._on_trade_select)
        self.log_tree.bind("<Button-3>", self._show_trade_right_click)

        hist_cols = cols + ("dte_target","allocation_pct","profit_target_pct")
        self.history_tree = ttk.Treeview(hist_tab, columns=hist_cols, show="headings", height=15)
        for c in hist_cols:
            self.history_tree.heading(c, text=c)
            self.history_tree.column(c, width=80, anchor="c")
        self.history_tree.tag_configure('profit', background=profit_color, foreground=self.summary_txt_fg)
        self.history_tree.tag_configure('loss', background=loss_color, foreground=self.summary_txt_fg)

        vsb_hist = ttk.Scrollbar(hist_tab, orient="vertical", command=self.history_tree.yview)
        hsb_hist = ttk.Scrollbar(hist_tab, orient="horizontal", command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=vsb_hist.set, xscrollcommand=hsb_hist.set)
        hist_tab.rowconfigure(0, weight=1)
        hist_tab.columnconfigure(0, weight=1)
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        vsb_hist.grid(row=0, column=1, sticky="ns")
        hsb_hist.grid(row=1, column=0, sticky="ew")

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
        dlg = CustomLegBuilder(self.win, theme=self.theme, existing_legs=self.custom_legs.copy(), controller=self)
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
        OptimizeDialog(self.win, controller=self, theme=self.theme)

    def _start_optimization(self, param_grid: dict):
        """Kick off a batch run over our param grid with live progress & trades."""
        base_cfg = self._validate_inputs()
        if base_cfg is None:
            return

        # ensure filters object
        if isinstance(base_cfg.get("filters"), dict):
            base_cfg["filters"] = FilterConfig(**base_cfg["filters"])

        # ─── load (cached) earnings calendar only once ──────────────────────────────
        #cal = fetch_earnings_calendar(base_cfg["underlying"])
        #base_cfg["filters"].earnings_calendar = { base_cfg["underlying"]: cal }

        # start bounce animation during long optimize phase
        self.bounce.start()
        self.win.update_idletasks()

        # Build a StrategyConfig template (validates internally)
        try:
            template = StrategyConfig(**base_cfg)
        except Exception as e:
            messagebox.showerror("Config Error", str(e), parent=self.win)
            return

        # Clear summary & disable main buttons
        self.run_btn.configure(state="disabled")
        self.optimize_btn.configure(state="disabled")
        # also disable Build-Legs (but don’t hide it)
        self.build_btn.configure(state="disabled")

        # Show the secondary toolbar
        self.opt_toolbar.pack(fill='x', pady=5)
        self.pause_opt_btn.configure(state='normal', text='⏸ Pause')
        self.end_early_btn.configure(state='normal')
        self.cancel_opt_btn.configure(state='normal')

        # Show status labels
        self.opt_combo_lbl.configure(text="")
        self.opt_combo_lbl.pack(fill='x', padx=4, pady=(2,0))
        self.opt_progress_lbl.configure(text="")
        self.opt_progress_lbl.pack(fill='x', padx=4)

        # Configure & show progress bar
        self.progress.configure(mode='determinate', value=0, maximum=1)
        self.progress.pack(fill='x', padx=4, pady=(2,10))

        # Compute total combinations
        total = 1
        for vals in param_grid.values():
            total *= len(vals)
        self.progress.configure(maximum=total)

        # Record start time for ETA
        self.opt_start_time = _dt.datetime.now()

        # Reset combo label for the first iteration
        self.opt_combo_lbl.config(text="Testing: ")

        # ─────────────────────────────────────────────────────────────
        # 1) Preload all price & vol data once for the entire grid
        #    (avoids repeated I/O and roll-vol computation)
        price_data = get_prices(
            template.underlying,
            template.start,
            template.end,
        )
        vol_data = realized_vol(price_data).ffill().bfill().clip(lower=0.05)

        # Optional: preload benchmark too
        benchmark_data = None
        if template.use_benchmark:
            benchmark_data = get_prices(
                template.benchmark_ticker,
                template.start,
                template.end,
            )


        # Create and store the BatchRunner with shared data
        self.runner = BatchRunner(
            base_cfg=template,
            sweep_params=param_grid,
            price_data=price_data,
            vol_data=vol_data,
            benchmark_data=benchmark_data,
            progress_callback=self._update_opt_progress,
            trade_callback=self._log_trade
        )


        # Run in background
        threading.Thread(target=self._run_optimization_thread, daemon=True).start()




    def _run_optimization_thread(self):
        """Execute BatchRunner and schedule display."""
        try:
            self.runner.run()
            self.win.after(0, self._populate_optimization_results)
        except Exception as e:
            logging.exception("Error during optimization:")
            # capture e into the lambda
            self.win.after(0, lambda exc=e: messagebox.showerror(
                "Optimize Error", str(exc), parent=self.win))

        finally:
            self.win.after(0, self._finalize_backtest_ui)  # re-enable Run & Optimize

    def _populate_optimization_results(self):
        """After grid-search, pick the best combo and display it just like a normal backtest."""

        # ─── STOP THE BOUNCE OVERLAY ───
        self.bounce.stop()

        # 1) grab the DataFrame and find the best row
        df = self.runner.results_df()
        best = df.sort_values("total_return_pct", ascending=False).iloc[0]

        # 2) write best values back into the inputs
        self.dte_ent.delete(0, tk.END)
        self.dte_ent.insert(0, str(int(best["dte_target"])))

        self.alloc_ent.delete(0, tk.END)
        self.alloc_ent.insert(0, f"{best['allocation_pct']}")

        self.pt_ent.delete(0, tk.END)
        self.pt_ent.insert(0, f"{best['profit_target_pct']}")

        self.sl_ent.delete(0, tk.END)
        self.sl_ent.insert(0, f"{best['stop_loss_mult']}")

        # ─── popup with best settings ───────────────────────────
        msg = (
            "🎉 Optimization Complete! 🎉\n\n"
            "Best Settings Applied:\n"
            f"• DTE: {int(best['dte_target'])}\n"
            f"• Allocation %: {best['allocation_pct']}\n"
            f"• Profit Target %: {best['profit_target_pct']}\n\n"
            f"Win Rate: {best['win_rate']:.2f}%\n"
            f"Total Return: {best['total_return_pct']:.2f}%"
        )
        messagebox.showinfo("Optimization Results", msg, parent=self.win)

        # 3) build a config with overrides
        base_cfg = self._validate_inputs()
        merged = {
            **base_cfg,
            "dte_target":        int(best["dte_target"]),
            "allocation_pct":    best["allocation_pct"],
            "profit_target_pct": best["profit_target_pct"],
            "stop_loss_mult":    best["stop_loss_mult"],
        }
        self.filters = merged["filters"]

        # 4) run single backtest on best
        cfg_obj = StrategyConfig(**merged)
        engine = BacktestEngine(cfg_obj)
        engine.run()
        self.engine = engine

        # 5) clear and redraw trade logs
        self.log_tree.delete(*self.log_tree.get_children())
        self.history_tree.delete(*self.history_tree.get_children())

        # Insert best-run trades into Best Run tab
        best_trades = self.runner.best_run_trades()
        for i, t in enumerate(best_trades):
            pnl = t.get('pnl', 0.0)
            tag = 'profit' if pnl > 0 else 'loss' if pnl < 0 else ('evenrow' if i % 2 == 0 else 'oddrow')

            k_short = t.get('K_short')
            k_short_str = f"{k_short:.2f}" if isinstance(k_short, (int, float)) else ""
            k_long = t.get('K_long')
            k_long_str = f"{k_long:.2f}" if isinstance(k_long, (int, float)) else ""

            vals = (
                i + 1,
                t['open'].strftime('%Y-%m-%d'),
                t['close'].strftime('%Y-%m-%d'),
                k_short_str,
                k_long_str,
                t.get('contracts', 0),
                f"{t.get('credit', 0):.2f}",
                f"{pnl:.2f}"
            )
            self.log_tree.insert("", "end", values=vals, tags=(tag,))

            # Insert all trades into All History tab
            for i, record in enumerate(self.runner.all_trades(), start=1):
                pnl = record.get('pnl', 0)
                tag = 'profit' if pnl > 0 else 'loss'
                vals = (
                    i,
                    record['open'].strftime('%Y-%m-%d'),
                    record['close'].strftime('%Y-%m-%d'),
                    f"{record.get('K_short',''):.2f}" if record.get('K_short') is not None else "",
                    f"{record.get('K_long',''):.2f}"  if record.get('K_long')  is not None else "",
                    record.get('contracts', 0),
                    f"{record.get('credit', 0):.2f}",
                    f"{record.get('pnl', 0):.2f}",
                    record.get('dte_target', ''),
                    record.get('allocation_pct', ''),
                    record.get('profit_target_pct', ''),
                )
                self.history_tree.insert("", "end", values=vals, tags=(tag,))


        self.opt_combo_lbl.pack_forget()  # hide label
        self._populate_results()


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




    def _update_opt_progress(self, done, total, overrides):
        # update progress bar
        self.progress['value'] = done
        elapsed = (_dt.datetime.now() - self.opt_start_time).total_seconds()
        eta = int(elapsed / done * (total - done)) if done else None
        eta_str = f" — ETA {eta}s" if eta is not None else ""



        # update progress text
        self.opt_progress_lbl.config(text=f"{done}/{total}{eta_str}")

        # update combo label
        combo_text = (
            f"Testing: DTE={overrides['dte_target']}, "
            f"Alloc={overrides['allocation_pct']}%, "
            f"ProfitTgt={overrides['profit_target_pct']}%, "
            f"Stop×={overrides['stop_loss_mult']}"
        )
        self.opt_combo_lbl.config(text=combo_text)


    def _log_trade(self, trade):
        """
        Instead of inserting + scrolling on every trade,
        buffer it and schedule a single flush at idle time.
        """
        self._pending_trades.append(trade)
        if not self._flush_scheduled:
            self._flush_scheduled = True
            self.win.after_idle(self._flush_trade_log)


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



    def _update_backtest_progress(self, done, total):
        now = time.time()
        # throttle to ~50 Hz, but always show the final tick
        if now - self._last_progress_ts >= 0.02 or done == total:
            self._last_progress_ts = now
            self.progress['maximum'] = total
            self.progress['value']   = done
            # lightweight repaint
            self.progress.update_idletasks()




    def _cancel_optimization(self):
        """Completely reset after a Cancel Optimize."""
        if hasattr(self, 'runner'):
            self.runner.cancel()

        # Stop and reset progress
        try:
            self.progress.stop()
        except tk.TclError:
            pass
        self.progress.configure(value=0, mode="determinate")

        # Clear summary & trade logs
        for tree in (self.log_tree, self.history_tree):
            for iid in tree.get_children():
                tree.delete(iid)

        # Restore buttons & hide cancel/pause labels
        self.run_btn.configure(state="normal")
        self.optimize_btn.configure(state="normal")
        self.cancel_opt_btn.pack_forget()
        self.pause_opt_btn.pack_forget()
        self.opt_progress_lbl.pack_forget()
        self.end_early_btn.pack_forget()

        self.pause_opt_btn.configure(text="⏸ Pause", state="disabled")
        self.end_early_btn.configure(state="disabled")
        self.cancel_opt_btn.configure(state="disabled")



    def _toggle_pause_opt(self):
        """Pause or resume the running optimization."""
        if not hasattr(self, 'runner'):
            return

        if not getattr(self.runner, 'is_paused', False):
            # pause
            self.runner.pause()
            self.pause_opt_btn.configure(text="▶ Resume Optimize")
            self.opt_progress_lbl.configure(text="Paused — click Resume to continue")
        else:
            # resume
            self.runner.resume()
            self.pause_opt_btn.configure(text="⏸ Pause Optimize")
            self.opt_progress_lbl.configure(text="")

    def _end_early_optimization(self):
        """Stop the grid-search immediately and display the best‐so‐far result."""
        if hasattr(self, 'runner'):
            self.runner.cancel()
        # update UI
        self.opt_progress_lbl.config(text="Optimization ended early")
        self.cancel_opt_btn.pack_forget()
        self.end_early_btn.pack_forget()

        # pick the best row so far
        df = self.runner.results_df()
        if df.empty:
            messagebox.showinfo("No results", "No completed runs to show yet.", parent=self.win)
            # re-enable buttons
            self._finalize_backtest_ui()
            return

        best = df.sort_values("total_return_pct", ascending=False).iloc[0]

        # write best values back into inputs (same as in _populate_optimization_results)
        self.dte_ent.delete(0, tk.END)
        self.dte_ent.insert(0, str(int(best["dte_target"])))
        self.alloc_ent.delete(0, tk.END)
        self.alloc_ent.insert(0, f"{best['allocation_pct']}")
        self.pt_ent.delete(0, tk.END)
        self.pt_ent.insert(0, f"{best['profit_target_pct']}")
        self.sl_ent.delete(0, tk.END)
        self.sl_ent.insert(0, f"{best['stop_loss_mult']}")

        # show a short popup
        msg = (
            "🏁 Ended Early! Best‐so‐Far Settings:\n"
            f"• DTE: {int(best['dte_target'])}\n"
            f"• Allocation %: {best['allocation_pct']}\n"
            f"• Profit Target %: {best['profit_target_pct']}\n\n"
            f"Total Return: {best['total_return_pct']:.2f}%"
        )
        messagebox.showinfo("Early Optimization Results", msg, parent=self.win)

        self.pause_opt_btn.configure(text="⏸ Pause", state="disabled")
        self.end_early_btn.configure(state="disabled")
        self.cancel_opt_btn.configure(state="disabled")

        # now run a single backtest on that best combo
        # (reuse the same routine as when optimization finishes)
        self._populate_optimization_results()
        self._finalize_backtest_ui()



    def _open_filter_dialog(self):
        dlg = FilterDialog(self.win, controller=self, theme=self.theme)
        self.win.wait_window(dlg)
        self.filters = dlg.filter_config
        self._rebuild_trade_log_from_last_run()


     


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
        self.engine = BacktestEngine(cfg, progress_callback=self._update_backtest_progress, trade_callback=self._handle_trade)


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


    def _flush_trade_log(self):
        """
        Called via after_idle() to drain the pending‐trades buffer
        and insert them into the log in one go.
        """
        # Copy & clear buffer
        batch = self._pending_trades
        self._pending_trades = []
        self._flush_scheduled = False

        # Let _handle_trade do the insertion for us
        # It accepts either a single dict or a list of dicts.
        self._handle_trade(batch)




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



    def _format_stat(self, key, value):
        """Format statistic value for display."""
        if isinstance(value, (int, float)):
            if 'pct' in key or 'rate' in key or key in ['cagr', 'sharpe', 'sortino']:
                return f"{value:.2f}%" if 'pct' in key or 'rate' in key or key == 'cagr' else f"{value:.3f}"
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
    
    def _add_numeric_validation(self, widget, cast_type, min_val=None, max_val=None):
        """Attach realtime validation to highlight widget red if cast_type(value) fails or out of bounds."""
        def on_key(event):
            val = widget.get().strip()
            try:
                num = cast_type(val)
                if (min_val is not None and num < min_val) or (max_val is not None and num > max_val):
                    raise ValueError
                widget.configure(foreground='black')
            except:
                widget.configure(foreground='red')
        widget.bind("<KeyRelease>", on_key)


    def _populate_results(self):
        """Pull results out of the engine and plot equity + Stooq benchmark."""
        import io, requests
        import matplotlib.pyplot as plt

        # ─── clear the “log” pane ──────────────────────────────────────────────
        self.summary_txt.configure(state="normal")
        self.summary_txt.delete("1.0", "end")

        result  = self.engine.result()
        stats   = result.summary()
        equity  = result.equity_curve()
        trades  = result.trade_list()



        # ─── Summary panel ─────────────────────────────────────────
        summary_lines = []
        if stats:
            display_order = [
                ('start_value', 'Start Equity'), ('end_value', 'End Equity'),
                ('total_return', 'Total Return ($)'), ('total_return_pct', 'Total Return (%)'),
                ('cagr', 'CAGR (%)'), ('sharpe', 'Sharpe Ratio'),
                ('sortino', 'Sortino Ratio'), ('max_drawdown', 'Max Drawdown ($)'),
                ('total_trades', 'Total Trades'), ('win_rate', 'Win Rate (%)'),
                ('avg_win', 'Average Win ($)'), ('avg_loss', 'Average Loss ($)'),
                ('profit_factor', 'Profit Factor'), ('expectancy', 'Expectancy ($)'),
                ('gross_profit', 'Gross Profit ($)'), ('gross_loss', 'Gross Loss ($)'),
            ]
            max_label_len = max(len(lbl) for _, lbl in display_order) + 1
            for key, lbl in display_order:
                v = stats.get(key, 'N/A')
                formatted = self._format_stat(key, v) if v != 'N/A' else 'N/A'
                summary_lines.append(f"{lbl:<{max_label_len}}: {formatted}")

            # only show beat‐benchmark if enabled and we have data
            if self.benchmark_var.get() and not equity.empty:
                # fetch Stooq to compare
                ticker = self.benchmark_cbo.get().lower()
                s_str = equity.index[0].strftime("%Y%m%d")
                e_str = equity.index[-1].strftime("%Y%m%d")
                url = f"https://stooq.com/q/d/l/?s={ticker}.us&d1={s_str}&d2={e_str}&i=d"
                try:
                    resp = requests.get(url, timeout=10); resp.raise_for_status()
                    df2 = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"], index_col="Date")
                    series = df2["Adj Close"] if "Adj Close" in df2.columns else df2["Close"]
                    series = series.reindex(equity.index).ffill().bfill()
                    # normalize to strategy start
                    strat_start = float(equity.iloc[0])
                    series = series / series.iloc[0] * strat_start
                    last_strat = float(equity.iloc[-1])
                    last_bench = float(series.iloc[-1])
                    beat = "Yes" if last_strat >= last_bench else "No"
                    summary_lines.append(f"{'Beat ' + ticker.upper():<{max_label_len}}: {beat}")
                except Exception:
                    summary_lines.append(f"{'Beat ' + ticker.upper():<{max_label_len}}: N/A")

        else:
            summary_lines.append("Backtest failed or produced no results.")

         # ─── dump performance summary into the text pane ───────────────────────
        self.summary_txt.insert("1.0", "\n".join(summary_lines))
        self.summary_txt.configure(state="disabled")


        # ─── Trade log ─────────────────────────────────────────────
        self.log_tree.delete(*self.log_tree.get_children())
        for i, t in enumerate(trades):
            pnl = t.get('pnl', 0.0)
            tag = 'profit' if pnl>0 else 'loss' if pnl<0 else ('evenrow' if i%2==0 else 'oddrow')
            vals = (
                i+1,
                t['open'].strftime('%Y-%m-%d'),
                t['close'].strftime('%Y-%m-%d'),
                f"{t.get('K_short',''):.2f}" if t.get('K_short') is not None else "",
                f"{t.get('K_long',''):.2f}" if t.get('K_long') is not None else "",
                t.get('contracts',0),
                f"{t.get('credit',0):.2f}",
                f"{pnl:.2f}"
            )
            self.log_tree.insert("", "end", values=vals, tags=(tag,))

        # ─── Equity curve + Stooq benchmark ────────────────────────
        self.ax.clear()
        self.plot_data['dates'], self.plot_data['pnl'] = [], []
        if self.tooltip:
            self.tooltip.set_visible(False);  self.tooltip=None
        if self.tooltip_line:
            self.tooltip_line.set_visible(False); self.tooltip_line=None

        if not equity.empty:
            dates  = equity.index.to_pydatetime()
            values = equity.to_numpy()
            self.plot_data['dates'] = list(dates)
            self.plot_data['pnl']   = list(values)

            # strategy
            self.ax.plot(dates, values, lw=1.5, color="#3498db", label="Strategy")

            # stooq benchmark
            if self.benchmark_var.get():
                ticker = self.benchmark_cbo.get().lower()
                s_str = equity.index[0].strftime("%Y%m%d")
                e_str = equity.index[-1].strftime("%Y%m%d")
                url = f"https://stooq.com/q/d/l/?s={ticker}.us&d1={s_str}&d2={e_str}&i=d"
                resp = requests.get(url, timeout=10); resp.raise_for_status()
                df2 = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"], index_col="Date")
                series = df2["Adj Close"] if "Adj Close" in df2.columns else df2["Close"]
                series = series.reindex(equity.index).ffill().bfill()
                strat_start = float(equity.iloc[0])
                series = series / series.iloc[0] * strat_start
                self.ax.plot(
                    dates,
                    series.to_numpy(),
                    lw=1.2,
                    linestyle="--",
                    color="#888888",
                    label=self.benchmark_cbo.get()
                )

            self.ax.legend()
            self.ax.set_title("Equity Curve", color=self.summary_txt_fg)
            self.ax.set_xlabel("Date", color=self.summary_txt_fg)
            self.ax.set_ylabel("Account Value ($)", color=self.summary_txt_fg)
            fmt = plt.FuncFormatter(lambda x, p: f'${x:,.0f}')
            self.ax.yaxis.set_major_formatter(fmt)
            self.ax.grid(True, linestyle='--', linewidth=0.5,
                        color=self.summary_txt_fg, alpha=0.7)
        else:
            self.ax.set_title("Equity Curve (No Data)", color=self.summary_txt_fg)

        for spine in self.ax.spines.values():
            spine.set_edgecolor(self.summary_txt_fg)
        self.ax.tick_params(colors=self.summary_txt_fg)

        # ─── tooltip handler (unchanged) ───────────────────────────
        if hasattr(self, 'tooltip_cid'):
            self.canvas.mpl_disconnect(self.tooltip_cid)

        def on_motion(event):
            if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
                if self.tooltip:
                    self.tooltip.set_visible(False)
                    self.tooltip_line.set_visible(False)
                    self.canvas.draw_idle()
                return

            x, y = event.xdata, event.ydata
            dates, pnl = self.plot_data['dates'], self.plot_data['pnl']
            if not dates:
                return

            # find nearest point
            arr = np.array([d.date() for d in dates], dtype='datetime64[D]').astype(float)
            idx = np.argmin(np.abs(arr - x))
            nd, npnl = dates[idx], pnl[idx]

            # format text
            date_str = pd.Timestamp(nd).strftime('%Y-%m-%d')
            pnl_str  = f"${npnl:,.2f}" if npnl >= 0 else f"-${-npnl:,.2f}"
            txt = f"Results on {date_str}\nProfit/Loss: {pnl_str}"

            # figure + canvas pixel size
            fig_w, fig_h = self.canvas.get_width_height()
            # data → display coords
            disp_x, disp_y = self.ax.transData.transform((x, y))
            margin = 200  # px

            # choose offset & alignment based on proximity to right edge
            if disp_x > fig_w - margin:
                offset, ha = (-10, 10), 'right'
            else:
                offset, ha = (10, 10), 'left'

            if not self.tooltip:
                self.tooltip = self.ax.annotate(
                    txt,
                    xy=(x, y),
                    xytext=offset,
                    textcoords="offset points",
                    bbox=dict(boxstyle="round,pad=0.5", fc="green", alpha=0.8),
                    arrowprops=dict(arrowstyle="->"),
                    ha=ha, va='bottom'
                )
                self.tooltip_line, = self.ax.plot(
                    [x, x],
                    [self.ax.get_ylim()[0], y],
                    'k--', lw=1, visible=False
                )
            else:
                self.tooltip.set_text(txt)
                self.tooltip.xy = (x, y)
                self.tooltip.set_ha(ha)
                self.tooltip.set_position(offset)
                self.tooltip_line.set_xdata([x, x])
                self.tooltip_line.set_ydata([self.ax.get_ylim()[0], y])

            self.tooltip.set_visible(True)
            self.tooltip_line.set_visible(True)
            self.canvas.draw_idle()


        # --- Disconnect old handlers if they exist ---
        if hasattr(self, 'tooltip_cid') and self.tooltip_cid:
            try:
                self.canvas.mpl_disconnect(self.tooltip_cid)
            except:
                pass # Ignore errors if already disconnected

        # --- Connect the new _on_plot_motion method ---
        self.tooltip_cid = self.canvas.mpl_connect('motion_notify_event', self._on_plot_motion)

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
        txt = f"Results on {date_str}\nProfit/Loss: {pnl_str}"

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
        # Get the text from the summary_txt widget
        summary_text = self.summary_txt.get("1.0", tk.END).strip()
        if not summary_text:
            messagebox.showwarning("No Metrics", "No performance metrics available to copy.", parent=self.win)
            return

        # Copy the summary text to the clipboard
        self.win.clipboard_clear()
        self.win.clipboard_append(summary_text)
        self.win.update()

        # Create a temporary notification window
        notify = tk.Toplevel(self.win)
        notify.transient(self.win)
        notify.overrideredirect(True)  # Remove window decorations
        notify.geometry("200x50")  # Small window size
        notify.lift()  # Ensure window is on top
        notify.update()  # Force redraw

        # Style based on theme
        bg = THEMES[self.theme]["bg"]
        fg = THEMES[self.theme]["fg"]
        notify.configure(bg=bg)

        # Create label with "Metrics Copied!" message
        label = ttk.Label(
            notify,
            text="Metrics Copied!",
            background="#888888",
            foreground="#000000", 
            font=('Segoe UI', 10, 'italic'),  # Added italic for emphasis
            anchor='center'
        )
        label.pack(fill=tk.BOTH, expand=True)

        # Center the window relative to the main window
        x = self.win.winfo_rootx() + (self.win.winfo_width() - 200) // 2
        y = self.win.winfo_rooty() + (self.win.winfo_height() - 50) // 2
        notify.geometry(f"+{x}+{y}")

        # Destroy the window after 1.5 seconds
        notify.after(1500, notify.destroy)


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
        if not getattr(self, '_fs_window', None) or not self._fs_window.winfo_exists():
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

            # 5) Connect the tooltip handler to this new canvas
            self._fs_tooltip_cid = self._fs_canvas.mpl_connect(
                'motion_notify_event', self._on_plot_motion)

            # 6) Create a close button for the fullscreen window
            try:
                # Load minimize icon with smaller size
                self.minimize_icon = load_icon(
                    ICON_DIR / "minimize.png",
                    tint_black=(self.theme == "light"),
                    size=(16, 16)  # Smaller size
                )
                if self.minimize_icon is None:
                    raise ValueError("Failed to load minimize icon")

                # Create button with transparent style
                self.style.configure('Transparent.TButton', background=self.win.cget('bg'), borderwidth=0)
                self._fs_close_btn = ttk.Button(
                    self._fs_window,
                    image=self.minimize_icon,
                    command=self._toggle_fullscreen_graph,
                    style='Transparent.TButton'
                )
                # Explicitly retain the icon reference
                self._fs_close_btn.image_ref = self.minimize_icon
                self._fs_close_btn.place(relx=0.99, rely=0.01, anchor='ne', x=-2, y=2)  # Adjusted position

            except Exception as e:
                logging.error(f"Could not load minimize icon for fullscreen window: {e}")
                # Fallback to minimal text button
                self.style.configure('Transparent.TButton', background=self.win.cget('bg'), borderwidth=0)
                self._fs_close_btn = ttk.Button(
                    self._fs_window,
                    text="Exit FS",
                    command=self._toggle_fullscreen_graph,
                    style='Transparent.TButton'
                )
                self._fs_close_btn.place(relx=0.99, rely=0.01, anchor='ne', x=-2, y=2)

            # 7) Update the main button icon
            self.fullscreen_button.configure(image=self.minimize_icon)
            self.fullscreen_button.image_ref = self.minimize_icon

            # 8) Adjust layout & redraw
            self.fig.tight_layout()
            self._fs_canvas.draw_idle()
            self.is_graph_fullscreen = True

        # → EXIT fullscreen
        else:
            # 1) Disconnect tooltip from fullscreen canvas
            if hasattr(self, '_fs_tooltip_cid') and hasattr(self, '_fs_canvas') and self._fs_canvas:
                try:
                    self._fs_canvas.mpl_disconnect(self._fs_tooltip_cid)
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
            self.fig.tight_layout()
            self.canvas.draw_idle()
            self.is_graph_fullscreen = False

   
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
        StrategyTesterWindow(root, current_theme=theme)

    ttk.Button(root, text="Open Strategy Tester", command=open_tester).pack(pady=20)
    root.mainloop()


class CustomLegBuilder(tk.Toplevel):
    """Modal window for adding custom strategy legs with a modern UI."""
    def __init__(self, master, theme="light", existing_legs=None, controller=None):
        super().__init__(master)
        self.title("Build Custom Strategy")
        self.geometry("600x450")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.legs = existing_legs or []
        self.theme = theme
        self.controller = controller  # Reference to StrategyTesterWindow instance
        self._make_widgets(theme)

    def _make_widgets(self, theme):
        bg, fg = ("#2e2e2e", "#ffffff") if theme == "dark" else ("#f0f0f0", "#000000")
        entry_bg = "#3c3c3c" if theme == "dark" else "#ffffff"
        button_bg = "#555555" if theme == "dark" else "#e0e0e0"
        self.configure(bg=bg)

        style = ttk.Style()
        style.configure('CustomLeg.TLabel', background=bg, foreground=fg, font=('Segoe UI', 10))
        style.configure('CustomLeg.TEntry', fieldbackground=entry_bg, foreground=fg, font=('Segoe UI', 10))
        style.configure('CustomLeg.TCombobox', fieldbackground=entry_bg, foreground=fg, arrowcolor=fg, font=('Segoe UI', 10))
        style.map('CustomLeg.TCombobox', fieldbackground=[('readonly', entry_bg)])
        style.configure('CustomLeg.TButton', background=button_bg, foreground=fg, font=('Segoe UI', 10))
        style.map('CustomLeg.TButton', background=[('active', '#666666' if theme == 'dark' else '#d0d0d0')])
        style.configure('CustomLeg.Treeview', background=entry_bg, fieldbackground=entry_bg, foreground=fg, font=('Segoe UI', 10))
        style.configure('CustomLeg.Treeview.Heading', background=button_bg, foreground=fg, font=('Segoe UI', 10))

        frm = ttk.Frame(self, padding=20)
        frm.pack(fill="both", expand=True)

        # Input frame
        input_frm = ttk.Frame(frm)
        input_frm.pack(fill="x", pady=(0, 10))

        ttk.Label(input_frm, text="Strike", style='CustomLeg.TLabel').grid(row=0, column=0, padx=5, pady=5)
        self.strike_e = ttk.Entry(input_frm, width=10, style='CustomLeg.TEntry')
        self.strike_e.grid(row=1, column=0, padx=5, pady=5)

        ttk.Label(input_frm, text="Type", style='CustomLeg.TLabel').grid(row=0, column=1, padx=5, pady=5)
        self.type_c = ttk.Combobox(input_frm, values=["Call", "Put"], width=8, state="readonly", style='CustomLeg.TCombobox')
        self.type_c.grid(row=1, column=1, padx=5, pady=5)
        self.type_c.current(0)

        ttk.Label(input_frm, text="Long/Short", style='CustomLeg.TLabel').grid(row=0, column=2, padx=5, pady=5)
        self.dir_c = ttk.Combobox(input_frm, values=["Long (+1)", "Short (-1)"], width=12, state="readonly", style='CustomLeg.TCombobox')
        self.dir_c.grid(row=1, column=2, padx=5, pady=5)
        self.dir_c.current(1)

        ttk.Label(input_frm, text="Quantity", style='CustomLeg.TLabel').grid(row=0, column=3, padx=5, pady=5)
        self.qty_e = ttk.Entry(input_frm, width=8, style='CustomLeg.TEntry')
        self.qty_e.grid(row=1, column=3, padx=5, pady=5)
        self.qty_e.insert(0, "1")

        ttk.Button(input_frm, text="➕ Add", command=self._add_leg, style='CustomLeg.TButton').grid(row=1, column=4, padx=10, pady=5)

        # Legs table
        table_frm = ttk.Frame(frm)
        table_frm.pack(fill="both", expand=True, pady=10)
        cols = ("Strike", "Type", "Direction", "Quantity")
        self.legs_tree = ttk.Treeview(table_frm, columns=cols, show="headings", height=10, style='CustomLeg.Treeview')
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
        ttk.Button(action_frm, text="🗑 Remove Selected", command=self._remove_leg, style='CustomLeg.TButton').pack(side="left", padx=5)
        ttk.Button(action_frm, text="✔ Confirm Strategy", command=self._confirm, style='CustomLeg.TButton').pack(side="left", padx=5)

        # Control buttons
        btn_frm = ttk.Frame(frm)
        btn_frm.pack(fill="x", pady=15)
        ttk.Button(btn_frm, text="Done", command=self._finish, style='CustomLeg.TButton').pack(side="right", padx=5)
        ttk.Button(btn_frm, text="Cancel", command=self._cancel, style='CustomLeg.TButton').pack(side="right", padx=5)

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


class OptimizeDialog(tk.Toplevel):
    """Gather ranges for DTE, Alloc %, Profit Target."""
    def __init__(self, master, controller, theme="light"):
        super().__init__(master)
        self.controller = controller
        self.transient(master)
        self.grab_set()
        self.title("Optimize Grid Search")
        frm = ttk.Frame(self, padding=15)
        frm.pack(fill="both", expand=True)
        # Labels + entries for four parameters: from, to, step
        labels = ["DTE", "Alloc %", "Profit Target %", "Stop Loss ×"]
        self.vars = {}
        for i, name in enumerate(labels):
            ttk.Label(frm, text=f"{name} from").grid(row=i, column=0, sticky="e")
            v0 = ttk.Entry(frm, width=6); v0.grid(row=i, column=1)
            ttk.Label(frm, text="to").grid(row=i, column=2)
            v1 = ttk.Entry(frm, width=6); v1.grid(row=i, column=3)
            ttk.Label(frm, text="step").grid(row=i, column=4)
            v2 = ttk.Entry(frm, width=6); v2.grid(row=i, column=5)
            self.vars[name] = (v0, v1, v2)

        # Control buttons
        btns = ttk.Frame(frm); btns.grid(row=len(labels), column=0, columnspan=6, pady=10)
        ttk.Button(btns, text="Run", command=self._on_run).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="left", padx=5)

    def _on_run(self):
        try:
            grid = {}
            for key, (e0,e1,e2) in self.vars.items():
                start = float(e0.get()); end = float(e1.get()); step = float(e2.get())
                grid_key = {
                    "DTE":                   "dte_target",
                    "Alloc %":              "allocation_pct",
                    "Profit Target %":      "profit_target_pct",
                    "Stop Loss ×":          "stop_loss_mult"
                }[key]
                grid[grid_key] = list(np.arange(start, end + 1e-9, step))
            self.controller._start_optimization(grid)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Input Error", str(e), parent=self)
