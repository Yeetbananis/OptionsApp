import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates
from tkinter import TclError
import matplotlib.ticker as mticker
from PIL import Image, ImageTk
from io import BytesIO


class MockFinancialDataAPI:
    """A mock API to simulate fetching financial data with more detail."""
    def get_stock_details(self, ticker):
        price = np.random.uniform(50, 500)
        prev_close = price * (1 + np.random.uniform(-0.05, 0.05))
        # Mock factor exposures (should sum to 1)
        factors = {"Value": np.random.uniform(0,1), "Growth": np.random.uniform(0,1), "Quality": np.random.uniform(0,1)}
        total_factor = sum(factors.values())
        factors = {k: v/total_factor for k,v in factors.items()}
        # Simple mock logo URLs using a free service (replace with a real API key for production)
        # This uses clearbit's free logo API which works well for known companies.
        domain_map = {"AAPL": "apple.com", "MSFT": "microsoft.com", "NVDA": "nvidia.com", "GOOGL": "google.com", "TSLA": "tesla.com"}
        logo_url = f"https://logo.clearbit.com/{domain_map.get(ticker, 'tk.com')}" # fallback to a generic logo

        return {
            "symbol": ticker,
            "shortName": f"{ticker.capitalize()} Inc.",
            "regularMarketPrice": price,
            "previousClose": prev_close,
            "marketCap": np.random.randint(1e9, 2e12, dtype=np.int64),
            "trailingPE": np.random.uniform(10, 30),
            "dividendYield": np.random.uniform(0.005, 0.03),
            "sector": np.random.choice(["Technology", "Healthcare", "Financials", "Industrials", "Consumer Discretionary"]),
            "beta": np.random.uniform(0.5, 1.8),
            "interest_rate_sensitivity": np.random.uniform(-0.5, 0.2), # Mock sensitivity to rate changes
            "factor_exposures": factors,
            "logo_url": logo_url
        }

    def get_benchmark_details(self, ticker="SPY"):
        """Returns data for a benchmark ETF."""
        return {
            "symbol": ticker,
            "trailingPE": 21.5, # Realistic P/E for S&P 500
            "dividendYield": 0.015 # Realistic yield for S&P 500
        }

class DataManager:
    """Handles fetching and caching historical data."""
    def __init__(self, api):
        self.api = api
        self.history_cache = {}

    def get_portfolio_history(self, portfolio, start_date, end_date):
        # This is a mock implementation. In a real app, this would
        # fetch historical price data for each stock and calculate daily portfolio values.
        # For now, we'll generate a simple random walk.
        if start_date is None:
            days = 365 * 5
            start_date = datetime.now() - timedelta(days=days)
        else:
            days = (end_date - start_date).days

        dates = pd.date_range(start=start_date, end=end_date)
        
        total_value = sum(pos["shares"] * self.api.get_stock_details(pos["symbol"])['regularMarketPrice'] for pos in portfolio['positions'])
        if total_value == 0:
            return pd.DataFrame(columns=['value'])
            
        # Simulate a random walk for the portfolio value
        returns = np.random.normal(loc=0.0005, scale=0.015, size=len(dates))
        price_path = np.cumprod(1 + returns)
        
        # Start the path from a value that ends near the current total_value
        initial_value = total_value / price_path[-1]
        
        history_df = pd.DataFrame(initial_value * price_path, index=dates, columns=['value'])
        return history_df
    
import multiprocessing

# --- Main Portfolio Application ---
class PortfolioApp(tk.Tk):
    """
    A standalone portfolio application with a professional, modern UI.
    Designed to be isolated from the main app, maintaining all original features with an enhanced look.
    """
    def __init__(self, theme_name='dark'):
        super().__init__()
        self.api = MockFinancialDataAPI()
        self.data_manager = DataManager(self.api)
        # self.is_first_analysis_draw = True # REMOVED: This flag is no longer needed.

        # --- DYNAMIC THEME DEFINITION ---
        self.themes = {
            "dark": {
                "bg": "#1a1a1a", "card": "#252525", "sidebar": "#141414",
                "text": "#d9d9d9", "secondary_text": "#8a8a8a", "accent": "#00aaff",
                "positive": "#00cc66", "negative": "#ff4444", "border": "#404040"
            },
            "light": {
                "bg": "#f0f0f0", "card": "#ffffff", "sidebar": "#e5e5e5",
                "text": "#1a1a1a", "secondary_text": "#555555", "accent": "#0078d4",
                "positive": "#00994d", "negative": "#d32f2f", "border": "#cccccc"
            }
        }
        
        # Select the active theme colors
        active_theme = self.themes.get(theme_name, self.themes['dark']) # Default to dark if theme name is invalid
        self.BG_COLOR = active_theme["bg"]
        self.CARD_COLOR = active_theme["card"]
        self.SIDEBAR_COLOR = active_theme["sidebar"]
        self.TEXT_COLOR = active_theme["text"]
        self.SECONDARY_TEXT = active_theme["secondary_text"]
        self.ACCENT_COLOR = active_theme["accent"]
        self.POSITIVE_COLOR = active_theme["positive"]
        self.NEGATIVE_COLOR = active_theme["negative"]
        self.BORDER_COLOR = active_theme["border"]
        
        # --- Window Configuration ---
        self.title("Portfolio Analytics Pro")
        self.geometry("1600x1000")
        self.minsize(1400, 900)
        self.configure(bg=self.BG_COLOR)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Data Storage ---
        self.portfolio = {"positions": [], "goals": []}
        self.view_cache = {}
        self.tax_sim_entries = {}
        self.market_data_cache = {}
        self.analysis_data = {} 
        self.logo_cache = {} 
        self.active_view_key = None
        self.sidebar_buttons = {}
        self.chart_hover_elements = {}
        self.pie_wedges = []
        self.pie_annot = None
        self.sector_details = {}
        self.active_timeframe = "6M"
        self.goal_simulation_results = {}
        
        # --- Dashboard Radar Chart State ---
        self.radar_fig_dash, self.radar_ax_dash = None, None
        self.radar_canvas_dash = None
        self.radar_annot_dash = None
        self.radar_data_dash = {}
        self.radar_plot_data_dash = {}

        # --- Analysis Radar Chart State ---
        self.radar_fig_analysis, self.radar_ax_analysis = None, None
        self.radar_canvas_analysis = None
        self.radar_annot_analysis = None
        self.radar_data_analysis = {}
        self.radar_plot_data_analysis = {}

        self.is_initial_dashboard_draw_pending = True
        self.has_built_analysis_tab = False
        self.update_job_id = None
        self.goal_analysis_data = {}

        self.chart_hover_line = None
        self.chart_hover_text = None
        self.warning_icon = None

        # --- FIX: Get screen DPI for consistent chart scaling ---
        try:
            self.dpi = self.winfo_fpixels('1i')
        except tk.TclError:
            self.dpi = 96 

        # --- Create all figures with synchronized DPI and explicit padding ---
        self.fig_dash, self.ax_dash = plt.subplots(dpi=self.dpi)
        self.fig_dash.subplots_adjust(left=0.12, right=0.98, top=0.92, bottom=0.18)
        
        self.fig_pie, self.ax_pie = plt.subplots(dpi=self.dpi)
        self.radar_fig_analysis, self.radar_ax_analysis = plt.subplots(dpi=self.dpi)
        self.fig_risk, self.ax_risk = plt.subplots(dpi=self.dpi)
        self.fig_corr, self.ax_corr = plt.subplots(dpi=self.dpi)
        self.fig_attr, self.ax_attr = plt.subplots(dpi=self.dpi)
        
        self.fig_stress, self.ax_stress = plt.subplots(dpi=self.dpi)
        # This pre-allocates space for the Stress Test's two-line title.
        self.fig_stress.subplots_adjust(left=0.1, right=0.98, top=0.88, bottom=0.15)

        self.fig_interactive, self.ax_interactive = plt.subplots(dpi=self.dpi)
        self.fig_breakdown, self.ax_breakdown = plt.subplots(dpi=self.dpi)
        self.fig_dist, self.ax_dist = plt.subplots(dpi=self.dpi)
        self.radar_fig_dash, self.radar_ax_dash = plt.subplots(dpi=self.dpi)


        # --- Build UI ---
        self._build_styles()
        self._build_main_layout()
        self.show_view("dashboard")

        self.load_portfolio_data()
        self._load_warning_icon()
        self.start_periodic_updates()

    
    def on_closing(self):
        """Ensure clean shutdown by canceling pending jobs."""
        if self.update_job_id:
            self.after_cancel(self.update_job_id)
        self.destroy()

    def _setup_matplotlib_style(self, fig, ax):
        """
        A centralized function to apply the correct theme to any Matplotlib figure and axes.
        This version is robust and handles both standard and polar (radar) charts.
        """
        fig.patch.set_facecolor(self.CARD_COLOR)
        
        # This function now handles both single axes objects and arrays of them
        axes_list = ax.flatten() if isinstance(ax, np.ndarray) else [ax]

        for subplot in axes_list:
            subplot.patch.set_facecolor(self.CARD_COLOR)
            
            # --- THE KEY FIX ---
            # Check if the 'top' spine exists. This is True for standard plots and False for polar plots.
            if 'top' in subplot.spines: 
                subplot.spines['top'].set_visible(False)
                subplot.spines['right'].set_visible(False)
                subplot.spines['left'].set_color(self.BORDER_COLOR)
                subplot.spines['bottom'].set_color(self.BORDER_COLOR)
            
            # This is safe for all plot types
            subplot.tick_params(colors=self.SECONDARY_TEXT)

    def _build_styles(self):
        """Define consistent, professional styles with smaller, denser fonts."""
        style = ttk.Style(self)
        style.theme_use('clam')

        # --- Font sizes ---
        self.FONT_NORMAL = ("Calibri", 10)
        self.FONT_BOLD = ("Calibri", 10, "bold")
        self.FONT_HEADER = ("Calibri", 14, "bold")
        self.FONT_TITLE = ("Calibri", 20, "bold")
        self.FONT_KPI = ("Calibri", 24, "bold")
        self.FONT_SIDEBAR = ("Calibri", 12)

        # --- General Styles ---
        style.configure("TFrame", background=self.BG_COLOR)
        style.configure("Card.TFrame", background=self.CARD_COLOR, relief="flat", borderwidth=1, bordercolor=self.BORDER_COLOR)
        style.configure("Sidebar.TFrame", background=self.SIDEBAR_COLOR)
        style.configure("Green.Horizontal.TProgressbar", background=self.POSITIVE_COLOR)

        # --- Labels ---
        style.configure("TLabel", background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=self.FONT_NORMAL)
        style.configure("Header.TLabel", font=self.FONT_HEADER, foreground=self.TEXT_COLOR)
        style.configure("Title.TLabel", font=self.FONT_TITLE)
        style.configure("Secondary.TLabel", foreground=self.SECONDARY_TEXT)
        style.configure("KPI.TLabel", font=self.FONT_KPI)

        # --- Buttons ---
        style.configure("TButton", font=self.FONT_BOLD, padding=8, background=self.CARD_COLOR, foreground=self.TEXT_COLOR, relief="flat")
        style.map("TButton", background=[('active', '#333333')], foreground=[('active', self.TEXT_COLOR)])
        style.configure("Accent.TButton", background=self.ACCENT_COLOR, foreground="#ffffff")
        style.map("Accent.TButton", background=[('active', '#0088cc')])

        # --- Timeframe Buttons (New) ---
        style.configure("Timeframe.TButton", font=self.FONT_NORMAL, padding=(8, 4), background=self.CARD_COLOR, foreground=self.SECONDARY_TEXT, relief="flat")
        style.map("Timeframe.TButton", background=[('active', '#333333')])
        style.configure("ActiveTimeframe.TButton", font=self.FONT_BOLD, padding=(8, 4), background=self.BG_COLOR, foreground=self.TEXT_COLOR, relief="flat")

        # --- Treeview ---
        style.configure("Treeview", background=self.CARD_COLOR, foreground=self.TEXT_COLOR, fieldbackground=self.CARD_COLOR, font=self.FONT_NORMAL, rowheight=30)
        style.configure("Treeview.Heading", background=self.BORDER_COLOR, foreground=self.TEXT_COLOR, font=self.FONT_BOLD, padding=6)
        style.map("Treeview", background=[('selected', '#333333')])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

    def _build_main_layout(self):
        """Construct the main layout with sidebar and content area."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar ---
        sidebar = ttk.Frame(self, style="Sidebar.TFrame", width=250)
        sidebar.grid(row=0, column=0, sticky="ns", padx=(0, 1))
        sidebar.grid_propagate(False)

        ttk.Label(sidebar, text="Portfolio Pro", style="Header.TLabel", background=self.SIDEBAR_COLOR).pack(pady=(20, 30))

        menu_items = {
            "dashboard": ("📈", "Dashboard"),
            "goals": ("🎯", "Goals"),
            "analysis": ("🔍", "Analysis"),
            "tax": ("💰", "Tax")
        }
        for key, (icon, text) in menu_items.items():
            btn_frame = ttk.Frame(sidebar, style="Sidebar.TFrame")
            btn_frame.pack(fill="x", pady=5, padx=10)
            indicator = ttk.Frame(btn_frame, width=4, style="AccentIndicator.TFrame")
            icon_lbl = ttk.Label(btn_frame, text=icon, font=("Helvetica", 16), background=self.SIDEBAR_COLOR)
            text_lbl = ttk.Label(btn_frame, text=text, style="Sidebar.TButton")
            icon_lbl.pack(side="left", padx=(10, 10))
            text_lbl.pack(side="left")
            for widget in (btn_frame, icon_lbl, text_lbl):
                widget.bind("<Button-1>", lambda e, k=key: self.show_view(k))
            self.sidebar_buttons[key] = {"frame": btn_frame, "indicator": indicator, "text": text_lbl, "icon": icon_lbl}

        # --- Main Content ---
        self.content_frame = ttk.Frame(self, padding=20)
        self.content_frame.grid(row=0, column=1, sticky="nsew")
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)

    def _build_hero_snapshot_card(self, parent):
        """Builds the new primary KPI 'hero' card for the dashboard."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=(25, 20))
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        # Main Portfolio Value
        ttk.Label(card, text="Total Portfolio Value", style="Secondary.TLabel", background=self.CARD_COLOR).pack(anchor="w")
        self.hero_total_value = ttk.Label(card, text="$0.00", font=("Calibri", 36, "bold"), background=self.CARD_COLOR, foreground=self.TEXT_COLOR)
        self.hero_total_value.pack(anchor="w", pady=(0, 2))

        # Daily Change
        self.hero_day_change = ttk.Label(card, text="+$0.00 (+0.00%)", font=("Calibri", 14), background=self.CARD_COLOR)
        self.hero_day_change.pack(anchor="w")

        return card

    def _update_dashboard_kpis(self):
        """Updates the new hero snapshot KPI values."""
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", pos["entry_price"]) for pos in self.portfolio["positions"])
        
        # Calculate daily change more robustly
        previous_day_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("previousClose", pos["entry_price"]) for pos in self.portfolio["positions"])
        day_change_usd = total_value - previous_day_value
        day_change_pct = (day_change_usd / previous_day_value * 100) if previous_day_value > 0 else 0
        
        # Update hero labels
        self.hero_total_value.config(text=f"${total_value:,.2f}")
        self.hero_day_change.config(
            text=f"${day_change_usd:+,.2f} ({day_change_pct:+.2f}%) Today",
            foreground=self.POSITIVE_COLOR if day_change_usd >= 0 else self.NEGATIVE_COLOR
        )

    def _create_timeframe_selector(self, parent):
        """Creates the timeframe button group for the history chart."""
        frame = ttk.Frame(parent, style="Card.TFrame")
        self.timeframe_buttons = {}
        timeframes = ["1M", "6M", "1Y", "5Y", "ALL"]

        for i, tf in enumerate(timeframes):
            btn = ttk.Button(
                frame,
                text=tf,
                style="ActiveTimeframe.TButton" if tf == self.active_timeframe else "Timeframe.TButton",
                command=lambda t=tf: self._set_timeframe(t)
            )
            btn.grid(row=0, column=i, padx=(2, 0))
            self.timeframe_buttons[tf] = btn
            
        return frame

    def _set_timeframe(self, timeframe):
        """Callback to set the active timeframe and replot the chart."""
        self.active_timeframe = timeframe
        
        # Update button styles
        for tf, btn in self.timeframe_buttons.items():
            style = "ActiveTimeframe.TButton" if tf == timeframe else "Timeframe.TButton"
            btn.configure(style=style)
            
        # Re-plot the history chart with the new timeframe
        self._plot_history_area_chart(timeframe)

    def show_view(self, view_key):
        """
        REWRITTEN: Switches views using a caching mechanism to prevent layout
        instability. The view is built only once and then hidden/shown,
        preserving the layout perfectly.
        """
        # --- 1. Hide the currently active view (if one exists) ---
        if hasattr(self, 'active_view') and self.active_view:
            self.active_view.grid_forget()

        self.active_view_key = view_key

        # --- 2. Update the sidebar UI to highlight the correct button ---
        for key, btn in self.sidebar_buttons.items():
            is_active = key == view_key
            # Use a simpler background color change for the active frame
            btn["frame"].configure(style="Card.TFrame" if is_active else "Sidebar.TFrame")
            btn["text"].configure(foreground=self.TEXT_COLOR if is_active else self.SECONDARY_TEXT)
            btn["icon"].configure(foreground=self.TEXT_COLOR if is_active else self.SECONDARY_TEXT)
            if is_active:
                btn["indicator"].pack(side="left", fill="y", before=btn["icon"])
            else:
                btn["indicator"].pack_forget()

        # --- 3. Show the new view, building it only if it's not in the cache ---
        if view_key in self.view_cache:
            self.active_view = self.view_cache[view_key]
            self.active_view.grid(row=0, column=0, sticky="nsew")
        else:
            # If view is not cached, build it for the first time
            views = {
                "dashboard": self._build_dashboard_view,
                "goals": self._build_goals_view,
                "analysis": self._build_analysis_view,
                "tax": self._build_tax_view
            }
            # Create the new view and store it in the cache
            new_view = views[view_key](self.content_frame)
            self.view_cache[view_key] = new_view
            self.active_view = new_view
            self.active_view.grid(row=0, column=0, sticky="nsew")

        # --- 4. Trigger a data refresh for the now-visible view ---
        # This ensures the data is current without rebuilding the layout.
        self.after(50, self._update_all_views)

    # --- View Builders ---
    def _build_dashboard_view(self, parent):
        """Builds the professional 'Command Center' dashboard view."""
        view = ttk.Frame(parent)
        view.columnconfigure(0, weight=7)
        view.columnconfigure(1, weight=3)
        view.rowconfigure(1, weight=1)

        header = ttk.Frame(view)
        header.grid(row=0, column=0, columnspan=2, pady=(0, 25), sticky="ew")
        ttk.Label(header, text="Dashboard Overview", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Add Position", style="Accent.TButton", command=self._open_add_position_dialog).pack(side="right")

        primary_col = ttk.Frame(view)
        primary_col.grid(row=1, column=0, sticky="nsew", padx=(0, 20))
        primary_col.rowconfigure(1, weight=5)
        primary_col.rowconfigure(2, weight=4)
        primary_col.columnconfigure(0, weight=1)

        self._build_hero_snapshot_card(primary_col)

        # Performance Chart Card
        chart_card = ttk.Frame(primary_col, style="Card.TFrame", padding=20)
        chart_card.grid(row=1, column=0, sticky="nsew", pady=20)
        chart_card.rowconfigure(1, weight=1)
        chart_card.columnconfigure(0, weight=1)
        chart_header = ttk.Frame(chart_card, style="Card.TFrame")
        chart_header.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        ttk.Label(chart_header, text="Performance History", style="Header.TLabel", background=self.CARD_COLOR).pack(side="left")
        self.timeframe_selector = self._create_timeframe_selector(chart_header)
        self.timeframe_selector.pack(side="right")
        self.canvas_dash = FigureCanvasTkAgg(self.fig_dash, chart_card)
        self.canvas_dash.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self._setup_chart_hover()

        # --- THIS IS THE FIX ---
        # Call the dedicated builder for our new custom positions card.
        # This was the missing link causing the table to be empty.
        self._build_positions_card(primary_col)
        # --- END OF FIX ---

        secondary_col = ttk.Frame(view)
        secondary_col.grid(row=1, column=1, sticky="nsew")
        secondary_col.rowconfigure(0, weight=1)
        secondary_col.rowconfigure(1, weight=1)
        secondary_col.columnconfigure(0, weight=1)

        # Allocation Chart Card
        pie_card = ttk.Frame(secondary_col, style="Card.TFrame", padding=20)
        pie_card.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        pie_card.rowconfigure(1, weight=1)
        pie_card.columnconfigure(0, weight=1)
        ttk.Label(pie_card, text="Sector Allocation", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 15))
        self.canvas_pie = FigureCanvasTkAgg(self.fig_pie, pie_card)
        self.canvas_pie.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        # Portfolio DNA Card
        drivers_card = ttk.Frame(secondary_col, style="Card.TFrame", padding=20)
        drivers_card.grid(row=1, column=0, sticky="nsew", pady=10)
        drivers_card.rowconfigure(1, weight=1)
        drivers_card.columnconfigure(0, weight=1)
        ttk.Label(drivers_card, text="Portfolio DNA", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.radar_canvas_dash = FigureCanvasTkAgg(self.radar_fig_dash, drivers_card)
        self.radar_canvas_dash.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self.radar_canvas_dash.mpl_connect('motion_notify_event', self._on_radar_hover_dash)
        self.radar_canvas_dash.mpl_connect('axes_leave_event', self._on_radar_leave_dash)

        self._update_dashboard_drivers_card()

        return view
        

    def _initial_dashboard_draw(self, event):
        """
        A one-time event handler for the <Map> event. This robustly ensures
        the initial draw happens only after the UI is visible and has its
        correct final size, preventing the "zoomed-in" bug.
        """
        # Unbind immediately to ensure this only ever runs once.
        if event.widget == self.active_view:
            event.widget.unbind("<Map>")
            
            # Now that the frame is guaranteed to be mapped with its final size,
            # trigger the first draw.
            self._update_dashboard_drivers_card()
            
            # FIX: Signal that the special initial draw is complete.
            # All subsequent updates will now be handled by the main loop.
            self.is_initial_dashboard_draw_pending = False

    def _build_goals_view(self, parent):
        """Builds a goals view with a fixed-width list and a flexible analysis area."""
        view = ttk.Frame(parent)
        # --- FIX: Define a 2-column grid layout ---
        # Col 0 is for the goals list, with a fixed width.
        # Col 1 is for the analysis, and it will expand to fill the rest of the space.
        view.columnconfigure(0, minsize=570) # Locked width for the goals list adjut this to change ratio
        view.columnconfigure(1, weight=1)   # Flexible width for the analysis
        view.rowconfigure(1, weight=1)

        # --- Header (now spans both columns) ---
        header = ttk.Frame(view)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 20))
        ttk.Label(header, text="Financial Goals", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Add Goal", style="Accent.TButton", command=self._open_add_goal_dialog).pack(side="right")

        # --- Left Pane: Scrollable Goal Cards (placed in column 0) ---
        goals_list_frame = ttk.Frame(view)
        goals_list_frame.grid(row=1, column=0, sticky="nsew")
        
        canvas = tk.Canvas(goals_list_frame, bg=self.BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(goals_list_frame, orient="vertical", command=canvas.yview)
        self.goals_container = ttk.Frame(canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        canvas.create_window((0, 0), window=self.goals_container, anchor="nw")
        
        # This binding ensures the scrollable area resizes correctly with its content
        self.goals_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        # FIX: Bind scroll events locally to the canvas, not globally to the app.
        # This prevents the "invalid command name" error when switching views.
        canvas.bind("<MouseWheel>", lambda e, c=canvas: self._on_mousewheel(e, c))
        canvas.bind("<Button-4>", lambda e, c=canvas: self._on_mousewheel(e, c))
        canvas.bind("<Button-5>", lambda e, c=canvas: self._on_mousewheel(e, c))

        # --- Right Pane: Goal Analysis Area (placed in column 1) ---
        self.analysis_frame = ttk.Frame(view, style="Card.TFrame")
        self.analysis_frame.grid(row=1, column=1, sticky="nsew", padx=(20, 0)) # Add left padding for separation
        
        self.analysis_frame.columnconfigure(0, weight=1)
        self.analysis_frame.rowconfigure(1, weight=1)
        self.analysis_placeholder = ttk.Label(self.analysis_frame, text="Run a simulation to view its analysis here.", style="Header.TLabel", justify="center", background=self.CARD_COLOR)
        self.analysis_placeholder.pack(expand=True)
        
        return view
    
    def _process_portfolio_data(self):
        """
        The single source of truth for calculating all derived portfolio data.
        This is called after market data is fetched but before the UI is updated.
        """
        if not self.portfolio["positions"]:
            self.analysis_data = {}
        else:
            # Generate mock returns and calculate all analytics
            self.analysis_data['returns'] = self._generate_mock_historical_returns()
            self.analysis_data['analytics'] = self._calculate_portfolio_analytics(self.analysis_data['returns'])

        # --- Analysis Lab: Final Enhanced Methods ---
    # Replace the entire block of analysis methods in your file with this one.
    # This includes _build_analysis_view and all its helpers.

    def _build_analysis_view(self, parent):
        """
        Builds a completely revamped and professional Analysis Lab with advanced tools.
        """
        self.has_built_analysis_tab = True

        view = ttk.Frame(parent)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(1, weight=1)

        # --- Header ---
        header = ttk.Frame(view)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ttk.Label(header, text="Analysis Lab", style="Title.TLabel").pack(side="left")

        # --- Notebook for different analysis tools ---
        notebook = ttk.Notebook(view)
        notebook.grid(row=1, column=0, sticky="nsew")
        style = ttk.Style()
        style.configure("TNotebook", background=self.BG_COLOR, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.CARD_COLOR, padding=(12, 6), font=self.FONT_BOLD, borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", self.BG_COLOR)],
                  foreground=[("selected", self.ACCENT_COLOR)],
                  expand=[("selected", [1, 1, 1, 0])])

        # --- Create and add the tabs ---
        self.drivers_tab = self._create_key_drivers_tab(notebook)
        self.risk_tab = self._create_risk_volatility_tab(notebook)
        self.correlation_tab = self._create_correlation_tab(notebook)
        self.attribution_tab = self._create_attribution_tab(notebook)
        self.stress_test_tab = self._create_stress_test_tab(notebook)

        notebook.add(self.drivers_tab, text="Key Drivers")
        notebook.add(self.risk_tab, text="Risk & Volatility")
        notebook.add(self.correlation_tab, text="Correlation")
        notebook.add(self.attribution_tab, text="Attribution")
        notebook.add(self.stress_test_tab, text="Stress Tests")

         # --- FIX: Connect events to the dedicated 'analysis' canvas ---
        self.radar_canvas_analysis.mpl_connect('motion_notify_event', self._on_radar_hover)
        self.radar_canvas_analysis.mpl_connect('axes_leave_event', self._on_radar_leave)
        
        self.after(50, self._update_analysis_view_data)

        return view
    
    def _create_key_drivers_tab(self, parent_notebook):
        """Creates the UI for the Key Drivers tab with benchmark comparisons and a treemap."""
        tab = ttk.Frame(parent_notebook, padding=15)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        kpi_frame = ttk.Frame(tab)
        kpi_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        kpi_frame.columnconfigure((0, 1, 2), weight=1)
        
        self.drivers_kpi_pe, self.drivers_kpi_pe_bench = self._create_kpi_card_with_benchmark(kpi_frame, "Portfolio P/E Ratio", "...", 0)
        self.drivers_kpi_yield, self.drivers_kpi_yield_bench = self._create_kpi_card_with_benchmark(kpi_frame, "Portfolio Dividend Yield", "...", 1)
        self.drivers_kpi_beta = self._create_kpi_card(kpi_frame, "Portfolio Beta", "...", 2)

        chart_card = ttk.Frame(tab, style="Card.TFrame", padding=20)
        chart_card.grid(row=1, column=0, sticky="nsew")
        chart_card.columnconfigure(0, weight=1)
        chart_card.rowconfigure(1, weight=1)
        
        ttk.Label(chart_card, text="Factor Exposure", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 10))

        # --- FIX: Use the dedicated 'analysis' canvas and figure ---
        self.radar_canvas_analysis = FigureCanvasTkAgg(self.radar_fig_analysis, chart_card)
        self.radar_canvas_analysis.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        return tab
    
    def _create_risk_volatility_tab(self, parent_notebook):
        """Creates the UI for the Risk & Volatility tab with VaR."""
        tab = ttk.Frame(parent_notebook, padding=15)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)
        
        kpi_frame = ttk.Frame(tab)
        kpi_frame.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        kpi_frame.columnconfigure((0, 1, 2), weight=1)
        self.risk_kpi_vol = self._create_kpi_card(kpi_frame, "Annualized Volatility", "...", 0)
        self.risk_kpi_sharpe = self._create_kpi_card(kpi_frame, "Sharpe Ratio", "...", 1)
        self.risk_kpi_var = self._create_kpi_card(kpi_frame, "Value at Risk (95%, 1-day)", "...", 2)

        chart_card = ttk.Frame(tab, style="Card.TFrame", padding=20)
        chart_card.grid(row=1, column=0, sticky="nsew", pady=(0, 15))
        chart_card.columnconfigure(0, weight=1)
        chart_card.rowconfigure(1, weight=1)
        ttk.Label(chart_card, text="1-Year Rolling Volatility vs. Benchmark (S&P 500)", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self.canvas_risk = FigureCanvasTkAgg(self.fig_risk, chart_card)
        self.canvas_risk.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        
        return tab

    def _create_correlation_tab(self, parent_notebook):
        """Creates the UI for the Correlation Matrix tab with Diversification Score."""
        tab = ttk.Frame(parent_notebook, padding=15)
        tab.columnconfigure(0, weight=2)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        kpi_frame = ttk.Frame(tab)
        kpi_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 15))
        kpi_frame.columnconfigure(0, weight=1)
        self.corr_kpi_score = self._create_kpi_card(kpi_frame, "Portfolio Diversification Score", "...", 0)

        chart_card = ttk.Frame(tab, style="Card.TFrame", padding=20)
        chart_card.grid(row=1, column=0, sticky="nsew", padx=(0, 15))
        chart_card.columnconfigure(0, weight=1)
        chart_card.rowconfigure(0, weight=1)
        self.canvas_corr = FigureCanvasTkAgg(self.fig_corr, chart_card)
        self.canvas_corr.get_tk_widget().pack(fill="both", expand=True)
        self.cbar_corr = None

        summary_card = ttk.Frame(tab, style="Card.TFrame", padding=20)
        summary_card.grid(row=1, column=1, sticky="nsew")
        ttk.Label(summary_card, text="Correlation Insights", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w")
        self.corr_summary_text = tk.Text(summary_card, wrap="word", height=10, bg=self.CARD_COLOR, fg=self.TEXT_COLOR, font=self.FONT_NORMAL, relief="flat", highlightthickness=0, borderwidth=0)
        self.corr_summary_text.pack(fill="both", expand=True, pady=(10, 0))
        self.corr_summary_text.tag_configure("bold", font=self.FONT_BOLD)
        self.corr_summary_text.tag_configure("good", foreground=self.POSITIVE_COLOR)
        self.corr_summary_text.tag_configure("bad", foreground=self.NEGATIVE_COLOR)
        self.corr_summary_text.tag_configure("heading", font=self.FONT_BOLD, foreground=self.ACCENT_COLOR)

        return tab

    def _create_stress_test_tab(self, parent_notebook):
        """Creates the UI for the Stress Testing tab with corrected slider ranges."""
        tab = ttk.Frame(parent_notebook, padding=15)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(3, weight=1)

        # --- Historical Scenarios (No changes here) ---
        hist_frame = ttk.Frame(tab, style="Card.TFrame", padding=15)
        hist_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        ttk.Label(hist_frame, text="Historical Scenarios", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w", pady=(0, 10))
        
        hist_controls = ttk.Frame(hist_frame, style="Card.TFrame")
        hist_controls.pack(fill="x")
        ttk.Label(hist_controls, text="Select Scenario:", style="Secondary.TLabel", background=self.CARD_COLOR).pack(side="left", padx=(0, 10))
        self.scenario_var = tk.StringVar(value="2008 Financial Crisis")
        scenario_menu = ttk.Combobox(hist_controls, textvariable=self.scenario_var,
                                     values=["2008 Financial Crisis", "2020 COVID Crash", "Dot-com Burst"],
                                     state="readonly", font=self.FONT_NORMAL)
        scenario_menu.pack(side="left", fill="x", expand=True)
        scenario_menu.bind("<<ComboboxSelected>>", self._update_stress_test_view)

        # --- Custom Scenarios with Corrected Sliders ---
        custom_frame = ttk.Frame(tab, style="Card.TFrame", padding=15)
        custom_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        ttk.Label(custom_frame, text="Custom Scenario Builder", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w", pady=(0, 15))
        
        custom_controls = ttk.Frame(custom_frame, style="Card.TFrame")
        custom_controls.pack(fill="x", expand=True)
        custom_controls.columnconfigure((0, 1), weight=1)
        custom_controls.columnconfigure(2, weight=0)

        # Create the sliders with the new, corrected ranges
        self.custom_shock_var = self._create_custom_scenario_slider(custom_controls, "Market Shock", -100.0, 0.0, -15.0, 0, format_str="{:.1f}%")
        self.custom_rate_var = self._create_custom_scenario_slider(custom_controls, "Rate Shock", -5.0, 5.0, 0.5, 1, format_str="{:+.1f}%")

        run_btn = ttk.Button(custom_controls, text="Run Custom", style="Accent.TButton", command=self._run_custom_stress_test)
        run_btn.grid(row=0, column=2, sticky="e", padx=(20,0))
        
        # --- KPI Cards and Chart (No changes here) ---
        kpi_frame = ttk.Frame(tab)
        kpi_frame.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        kpi_frame.columnconfigure((0, 1, 2), weight=1)
        self.stress_kpi_loss_usd = self._create_kpi_card(kpi_frame, "Estimated Max Loss ($)", "...", 0)
        self.stress_kpi_loss_pct = self._create_kpi_card(kpi_frame, "Estimated Max Loss (%)", "...", 1)
        self.stress_kpi_recovery = self._create_kpi_card(kpi_frame, "Est. Recovery Time", "...", 2)

        chart_card = ttk.Frame(tab, style="Card.TFrame", padding=20)
        chart_card.grid(row=3, column=0, sticky="nsew")
        chart_card.columnconfigure(0, weight=1)
        chart_card.rowconfigure(0, weight=1)
        self.canvas_stress = FigureCanvasTkAgg(self.fig_stress, chart_card)
        self.canvas_stress.get_tk_widget().pack(fill="both", expand=True)

        return tab


    def _create_attribution_tab(self, parent_notebook):
        """Creates the UI for the enhanced Performance Attribution tab."""
        tab = ttk.Frame(parent_notebook, padding=15)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        ttk.Label(tab, text="Contribution to 1-Year Return", style="Header.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        
        chart_card = ttk.Frame(tab, style="Card.TFrame", padding=20)
        chart_card.grid(row=1, column=0, sticky="nsew")
        chart_card.columnconfigure(0, weight=1)
        chart_card.rowconfigure(0, weight=1)
        self.canvas_attr = FigureCanvasTkAgg(self.fig_attr, chart_card)
        self.canvas_attr.get_tk_widget().pack(fill="both", expand=True)
        
        return tab

    def _update_dashboard_drivers_card(self):
        """
        REWRITTEN: Populates the Key Drivers card on the dashboard with a simplified,
        interactive radar chart showing the portfolio's 'DNA'.
        """
        if not hasattr(self, 'radar_canvas_dash') or not self.radar_canvas_dash:
            return

        fig = self.radar_fig_dash
        fig.clear() # Clear the whole figure for polar projection

        analytics = self.analysis_data.get('analytics', {})
        fundamentals = analytics.get('fundamentals', {})


        if not self.portfolio["positions"] or not analytics:
            ax = fig.add_subplot(111)
            self._setup_matplotlib_style(fig, ax)
            ax.text(0.5, 0.5, "Add positions\nto see drivers", ha='center', va='center', color=self.TEXT_COLOR)
            ax.axis('off')
            self.radar_canvas_dash.draw()
            return

        # --- Data Prep (No Changes Here) ---
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
        pos_values = {p["symbol"]: p["shares"] * self.market_data_cache.get(p["symbol"], {}).get("regularMarketPrice", 0) for p in self.portfolio["positions"]}
        top_holding_pct = max(pos_values.values()) / total_value if total_value else 0
        sector_values = {}
        for pos in self.portfolio["positions"]:
            sector = self.market_data_cache.get(pos["symbol"], {}).get("sector", "Other")
            sector_values[sector] = sector_values.get(sector, 0) + pos_values[pos["symbol"]]
        top_sector_pct = max(sector_values.values()) / total_value if total_value else 0
        factors = fundamentals.get('factor_exposures', {"Growth": 0, "Value": 0, "Quality": 0})
        portfolio_dna_raw = {
            'Concentration': (top_holding_pct + top_sector_pct) / 2,
            'Growth': factors.get('Growth', 0),
            'Value': factors.get('Value', 0),
            'Quality': factors.get('Quality', 0),
            'Risk (Beta)': analytics.get('beta', 0)
        }
        labels = list(portfolio_dna_raw.keys())
        self.radar_data_dash = {'labels': labels, 'portfolio': portfolio_dna_raw}
        def normalize(raw_val, min_val, max_val):
            return np.clip((raw_val - min_val) / (max_val - min_val), 0, 1)
        portfolio_dna_norm = [
            normalize(portfolio_dna_raw['Concentration'], 0, 1),
            normalize(portfolio_dna_raw['Growth'], 0, 1),
            normalize(portfolio_dna_raw['Value'], 0, 1),
            normalize(portfolio_dna_raw['Quality'], 0, 1),
            normalize(portfolio_dna_raw['Risk (Beta)'], 0.5, 2.0)
        ]
        num_vars = len(labels)
        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        self.radar_plot_data_dash = {'angles': angles, 'portfolio': portfolio_dna_norm}
        portfolio_dna_norm_closed = portfolio_dna_norm + portfolio_dna_norm[:1]
        angles_closed = angles + angles[:1]

        # --- Plotting & Theming ---
        ax = fig.add_subplot(111, polar=True)
        self._setup_matplotlib_style(fig, ax) # Apply theme AFTER creating polar axes

        ax.fill(angles_closed, portfolio_dna_norm_closed, color=self.ACCENT_COLOR, alpha=0.4)
        ax.plot(angles_closed, portfolio_dna_norm_closed, color=self.ACCENT_COLOR, linewidth=2)

        ax.set_yticklabels([])
        # THEME FIX: Set the color of the labels on the spokes
        ax.set_thetagrids(np.degrees(angles), labels, fontsize=8, color=self.SECONDARY_TEXT)
        ax.grid(color=self.BORDER_COLOR, linestyle='--', linewidth=0.5)
        ax.spines['polar'].set_color(self.BORDER_COLOR)

        fig.tight_layout(pad=0.5)
        self.radar_canvas_dash.draw()

    def _update_key_drivers_view(self):
        """
        REWRITTEN: Creates the 'Portfolio DNA' Radar Chart for the Analysis tab
        using its own dedicated state variables to prevent conflicts with the dashboard.
        """
        # Check for the dedicated 'analysis' objects
        if not hasattr(self, 'radar_fig_analysis') or not self.radar_fig_analysis or not hasattr(self, 'radar_canvas_analysis'):
            return

        self.radar_fig_analysis.clear()

        analytics = self.analysis_data.get('analytics', {})
        fundamentals = analytics.get('fundamentals', {})
        self.drivers_kpi_pe.config(text=f"{fundamentals.get('pe_ratio', 0):.2f}x")
        self.drivers_kpi_pe_bench.config(text=f"vs SPY: {fundamentals.get('benchmark_pe', 0):.2f}x")
        self.drivers_kpi_yield.config(text=f"{fundamentals.get('dividend_yield', 0):.2%}")
        self.drivers_kpi_yield_bench.config(text=f"vs SPY: {fundamentals.get('benchmark_yield', 0):.2%}")
        self.drivers_kpi_beta.config(text=f"{analytics.get('beta', 0):.2f}")

        if not self.portfolio["positions"] or not analytics:
            ax = self.radar_fig_analysis.add_subplot(111)
            self._setup_matplotlib_style(self.radar_fig_analysis, ax)
            ax.text(0.5, 0.5, "Add positions to build Portfolio DNA", ha='center', va='center', transform=ax.transAxes)
            ax.axis('off')
            # Draw on the correct canvas
            self.radar_canvas_analysis.draw()
            return

        # --- Data Prep ---
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
        pos_values = {p["symbol"]: p["shares"] * self.market_data_cache.get(p["symbol"], {}).get("regularMarketPrice", 0) for p in self.portfolio["positions"]}
        top_holding_pct = max(pos_values.values()) / total_value if total_value else 0
        sector_values = {}
        for pos in self.portfolio["positions"]:
            sector = self.market_data_cache.get(pos["symbol"], {}).get("sector", "Other")
            sector_values[sector] = sector_values.get(sector, 0) + pos_values[pos["symbol"]]
        top_sector_pct = max(sector_values.values()) / total_value if total_value else 0
        factors = fundamentals.get('factor_exposures', {"Growth": 0, "Value": 0, "Quality": 0})
        portfolio_dna_raw = {
            'Concentration': (top_holding_pct + top_sector_pct) / 2,
            'Growth': factors.get('Growth', 0),
            'Value': factors.get('Value', 0),
            'Quality': factors.get('Quality', 0),
            'Market Risk (Beta)': analytics.get('beta', 0)
        }
        benchmark_dna_raw = {'Concentration': 0.18, 'Growth': 0.4, 'Value': 0.4, 'Quality': 0.5, 'Market Risk (Beta)': 1.0}
        
        # Store data in dedicated 'analysis' variables
        labels = list(portfolio_dna_raw.keys())
        self.radar_data_analysis = {'labels': labels, 'portfolio': portfolio_dna_raw, 'benchmark': benchmark_dna_raw}
        def normalize(raw_val, min_val, max_val):
            return np.clip((raw_val - min_val) / (max_val - min_val), 0, 1)
        portfolio_dna_norm = [normalize(v, 0.5 if k == 'Market Risk (Beta)' else 0, 2.0 if k == 'Market Risk (Beta)' else 1) for k, v in portfolio_dna_raw.items()]
        benchmark_dna_norm = [normalize(v, 0.5 if k == 'Market Risk (Beta)' else 0, 2.0 if k == 'Market Risk (Beta)' else 1) for k, v in benchmark_dna_raw.items()]
        num_vars = len(labels)
        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        self.radar_plot_data_analysis = {'angles': angles, 'portfolio': portfolio_dna_norm, 'benchmark': benchmark_dna_norm}
        portfolio_dna_norm_closed = portfolio_dna_norm + portfolio_dna_norm[:1]
        benchmark_dna_norm_closed = benchmark_dna_norm + benchmark_dna_norm[:1]
        angles_closed = angles + angles[:1]

        # --- Plotting & Theming ---
        ax = self.radar_fig_analysis.add_subplot(111, polar=True)
        self._setup_matplotlib_style(self.radar_fig_analysis, ax)

        ax.fill(angles_closed, portfolio_dna_norm_closed, color=self.ACCENT_COLOR, alpha=0.4)
        ax.plot(angles_closed, portfolio_dna_norm_closed, color=self.ACCENT_COLOR, linewidth=2, label='Your Portfolio')
        ax.plot(angles_closed, benchmark_dna_norm_closed, color=self.POSITIVE_COLOR, linewidth=2, linestyle='--', label='S&P 500 (Benchmark)')

        ax.set_rlabel_position(0)
        ax.set_thetagrids(np.degrees(angles), labels, color=self.SECONDARY_TEXT)
        ax.set_yticklabels([])
        ax.grid(color=self.BORDER_COLOR, linestyle='--', linewidth=0.5)
        ax.spines['polar'].set_color(self.BORDER_COLOR)
        legend = ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.1), facecolor=self.CARD_COLOR, edgecolor=self.BORDER_COLOR)
        for text in legend.get_texts():
            text.set_color(self.TEXT_COLOR)

        self.radar_fig_analysis.suptitle("Portfolio DNA vs. Benchmark", fontsize=16, y=0.98, color=self.TEXT_COLOR, fontweight='bold')
        ax.set_title("Hover over a point to see detailed values.", fontsize=9, color=self.SECONDARY_TEXT, pad=20)

        # Draw the dedicated 'analysis' canvas
        self.radar_canvas_analysis.draw()

    
    def _on_radar_hover(self, event):
        """
        Handles hover events for the ANALYSIS chart with a robust,
        distance-based detection system using isolated state variables.
        """
        # Use dedicated 'analysis' variables throughout
        if not self.radar_fig_analysis or not event.inaxes or not self.radar_plot_data_analysis:
            self._on_radar_leave(event)
            return

        ax = event.inaxes
        if ax.name != 'polar':
            self._on_radar_leave(event)
            return

        hover_radius = 20
        mouse_pos_pixels = (event.x, event.y)
        min_dist = float('inf')
        closest_point_info = None

        plot_data = self.radar_plot_data_analysis
        angles = plot_data['angles']
        portfolio_points = plot_data['portfolio']
        benchmark_points = plot_data['benchmark']

        for i in range(len(angles)):
            for series_type, data_points in [('portfolio', portfolio_points), ('benchmark', benchmark_points)]:
                point_data_coords = (angles[i], data_points[i])
                point_pixel_coords = ax.transData.transform([point_data_coords])[0]
                dist = np.sqrt((mouse_pos_pixels[0] - point_pixel_coords[0])**2 + (mouse_pos_pixels[1] - point_pixel_coords[1])**2)
                if dist < min_dist:
                    min_dist = dist
                    closest_point_info = {
                        'axis_idx': i,
                        'series_type': series_type,
                        'data_coords': point_data_coords
                    }

        if closest_point_info and min_dist < hover_radius:
            idx = closest_point_info['axis_idx']

            # Get raw data from the 'analysis' dictionary
            label = self.radar_data_analysis['labels'][idx]
            portfolio_val = self.radar_data_analysis['portfolio'][label]
            benchmark_val = self.radar_data_analysis['benchmark'][label]

            if label == 'Market Risk (Beta)':
                text = f"{label}\nPortfolio: {portfolio_val:.2f}\nBenchmark: {benchmark_val:.2f}"
            else:
                text = f"{label}\nPortfolio: {portfolio_val:.1%}\nBenchmark: {benchmark_val:.1%}"

            # Use the dedicated 'analysis' annotation object
            if not self.radar_annot_analysis:
                self.radar_annot_analysis = ax.annotate("", xy=(0,0), xytext=(15, 15),
                                               textcoords='offset points',
                                               bbox=dict(boxstyle="round,pad=0.4", fc=self.CARD_COLOR, ec=self.BORDER_COLOR, lw=1),
                                               arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.1", color=self.ACCENT_COLOR),
                                               ha='left', va='bottom',
                                               color=self.TEXT_COLOR,
                                               fontweight='bold')

            self.radar_annot_analysis.set_text(text)
            self.radar_annot_analysis.xy = closest_point_info['data_coords']
            self.radar_annot_analysis.set_visible(True)

        else:
            if self.radar_annot_analysis:
                self.radar_annot_analysis.set_visible(False)

        # Draw the dedicated 'analysis' canvas
        if hasattr(self, 'radar_canvas_analysis'):
            self.radar_canvas_analysis.draw_idle()

    def _on_radar_leave(self, event):
        """Hides the ANALYSIS annotation when the mouse leaves the chart."""
        # Use the dedicated 'analysis' annotation object
        if self.radar_annot_analysis:
            self.radar_annot_analysis.set_visible(False)
            if hasattr(self, 'radar_canvas_analysis'):
                self.radar_canvas_analysis.draw_idle()


    def _on_radar_hover_dash(self, event):
        """Handles hover events specifically for the DASHBOARD radar chart."""
        if not self.radar_canvas_dash or not event.inaxes or not self.radar_plot_data_dash:
            self._on_radar_leave_dash(event)
            return

        ax = event.inaxes
        if ax.name != 'polar':
            self._on_radar_leave_dash(event)
            return

        hover_radius = 20
        mouse_pos_pixels = (event.x, event.y)
        min_dist = float('inf')
        closest_point_info = None

        plot_data = self.radar_plot_data_dash
        angles = plot_data['angles']
        portfolio_points = plot_data['portfolio']

        for i in range(len(angles)):
            point_data_coords = (angles[i], portfolio_points[i])
            point_pixel_coords = ax.transData.transform([point_data_coords])[0]
            dist = np.sqrt((mouse_pos_pixels[0] - point_pixel_coords[0])**2 + (mouse_pos_pixels[1] - point_pixel_coords[1])**2)
            if dist < min_dist:
                min_dist = dist
                closest_point_info = {'axis_idx': i, 'data_coords': point_data_coords}
        
        if closest_point_info and min_dist < hover_radius:
            idx = closest_point_info['axis_idx']
            label = self.radar_data_dash['labels'][idx]
            portfolio_val = self.radar_data_dash['portfolio'][label]
            
            text = f"{label}\nValue: {portfolio_val:.2f}" if 'Beta' in label else f"{label}\nExposure: {portfolio_val:.1%}"
            
            if not self.radar_annot_dash:
                self.radar_annot_dash = ax.annotate("", xy=(0,0), xytext=(15, 15),
                                           textcoords='offset points',
                                           bbox=dict(boxstyle="round,pad=0.4", fc=self.CARD_COLOR, ec=self.BORDER_COLOR, lw=1),
                                           arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.1", color=self.ACCENT_COLOR),
                                           ha='left', va='bottom',
                                           color=self.TEXT_COLOR,
                                           fontweight='bold', fontsize=9)
            
            self.radar_annot_dash.set_text(text)
            self.radar_annot_dash.xy = closest_point_info['data_coords']
            self.radar_annot_dash.set_visible(True)
        else:
            if self.radar_annot_dash:
                self.radar_annot_dash.set_visible(False)
        
        self.radar_canvas_dash.draw_idle()

    def _on_radar_leave_dash(self, event):
        """Hides the annotation when the mouse leaves the DASHBOARD chart."""
        if self.radar_annot_dash:
            self.radar_annot_dash.set_visible(False)
            self.radar_canvas_dash.draw_idle()


    
    def _update_stress_test_view(self, event=None):
        """Handles running a HISTORICAL stress test scenario."""
        if not self.portfolio["positions"]: return

        scenario_name = self.scenario_var.get()
        scenarios = {
            "2008 Financial Crisis": {"shock": -0.55, "rebound_annual": 0.12},
            "2020 COVID Crash":      {"shock": -0.34, "rebound_annual": 0.30},
            "Dot-com Burst":         {"shock": -0.49, "rebound_annual": 0.18}
        }
        
        market_shock = scenarios[scenario_name]["shock"]
        rebound_rate = scenarios[scenario_name]["rebound_annual"]
        
        # Rate shock is 0 for historical scenarios
        self._execute_and_plot_stress_test(market_shock, 0, rebound_rate, scenario_name)

    def _run_custom_stress_test(self):
        """Handles running a CUSTOM stress test scenario from the new slider inputs."""
        if not self.portfolio["positions"]:
            messagebox.showwarning("No Positions", "Please add positions to your portfolio before running a scenario.", parent=self)
            return
        
        try:
            # FIX: Wrap the variable access in a try/except block to prevent TclError
            # if the widgets have been destroyed during a view change.
            market_shock = self.custom_shock_var.get() / 100.0
            rate_shock = self.custom_rate_var.get() / 100.0
        except (ValueError, TclError):
            # TclError can happen if the view is destroyed while trying to get the value.
            # This is a safe way to exit the function without crashing the app.
            print("Could not read stress test slider values, likely because the view was changed. This is safe to ignore.")
            return

        # For custom scenarios, use a generic strong rebound rate
        rebound_rate = 0.18 
        scenario_name = "Custom Scenario"
        
        self._execute_and_plot_stress_test(market_shock, rate_shock, rebound_rate, scenario_name)

    def _execute_and_plot_stress_test(self, market_shock, rate_shock, rebound_annual_rate, scenario_name):
        """
        The shared engine for calculating and plotting any stress test scenario
        with full and correct theming.
        """
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
        if total_value == 0: return

        # --- Calculation Logic (No Changes Here) ---
        portfolio_beta = self.analysis_data.get('analytics', {}).get('beta', 1.0)
        market_impact = total_value * portfolio_beta * market_shock
        rate_impact = sum(
            pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) *
            self.market_data_cache.get(pos["symbol"], {}).get("interest_rate_sensitivity", 0) *
            rate_shock
            for pos in self.portfolio["positions"]
        )
        total_shock_usd = market_impact + rate_impact
        total_shock_pct = total_shock_usd / total_value if total_value > 0 else 0
        weights = {pos["symbol"]: (pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0)) / total_value for pos in self.portfolio["positions"]}
        portfolio_returns = (self.analysis_data['returns'][list(weights.keys())] * pd.Series(weights)).sum(axis=1)
        last_val = total_value
        trough_val = last_val + total_shock_usd
        scenario_daily_rebound_rate = (1 + rebound_annual_rate)**(1/252) - 1
        portfolio_avg_daily_return = portfolio_returns.mean()
        recovery_growth_rate = max(portfolio_avg_daily_return, scenario_daily_rebound_rate)
        estimated_recovery_days = -1
        if trough_val > 0 and last_val > trough_val:
            log_growth_rate = np.log(1 + recovery_growth_rate)
            log_value_ratio = np.log(last_val / trough_val)
            if log_growth_rate > 0:
                estimated_recovery_days = int(log_value_ratio / log_growth_rate)

        if estimated_recovery_days > 0:
            if estimated_recovery_days > 5 * 365: recovery_text = "5+ Years"
            elif estimated_recovery_days > 365: recovery_text = f"~{estimated_recovery_days / 365.25:.1f} Years"
            else: recovery_text = f"~{max(1, estimated_recovery_days / (365.25/12)):.0f} Months"
        else: recovery_text = "N/A"

        self.stress_kpi_loss_usd.config(text=f"${total_shock_usd:,.2f}", foreground=self.NEGATIVE_COLOR)
        self.stress_kpi_loss_pct.config(text=f"{total_shock_pct:.2%}", foreground=self.NEGATIVE_COLOR)
        self.stress_kpi_recovery.config(text=recovery_text)

        # --- Plotting & Theming ---
        self.ax_stress.clear()
        self._setup_matplotlib_style(self.fig_stress, self.ax_stress) # Apply base theme

        historical_returns = portfolio_returns.iloc[-180:]
        growth_factors = (1 + historical_returns).cumprod()
        normalized_factors = growth_factors / growth_factors.iloc[-1]
        pre_shock_path = last_val * normalized_factors
        
        path = list(pre_shock_path.values)
        path.append(trough_val)
        
        recovery_days = estimated_recovery_days if estimated_recovery_days > 0 else 22
        if recovery_days > 0:
            daily_std_dev = portfolio_returns.std()
            random_returns = np.random.normal(recovery_growth_rate, daily_std_dev, recovery_days)
            unadjusted_path = [trough_val]
            for r in random_returns:
                unadjusted_path.append(unadjusted_path[-1] * (1 + r))
            error = last_val - unadjusted_path[-1]
            adjustment = np.linspace(0, error, len(unadjusted_path))
            recovery_path = np.array(unadjusted_path) + adjustment
            path.extend(list(recovery_path))
        
        x_axis = np.arange(-180, len(path) - 180)

        self.ax_stress.plot(x_axis, path, color=self.ACCENT_COLOR, lw=1.5, zorder=10)
        self.ax_stress.axvline(x=0, color=self.NEGATIVE_COLOR, linestyle='--', label=f"Event: {scenario_name}", zorder=5)
        self.ax_stress.axhline(y=last_val, color=self.SECONDARY_TEXT, linestyle=':', label='Pre-Crash Value', zorder=5)

        recovery_point_x = next((x_axis[i] for i in range(181, len(path)) if path[i] >= last_val), None)
        
        if recovery_point_x is not None:
            self.ax_stress.plot(recovery_point_x, last_val, 'o', color=self.POSITIVE_COLOR, markersize=8, zorder=20, label="Recovery Point")
            self.ax_stress.annotate(
                f'Recovered\nDay {recovery_point_x}',
                xy=(recovery_point_x, last_val),
                xytext=(recovery_point_x + 30, last_val + (self.ax_stress.get_ylim()[1] - self.ax_stress.get_ylim()[0]) * 0.05),
                arrowprops=dict(facecolor=self.SECONDARY_TEXT, shrink=0.05, width=1, headwidth=4),
                ha='center', va='bottom',
                bbox=dict(boxstyle="round,pad=0.3", fc=self.CARD_COLOR, ec=self.BORDER_COLOR, lw=0.5, alpha=0.9),
                color=self.TEXT_COLOR, # THEME FIX: Set text color
                zorder=30
            )
        
        # THEME FIX: Apply theme colors to all text elements
        self.ax_stress.set_title(f"Simulated Impact of {scenario_name}", fontsize=14, pad=20, color=self.TEXT_COLOR)
        self.fig_stress.suptitle("Simulated path showing the shock and a projected recovery.", fontsize=9, color=self.SECONDARY_TEXT, y=0.92)
        self.ax_stress.set_ylabel("Portfolio Value ($)", color=self.SECONDARY_TEXT)
        self.ax_stress.set_xlabel("Trading Days From Event", color=self.SECONDARY_TEXT)
        
        legend = self.ax_stress.legend(facecolor=self.CARD_COLOR, edgecolor=self.BORDER_COLOR)
        for text in legend.get_texts():
            text.set_color(self.TEXT_COLOR)

        self.ax_stress.grid(True, linestyle='--', alpha=0.5)
        #self.fig_stress.tight_layout(rect=[0, 0, 1, 0.9])
        self.canvas_stress.draw()

    def _update_analysis_view_data(self):
        """
        Updates all UI components that depend on calculated analytics data.
        Assumes self.analysis_data is already populated.
        """
        # Always update the dashboard drivers card
        self._update_dashboard_drivers_card()

        # Only update the dedicated analysis tab charts if that tab has been built
        if self.has_built_analysis_tab:
            self._update_key_drivers_view()
            self._update_risk_volatility_view()
            self._update_correlation_view()
            self._update_attribution_view()
            self._update_stress_test_view()

    def _generate_mock_historical_returns(self, days=252):
        """Generates a DataFrame of mock daily returns for all assets and a benchmark."""
        dates = pd.date_range(end=datetime.now(), periods=days)
        returns_df = pd.DataFrame(index=dates)
        returns_df['SPY'] = np.random.normal(loc=0.0005, scale=0.01, size=days)

        for pos in self.portfolio["positions"]:
            symbol = pos["symbol"]
            mock_beta = self.market_data_cache.get(symbol, {}).get("beta", 1.0)
            mock_vol = np.random.uniform(0.01, 0.03)
            asset_returns = returns_df['SPY'] * mock_beta + np.random.normal(loc=0, scale=mock_vol, size=days)
            returns_df[symbol] = asset_returns
            
        return returns_df

    def _calculate_portfolio_analytics(self, returns_df):
        """Calculates all key risk, performance, and fundamental metrics."""
        analytics = {'positions': {}, 'fundamentals': {}}
        
        positions = self.portfolio["positions"]
        if not positions: return analytics

        total_value = sum(lot["shares"] * self.market_data_cache.get(lot["symbol"], {}).get("regularMarketPrice", 0) for lot in positions)
        if total_value == 0: return analytics

        # --- THIS IS THE FIX: Aggregate position values by symbol before calculating weights ---
        symbol_values = {}
        for lot in positions:
            symbol = lot['symbol']
            value = lot["shares"] * self.market_data_cache.get(symbol, {}).get("regularMarketPrice", 0)
            symbol_values[symbol] = symbol_values.get(symbol, 0) + value
        
        weights = {symbol: value / total_value for symbol, value in symbol_values.items()}
        # --- END OF FIX ---

        portfolio_symbols = list(weights.keys())
        portfolio_returns = (returns_df[portfolio_symbols] * pd.Series(weights)).sum(axis=1)

        # --- Risk Metrics ---
        covariance = portfolio_returns.cov(returns_df['SPY'])
        market_variance = returns_df['SPY'].var()
        analytics['beta'] = covariance / market_variance if market_variance != 0 else 0
        analytics['volatility'] = portfolio_returns.std() * np.sqrt(252)
        risk_free_rate = 0.01
        excess_returns = portfolio_returns.mean() * 252 - risk_free_rate
        analytics['sharpe_ratio'] = excess_returns / analytics['volatility'] if analytics['volatility'] != 0 else 0
        
        daily_volatility = portfolio_returns.std()
        analytics['var_95'] = total_value * daily_volatility * 1.645

        # --- Diversification Score ---
        corr_matrix = returns_df[portfolio_symbols].corr()
        if len(portfolio_symbols) > 1:
            # Correctly calculate average correlation by excluding self-correlation
            corr_unstacked = corr_matrix.unstack()
            corr_filtered = corr_unstacked[corr_unstacked.index.get_level_values(0) != corr_unstacked.index.get_level_values(1)]
            avg_corr = corr_filtered.mean()
            analytics['diversification_score'] = (1 - avg_corr) * 100
        else:
            analytics['diversification_score'] = 0

        # --- Fundamental Metrics ---
        analytics['fundamentals']['pe_ratio'] = sum(self.market_data_cache.get(s, {}).get("trailingPE", 0) * w for s, w in weights.items())
        analytics['fundamentals']['dividend_yield'] = sum(self.market_data_cache.get(s, {}).get("dividendYield", 0) * w for s, w in weights.items())
        
        benchmark_data = self.api.get_benchmark_details()
        analytics['fundamentals']['benchmark_pe'] = benchmark_data.get('trailingPE')
        analytics['fundamentals']['benchmark_yield'] = benchmark_data.get('dividendYield')

        weighted_factors = {"Value": 0, "Growth": 0, "Quality": 0}
        for s, w in weights.items():
            factors = self.market_data_cache.get(s, {}).get("factor_exposures", {})
            for factor, exposure in factors.items():
                weighted_factors[factor] += w * exposure
        analytics['fundamentals']['factor_exposures'] = weighted_factors
        
        return analytics
    
    def _calculate_dashboard_data(self):
        """
        Calculates data specifically needed for the dashboard UI, 
        like sector allocations.
        """
        self.sector_details = {}
        if not self.portfolio["positions"]:
            return

        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
        if total_value == 0:
            return

        # Use a predefined, professional color palette for sectors
        colors = ["#00aaff", "#00cc66", "#ffcc00", "#ff6666", "#9966ff", "#ff9933", "#33cccc", "#cc6699"]
        color_idx = 0

        for pos in self.portfolio["positions"]:
            market_info = self.market_data_cache.get(pos["symbol"], {})
            sector = market_info.get("sector", "Other")
            value = pos["shares"] * market_info.get("regularMarketPrice", 0)
            
            if sector not in self.sector_details:
                self.sector_details[sector] = {'value': 0, 'color': colors[color_idx % len(colors)]}
                color_idx += 1
            
            self.sector_details[sector]['value'] += value

        for sector in self.sector_details:
            self.sector_details[sector]['percentage'] = self.sector_details[sector]['value'] / total_value
        
    

    def _update_risk_volatility_view(self):
        """Populates the Risk & Volatility tab with calculated data, including VaR."""
        analytics = self.analysis_data.get('analytics', {})
        
        self.risk_kpi_vol.config(text=f"{analytics.get('volatility', 0):.2%}")
        self.risk_kpi_sharpe.config(text=f"{analytics.get('sharpe_ratio', 0):.2f}")
        self.risk_kpi_var.config(text=f"${analytics.get('var_95', 0):,.2f}")

        self.ax_risk.clear()
        self._setup_matplotlib_style(self.fig_risk, self.ax_risk) # Apply theme
        
        returns_df = self.analysis_data.get('returns')
        if returns_df is not None:
            total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
            if total_value > 0:
                weights = {pos["symbol"]: (pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0)) / total_value for pos in self.portfolio["positions"]}
                portfolio_returns = (returns_df[list(weights.keys())] * pd.Series(weights)).sum(axis=1)
                rolling_vol = portfolio_returns.rolling(window=22).std() * np.sqrt(252)
                benchmark_rolling_vol = returns_df['SPY'].rolling(window=22).std() * np.sqrt(252)
                rolling_vol.plot(ax=self.ax_risk, label="Portfolio", color=self.ACCENT_COLOR, lw=2)
                benchmark_rolling_vol.plot(ax=self.ax_risk, label="S&P 500", color=self.SECONDARY_TEXT, ls="--")
        
        # THEME FIX: Apply theme colors to all text elements
        self.ax_risk.set_title("1-Year Rolling Volatility", color=self.TEXT_COLOR, fontsize=12)
        self.ax_risk.set_ylabel("Annualized Volatility", color=self.SECONDARY_TEXT)
        legend = self.ax_risk.legend(facecolor=self.CARD_COLOR, edgecolor=self.BORDER_COLOR)
        for text in legend.get_texts():
            text.set_color(self.TEXT_COLOR)
            
        self.ax_risk.grid(True, axis='y', linestyle='--', alpha=0.5)
        self.fig_risk.tight_layout()
        self.canvas_risk.draw()

    def _update_correlation_view(self):
        """
        Populates the Correlation tab, including the Diversification Score
        and the detailed text insights.
        """
        analytics = self.analysis_data.get('analytics', {})
        score = analytics.get('diversification_score', 0)
        self.corr_kpi_score.config(text=f"{score:.1f} / 100")
        
        if score > 75: color = self.POSITIVE_COLOR
        elif score > 50: color = "#f0c420" # Warning yellow
        else: color = self.NEGATIVE_COLOR
        self.corr_kpi_score.config(foreground=color)

        returns = self.analysis_data.get('returns')
        
        self.fig_corr.clear()
        self.ax_corr = self.fig_corr.add_subplot(111)
        self._setup_matplotlib_style(self.fig_corr, self.ax_corr)

        # --- THIS IS THE FIX: Ensure the list of symbols is unique ---
        portfolio_symbols = sorted(list(set(pos['symbol'] for pos in self.portfolio['positions'])))
        # --- END OF FIX ---

        if returns is None or len(portfolio_symbols) < 2:
            self.ax_corr.text(0.5, 0.5, "Add at least 2 positions\nto see correlations", ha='center', va='center', color=self.TEXT_COLOR)
            self.canvas_corr.draw()
            return
            
        corr_matrix = returns[portfolio_symbols].corr()
        
        im = self.ax_corr.imshow(corr_matrix, cmap='coolwarm', interpolation='nearest', vmin=-1, vmax=1)
        
        cbar = self.fig_corr.colorbar(im, ax=self.ax_corr)
        cbar.ax.yaxis.set_tick_params(color=self.SECONDARY_TEXT)
        cbar.outline.set_edgecolor(self.BORDER_COLOR)
        plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color=self.SECONDARY_TEXT)
        
        self.ax_corr.set_xticks(np.arange(len(portfolio_symbols)))
        self.ax_corr.set_yticks(np.arange(len(portfolio_symbols)))
        self.ax_corr.set_xticklabels(portfolio_symbols, rotation=45, ha="right", color=self.TEXT_COLOR)
        self.ax_corr.set_yticklabels(portfolio_symbols, color=self.TEXT_COLOR)
        self.ax_corr.set_title("Asset Correlation Matrix", fontsize=12, color=self.TEXT_COLOR)
        
        self.fig_corr.tight_layout(pad=2.0)
        self.canvas_corr.draw()

        summary = self.corr_summary_text
        summary.config(state="normal")
        summary.delete("1.0", tk.END)
        summary.insert(tk.END, "What is Correlation?\n", "heading")
        summary.insert(tk.END, "It measures how two assets move in relation to each other. Values range from -1 to +1.\n\n")
        
        summary.insert(tk.END, "Low/Negative (Good for Diversification)\n", ("heading", "good"))
        summary.insert(tk.END, "Assets with low correlation (close to 0 or negative) tend to move independently. This is desirable as it reduces overall portfolio volatility.\n\n", "good")

        summary.insert(tk.END, "High/Positive (Bad for Diversification)\n", ("heading", "bad"))
        summary.insert(tk.END, "Assets with high correlation (close to +1) tend to move in the same direction. A portfolio of highly correlated assets is riskier.\n\n", "bad")

        if len(portfolio_symbols) > 1:
            corr_unstacked = corr_matrix.unstack()
            corr_unstacked = corr_unstacked[corr_unstacked.index.get_level_values(0) != corr_unstacked.index.get_level_values(1)]
            max_corr = corr_unstacked.idxmax()
            min_corr = corr_unstacked.idxmin()
            summary.insert(tk.END, "Highest Correlation (Risk Concentrator):\n", "bold")
            summary.insert(tk.END, f"{max_corr[0]} & {max_corr[1]}: {corr_unstacked[max_corr]:.2f}\n\n", "bad")
            summary.insert(tk.END, "Lowest Correlation (Best Diversifier):\n", "bold")
            summary.insert(tk.END, f"{min_corr[0]} & {min_corr[1]}: {corr_unstacked[min_corr]:.2f}", "good")
        
        summary.config(state="disabled")

    def _update_attribution_view(self):
        """Calculates and plots contribution to return with correct theming."""
        self.ax_attr.clear()
        self._setup_matplotlib_style(self.fig_attr, self.ax_attr) # Apply theme

        returns = self.analysis_data.get('returns')
        if returns is None or returns.empty:
            self.canvas_attr.draw()
            return

        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
        if total_value == 0:
            self.canvas_attr.draw()
            return
            
        weights = {pos["symbol"]: (pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0)) / total_value for pos in self.portfolio["positions"]}

        total_returns = (1 + returns).prod() - 1
        contributions = total_returns * pd.Series(weights)
        contributions_usd = contributions * total_value
        
        sorted_contributions = contributions_usd.sort_values()
        colors = [self.POSITIVE_COLOR if v >= 0 else self.NEGATIVE_COLOR for v in sorted_contributions]

        sorted_contributions.plot(kind='barh', ax=self.ax_attr, color=colors)
        
        # THEME FIX: Apply theme colors to all text elements
        self.ax_attr.set_title("Contribution to Return ($)", fontsize=12, color=self.TEXT_COLOR)
        self.ax_attr.set_xlabel("Dollar Contribution", color=self.SECONDARY_TEXT)
        self.ax_attr.grid(True, axis='x', linestyle='--', alpha=0.3)
        
        self.fig_attr.tight_layout()
        self.canvas_attr.draw()

    def _create_kpi_card(self, parent, title, value, col):
        """Create a professional KPI card."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=15)
        card.grid(row=0, column=col, sticky="nsew", padx=5)
        ttk.Label(card, text=title, style="Secondary.TLabel", background=self.CARD_COLOR).pack()
        value_lbl = ttk.Label(card, text=value, style="KPI.TLabel", background=self.CARD_COLOR)
        value_lbl.pack(pady=5)
        return value_lbl

    def _create_timeframe_selector(self, parent):
        """Creates the timeframe button group for the history chart."""
        frame = ttk.Frame(parent, style="Card.TFrame")
        self.timeframe_buttons = {}
        timeframes = ["1M", "6M", "1Y", "5Y", "ALL"]

        for i, tf in enumerate(timeframes):
            btn = ttk.Button(
                frame,
                text=tf,
                style="ActiveTimeframe.TButton" if tf == self.active_timeframe else "Timeframe.TButton",
                command=lambda t=tf: self._set_timeframe(t)
            )
            btn.grid(row=0, column=i, padx=(2, 0))
            self.timeframe_buttons[tf] = btn
            
        return frame

    def _on_position_right_click(self, event, symbol):
        """Handle right-click event on the custom positions table."""
        # The symbol is now passed directly, so we store it for the menu commands
        self.active_context_symbol = symbol 
        self.position_context_menu.post(event.x_root, event.y_root)

    def _remove_position(self):
        """Remove the selected position and log it as a realized gain/loss."""
        if not hasattr(self, 'active_context_symbol'): return

        symbol_to_remove = self.active_context_symbol
        pos_data = next((p for p in self.portfolio["positions"] if p["symbol"] == symbol_to_remove), None)
        if not pos_data: return

        confirm = messagebox.askyesno(
            "Confirm Sale",
            f"This will sell all {pos_data['shares']} shares of {symbol_to_remove} and realize the gain or loss. Are you sure?",
            parent=self
        )

        if confirm:
            # Realize the gain/loss
            current_price = self.market_data_cache.get(symbol_to_remove, {}).get("regularMarketPrice", pos_data["entry_price"])
            gain_loss = (current_price - pos_data["entry_price"]) * pos_data["shares"]
            
            purchase_date = datetime.strptime(pos_data["purchase_date"], '%Y-%m-%d')
            holding_period = (datetime.now() - purchase_date).days
            gain_type = "Long-Term" if holding_period > 365 else "Short-Term"

            self.portfolio["realized_gains"].append({
                "symbol": symbol_to_remove,
                "gain_loss": gain_loss,
                "date": datetime.now().strftime('%Y-%m-%d'),
                "type": gain_type
            })

            # Remove the position from holdings
            self.portfolio["positions"] = [
                pos for pos in self.portfolio["positions"] if pos["symbol"] != symbol_to_remove
            ]
            if symbol_to_remove in self.logo_cache:
                del self.logo_cache[symbol_to_remove]
            
            self._update_all_views()

    def _edit_position(self):
        """Open a dialog to edit the selected position."""
        if not hasattr(self, 'active_context_symbol'): return
            
        symbol_to_edit = self.active_context_symbol
        position_data = next((pos for pos in self.portfolio["positions"] if pos["symbol"] == symbol_to_edit), None)
        
        if position_data:
            dialog = PositionDialog(self, title=f"Edit {symbol_to_edit}", initial_data=position_data)
            if dialog.result:
                for i, pos in enumerate(self.portfolio["positions"]):
                    if pos["symbol"] == symbol_to_edit:
                        self.portfolio["positions"][i] = dialog.result
                        break
                self._update_all_views()

    def _build_hero_snapshot_card(self, parent):
        """Builds the new primary KPI 'hero' card for the dashboard."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=(25, 20))
        card.grid(row=0, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)

        # Main Portfolio Value
        ttk.Label(card, text="Total Portfolio Value", style="Secondary.TLabel", background=self.CARD_COLOR).pack(anchor="w")
        self.hero_total_value = ttk.Label(card, text="$0.00", font=("Calibri", 36, "bold"), background=self.CARD_COLOR, foreground=self.TEXT_COLOR)
        self.hero_total_value.pack(anchor="w", pady=(0, 2))

        # Daily Change
        self.hero_day_change = ttk.Label(card, text="+$0.00 (+0.00%)", font=("Calibri", 14), background=self.CARD_COLOR)
        self.hero_day_change.pack(anchor="w")

        return card

    def _create_kpi_card_with_benchmark(self, parent, title, value, col):
        """Creates a KPI card that includes a smaller line for benchmark comparison."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=15)
        card.grid(row=0, column=col, sticky="nsew", padx=5)
        
        ttk.Label(card, text=title, style="Secondary.TLabel", background=self.CARD_COLOR).pack(anchor="w")
        
        value_lbl = ttk.Label(card, text=value, style="KPI.TLabel", background=self.CARD_COLOR)
        value_lbl.pack(anchor="w", pady=(5,0))
        
        benchmark_lbl = ttk.Label(card, text="vs SPY: ...", font=self.FONT_NORMAL, foreground=self.SECONDARY_TEXT, background=self.CARD_COLOR)
        benchmark_lbl.pack(anchor="w")
        
        return value_lbl, benchmark_lbl

    def _create_custom_scenario_slider(self, parent, label_text, from_, to, initial_value, col, format_str="{:+.1f}%"):
        """
        Creates a labeled slider with a live value display.
        This version fixes the bug where the text label did not update on slide.
        """
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=0, column=col, sticky="ew", padx=(10, 5))
        frame.columnconfigure(0, weight=1)

        label_frame = ttk.Frame(frame, style="Card.TFrame")
        label_frame.pack(fill="x")
        
        ttk.Label(label_frame, text=label_text, style="Secondary.TLabel", background=self.CARD_COLOR).pack(side="left")
        value_lbl = ttk.Label(label_frame, text=format_str.format(initial_value), font=self.FONT_BOLD, background=self.CARD_COLOR)
        value_lbl.pack(side="right")

        var = tk.DoubleVar(value=initial_value)
        slider = ttk.Scale(frame, from_=from_, to=to, orient="horizontal", variable=var, style="Horizontal.TScale")
        slider.pack(fill="x", expand=True, pady=(5,0))
        
        # This trace is now correctly configured to update the label.
        var.trace_add("write", lambda name, index, mode, v=var, l=value_lbl, f=format_str: l.config(text=f.format(v.get())))
        
        return var



    def _build_tax_view(self, parent):
        """Builds the advanced 'Tax Center' with a smarter, conditional Treeview."""
        view = ttk.Frame(parent)
        view.columnconfigure(0, weight=3)
        view.columnconfigure(1, weight=2)
        view.rowconfigure(1, weight=1)

        header = ttk.Frame(view)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 20))
        ttk.Label(header, text="Tax Center", style="Title.TLabel").pack(side="left")
        
        info_button = ttk.Button(header, text="[?]", command=self._show_tax_info_dialog, style="Toolbutton")
        info_button.pack(side="left", padx=10, pady=0)
        style = ttk.Style(self)
        style.configure("Toolbutton", padding=5, relief="flat", background=self.BG_COLOR, font=self.FONT_BOLD, foreground=self.SECONDARY_TEXT)
        style.map("Toolbutton", background=[('active', self.CARD_COLOR)], foreground=[('active', self.ACCENT_COLOR)])

        left_col = ttk.Frame(view)
        left_col.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left_col.rowconfigure(1, weight=1)
        left_col.columnconfigure(0, weight=1)
        
        kpi_frame = ttk.Frame(left_col)
        kpi_frame.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        kpi_frame.columnconfigure((0, 1, 2), weight=1)
        self.tax_kpi_realized = self._create_kpi_card(kpi_frame, "Realized Gains YTD", "...", 0)
        self.tax_kpi_harvestable = self._create_kpi_card(kpi_frame, "Total Harvestable Loss", "...", 1)
        self.tax_kpi_efficiency = self._create_kpi_card(kpi_frame, "Tax Efficiency Score", "...", 2)

        unrealized_card = ttk.Frame(left_col, style="Card.TFrame", padding=15)
        unrealized_card.grid(row=1, column=0, sticky="nsew")
        unrealized_card.rowconfigure(1, weight=1)
        unrealized_card.columnconfigure(0, weight=1)
        ttk.Label(unrealized_card, text="Unrealized Gains & Losses (by Lot)", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w", pady=(0, 10))
        
        # THIS IS THE CHANGE: The columns are redefined for the new structure.
        self.unrealized_tree = ttk.Treeview(unrealized_card, columns=("name", "shares", "term", "cost", "value", "gain", "gain_pct"), show="headings")
        self.unrealized_tree.pack(fill="both", expand=True)
        self.unrealized_tree.heading("#0", text="Symbol / Lot")
        self.unrealized_tree.heading("name", text="Name")
        self.unrealized_tree.heading("shares", text="Shares")
        self.unrealized_tree.heading("term", text="Term")
        self.unrealized_tree.heading("cost", text="Cost Basis")
        self.unrealized_tree.heading("value", text="Market Value")
        self.unrealized_tree.heading("gain", text="Unrealized ($)")
        self.unrealized_tree.heading("gain_pct", text="Unrealized (%)")
        
        self.unrealized_tree.column("#0", anchor="w", width=200)
        self.unrealized_tree.column("name", anchor="w", width=180)
        self.unrealized_tree.column("shares", anchor="e", width=60, stretch=False)
        self.unrealized_tree.column("term", anchor="center", width=100, stretch=False)
        self.unrealized_tree.column("cost", anchor="e", width=120)
        self.unrealized_tree.column("value", anchor="e", width=120)
        self.unrealized_tree.column("gain", anchor="e", width=120)
        self.unrealized_tree.column("gain_pct", anchor="e", width=120)

        self.unrealized_tree.tag_configure('gain', foreground=self.POSITIVE_COLOR)
        self.unrealized_tree.tag_configure('loss', foreground=self.NEGATIVE_COLOR)
        self.unrealized_tree.tag_configure('parent', font=self.FONT_BOLD)

        # ... (The rest of the method remains the same)
        right_col = ttk.Frame(view)
        right_col.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        right_col.rowconfigure(0, weight=1)
        right_col.rowconfigure(1, weight=1)
        right_col.columnconfigure(0, weight=1)

        self._build_tax_simulator_card(right_col)

        realized_card = ttk.Frame(right_col, style="Card.TFrame", padding=15)
        realized_card.grid(row=1, column=0, sticky="nsew", pady=(15, 0))
        realized_card.rowconfigure(1, weight=1)
        realized_card.columnconfigure(0, weight=1)
        ttk.Label(realized_card, text="Realized Gains Log (YTD)", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w", pady=(0, 10))

        self.realized_tree = ttk.Treeview(realized_card, columns=("date", "symbol", "type", "gain_loss"), show="headings")
        self.realized_tree.pack(fill="both", expand=True)
        self.realized_tree.heading("date", text="Date")
        self.realized_tree.heading("symbol", text="Symbol")
        self.realized_tree.heading("type", text="Type")
        self.realized_tree.heading("gain_loss", text="Gain/Loss ($)")
        for col in ("date", "symbol", "type", "gain_loss"):
            self.realized_tree.column(col, anchor="center", width=80)
        self.realized_tree.column("gain_loss", anchor="e")
        self.realized_tree.tag_configure('realized_gain', foreground=self.NEGATIVE_COLOR)
        self.realized_tree.tag_configure('realized_loss', foreground=self.POSITIVE_COLOR)

        return view

    def _build_tax_simulator_card(self, parent):
        """Builds the new interactive 'What-If' sale simulator with a professional grid layout."""
        sim_card = ttk.Frame(parent, style="Card.TFrame", padding=15)
        sim_card.grid(row=0, column=0, sticky="nsew")
        sim_card.rowconfigure(2, weight=1) # Make the canvas area expand
        sim_card.columnconfigure(0, weight=1)

        # --- Header ---
        ttk.Label(sim_card, text="\"What-If\" Sale Simulator", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 15))

        # --- Tax Rate Inputs (Neat Grid Layout) ---
        rates_frame = ttk.Frame(sim_card, style="Card.TFrame")
        rates_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        rates_frame.columnconfigure(1, weight=1)
        rates_frame.columnconfigure(3, weight=1)

        ttk.Label(rates_frame, text="Short-Term Rate (%):", style="Secondary.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w")
        self.st_rate_var = tk.StringVar(value="24")
        ttk.Entry(rates_frame, textvariable=self.st_rate_var, width=8).grid(row=0, column=1, sticky="w", padx=10)

        ttk.Label(rates_frame, text="Long-Term Rate (%):", style="Secondary.TLabel", background=self.CARD_COLOR).grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.lt_rate_var = tk.StringVar(value="15")
        ttk.Entry(rates_frame, textvariable=self.lt_rate_var, width=8).grid(row=0, column=3, sticky="w", padx=10)

        # --- Scrollable Frame for Position Inputs ---
        canvas_frame = ttk.Frame(sim_card) # No style needed, it's just a container
        canvas_frame.grid(row=2, column=0, sticky="nsew")
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)

        canvas = tk.Canvas(canvas_frame, bg=self.CARD_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        self.tax_sim_container = ttk.Frame(canvas, style="Card.TFrame")
        
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.create_window((0, 0), window=self.tax_sim_container, anchor="nw")
        self.tax_sim_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>", lambda e, c=canvas: self._on_mousewheel(e, c))

        # --- Results and Calculation Button ---
        sim_footer = ttk.Frame(sim_card, style="Card.TFrame")
        sim_footer.grid(row=3, column=0, sticky="ew", pady=(15, 0))
        sim_footer.columnconfigure(0, weight=1)
        
        self.tax_sim_result_lbl = self._create_metric_display(sim_footer, "Total Estimated Tax Impact", "$0.00", 0, 0)
        
        calc_btn = ttk.Button(sim_footer, text="Calculate Impact", style="Accent.TButton", command=self._run_tax_simulation)
        calc_btn.grid(row=0, column=1, sticky="e", rowspan=2, padx=(10,0))
        
    def _update_tax_view(self):
        """The master update function for the Tax Center."""
        if not self.winfo_exists(): return
        
        # Populate the main table of all positions
        self._populate_unrealized_gains_table()
        
        # Populate the KPIs at the top
        self._populate_tax_kpis()
        
        # Populate the simulator with an entry for each position
        self._populate_tax_simulator_inputs()
        
        # Populate the log of past sales
        self._populate_realized_gains_table()

    def _populate_tax_kpis(self):
        """Calculates and displays the key tax metrics, including the new efficiency score."""
        total_realized = sum(item['gain_loss'] for item in self.portfolio.get('realized_gains', []))
        
        harvestable_loss = 0
        for lot in self.portfolio["positions"]:
            market_info = self.market_data_cache.get(lot["symbol"], {})
            price = market_info.get("regularMarketPrice", lot["entry_price"])
            unrealized_gain = (price - lot["entry_price"]) * lot["shares"]
            if unrealized_gain < 0:
                harvestable_loss += unrealized_gain

        self.tax_kpi_realized.config(text=f"${total_realized:,.2f}", foreground=self.NEGATIVE_COLOR if total_realized > 0 else self.POSITIVE_COLOR)
        self.tax_kpi_harvestable.config(text=f"${harvestable_loss:,.2f}", foreground=self.POSITIVE_COLOR)
        
        # Calculate and display the new efficiency score
        score, grade = self._calculate_tax_efficiency_score()
        self.tax_kpi_efficiency.config(text=f"{score}/100 ({grade})")
        if score >= 90: color = self.POSITIVE_COLOR
        elif score >= 70: color = "#4caf50" # Lighter Green
        elif score >= 50: color = "#ffc107" # Amber
        else: color = self.NEGATIVE_COLOR
        self.tax_kpi_efficiency.config(foreground=color)

    def _populate_unrealized_gains_table(self):
        """Fills the Treeview with single rows for single lots and expandable rows for multiple lots."""
        for i in self.unrealized_tree.get_children():
            self.unrealized_tree.delete(i)

        positions_by_symbol = {}
        for lot in self.portfolio["positions"]:
            symbol = lot['symbol']
            if symbol not in positions_by_symbol:
                positions_by_symbol[symbol] = []
            positions_by_symbol[symbol].append(lot)

        for symbol in sorted(positions_by_symbol.keys()):
            lots = positions_by_symbol[symbol]
            market_info = self.market_data_cache.get(symbol, {})
            name = market_info.get("shortName", "N/A")

            # --- THIS IS THE NEW CONDITIONAL LOGIC ---
            if len(lots) == 1:
                # --- Single Lot Logic: Insert one clean row ---
                lot = lots[0]
                price = market_info.get("regularMarketPrice", lot["entry_price"])
                cost_basis = lot["entry_price"] * lot["shares"]
                market_value = price * lot["shares"]
                unrealized_gain = market_value - cost_basis
                unrealized_pct = (unrealized_gain / cost_basis * 100) if cost_basis != 0 else 0
                purchase_date = datetime.strptime(lot["purchase_date"], '%Y-%m-%d')
                holding_period = (datetime.now() - purchase_date).days
                term = "Long-Term" if holding_period > 365 else "Short-Term"
                tag = 'gain' if unrealized_gain >= 0 else 'loss'

                # Insert a single, non-expandable row with all data
                self.unrealized_tree.insert("", "end", text=symbol, values=(
                    name,
                    f"{lot['shares']}",
                    term,
                    f"${cost_basis:,.2f}",
                    f"${market_value:,.2f}",
                    f"{unrealized_gain:,.2f}",
                    f"{unrealized_pct:.2f}%"
                ), tags=(tag,))
            else:
                # --- Multi-Lot Logic: Insert parent with children ---
                # The parent row only contains the symbol and name
                parent_id = self.unrealized_tree.insert("", "end", text=symbol, values=(name, "", "", "", "", "", ""), open=True, tags=('parent',))

                # Child rows contain the specific lot details
                for lot in sorted(lots, key=lambda x: x['purchase_date']):
                    price = market_info.get("regularMarketPrice", lot["entry_price"])
                    cost_basis = lot["entry_price"] * lot["shares"]
                    market_value = price * lot["shares"]
                    unrealized_gain = market_value - cost_basis
                    unrealized_pct = (unrealized_gain / cost_basis * 100) if cost_basis != 0 else 0
                    purchase_date = datetime.strptime(lot["purchase_date"], '%Y-%m-%d')
                    holding_period = (datetime.now() - purchase_date).days
                    term = "Long-Term" if holding_period > 365 else "Short-Term"
                    tag = 'gain' if unrealized_gain >= 0 else 'loss'
                    
                    # Insert child row under the parent
                    self.unrealized_tree.insert(parent_id, "end", text=f"   Purchased: {lot['purchase_date']}", values=(
                        "",  # Name column is blank for child rows
                        f"{lot['shares']}",
                        term,
                        f"${cost_basis:,.2f}",
                        f"${market_value:,.2f}",
                        f"{unrealized_gain:,.2f}",
                        f"{unrealized_pct:.2f}%"
                    ), tags=(tag,))


    def _populate_tax_simulator_inputs(self):
        """Creates the dynamic input rows for each specific tax lot."""
        for widget in self.tax_sim_container.winfo_children():
            widget.destroy()
        self.tax_sim_entries.clear()

        header_frame = ttk.Frame(self.tax_sim_container, style="Card.TFrame")
        header_frame.pack(fill="x", expand=True, pady=(0, 5))
        header_frame.columnconfigure(0, weight=2)
        header_frame.columnconfigure(1, weight=1)
        header_frame.columnconfigure(2, weight=0) # For warning icon
        ttk.Label(header_frame, text="Position Lot (Shares Held)", font=self.FONT_BOLD, background=self.CARD_COLOR).grid(row=0, column=0, sticky="w")
        ttk.Label(header_frame, text="Shares to Sell", font=self.FONT_BOLD, background=self.CARD_COLOR).grid(row=0, column=1, sticky="w")

        sorted_lots = sorted(self.portfolio["positions"], key=lambda lot: (lot['symbol'], lot['purchase_date']))

        for lot in sorted_lots:
            row_frame = ttk.Frame(self.tax_sim_container, style="Card.TFrame")
            row_frame.pack(fill="x", expand=True, pady=2)
            row_frame.columnconfigure(0, weight=2)
            row_frame.columnconfigure(1, weight=1)
            row_frame.columnconfigure(2, weight=0)

            label_text = f"{lot['symbol']} ({lot['purchase_date']}) - {lot['shares']} shares"
            ttk.Label(row_frame, text=label_text, background=self.CARD_COLOR).grid(row=0, column=0, sticky="w")
            
            entry = ttk.Entry(row_frame, width=10)
            entry.grid(row=0, column=1, sticky="w")
            entry.insert(0, "0")

            warning_label = ttk.Label(row_frame, image=self.warning_icon, text="", compound="left", style="Warning.TLabel")
            warning_label.grid(row=0, column=2, sticky="w", padx=5)
            warning_label.grid_remove() # Hide it initially

            self.tax_sim_entries[lot['lot_id']] = {'entry': entry, 'warning_label': warning_label}

    def _run_tax_simulation(self):
        """Calculates tax impact with lot-specificity and wash sale detection."""
        total_tax_impact = 0
        try:
            st_rate = float(self.st_rate_var.get()) / 100.0
            lt_rate = float(self.lt_rate_var.get()) / 100.0

            # Get all simulated sales first
            simulated_sales = []
            for lot_id, widgets in self.tax_sim_entries.items():
                shares_to_sell = float(widgets['entry'].get())
                if shares_to_sell > 0:
                    lot_data = next((p for p in self.portfolio["positions"] if p["lot_id"] == lot_id), None)
                    if not lot_data or shares_to_sell > lot_data['shares']:
                        messagebox.showwarning("Invalid Input", f"Shares to sell for lot {lot_id} exceeds holdings.", parent=self)
                        return
                    simulated_sales.append({'lot_id': lot_id, 'shares': shares_to_sell, 'sale_date': datetime.now()})

            # Now iterate and check for wash sales
            for sale in simulated_sales:
                lot_data = next((p for p in self.portfolio["positions"] if p["lot_id"] == sale['lot_id']), None)
                widgets = self.tax_sim_entries[sale['lot_id']]
                
                current_price = self.market_data_cache.get(lot_data['symbol'], {}).get("regularMarketPrice", lot_data["entry_price"])
                gain_loss = (current_price - lot_data["entry_price"]) * sale['shares']
                
                purchase_date = datetime.strptime(lot_data["purchase_date"], '%Y-%m-%d')
                holding_period = (datetime.now() - purchase_date).days
                tax_rate = lt_rate if holding_period > 365 else st_rate
                
                is_wash_sale = False
                if gain_loss < 0:
                    # Check for purchases within 30 days (before or after) the simulated sale
                    for other_lot in self.portfolio["positions"]:
                        if other_lot['symbol'] == lot_data['symbol']:
                            other_purchase_date = datetime.strptime(other_lot['purchase_date'], '%Y-%m-%d')
                            if abs((sale['sale_date'] - other_purchase_date).days) <= 30:
                                is_wash_sale = True
                                break
                
                if is_wash_sale:
                    widgets['warning_label'].grid() # Show the warning
                else:
                    widgets['warning_label'].grid_remove() # Hide the warning
                    total_tax_impact += gain_loss * tax_rate

            color = self.NEGATIVE_COLOR if total_tax_impact > 0 else self.POSITIVE_COLOR
            self.tax_sim_result_lbl.config(text=f"${total_tax_impact:,.2f}", foreground=color)

        except (ValueError, TypeError):
            messagebox.showerror("Invalid Input", "Please check that tax rates and shares to sell are valid numbers.", parent=self)

    def _populate_realized_gains_table(self):
        """Fills the Treeview with the log of realized gains/losses for the year."""
        for i in self.realized_tree.get_children():
            self.realized_tree.delete(i)

        for sale in sorted(self.portfolio.get('realized_gains', []), key=lambda x: x['date'], reverse=True):
            gain_loss = sale['gain_loss']
            tag = 'realized_gain' if gain_loss >= 0 else 'realized_loss'
            
            self.realized_tree.insert("", "end", values=(
                sale['date'],
                sale['symbol'],
                sale['type'],
                f"${gain_loss:,.2f}"
            ), tags=(tag,))
    def _on_mousewheel(self, event, canvas):
        """Handle mouse wheel and trackpad scrolling for a canvas."""
        # FIX: Add a safety check to ensure the canvas widget still exists before
        # trying to scroll it. This prevents errors during view transitions.
        if not canvas.winfo_exists():
            return
            
        # For Windows/macOS, event.delta is used.
        # For Linux, event.num 4 is scroll up, 5 is scroll down.
        if event.num == 4 or event.delta > 0:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5 or event.delta < 0:
            canvas.yview_scroll(1, "units")

    # --- Data Management ---
    # The portfolio data is now structured as a list of individual lots.
    def load_portfolio_data(self):
        """Load initial mock data with multiple tax lots per position."""
        self.portfolio = {
            "positions": [
                # Each dictionary is now a specific purchase lot
                {"lot_id": "aapl1", "symbol": "AAPL", "shares": 20, "entry_price": 150.0, "purchase_date": (datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d')},
                {"lot_id": "aapl2", "symbol": "AAPL", "shares": 30, "entry_price": 180.0, "purchase_date": (datetime.now() - timedelta(days=100)).strftime('%Y-%m-%d')},
                {"lot_id": "msft1", "symbol": "MSFT", "shares": 30, "entry_price": 280.0, "purchase_date": (datetime.now() - timedelta(days=400)).strftime('%Y-%m-%d')},
                {"lot_id": "googl1", "symbol": "GOOGL", "shares": 10, "entry_price": 140.0, "purchase_date": (datetime.now() - timedelta(days=250)).strftime('%Y-%m-%d')},
                {"lot_id": "googl2", "symbol": "GOOGL", "shares": 15, "entry_price": 175.0, "purchase_date": (datetime.now() - timedelta(days=25)).strftime('%Y-%m-%d')}, # Recent purchase for wash sale demo
                {"lot_id": "tsla1", "symbol": "TSLA", "shares": 40, "entry_price": 300.0, "purchase_date": (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')},
            ],
            "goals": [],
            "realized_gains": [
                 {"symbol": "AMD", "gain_loss": -550.75, "date": (datetime.now() - timedelta(days=45)).strftime('%Y-%m-%d'), "type": "Short-Term"},
                 {"symbol": "PYPL", "gain_loss": 1203.40, "date": (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d'), "type": "Long-Term"},
            ]
        }
        self._fetch_market_data()

        if self.active_view_key == "dashboard" and self.is_initial_dashboard_draw_pending:
            self.after(300, self._update_dashboard_drivers_card)




    def start_periodic_updates(self):
        """Start periodic data refresh."""
        self._fetch_market_data()
        
        if self.winfo_exists():
            # Store the ID of the scheduled job
            self.update_job_id = self.after(60000, self.start_periodic_updates)

    def _fetch_market_data(self):
        """Fetch market data in a separate thread."""
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    # --- Replace this method entirely ---
    def _fetch_worker(self):
        from curl_cffi import requests as cffi_requests
        """Worker for fetching market data and logos."""
        for pos in self.portfolio["positions"]:
            symbol = pos["symbol"]
            self.market_data_cache[symbol] = self.api.get_stock_details(symbol)
            
            # Fetch logo only if it's not already in the cache
            if symbol not in self.logo_cache:
                try:
                    url = self.market_data_cache[symbol]['logo_url']
                    # Use curl_cffi to impersonate a browser and avoid being blocked
                    response = cffi_requests.get(url, impersonate="chrome110", timeout=10)
                    
                    if response.status_code == 200:
                        img_data = response.content
                        img = Image.open(BytesIO(img_data))
                        img.thumbnail((24, 24), Image.Resampling.LANCZOS)
                        # Store the PhotoImage object, not the raw image
                        self.logo_cache[symbol] = ImageTk.PhotoImage(img)
                    else:
                        self.logo_cache[symbol] = None # Mark as failed
                except Exception as e:
                    print(f"Could not fetch logo for {symbol}: {e}")
                    self.logo_cache[symbol] = None # Mark as failed

        # After fetching all data, run calculations
        self._process_portfolio_data()
        self._calculate_dashboard_data()

        # Schedule the UI update on the main thread
        self.after(0, self._update_all_views)

    def _update_all_views(self):
        """Update the active view with latest data."""
        if not self.active_view_key or not self.winfo_exists():
            return

        if 'analytics' not in self.analysis_data and self.portfolio["positions"]:
            self._process_portfolio_data()

        if self.active_view_key == "dashboard":
            if hasattr(self, "hero_total_value"): self._update_dashboard_kpis()
            if hasattr(self, "positions_table_frame"): self._update_positions()
            if hasattr(self, "ax_dash"): self._plot_history_area_chart(self.active_timeframe)
            if hasattr(self, "ax_pie"): self._plot_allocation_bars()
            if hasattr(self, "radar_canvas_dash"): self._update_dashboard_drivers_card()

        elif self.active_view_key == "goals":
            if hasattr(self, "goals_container"):
                self._update_goals()
        
        elif self.active_view_key == "analysis":
            self._update_analysis_view_data()
            
        # THIS IS THE MODIFIED PART
        elif self.active_view_key == "tax":
            self._update_tax_view() # Call the new master update method
            
    def _update_dashboard_kpis(self):
        """Updates the new hero snapshot KPI values."""
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", pos["entry_price"]) for pos in self.portfolio["positions"])
        
        # Calculate daily change more robustly
        previous_day_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("previousClose", pos["entry_price"]) for pos in self.portfolio["positions"])
        day_change_usd = total_value - previous_day_value
        day_change_pct = (day_change_usd / previous_day_value * 100) if previous_day_value > 0 else 0
        
        # Update hero labels
        self.hero_total_value.config(text=f"${total_value:,.2f}")
        self.hero_day_change.config(
            text=f"${day_change_usd:+,.2f} ({day_change_pct:+.2f}%) Today",
            foreground=self.POSITIVE_COLOR if day_change_usd >= 0 else self.NEGATIVE_COLOR
        )

    def _plot_history_area_chart(self, timeframe="6M"):
        """Plots a professional-looking area chart with a gradient fill."""
        self.ax_dash.clear()
        self._setup_matplotlib_style(self.fig_dash, self.ax_dash)

        if self.portfolio["positions"]:
            # Data fetching and processing (same as before)
            end_date = datetime.now()
            if timeframe == "1M": start_date = end_date - timedelta(days=30)
            elif timeframe == "6M": start_date = end_date - timedelta(days=180)
            elif timeframe == "1Y": start_date = end_date - timedelta(days=365)
            elif timeframe == "5Y": start_date = end_date - timedelta(days=365*5)
            else: start_date = None # ALL
            
            history_df = self.data_manager.get_portfolio_history(self.portfolio, start_date, end_date)
            self.history_data = history_df # Store for hover
            
            if not history_df.empty:
                line, = self.ax_dash.plot(history_df.index, history_df['value'], color=self.ACCENT_COLOR, lw=2)

                # --- The Gradient Fill ---
                x = history_df.index
                y = history_df['value']
                self.ax_dash.fill_between(x, y, color=self.ACCENT_COLOR, alpha=0.5)

                # Create a gradient effect by layering another fill on top
                self.ax_dash.fill_between(x, y,
                    where=(y > y.min()),
                    interpolate=True,
                    color=self.ACCENT_COLOR,
                    alpha=0.2,
                    zorder=line.get_zorder()-1 # Ensure it's below the line
                )
                self.ax_dash.set_title(f"Portfolio Performance ({timeframe})", fontsize=11, color=self.SECONDARY_TEXT, pad=10)

        # --- Styling ---
        self.ax_dash.spines['top'].set_visible(False)
        self.ax_dash.spines['right'].set_visible(False)
        self.ax_dash.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f'${x/1000:.0f}K'))
        self.ax_dash.tick_params(axis='x', rotation=0, labelsize=9)
        self.ax_dash.tick_params(axis='y', labelsize=9)
        self.ax_dash.grid(axis='y', linestyle='--', color=self.BORDER_COLOR, alpha=0.5)
        # self.fig_dash.tight_layout(pad=2.0) # REMOVED THIS LINE
        self.canvas_dash.draw()

    def _plot_allocation_bars(self):
        """Plots a much cleaner horizontal bar chart for sector allocations."""
        self.ax_pie.clear()
        self._setup_matplotlib_style(self.fig_pie, self.ax_pie)

        if not self.sector_details:
            self.ax_pie.text(0.5, 0.5, "No data for allocation", ha='center', va='center', transform=self.ax_pie.transAxes)
        else:
            # Prepare data
            sorted_sectors = sorted(self.sector_details.items(), key=lambda item: item[1]['value'], reverse=True)
            sectors = [item[0] for item in sorted_sectors]
            percentages = [item[1]['percentage'] * 100 for item in sorted_sectors]
            colors = [item[1]['color'] for item in sorted_sectors]

            # Plot bars
            bars = self.ax_pie.barh(sectors, percentages, color=colors, height=0.6)
            self.ax_pie.invert_yaxis() # Display largest at the top

            # Add percentage labels on the bars
            for bar in bars:
                width = bar.get_width()
                label_x_pos = width + 0.5
                self.ax_pie.text(label_x_pos, bar.get_y() + bar.get_height()/2., f'{width:.1f}%', 
                                va='center', ha='left', color=self.TEXT_COLOR, fontsize=9)

        # --- Styling ---
        self.ax_pie.spines['top'].set_visible(False)
        self.ax_pie.spines['right'].set_visible(False)
        self.ax_pie.spines['bottom'].set_visible(False)
        self.ax_pie.spines['left'].set_color(self.BORDER_COLOR)
        self.ax_pie.xaxis.set_visible(False) # The labels on bars are enough
        self.ax_pie.tick_params(axis='y', length=0, labelsize=9, colors=self.SECONDARY_TEXT)
        self.fig_pie.tight_layout(pad=1.5)
        
        self.canvas_pie.draw()

    def _build_positions_card(self, parent):
        """Builds the new custom-styled positions table with a precise grid layout."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=20)
        card.grid(row=2, column=0, sticky="nsew")
        card.rowconfigure(2, weight=1) # The canvas with rows will expand
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="Current Positions", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 15))

        # --- Custom Table Header ---
        # This frame's grid configuration will be the master layout for all data rows.
        self.positions_header = ttk.Frame(card, style="Card.TFrame", padding=(10, 5))
        self.positions_header.grid(row=1, column=0, sticky="ew")
        
        # Define column weights for a balanced layout
        self.positions_header.columnconfigure(0, weight=3)  # Symbol
        self.positions_header.columnconfigure(1, weight=2)  # Shares
        self.positions_header.columnconfigure(2, weight=2)  # Price
        self.positions_header.columnconfigure(3, weight=3)  # Value
        self.positions_header.columnconfigure(4, weight=2)  # Day %

        headers = ["Symbol", "Shares", "Price", "Value", "Day %"]
        for i, text in enumerate(headers):
            anchor = "w" if text == "Symbol" else "e"
            lbl = ttk.Label(self.positions_header, text=text, style="Secondary.TLabel", font=self.FONT_BOLD, background=self.CARD_COLOR, anchor=anchor)
            lbl.grid(row=0, column=i, sticky="ew", padx=(0, 20))

        # --- Canvas and Scrollable Frame for Table Rows ---
        canvas = tk.Canvas(card, background=self.CARD_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(card, orient="vertical", command=canvas.yview)
        self.positions_table_frame = ttk.Frame(canvas, style="Card.TFrame")

        self.positions_table_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.positions_table_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=2, column=0, sticky="nsew")
        scrollbar.grid(row=2, column=1, sticky="ns")
        card.rowconfigure(2, weight=1)

        self.position_context_menu = tk.Menu(self, tearoff=0, background=self.CARD_COLOR, foreground=self.TEXT_COLOR)
        self.position_context_menu.add_command(label="Edit Position", command=self._edit_position)
        self.position_context_menu.add_command(label="Remove Position", command=self._remove_position)

    def _update_positions(self):
        """Populates the positions table with a perfectly aligned grid layout."""
        for widget in self.positions_table_frame.winfo_children():
            widget.destroy()

        if not self.portfolio["positions"]:
            ttk.Label(self.positions_table_frame, text="No positions added yet.", style="Secondary.TLabel").pack(pady=20)
            return

        for i, pos in enumerate(self.portfolio["positions"]):
            market_info = self.market_data_cache.get(pos["symbol"], {})
            price = market_info.get("regularMarketPrice", pos["entry_price"])
            value = pos["shares"] * price
            day_change = market_info.get("regularMarketChangePercent", 0)

            # Each row frame gets the same grid configuration as the header
            row_frame = ttk.Frame(self.positions_table_frame, style="Card.TFrame", padding=(10, 15))
            row_frame.pack(fill="x", expand=True)

            row_frame.columnconfigure(0, weight=3)  # Symbol
            row_frame.columnconfigure(1, weight=2)  # Shares
            row_frame.columnconfigure(2, weight=2)  # Price
            row_frame.columnconfigure(3, weight=3)  # Value
            row_frame.columnconfigure(4, weight=2)  # Day %

            # --- Widgets are now placed on this new grid ---
            # 1. Symbol (Logo + Ticker), aligned left
            symbol_frame = ttk.Frame(row_frame, style="Card.TFrame")

            # --- THIS IS THE FIX ---
            # By changing sticky="w" to sticky="ew", the symbol_frame now expands
            # to fill the entire width of its column, just like the header does.
            symbol_frame.grid(row=0, column=0, sticky="ew", padx=(0, 20))
            # --- END OF FIX ---
            
            logo_image = self.logo_cache.get(pos["symbol"])
            if logo_image:
                logo_label = ttk.Label(symbol_frame, image=logo_image, background=self.CARD_COLOR)
                logo_label.pack(side="left", padx=(0, 8))
            
            ttk.Label(symbol_frame, text=pos["symbol"], font=self.FONT_BOLD, background=self.CARD_COLOR).pack(side="left")

            # 2. Other data points, aligned right
            ttk.Label(row_frame, text=f"{pos['shares']}", background=self.CARD_COLOR, anchor="e").grid(row=0, column=1, sticky="ew", padx=(0, 20))
            ttk.Label(row_frame, text=f"${price:,.2f}", background=self.CARD_COLOR, anchor="e").grid(row=0, column=2, sticky="ew", padx=(0, 20))
            ttk.Label(row_frame, text=f"${value:,.2f}", font=self.FONT_BOLD, background=self.CARD_COLOR, anchor="e").grid(row=0, column=3, sticky="ew", padx=(0, 20))
            
            change_color = self.POSITIVE_COLOR if day_change >= 0 else self.NEGATIVE_COLOR
            day_change_label = ttk.Label(row_frame, text=f"{day_change:+.2f}%", foreground=change_color, background=self.CARD_COLOR, anchor="e")
            day_change_label.grid(row=0, column=4, sticky="ew", padx=(0, 20))
            
            # Hover and Right-Click functionality
            def on_enter(e, rf=row_frame): rf.configure(style="Hover.Card.TFrame")
            def on_leave(e, rf=row_frame): rf.configure(style="Card.TFrame")

            all_widgets = [row_frame] + list(row_frame.winfo_children())
            all_widgets.extend(list(symbol_frame.winfo_children()))

            for widget in all_widgets:
                widget.bind("<Enter>", on_enter)
                widget.bind("<Leave>", on_leave)
                widget.bind("<Button-3>", lambda event, s=pos["symbol"]: self._on_position_right_click(event, s))

        style = ttk.Style(self)
        style.configure("Hover.Card.TFrame", background="#2F2F2F")

    def _update_goals(self):
        """Final update to goals display with a robust layout and Monte Carlo integration."""
        for widget in self.goals_container.winfo_children():
            widget.destroy()

        if not self.portfolio["goals"]:
            ttk.Label(self.goals_container, text="No goals set. Click '+ Add Goal' to start.", style="Secondary.TLabel").pack(pady=20, padx=20)
            return

        for goal in self.portfolio["goals"]:
            # The change is in the line below: padx=10 has been removed.
            card = ttk.Frame(self.goals_container, style="Card.TFrame", padding=(20, 15))
            card.pack(fill="x", pady=8) # FIX: Removed padx=10
            card.columnconfigure(0, weight=1)

            # --- Header, Progress Bar, etc. (as before) ---
            header_frame = ttk.Frame(card, style="Card.TFrame")
            header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
            header_frame.columnconfigure(0, weight=1)
            ttk.Label(header_frame, text=goal["name"], style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w")
            button_frame = ttk.Frame(header_frame, style="Card.TFrame")
            button_frame.grid(row=0, column=1, sticky="e")
            ttk.Button(button_frame, text="⚙ Edit", style="Timeframe.TButton", command=lambda g=goal: self._edit_goal(g)).pack(side="left", padx=5)
            ttk.Button(button_frame, text="🗑 Delete", style="Timeframe.TButton", command=lambda g=goal: self._remove_goal(g)).pack(side="left")
            sugg_btn = ttk.Button(button_frame, text="💡 Suggestions", style="Timeframe.TButton", command=lambda g=goal, b=button_frame: self._show_suggestion_menu(g, b))
            sugg_btn.pack(side="left", padx=5)

            target_text = f"Target: ${goal['target_amount']:,.2f} by {goal['target_date']}"
            ttk.Label(card, text=target_text, style="Secondary.TLabel").grid(row=1, column=0, sticky="w")
            progress = (goal["current_amount"] / goal["target_amount"]) * 100 if goal["target_amount"] > 0 else 0
            ttk.Progressbar(card, value=progress, style="Green.Horizontal.TProgressbar").grid(row=2, column=0, sticky="ew", pady=(5, 15))

            metrics_container = ttk.Frame(card, style="Card.TFrame")
            metrics_container.grid(row=3, column=0, sticky="ew")

            prob_value_widget = self._create_metric_display(metrics_container, "Success Probability", "Not Run Yet", 0, 0)
            status_value_widget = self._create_metric_display(metrics_container, "Status", "Run Simulation", 0, 1)

            card_widgets = {'prob_value': prob_value_widget, 'status_value': status_value_widget}

            # --- DYNAMIC BUTTON LOGIC (FIXED) ---
            goal_id = goal['name'] + goal['target_date']
            if goal_id in self.goal_simulation_results:
                # If results exist, create the "View Analysis" button
                sim_button = ttk.Button(card, text="View Analysis", style="Accent.TButton", command=lambda g=goal: self._show_goal_analysis(g))
                # *** FIX IS HERE: Add the button to the dictionary BEFORE calling the update function ***
                card_widgets['sim_button'] = sim_button
                # And immediately update the status from stored results
                self._update_simulation_result(goal, card_widgets, self.goal_simulation_results[goal_id])
            else:
                # Otherwise, create the "Run Simulation" button
                sim_button = ttk.Button(card, text="Run Monte Carlo Simulation", style="Accent.TButton", command=lambda g=goal, w=card_widgets: self._start_goal_simulation_thread(g, w))
                # Add the button to the dictionary
                card_widgets['sim_button'] = sim_button

            sim_button.grid(row=4, column=0, sticky="ew", pady=(15, 0))

    def _clear_analysis_pane(self):
        """Clears the analysis pane and shows the placeholder text."""
        for widget in self.analysis_frame.winfo_children():
            widget.destroy()
        
        # Re-create the placeholder
        self.analysis_placeholder = ttk.Label(self.analysis_frame, text="Run a simulation to view its analysis here.", style="Header.TLabel", justify="center", background=self.CARD_COLOR)
        self.analysis_placeholder.pack(expand=True)
        self.active_analysis_goal = None


    def _scan_tax_losses(self):
        """Scan for tax-loss opportunities."""
        losses = [f"{pos['symbol']}: ${((self.market_data_cache.get(pos['symbol'], {}).get('regularMarketPrice', pos['entry_price']) - pos['entry_price']) * pos['shares']):,.2f}" 
                  for pos in self.portfolio["positions"] if self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", pos["entry_price"]) < pos["entry_price"]]
        self.tlh_label.config(text="Losses:\n" + "\n".join(losses) if losses else "No opportunities found.")

    def _update_tax_dropdown(self):
        """Update tax position dropdown."""
        self.tax_menu["values"] = [pos["symbol"] for pos in self.portfolio["positions"]]
        if self.portfolio["positions"]:
            self.tax_pos_var.set(self.portfolio["positions"][0]["symbol"])

    def _calculate_tax_impact(self):
        """Calculate tax impact of a sale."""
        symbol = self.tax_pos_var.get()
        try:
            shares = float(self.tax_shares.get())
            pos = next(p for p in self.portfolio["positions"] if p["symbol"] == symbol)
            if shares > pos["shares"]:
                raise ValueError
            price = self.market_data_cache.get(symbol, {}).get("regularMarketPrice", pos["entry_price"])
            gain = (price - pos["entry_price"]) * shares * 0.15  # 15% tax rate
            self.tax_result.config(text=f"${gain:,.2f}", foreground=self.NEGATIVE_COLOR if gain > 0 else self.POSITIVE_COLOR)
        except (ValueError, StopIteration):
            messagebox.showerror("Error", "Invalid input or position not found.")

    def _create_metric_display(self, parent, title, value, row, col, align="w"):
        """Creates a consistent frame for displaying a title and a value."""
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=row, column=col, sticky=align, pady=(10, 0))
        
        ttk.Label(frame, text=title, style="Secondary.TLabel", background=self.CARD_COLOR).pack(anchor=align)
        value_label = ttk.Label(frame, text=value, font=self.FONT_HEADER, background=self.CARD_COLOR)
        value_label.pack(anchor=align)
        return value_label # Return the label for further configuration if needed

    

    # --- Dialogs ---
    def _open_add_position_dialog(self):
        """Open dialog to add a position."""
        dialog = PositionDialog(self)
        if dialog.result:
            self.portfolio["positions"].append(dialog.result)
            self._fetch_market_data()

    def _open_add_goal_dialog(self):
        """Open the custom dialog to add a new goal, pre-filled with default data."""
        
        # --- Create a set of default data for auto-filling ---
        default_goal_data = {
            "name": f"New Goal - {np.random.randint(100, 999)}",
            "target_amount": round(np.random.uniform(25000, 100000), -3),
            "current_amount": round(np.random.uniform(1000, 5000), -2),
            "monthly_contribution": round(np.random.uniform(200, 1000), -2),
            "target_date": (datetime.now() + timedelta(days=np.random.randint(365*3, 365*10))).strftime('%Y-%m-%d'),
            "annual_return": 7.0,
            "volatility": 15.0
        }

        dialog = GoalDialog(self, title="Add New Financial Goal", initial_data=default_goal_data)
        if dialog.result:
            self.portfolio["goals"].append(dialog.result)
            self._update_all_views()
    # --- Chart Interaction ---
    def _setup_chart_hover(self):
        """Sets up the new interactive crosshair for the main performance chart."""
        self.chart_hover_line = self.ax_dash.axvline(x=self.ax_dash.get_xlim()[0], color=self.ACCENT_COLOR, lw=0.8, linestyle='--', zorder=0)
        self.chart_hover_text = self.ax_dash.text(0.02, 0.98, '', transform=self.ax_dash.transAxes,
                                                  ha='left', va='top', fontsize=9,
                                                  bbox=dict(boxstyle='round,pad=0.3', fc=self.CARD_COLOR, ec='none', alpha=0.8))
        self.chart_hover_line.set_visible(False)
        self.chart_hover_text.set_visible(False)

        def on_hover(event):
            if not event.inaxes:
                if self.chart_hover_line.get_visible():
                    self.chart_hover_line.set_visible(False)
                    self.chart_hover_text.set_visible(False)
                    self.canvas_dash.draw_idle()
                return

            visible = True
            x, y = event.xdata, event.ydata
            self.chart_hover_line.set_xdata([x])

            # Find the closest data point to the hover event
            if hasattr(self, 'history_data') and not self.history_data.empty:
                # Convert matplotlib float date to datetime object
                date_obj = mdates.num2date(x).replace(tzinfo=None)
                # Find the index of the closest date in the dataframe
                closest_idx = self.history_data.index.get_indexer([date_obj], method='nearest')[0]
                # Get the actual data for that point
                actual_date = self.history_data.index[closest_idx]
                actual_value = self.history_data.iloc[closest_idx]['value']
                
                # Update the text with the actual data
                self.chart_hover_text.set_text(f"{actual_date.strftime('%b %d, %Y')}\nValue: ${actual_value:,.2f}")
            
            if self.chart_hover_line.get_visible() != visible:
                self.chart_hover_line.set_visible(visible)
                self.chart_hover_text.set_visible(visible)

            self.canvas_dash.draw_idle()

        def on_leave(event):
            self.chart_hover_line.set_visible(False)
            self.chart_hover_text.set_visible(False)
            self.canvas_dash.draw_idle()

        self.canvas_dash.mpl_connect('motion_notify_event', on_hover)
        self.canvas_dash.mpl_connect('axes_leave_event', on_leave)


    def _on_chart_hover(self, event):
        """Handle chart hover event."""
        if event.inaxes != self.ax_dash:
            self._on_chart_leave(event)
            return
        xdata = mdates.date2num(self.ax_dash.lines[0].get_xdata())
        index = np.searchsorted(xdata, event.xdata)
        if index >= len(xdata):
            index = len(xdata) - 1
        date = mdates.num2date(xdata[index]).strftime("%Y-%m-%d")
        value = self.ax_dash.lines[0].get_ydata()[index]
        self.chart_hover_elements["line"].set_xdata([xdata[index]])
        self.chart_hover_elements["line"].set_visible(True)
        self.chart_hover_elements["text"].set_text(f"{date}\n${value:,.2f}")
        self.chart_hover_elements["text"].set_visible(True)
        self.canvas_dash.draw_idle()

    def _on_chart_leave(self, event):
        """Handle chart leave event."""
        self.chart_hover_elements["line"].set_visible(False)
        self.chart_hover_elements["text"].set_visible(False)
        self.canvas_dash.draw_idle()

    def _calculate_required_contribution(self, goal):
        """Calculates the monthly contribution required to meet a goal."""
        try:
            today = datetime.now()
            target_date = datetime.strptime(goal["target_date"], '%Y-%m-%d')
            months_remaining = (target_date.year - today.year) * 12 + (target_date.month - today.month)
            if months_remaining <= 0: return 0

            annual_return_rate = goal["annual_return"] / 100
            monthly_rate = (1 + annual_return_rate)**(1/12) - 1

            # Required future value from contributions
            fv_needed = goal["target_amount"] - (goal["current_amount"] * ((1 + monthly_rate) ** months_remaining))
            if fv_needed <= 0: return 0 # Goal already met

            # Annuity payment formula to find the required contribution
            if monthly_rate > 0:
                required_pmt = fv_needed / ((((1 + monthly_rate) ** months_remaining) - 1) / monthly_rate)
            else: # No interest rate
                required_pmt = fv_needed / months_remaining
            return required_pmt
        except (ValueError, ZeroDivisionError, KeyError):
            return 0

    def _edit_goal(self, goal_to_edit):
        """Opens the custom dialog to edit an existing goal and resets its state."""
        dialog = GoalDialog(self, title=f"Edit {goal_to_edit['name']}", initial_data=goal_to_edit)
        
        if dialog.result:
            goal_id = goal_to_edit['name'] + goal_to_edit['target_date']
            if goal_id in self.goal_simulation_results:
                del self.goal_simulation_results[goal_id]

            if self.active_analysis_goal and (self.active_analysis_goal['name'] == goal_to_edit['name']):
                self._clear_analysis_pane()

            for i, goal in enumerate(self.portfolio["goals"]):
                if goal["name"] == goal_to_edit["name"] and goal["target_date"] == goal_to_edit["target_date"]:
                    self.portfolio["goals"][i] = dialog.result
                    break
                    
            self._update_all_views()

    def _remove_goal(self, goal_to_remove):
        """Removes a specified goal after confirmation."""
        confirm = messagebox.askyesno(
            "Confirm Removal",
            f"Are you sure you want to remove the goal '{goal_to_remove['name']}'?",
            parent=self
        )
        if confirm:
            self.portfolio["goals"] = [
                g for g in self.portfolio["goals"] if not (g["name"] == goal_to_remove["name"] and g["target_date"] == goal_to_remove["target_date"])
            ]
            self._update_all_views()
            
    def _run_monte_carlo_simulation(self, goal, card_widgets, num_simulations=200):
        """
        Runs an advanced Monte Carlo simulation to generate a "data cube" of pre-calculated
        results for various contributions and time horizons, enabling real-time "what-if" analysis.
        """
        try:
            today = datetime.now()
            target_date = datetime.strptime(goal["target_date"], '%Y-%m-%d')
            base_months = (target_date.year - today.year) * 12 + (target_date.month - today.month)

            # Define the range for our "what-if" parameters
            contrib_step = max(50, int(goal['monthly_contribution'] * 0.1))
            contrib_range = np.arange(max(0, goal['monthly_contribution'] - 5 * contrib_step), goal['monthly_contribution'] + 10 * contrib_step, contrib_step)
            
            # Time horizon range: from 2 years less to 5 years more
            horizon_range = np.arange(max(12, base_months - 24), base_months + 61, 12)

            data_cube = {} # To store results: {(contrib, horizon): [final_values]}
            
            mean_monthly_return = (goal["annual_return"] / 100) / 12
            monthly_volatility = (goal["volatility"] / 100) / np.sqrt(12)

            # Pre-calculate all scenarios
            for contrib in contrib_range:
                for horizon_months in horizon_range:
                    final_values = []
                    for _ in range(num_simulations):
                        val = goal["current_amount"]
                        for _ in range(horizon_months):
                            ret = np.random.normal(mean_monthly_return, monthly_volatility)
                            val = (val + contrib) * (1 + ret)
                        final_values.append(val)
                    data_cube[(contrib, horizon_months)] = final_values
            
            # Find the success rate for the base case (the user's actual inputs)
            base_final_values = data_cube.get((goal['monthly_contribution'], base_months), data_cube.get(min(data_cube.keys(), key=lambda k: abs(k[0]-goal['monthly_contribution'])+abs(k[1]-base_months))))
            success_rate = (np.sum(np.array(base_final_values) >= goal["target_amount"]) / num_simulations) * 100

            result = {
                "success_rate": success_rate, "data_cube": data_cube, "contrib_range": contrib_range,
                "horizon_range": horizon_range, "base_months": base_months
            }
            self.after(0, lambda: self._update_simulation_result(goal, card_widgets, result))

        except Exception as e:
            print(f"Monte Carlo Error: {e}")
            self.after(0, lambda: self._update_simulation_result(goal, card_widgets, {"success_rate": -1}))

    def _start_goal_simulation_thread(self, goal, card_widgets):
        """Starts the Monte Carlo simulation for a goal in a separate thread."""
        card_widgets['sim_button'].config(state="disabled", text="Running Simulation...")
        card_widgets['prob_value'].config(text="Running...", foreground=self.SECONDARY_TEXT)
        card_widgets['status_value'].config(text="Simulating...", foreground=self.SECONDARY_TEXT)
        
        thread = threading.Thread(target=self._run_monte_carlo_simulation, args=(goal, card_widgets), daemon=True)
        thread.start()

    def _update_simulation_result(self, goal, card_widgets, result):
        """Updates the goal card and stores the full simulation result."""
        goal_id = goal['name'] + goal['target_date']
        self.goal_simulation_results[goal_id] = result
        success_rate = result.get("success_rate", -1)

        if card_widgets['sim_button'].winfo_exists():
            card_widgets['sim_button'].config(state="normal", text="View Analysis", command=lambda g=goal: self._show_goal_analysis(g))

        if success_rate == -1:
            prob_text, status_text, color = "Error", "Calculation Error", self.NEGATIVE_COLOR
        else:
            prob_text = f"{success_rate:.1f}%"
            if success_rate > 85: status_text, color = "High Confidence", self.POSITIVE_COLOR
            elif success_rate > 60: status_text, color = "On Track", self.POSITIVE_COLOR
            elif success_rate > 40: status_text, color = "Uncertain", "#f0c420"
            else: status_text, color = "Needs Attention", self.NEGATIVE_COLOR
        
        if card_widgets['prob_value'].winfo_exists():
            card_widgets['prob_value'].config(text=prob_text, foreground=color)
        if card_widgets['status_value'].winfo_exists():
            card_widgets['status_value'].config(text=status_text, foreground=color)

    def _show_goal_analysis(self, goal):
        """
        REWRITTEN: Display an interactive analysis for a goal with a robust,
        foolproof chart embedding and update mechanism.
        """
        self.active_analysis_goal = goal
        goal_id = goal['name'] + goal['target_date']
        self.goal_analysis_data = self.goal_simulation_results.get(goal_id)
        if not self.goal_analysis_data or 'data_cube' not in self.goal_analysis_data:
            messagebox.showerror("Analysis Error", "Simulation data is missing or corrupt. Please run the simulation again.", parent=self)
            return

        # --- 1. Clear previous content ---
        for widget in self.analysis_frame.winfo_children():
            widget.destroy()

        # --- 2. Configure main layout ---
        self.analysis_frame.rowconfigure(0, weight=1)    # Notebook area expands
        self.analysis_frame.rowconfigure(1, weight=0)    # Controls area is fixed
        self.analysis_frame.columnconfigure(0, weight=1)

        # --- 3. Create Notebook for chart tabs ---
        notebook = ttk.Notebook(self.analysis_frame)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))

        # Create tab frames
        proj_tab = ttk.Frame(notebook, padding=5)
        breakdown_tab = ttk.Frame(notebook, padding=5)
        dist_tab = ttk.Frame(notebook, padding=5)
        
        notebook.add(proj_tab, text="Growth Projection")
        notebook.add(breakdown_tab, text="Contribution Breakdown")
        notebook.add(dist_tab, text="Outcomes Distribution")

        # --- 4. FOOLPROOF CHART EMBEDDING ---
        # Create canvases for the figures we already created in __init__
        self.fig_interactive.subplots_adjust(left=0.15, bottom=0.18, right=0.95, top=0.90)
        self.canvas_interactive = FigureCanvasTkAgg(self.fig_interactive, master=proj_tab)
        self.canvas_interactive.get_tk_widget().pack(fill="both", expand=True)

        self.fig_breakdown.subplots_adjust(left=0.15, bottom=0.18, right=0.95, top=0.90)
        self.canvas_breakdown = FigureCanvasTkAgg(self.fig_breakdown, master=breakdown_tab)
        self.canvas_breakdown.get_tk_widget().pack(fill="both", expand=True)

        self.fig_dist.subplots_adjust(left=0.15, bottom=0.18, right=0.95, top=0.90)
        self.canvas_dist = FigureCanvasTkAgg(self.fig_dist, master=dist_tab)
        self.canvas_dist.get_tk_widget().pack(fill="both", expand=True)
        
        # --- 5. Build Controls Panel ---
        controls_card = ttk.Frame(self.analysis_frame, style="Card.TFrame", padding=15)
        controls_card.grid(row=1, column=0, sticky="ew", pady=(5, 10), padx=10)
        controls_card.columnconfigure(0, weight=1)
        controls_card.columnconfigure(1, weight=1)
        
        # Left controls (sliders)
        left_controls = ttk.Frame(controls_card, style="Card.TFrame")
        left_controls.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_controls.columnconfigure(0, weight=1)
        
        # --- THIS IS THE FIX ---
        # The next 3 lines now correctly read from `self.goal_analysis_data`
        c_range = self.goal_analysis_data['contrib_range']
        self.contrib_slider = self._create_slider(left_controls, "Monthly Contribution", c_range[0], c_range[-1], goal['monthly_contribution'], 0)
        h_range = self.goal_analysis_data['horizon_range']
        self.horizon_slider = self._create_slider(left_controls, "Time Horizon (Years)", h_range[0]/12, h_range[-1]/12, self.goal_analysis_data['base_months']/12, 1)

        # Right controls (metrics and actions)
        right_controls = ttk.Frame(controls_card, style="Card.TFrame")
        right_controls.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right_controls.columnconfigure(0, weight=1)

        # Lump sum input
        lump_sum_frame = ttk.Frame(right_controls, style="Card.TFrame")
        lump_sum_frame.grid(row=0, column=0, sticky="ew", pady=(0,5))
        ttk.Label(lump_sum_frame, text="Add Lump Sum ($):", background=self.CARD_COLOR).pack(side="left", padx=(0,5))
        self.lump_sum_var = tk.StringVar(value="0")
        lump_sum_entry = ttk.Entry(lump_sum_frame, textvariable=self.lump_sum_var)
        lump_sum_entry.pack(side="left", fill="x", expand=True)
        lump_sum_entry.bind("<KeyRelease>", self._on_what_if_update)

        # Metrics display
        stats_frame = ttk.Frame(right_controls, style="Card.TFrame")
        stats_frame.grid(row=1, column=0, sticky="ew", pady=5)
        stats_frame.columnconfigure((0,1), weight=1)
        self.analysis_prob_lbl = self._create_metric_display(stats_frame, "Success Probability", "", 0, 0, "w")
        self.analysis_median_lbl = self._create_metric_display(stats_frame, "Median Outcome", "", 0, 1, "w")

        # Apply button
        apply_btn = ttk.Button(right_controls, text="Apply These Parameters to Goal", style="Accent.TButton", command=self._apply_what_if_parameters)
        apply_btn.grid(row=2, column=0, sticky="ew", pady=(10,0))
        
        # --- 6. Trigger the first draw ---
        self.update()
        self._on_what_if_update()  

    def _on_what_if_update(self, *args):
        """
        REVISED: The single, robust handler for updating all 'What-If' analysis.
        It calculates data, then calls the stateless plotting functions, and finally draws.
        """
        if not all([self.active_analysis_goal, self.goal_analysis_data, hasattr(self, 'contrib_slider')]):
            return

        try:
            # --- 1. Get current values from controls ---
            goal = self.active_analysis_goal
            contrib_val = self.contrib_slider.get()
            horizon_years = self.horizon_slider.get()
            horizon_months = int(horizon_years * 12)
            lump_sum = float(self.lump_sum_var.get() or "0")

            # --- 2. Find the closest pre-calculated data ---
            closest_contrib = min(self.goal_analysis_data['contrib_range'], key=lambda x: abs(x - contrib_val))
            closest_horizon = min(self.goal_analysis_data['horizon_range'], key=lambda x: abs(x - horizon_months))
            final_values = np.array(self.goal_analysis_data['data_cube'][(closest_contrib, closest_horizon)]) + lump_sum

            # --- 3. Update text-based metrics ---
            success_rate = (np.sum(final_values >= goal["target_amount"]) / len(final_values)) * 100
            median_outcome = np.median(final_values)
            self.analysis_prob_lbl.config(text=f"{success_rate:.1f}%")
            self.analysis_median_lbl.config(text=f"${median_outcome:,.2f}")

            # --- 4. Call stateless plotting functions to update charts ---
            self._plot_interactive_projection(goal, final_values, horizon_months, lump_sum)
            self._plot_contribution_breakdown(goal, final_values, horizon_months, lump_sum, contrib_val)
            self._plot_outcomes_histogram(final_values, goal)

        except (ValueError, TclError, KeyError) as e:
            # This can happen if the view is destroyed while an update is pending.
            print(f"What-if update error (can be ignored if closing view): {e}")


    def _plot_interactive_projection(self, goal, final_values, horizon_months, lump_sum):
        """REWRITTEN: Stateless function to draw the growth projection chart with full theming."""
        ax = self.ax_interactive
        ax.clear()
        self._setup_matplotlib_style(self.fig_interactive, ax) # Apply theme

        median = np.median(final_values)
        p10 = np.percentile(final_values, 10)
        p90 = np.percentile(final_values, 90)
        x_axis = np.arange(horizon_months + 1) / 12 if horizon_months > 0 else np.array([0])
        initial_value = goal['current_amount'] + lump_sum

        # Plot data
        ax.plot(x_axis, np.linspace(initial_value, median, len(x_axis)), color="#ffcc00", label="Median Path", zorder=10)
        ax.fill_between(x_axis,
                        np.linspace(initial_value, p10, len(x_axis)),
                        np.linspace(initial_value, p90, len(x_axis)),
                        color=self.ACCENT_COLOR, alpha=0.3, label="10th-90th Percentile", zorder=5)
        ax.axhline(y=goal['target_amount'], color=self.NEGATIVE_COLOR, linestyle=":", label=f"Target: ${goal['target_amount']:,.0f}")

        # THEME FIX: Apply theme colors to all text elements
        ax.set_title("Growth Projection", color=self.TEXT_COLOR)
        ax.set_xlabel("Years", color=self.SECONDARY_TEXT)
        ax.set_ylabel("Portfolio Value ($)", color=self.SECONDARY_TEXT)
        legend = ax.legend(loc="upper left", facecolor=self.CARD_COLOR, edgecolor=self.BORDER_COLOR)
        for text in legend.get_texts():
            text.set_color(self.TEXT_COLOR)

        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.3)
        ax.set_xlim(0, max(1, x_axis[-1]) if len(x_axis) > 1 else 1)
        ax.set_ylim(bottom=0)

        self.canvas_interactive.draw()

    def _plot_contribution_breakdown(self, goal, final_values, horizon_months, lump_sum, contrib_val):
        """REWRITTEN: Stateless function to draw the contribution breakdown chart with full theming."""
        ax = self.ax_breakdown
        ax.clear()
        self._setup_matplotlib_style(self.fig_breakdown, ax) # Apply theme

        initial_value = goal['current_amount'] + lump_sum
        median_path = np.linspace(initial_value, np.median(final_values), horizon_months + 1)
        x_axis = np.arange(horizon_months + 1) / 12 if horizon_months > 0 else np.array([0])

        contributions_path = [initial_value + (contrib_val * m) for m in range(horizon_months + 1)]
        growth_path = median_path - contributions_path

        # Plot data
        ax.stackplot(x_axis, contributions_path, growth_path,
                     labels=['Principal & Contributions', 'Simulated Growth'],
                     colors=[self.ACCENT_COLOR, self.POSITIVE_COLOR],
                     alpha=0.8)

        # THEME FIX: Apply theme colors to all text elements
        ax.set_title("Source of Final Value (Median)", color=self.TEXT_COLOR)
        ax.set_xlabel("Years", color=self.SECONDARY_TEXT)
        ax.set_ylabel("Portfolio Value ($)", color=self.SECONDARY_TEXT)
        legend = ax.legend(loc="upper left", facecolor=self.CARD_COLOR, edgecolor=self.BORDER_COLOR)
        for text in legend.get_texts():
            text.set_color(self.TEXT_COLOR)

        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.3)
        ax.set_xlim(0, max(1, x_axis[-1]) if len(x_axis) > 1 else 1)
        ax.set_ylim(bottom=0)

        self.canvas_breakdown.draw()


    def _plot_outcomes_histogram(self, final_values, goal):
        """REWRITTEN: Stateless function to draw the outcomes distribution chart with full theming."""
        ax = self.ax_dist
        ax.clear()
        self._setup_matplotlib_style(self.fig_dist, ax) # Apply theme

        # Plot data
        ax.hist(final_values, bins=50, color=self.ACCENT_COLOR, alpha=0.75, density=True)

        median = np.median(final_values)
        ax.axvline(median, color="#ffcc00", lw=2, label=f"Median: ${median:,.0f}")
        ax.axvline(goal['target_amount'], color="white", linestyle=":", lw=2, label=f"Target: ${goal['target_amount']:,.0f}")

        # THEME FIX: Apply theme colors to all text elements
        ax.set_title("Distribution of Final Portfolio Values", color=self.TEXT_COLOR)
        ax.set_xlabel("Final Value ($)", color=self.SECONDARY_TEXT)
        ax.set_ylabel("Probability Density", color=self.SECONDARY_TEXT)
        legend = ax.legend(loc="upper right", facecolor=self.CARD_COLOR, edgecolor=self.BORDER_COLOR)
        for text in legend.get_texts():
            text.set_color(self.TEXT_COLOR)

        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.3)
        ax.set_yticklabels([])
        ax.set_ylim(bottom=0)

        self.canvas_dist.draw()
        
    def _force_widget_configure_event(self, widget):
        """Force a <Configure> event to make Tkinter propagate geometry properly."""
        widget.event_generate("<Configure>")
        widget.update_idletasks()

    def _force_chart_draw(self, canvas, fig):
        """Redraws the canvas with tight layout after geometry is finalized."""
        def redraw():
            try:
                fig.tight_layout(pad=1.2)
                canvas.draw()
            except Exception as e:
                print(f"Chart draw error: {e}")
        self.after(100, redraw)


    def _embed_matplotlib_canvas(self, fig, parent):
        """Embed a Matplotlib figure in a Tkinter frame with proper resizing."""
        canvas = FigureCanvasTkAgg(fig, master=parent)
        widget = canvas.get_tk_widget()
        widget.pack(fill="both", expand=True)

        # Set initial size based on widget dimensions after layout
        def set_initial_size():
            widget.update_idletasks()
            width = max(widget.winfo_width(), 100)  # Minimum size to avoid zero
            height = max(widget.winfo_height(), 100)
            fig.set_size_inches(width / fig.dpi, height / fig.dpi)

        self.after(50, set_initial_size)

        # Resize handler
        def on_resize(event):
            if event.width > 10 and event.height > 10:  # Avoid invalid sizes
                fig.set_size_inches(event.width / fig.dpi, event.height / fig.dpi)
                canvas.draw()

        widget.bind("<Configure>", on_resize)
        return canvas

    def _find_required_contribution_for_target(self, goal, target_prob, dialog):
        """
        Worker function (run in a thread) to find the monthly contribution
        needed to hit a target success probability.
        """
        try:
            current_contrib = goal['monthly_contribution']
            test_contrib = current_contrib
            increment = max(50, current_contrib * 0.1) # Start with a reasonable increment
            
            # Use a simplified, non-UI version of the Monte Carlo logic
            today = datetime.now()
            target_date = datetime.strptime(goal["target_date"], '%Y-%m-%d')
            months = (target_date.year - today.year) * 12 + (target_date.month - today.month)
            mean_monthly_return = (goal["annual_return"] / 100) / 12
            monthly_volatility = (goal["volatility"] / 100) / np.sqrt(12)

            for i in range(20): # Limit to 20 iterations to prevent infinite loops
                test_goal = goal.copy()
                test_goal['monthly_contribution'] = test_contrib
                
                final_values = []
                for _ in range(500): # Number of simulations
                    val = test_goal["current_amount"]
                    for _ in range(months):
                        ret = np.random.normal(mean_monthly_return, monthly_volatility)
                        val = (val + test_goal['monthly_contribution']) * (1 + ret)
                    final_values.append(val)
                
                success_rate = (np.sum(np.array(final_values) >= goal["target_amount"]) / 500) * 100
                
                # Update dialog with progress
                self.after(0, lambda r=success_rate: dialog.status_label.config(text=f"Calculating... ({r:.0f}%)"))

                if success_rate >= target_prob:
                    increase = test_contrib - current_contrib
                    result_text = (f"Required Monthly Contribution: ${test_contrib:,.2f}\n"
                                   f"(An increase of ${increase:,.2f} from your current ${current_contrib:,.2f})")
                    self.after(0, lambda: dialog.result_label.config(text=result_text))
                    self.after(0, lambda: dialog.status_label.config(text=f"Suggestion for {target_prob}% Success:"))
                    return
                
                test_contrib += increment
            
            # If loop finishes without reaching target
            self.after(0, lambda: dialog.result_label.config(text="Goal may be unreachable within a reasonable contribution increase."))

        except Exception as e:
            print(f"Suggestion calculation error: {e}")
            self.after(0, lambda: dialog.result_label.config(text="An error occurred during calculation."))

    def _start_suggestion_thread(self, goal, target_prob):
        """Creates the suggestion dialog and starts the calculation thread."""
        dialog = SuggestionDialog(self, title="Goal Suggestion")
        thread = threading.Thread(
            target=self._find_required_contribution_for_target,
            args=(goal, target_prob, dialog),
            daemon=True
        )
        thread.start()

    def _show_suggestion_menu(self, goal, button_widget):
        """Creates and displays a menu with suggestion options."""
        goal_id = goal['name'] + goal['target_date']
        results = self.goal_simulation_results.get(goal_id)
        if not results or results['success_rate'] == -1:
            messagebox.showinfo("No Data", "Please run a simulation for this goal first.", parent=self)
            return

        current_prob = results['success_rate']
        
        menu = tk.Menu(self, tearoff=0, background=self.CARD_COLOR, foreground=self.TEXT_COLOR, font=self.FONT_NORMAL)
        
        targets = {"On Track": 60, "High Confidence": 85}
        
        added_option = False
        for name, prob in targets.items():
            if current_prob < prob:
                menu.add_command(label=f"How to get '{name}' ({prob}%)", command=lambda p=prob: self._start_suggestion_thread(goal, p))
                added_option = True
        
        if not added_option:
            menu.add_command(label="Already on track for all targets!", state="disabled")

        # Position the menu below the button
        x = button_widget.winfo_rootx()
        y = button_widget.winfo_rooty() + button_widget.winfo_height()
        menu.post(x, y)

    def _create_slider(self, parent, label, from_, to, initial_val, row):
        """
        REVISED: Creates a labeled slider (Scale) widget with a simplified, more direct command.
        """
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(5,0))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text=label, background=self.CARD_COLOR).grid(row=0, column=0, sticky="w")
        var = tk.DoubleVar(value=initial_val)
        
        # The command now directly calls the update function without extra lambda layers.
        slider = ttk.Scale(frame, from_=from_, to=to, orient="horizontal", variable=var, style="Horizontal.TScale",
                           command=self._on_what_if_update)
                           
        slider.grid(row=0, column=1, sticky="ew", padx=10)
        
        value_lbl = ttk.Label(frame, text=f"{initial_val:.2f}", background=self.CARD_COLOR, font=self.FONT_BOLD, width=7)
        value_lbl.grid(row=0, column=2, sticky="e", padx=5)
        var.trace_add("write", lambda *args, v=var, l=value_lbl: l.config(text=f"{v.get():.2f}"))
        
        return var

    def _initial_goal_chart_draw(self, event):
        """
        A one-time event handler for the <Map> event. This robustly ensures
        the initial draw happens only after the UI is visible and has its
        correct final size, preventing the "zoomed-in" bug.
        """
        # Unbind immediately to ensure this only ever runs once.
        self.analysis_frame.unbind("<Map>")
        
        # Now that the frame is guaranteed to be mapped with its final size,
        # trigger the first and only the first draw. Subsequent draws are
        # handled by the sliders directly.
        self._on_what_if_update()

    def _apply_what_if_parameters(self):
        """Saves the current values from the 'What-If' controls to the active goal."""
        if not self.active_analysis_goal:
            return

        # Get the original goal to find it in the list later
        original_goal = self.active_analysis_goal

        # Confirm with the user before making permanent changes
        confirm = messagebox.askyesno(
            "Apply Changes",
            f"This will permanently update the goal '{original_goal['name']}' with the new parameters from the sliders. The current analysis will be reset.\n\nAre you sure you want to continue?",
            parent=self
        )
        if not confirm:
            return

        # Read the current values from the interactive controls
        new_contrib = self.contrib_slider.get()
        new_horizon_years = self.horizon_slider.get()
        lump_sum = float(self.lump_sum_var.get() if self.lump_sum_var.get() else 0)

        # Calculate the new target date based on the new time horizon
        new_target_date = (datetime.now() + timedelta(days=new_horizon_years * 365.25)).strftime('%Y-%m-%d')
        
        # Add the lump sum to the goal's current amount
        new_current_amount = original_goal['current_amount'] + lump_sum

        # Find the goal in the main portfolio list and update it
        for i, goal in enumerate(self.portfolio["goals"]):
            if goal["name"] == original_goal["name"] and goal["target_date"] == original_goal["target_date"]:
                self.portfolio["goals"][i]['monthly_contribution'] = new_contrib
                self.portfolio["goals"][i]['target_date'] = new_target_date
                self.portfolio["goals"][i]['current_amount'] = new_current_amount
                break
        
        # Clear the old simulation result for this goal
        goal_id = original_goal['name'] + original_goal['target_date']
        if goal_id in self.goal_simulation_results:
            del self.goal_simulation_results[goal_id]
            
        # Clear the analysis pane and refresh the main goals list
        self._clear_analysis_pane()
        self._update_all_views()

    def _show_tax_info_dialog(self):
        """Creates and shows the tax information manual dialog."""
        TaxInfoDialog(self, title="Tax Center Manual")
    
    def _calculate_tax_efficiency_score(self):
        """Calculates a holistic tax efficiency score for the portfolio."""
        total_value = sum(lot["shares"] * self.market_data_cache.get(lot["symbol"], {}).get("regularMarketPrice", 0) for lot in self.portfolio["positions"])
        if total_value == 0:
            return 0, "N/A"

        # --- Component 1: Long-Term Holdings Ratio (40 points) ---
        long_term_value = 0
        for lot in self.portfolio["positions"]:
            purchase_date = datetime.strptime(lot['purchase_date'], '%Y-%m-%d')
            if (datetime.now() - purchase_date).days > 365:
                long_term_value += lot["shares"] * self.market_data_cache.get(lot["symbol"], {}).get("regularMarketPrice", 0)
        
        long_term_ratio = (long_term_value / total_value) if total_value > 0 else 0
        long_term_score = long_term_ratio * 40

        # --- Component 2: Harvestable Loss Ratio (30 points) ---
        unrealized_losses = abs(sum(
            (self.market_data_cache.get(lot["symbol"], {}).get("regularMarketPrice", lot["entry_price"]) - lot["entry_price"]) * lot["shares"]
            for lot in self.portfolio["positions"]
            if self.market_data_cache.get(lot["symbol"], {}).get("regularMarketPrice", lot["entry_price"]) < lot["entry_price"]
        ))
        # Score is capped at 5% of portfolio value being harvestable losses.
        harvest_ratio = min((unrealized_losses / total_value) / 0.05, 1.0) if total_value > 0 else 0
        harvest_score = harvest_ratio * 30

        # --- Component 3: Realized Gains Quality (30 points) ---
        realized_gains_log = self.portfolio.get('realized_gains', [])
        total_realized_gains = sum(g['gain_loss'] for g in realized_gains_log if g['gain_loss'] > 0)
        long_term_realized_gains = sum(g['gain_loss'] for g in realized_gains_log if g['gain_loss'] > 0 and g['type'] == 'Long-Term')
        
        realized_quality_ratio = (long_term_realized_gains / total_realized_gains) if total_realized_gains > 0 else 1.0 # Default to 1 if no gains
        realized_score = realized_quality_ratio * 30

        # --- Final Score and Grade ---
        final_score = int(long_term_score + harvest_score + realized_score)
        
        if final_score >= 97: grade = "A+"
        elif final_score >= 93: grade = "A"
        elif final_score >= 90: grade = "A-"
        elif final_score >= 87: grade = "B+"
        elif final_score >= 83: grade = "B"
        elif final_score >= 80: grade = "B-"
        elif final_score >= 77: grade = "C+"
        elif final_score >= 73: grade = "C"
        elif final_score >= 70: grade = "C-"
        elif final_score >= 60: grade = "D"
        else: grade = "F"
        
        return final_score, grade

    def _load_warning_icon(self):
        """Loads the base64 warning icon into a PhotoImage object."""
        try:
            import base64
            from io import BytesIO
            # A 16x16 yellow triangle with a black '!'
            icon_data = base64.b64decode(
                b'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAADPSURBVDhPzZExDoAwCERtEou9hYvsLdjd3t7D3sJQYmFhYREEIYIiSgI/pL9gIplgQzL5k2R+SY8kM0kQzL8xSflfAgCM4/g7RgC2aZp2u90BQJ7n2e/3I5PJtNvtJ5XKaTQazWq1arVaLa/X6/V6vb5er59bVzXgD4bhyWQiSRIURd/3fd/3Pd/3/Vd5nufz+UyS5Lqu4zhJkgDA8zxN0wCAOI6maZIk4ziSJAFAlmVZlhEEARAEURTl+Xw+n8/n8/l8Pp/PBwB+3CTcbg2YwQAAAABJRU5ErkJggg=='
            )
            img = Image.open(BytesIO(icon_data))
            self.warning_icon = ImageTk.PhotoImage(img)
            style = ttk.Style(self)
            style.configure("Warning.TLabel", background=self.CARD_COLOR, foreground="yellow", font=self.FONT_BOLD)
        except Exception as e:
            print(f"Failed to load warning icon: {e}")




   
# --- Dialog Classes ---

class TaxInfoDialog(tk.Toplevel):
    """A custom dialog to display the help manual for the Advanced Tax Center."""
    def __init__(self, parent, title):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.parent = parent
        self.resizable(True, True)
        self.geometry("650x750")
        self.configure(bg=parent.CARD_COLOR, padx=10, pady=10)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        main_frame = ttk.Frame(self, style="Card.TFrame")
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        self.text_widget = tk.Text(main_frame, wrap="word", bg=parent.CARD_COLOR, fg=parent.TEXT_COLOR, font=parent.FONT_NORMAL, relief="flat", highlightthickness=0, padx=15, pady=15)
        self.text_widget.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=self.text_widget.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text_widget.config(yscrollcommand=scrollbar.set)

        self.text_widget.tag_configure("h1", font=parent.FONT_HEADER, foreground=parent.ACCENT_COLOR, spacing3=10)
        self.text_widget.tag_configure("h2", font=parent.FONT_BOLD, foreground=parent.TEXT_COLOR, spacing1=15, spacing3=5)
        self.text_widget.tag_configure("p", spacing3=10)
        self.text_widget.tag_configure("bullet", lmargin1=20, lmargin2=20, spacing3=5)
        self.text_widget.tag_configure("sub_bullet", lmargin1=40, lmargin2=40, spacing3=5)

        self._add_content()
        self.text_widget.config(state="disabled")

        button_frame = ttk.Frame(self, style="Card.TFrame")
        button_frame.pack(fill="x", pady=(10,0))
        close_button = ttk.Button(button_frame, text="Close", style="Accent.TButton", command=self.destroy)
        close_button.pack(pady=5)

        self.grab_set()
        self.wait_window(self)

    def _add_content(self):
        """Adds the formatted help text to the Text widget."""
        self.text_widget.insert(tk.END, "Tax Center Manual\n\n", "h1")
        
        self.text_widget.insert(tk.END, "Tax Efficiency Score\n", "h2")
        self.text_widget.insert(tk.END, "This score (0-100) provides a holistic view of your portfolio's tax-friendliness. A higher score is better. It is calculated from three components:\n\n", "p")
        self.text_widget.insert(tk.END, "1. Long-Term Holdings (40 pts): ", "sub_bullet")
        self.text_widget.insert(tk.END, "Measures the percentage of your portfolio held for over a year. Long-term holdings are taxed at a lower rate.\n", "p")
        self.text_widget.insert(tk.END, "2. Harvestable Losses (30 pts): ", "sub_bullet")
        self.text_widget.insert(tk.END, "Measures the amount of unrealized losses relative to your portfolio size. Having losses available to offset gains is a key tax-saving strategy.\n", "p")
        self.text_widget.insert(tk.END, "3. Realized Gains Quality (30 pts): ", "sub_bullet")
        self.text_widget.insert(tk.END, "Measures the proportion of your realized gains for the year that were long-term. Prioritizing long-term gains is more tax-efficient.\n", "p")

        self.text_widget.insert(tk.END, "Unrealized Gains & Losses by Lot\n", "h2")
        self.text_widget.insert(tk.END, "This table shows every individual purchase (a 'tax lot') you own. Click the arrow next to a symbol to see all of its lots.\n\n", "p")
        self.text_widget.insert(tk.END, "• Term: ", "bullet")
        self.text_widget.insert(tk.END, "Indicates if a lot is 'Short-Term' (held ≤ 1 year) or 'Long-Term' (held > 1 year), which determines its tax rate upon sale.\n", "p")

        self.text_widget.insert(tk.END, "\"What-If\" Sale Simulator\n", "h2")
        self.text_widget.insert(tk.END, "This tool lets you preview the tax impact of selling specific lots.\n\n", "p")
        self.text_widget.insert(tk.END, "• Wash Sale Risk: ", "bullet")
        self.text_widget.insert(tk.END, "The [!] icon appears if you try to harvest a loss from a lot when you have purchased the same stock within the last 30 days. The IRS disallows these losses for tax purposes. The simulator will correctly ignore this loss in its 'Total Estimated Tax Impact' calculation.\n", "p")
        self.text_widget.insert(tk.END, "• Total Estimated Tax Impact: ", "bullet")
        self.text_widget.insert(tk.END, "Shows the net tax you would owe (red) or save (green) from the combination of all simulated sales, accounting for wash sale rules.\n", "p")

class PositionDialog(simpledialog.Dialog):
    """Dialog for adding or editing positions with better styling."""
    def __init__(self, parent, title="Add Position", initial_data=None):
        self.initial_data = initial_data
        # Store parent's colors
        self.bg_color = parent.CARD_COLOR
        self.text_color = parent.TEXT_COLOR
        self.entry_bg = parent.BG_COLOR
        super().__init__(parent, title=title)

    def body(self, master):
        master.configure(bg=self.bg_color)
        
        # Use a frame for better padding
        frame = tk.Frame(master, bg=self.bg_color)
        frame.pack(padx=10, pady=10)

        ttk.Label(frame, text="Symbol:", background=self.bg_color, foreground=self.text_color).grid(row=0, column=0, pady=5, sticky="w")
        self.symbol = ttk.Entry(frame, font=("Calibri", 10))
        self.symbol.grid(row=0, column=1, pady=5, padx=5)
        
        ttk.Label(frame, text="Shares:", background=self.bg_color, foreground=self.text_color).grid(row=1, column=0, pady=5, sticky="w")
        self.shares = ttk.Entry(frame, font=("Calibri", 10))
        self.shares.grid(row=1, column=1, pady=5, padx=5)
        
        ttk.Label(frame, text="Entry Price:", background=self.bg_color, foreground=self.text_color).grid(row=2, column=0, pady=5, sticky="w")
        self.price = ttk.Entry(frame, font=("Calibri", 10))
        self.price.grid(row=2, column=1, pady=5, padx=5)
        
        if self.initial_data:
            self.symbol.insert(0, self.initial_data["symbol"])
            self.symbol.config(state="readonly") # Can't edit symbol
            self.shares.insert(0, self.initial_data["shares"])
            self.price.insert(0, self.initial_data["entry_price"])
            
        return self.symbol

    def buttonbox(self):
        # Override to style buttons
        box = ttk.Frame(self)
        self.ok_button = ttk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE, style="Accent.TButton")
        self.ok_button.pack(side=tk.LEFT, padx=5, pady=5)
        cancel_button = ttk.Button(box, text="Cancel", width=10, command=self.cancel, style="TButton")
        cancel_button.pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def apply(self):
        try:
            self.result = {
                "symbol": self.symbol.get().upper(),
                "shares": float(self.shares.get()),
                "entry_price": float(self.price.get())
            }
        except (ValueError, TypeError):
            messagebox.showerror("Error", "Invalid input. Please check the values.", parent=self)
            self.result = None

class GoalDialog(tk.Toplevel):
    """A custom, professionally styled dialog for adding or editing goals."""
    def __init__(self, parent, title="Add Financial Goal", initial_data=None):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.parent = parent
        self.initial_data = initial_data if initial_data else {}
        self.result = None

        # --- Window Configuration ---
        self.configure(bg=parent.CARD_COLOR, padx=20, pady=20)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        # --- Build UI ---
        self.entries = {}
        self.contrib_var = tk.BooleanVar(value=bool(self.initial_data.get("monthly_contribution", 0) > 0))
        
        self._create_widgets()
        self._layout_widgets()
        self._populate_initial_data()
        self._toggle_contribution_entry() # Set initial state

        # --- Make Modal ---
        self.grab_set()
        self.wait_window(self)

    def _create_widgets(self):
        """Create all the input widgets for the dialog."""
        fields = {
            "Goal Name:": "name", "Target Amount ($):": "target_amount", "Current Amount ($):": "current_amount",
            "Target Date (YYYY-MM-DD):": "target_date", "Expected Annual Return (%):": "annual_return",
            "Annual Volatility (Std. Dev. %):": "volatility"
        }
        
        self.main_frame = ttk.Frame(self, style="Card.TFrame")
        
        for i, (label_text, key) in enumerate(fields.items()):
            label = ttk.Label(self.main_frame, text=label_text, style="Secondary.TLabel", background=self.parent.CARD_COLOR)
            label.grid(row=i, column=0, pady=8, padx=5, sticky="w")
            entry = ttk.Entry(self.main_frame, font=self.parent.FONT_NORMAL)
            entry.grid(row=i, column=1, pady=8, sticky="ew")
            self.entries[key] = entry
            
        # --- Conditional Contribution Section ---
        self.contrib_check = ttk.Checkbutton(self.main_frame, text="Add monthly contributions?", variable=self.contrib_var, style="TCheckbutton", command=self._toggle_contribution_entry)
        
        self.contrib_label = ttk.Label(self.main_frame, text="Monthly Contribution ($):", style="Secondary.TLabel", background=self.parent.CARD_COLOR)
        self.entries["monthly_contribution"] = ttk.Entry(self.main_frame, font=self.parent.FONT_NORMAL)

        # --- Buttons ---
        self.button_frame = ttk.Frame(self, style="Card.TFrame")
        self.ok_button = ttk.Button(self.button_frame, text="Save Goal", style="Accent.TButton", command=self._on_ok)
        self.cancel_button = ttk.Button(self.button_frame, text="Cancel", style="TButton", command=self._on_cancel)

    def _layout_widgets(self):
        """Position all widgets in the dialog."""
        self.main_frame.pack(fill="x", expand=True)
        self.main_frame.columnconfigure(1, weight=1)

        # Position contribution widgets
        self.contrib_check.grid(row=6, column=0, columnspan=2, sticky="w", pady=(15, 5))
        self.contrib_label.grid(row=7, column=0, pady=8, padx=5, sticky="w")
        self.entries["monthly_contribution"].grid(row=7, column=1, pady=8, sticky="ew")

        # Position buttons
        self.button_frame.pack(fill="x", expand=True, pady=(20, 0))
        self.button_frame.columnconfigure(0, weight=1)
        self.cancel_button.pack(side="right", padx=(10, 0))
        self.ok_button.pack(side="right")
        
    def _populate_initial_data(self):
        """Fill fields with data if editing an existing goal."""
        for key, entry in self.entries.items():
            if self.initial_data.get(key) is not None:
                entry.insert(0, self.initial_data[key])

        # Set sensible defaults for new goals
        if not self.initial_data:
            self.entries["annual_return"].insert(0, "7")
            self.entries["volatility"].insert(0, "15")
            self.entries["monthly_contribution"].insert(0, "0")

    def _toggle_contribution_entry(self):
        """Enable or disable the monthly contribution entry based on the checkbox."""
        if self.contrib_var.get():
            self.entries["monthly_contribution"].config(state="normal")
            self.contrib_label.config(foreground=self.parent.TEXT_COLOR)
        else:
            self.entries["monthly_contribution"].config(state="disabled")
            self.entries["monthly_contribution"].delete(0, tk.END)
            self.entries["monthly_contribution"].insert(0, "0")
            self.contrib_label.config(foreground=self.parent.SECONDARY_TEXT)

    def _on_ok(self, event=None):
        """Handle the OK button click, validate, and close."""
        try:
            self.result = {key: entry.get() for key, entry in self.entries.items()}
            for key in ["target_amount", "current_amount", "monthly_contribution", "annual_return", "volatility"]:
                self.result[key] = float(self.result[key])
            datetime.strptime(self.result["target_date"], '%Y-%m-%d')
            self.grab_release()
            self.destroy()
        except (ValueError, TypeError):
            messagebox.showerror("Invalid Input", "Please check all values and ensure the date is in YYYY-MM-DD format.", parent=self)

    def _on_cancel(self, event=None):
        """Handle the Cancel button click and close."""
        self.result = None
        self.grab_release()
        self.destroy()
   
def launch_portfolio_window(theme_name='dark'):
    """Initializes and runs the PortfolioApp in a separate process with a specified theme."""
    
    # --- FIX: Add DPI Awareness setting at the entry point of this new process ---
    try:
        import ctypes
        import sys
        if sys.platform == "win32":
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    # --- END DPI FIX ---

    app = PortfolioApp(theme_name=theme_name)
    app.mainloop()
class SuggestionDialog(tk.Toplevel):
    """A custom dialog to display goal-seeking calculation results."""
    def __init__(self, parent, title):
        super().__init__(parent)
        self.transient(parent)
        self.title(title)
        self.parent = parent
        self.resizable(False, False)
        self.configure(bg=parent.CARD_COLOR, padx=25, pady=20)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.status_label = ttk.Label(self, text="Calculating, please wait...", style="Header.TLabel", background=self.parent.CARD_COLOR, justify="center")
        self.status_label.pack(pady=(0, 15))

        self.result_label = ttk.Label(self, text="", style="Secondary.TLabel", background=self.parent.CARD_COLOR, justify="center")
        self.result_label.pack()
        
        # Center the window
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
        y = parent.winfo_y() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")
        
        self.grab_set()



if __name__ == "__main__":
    app = PortfolioApp(theme_name='dark')
    try:
        app.mainloop()
    except KeyboardInterrupt:
        # This block runs when you press Ctrl+C.
        # It allows the program to exit silently without a traceback.
        print("\nApplication shut down.")