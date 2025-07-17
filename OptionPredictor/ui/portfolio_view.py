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
from io import BytesIO
from PIL import Image, ImageTk
import squarify



class MockFinancialDataAPI:
    """A mock API to simulate fetching financial data with more detail."""
    def get_stock_details(self, ticker):
        price = np.random.uniform(50, 500)
        prev_close = price * (1 + np.random.uniform(-0.05, 0.05))
        # Mock factor exposures (should sum to 1)
        factors = {"Value": np.random.uniform(0,1), "Growth": np.random.uniform(0,1), "Quality": np.random.uniform(0,1)}
        total_factor = sum(factors.values())
        factors = {k: v/total_factor for k,v in factors.items()}

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
            "factor_exposures": factors
        }

    def get_benchmark_details(self, ticker="SPY"):
        """Returns data for a benchmark ETF."""
        return {
            "symbol": ticker,
            "trailingPE": 21.5, # Realistic P/E for S&P 500
            "dividendYield": 0.015 # Realistic yield for S&P 500
        }

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
        self.market_data_cache = {}
        self.active_view_key = None
        self.sidebar_buttons = {}
        self.chart_hover_elements = {}
        self.pie_wedges = []
        self.pie_annot = None
        self.sector_details = {}
        self.active_timeframe = "6M"
        self.goal_simulation_results = {}
        self.active_analysis_goal = None
        self.analysis_data = {}

        # --- Build UI ---
        self._build_styles()
        self._build_main_layout()
        self.show_view("dashboard")

        # --- Initialize Data ---
        self.load_portfolio_data()
        self.start_periodic_updates()
    
    def on_closing(self):
        """Ensure clean shutdown."""
        self.destroy()

    def _build_styles(self):
        """Define consistent, professional styles with smaller, denser fonts."""
        style = ttk.Style(self)
        style.theme_use('clam')

        # --- FIX: Font sizes have been reduced for a more compact UI ---
        self.FONT_NORMAL = ("Calibri", 10)      # Was 12
        self.FONT_BOLD = ("Calibri", 10, "bold") # Was 12
        self.FONT_HEADER = ("Calibri", 14, "bold") # Was 16
        self.FONT_TITLE = ("Calibri", 20, "bold")  # Was 24
        self.FONT_KPI = ("Calibri", 24, "bold")    # Was 28
        self.FONT_SIDEBAR = ("Calibri", 12)      # Was 14

        # --- General Styles ---
        style.configure("TFrame", background=self.BG_COLOR)
        style.configure("Card.TFrame", background=self.CARD_COLOR, relief="flat", borderwidth=1, bordercolor=self.BORDER_COLOR)
        style.configure("Sidebar.TFrame", background=self.SIDEBAR_COLOR)

        # --- Labels ---
        style.configure("TLabel", background=self.BG_COLOR, foreground=self.TEXT_COLOR, font=self.FONT_NORMAL)
        style.configure("Header.TLabel", font=self.FONT_HEADER, foreground=self.TEXT_COLOR)
        style.configure("Title.TLabel", font=self.FONT_TITLE)
        style.configure("Secondary.TLabel", foreground=self.SECONDARY_TEXT)
        style.configure("KPI.TLabel", font=self.FONT_KPI)

        # --- Buttons ---
        style.configure("TButton", font=self.FONT_BOLD, padding=8, background=self.CARD_COLOR, foreground=self.TEXT_COLOR, relief="flat") # Reduced padding
        style.map("TButton", background=[('active', '#333333')], foreground=[('active', self.TEXT_COLOR)])
        style.configure("Accent.TButton", background=self.ACCENT_COLOR, foreground="#ffffff")
        style.map("Accent.TButton", background=[('active', '#0088cc')])

        # --- Sidebar Buttons ---
        style.configure("Sidebar.TButton", background=self.SIDEBAR_COLOR, foreground=self.SECONDARY_TEXT, font=self.FONT_SIDEBAR, padding=(15, 8), relief="flat") # Reduced padding
        style.map("Sidebar.TButton", background=[('active', self.BG_COLOR)], foreground=[('active', self.TEXT_COLOR)])
        style.configure("AccentIndicator.TFrame", background=self.ACCENT_COLOR)

        # --- Sliders / Scale ---
        style.configure("TScale", background=self.CARD_COLOR)
        style.configure("Horizontal.TScale", background=self.CARD_COLOR)
        style.map("Horizontal.TScale",
                  background=[('active', self.CARD_COLOR)],
                  troughcolor=[('active', self.ACCENT_COLOR)],
                  highlightcolor=[('focus', self.BG_COLOR)])

        # --- Timeframe Buttons ---
        style.configure("Timeframe.TButton", font=self.FONT_NORMAL, padding=(8, 4), background=self.CARD_COLOR, foreground=self.SECONDARY_TEXT, relief="flat") # Reduced padding
        style.map("Timeframe.TButton", background=[('active', '#333333')])
        
        style.configure("ActiveTimeframe.TButton", font=self.FONT_BOLD, padding=(8, 4), background=self.BG_COLOR, foreground=self.TEXT_COLOR, relief="flat") # Reduced padding

        # --- Progress Bar ---
        style.configure("Green.Horizontal.TProgressbar",
                        background=self.POSITIVE_COLOR,
                        troughcolor=self.CARD_COLOR,
                        bordercolor=self.BORDER_COLOR,
                        lightcolor=self.POSITIVE_COLOR, 
                        darkcolor=self.POSITIVE_COLOR)
        
        # --- Notch Buttons for scrolling ---
        style.configure("Notch.TButton", font=self.FONT_NORMAL, background=self.BG_COLOR, foreground=self.SECONDARY_TEXT, relief="flat")
        style.map("Notch.TButton",
                  foreground=[('active', self.ACCENT_COLOR)],
                  background=[('active', self.BG_COLOR)])
        
        # --- Treeview ---
        # FIX: Reduced rowheight to match smaller font
        style.configure("Treeview", background=self.CARD_COLOR, foreground=self.TEXT_COLOR, fieldbackground=self.CARD_COLOR, font=self.FONT_NORMAL, rowheight=25) # Was 30
        style.configure("Treeview.Heading", background=self.BORDER_COLOR, foreground=self.TEXT_COLOR, font=self.FONT_BOLD, padding=6) # Reduced padding
        style.map("Treeview", background=[('selected', '#333333')])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

        # --- Matplotlib ---
        plt.style.use('dark_background')
        plt.rcParams.update({
            # *** THE FIX IS HERE: Changed figure.facecolor to CARD_COLOR ***
            # This ensures the figure background matches the card it sits in.
            "figure.facecolor": self.CARD_COLOR,
            "axes.facecolor": self.CARD_COLOR,
            "axes.edgecolor": self.BORDER_COLOR,
            "axes.labelcolor": self.SECONDARY_TEXT,
            "xtick.color": self.SECONDARY_TEXT,
            "ytick.color": self.SECONDARY_TEXT,
            "grid.color": self.BORDER_COLOR,
            "text.color": self.TEXT_COLOR,
            "font.family": "sans-serif",
            "font.size": 9, # Set a base font size for matplotlib
            "axes.titlesize": 12, # Was 14
            "axes.titleweight": "bold"
        })

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

    def show_view(self, view_key):
        """Switch between views and update sidebar."""
        if hasattr(self, 'active_view') and self.active_view:
            self.active_view.destroy()
        self.active_view_key = view_key

        for key, btn in self.sidebar_buttons.items():
            is_active = key == view_key
            btn["frame"].configure(style="TFrame" if is_active else "Sidebar.TFrame")
            btn["text"].configure(foreground=self.TEXT_COLOR if is_active else self.SECONDARY_TEXT)
            btn["icon"].configure(foreground=self.TEXT_COLOR if is_active else self.SECONDARY_TEXT)
            if is_active:
                btn["indicator"].pack(side="left", fill="y")
            else:
                btn["indicator"].pack_forget()

        views = {
            "dashboard": self._build_dashboard_view,
            "goals": self._build_goals_view,
            "analysis": self._build_analysis_view,
            "tax": self._build_tax_view
        }
        self.active_view = views[view_key](self.content_frame)
        self.active_view.grid(row=0, column=0, sticky="nsew")
        self._update_all_views()

    # --- View Builders ---
    def _build_dashboard_view(self, parent):
        """Build a completely revamped, professional dashboard view."""
        view = ttk.Frame(parent)
        view.columnconfigure(0, weight=3) # Main content area
        view.columnconfigure(1, weight=2) # Right sidebar area
        view.rowconfigure(1, weight=1)

        # --- Row 0: Header ---
        header = ttk.Frame(view)
        header.grid(row=0, column=0, columnspan=2, pady=(0, 25), sticky="ew")
        ttk.Label(header, text="Dashboard Overview", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Add Position", style="Accent.TButton", command=self._open_add_position_dialog).pack(side="right")

        # --- Column 0: Main Content (KPIs and History Chart) ---
        main_content = ttk.Frame(view)
        main_content.grid(row=1, column=0, sticky="nsew", padx=(0, 15))
        main_content.rowconfigure(1, weight=1)
        main_content.columnconfigure(0, weight=1)

        # --- KPI Row ---
        kpi_frame = ttk.Frame(main_content)
        kpi_frame.grid(row=0, column=0, pady=(0, 20), sticky="ew")
        kpi_frame.columnconfigure((0, 1, 2), weight=1)
        self.kpi_total = self._create_kpi_card(kpi_frame, "Total Portfolio Value", "$0.00", 0)
        self.kpi_day = self._create_kpi_card(kpi_frame, "Today's Gain / Loss", "$0.00", 1)
        self.kpi_gain = self._create_kpi_card(kpi_frame, "Total Unrealized Gain", "$0.00", 2)

        # --- History Chart Card ---
        chart_card = ttk.Frame(main_content, style="Card.TFrame", padding=20)
        chart_card.grid(row=1, column=0, sticky="nsew")
        chart_card.rowconfigure(1, weight=1)
        chart_card.columnconfigure(0, weight=1)
        
        chart_header = ttk.Frame(chart_card, style="Card.TFrame")
        chart_header.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        ttk.Label(chart_header, text="Performance History", style="Header.TLabel", background=self.CARD_COLOR).pack(side="left")
        
        # Add the new timeframe selector
        self.timeframe_selector = self._create_timeframe_selector(chart_header)
        self.timeframe_selector.pack(side="right")

        self.fig_dash, self.ax_dash = plt.subplots(dpi=100)
        self.canvas_dash = FigureCanvasTkAgg(self.fig_dash, chart_card)
        self.canvas_dash.get_tk_widget().grid(row=1, column=0, sticky="nsew")
        self._setup_chart_hover()

        # --- Column 1: Right Sidebar (Positions and Diversification) ---
        right_sidebar = ttk.Frame(view)
        right_sidebar.grid(row=1, column=1, sticky="nsew", padx=(15, 0))
        right_sidebar.rowconfigure(0, weight=5) # Positions take more space
        right_sidebar.rowconfigure(1, weight=4) # Pie chart takes less
        right_sidebar.columnconfigure(0, weight=1)

        # --- Positions Card ---
        pos_frame = ttk.Frame(right_sidebar, style="Card.TFrame", padding=20)
        pos_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        pos_frame.rowconfigure(1, weight=1)
        pos_frame.columnconfigure(0, weight=1)
        ttk.Label(pos_frame, text="Current Positions", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 15))
        self.tree = ttk.Treeview(pos_frame, columns=("symbol", "shares", "price", "value", "day_pct", "total_pct"), show="headings")
        self.tree.grid(row=1, column=0, sticky="nsew")
        for col, text in zip(self.tree["columns"], ["Symbol", "Shares", "Price", "Value", "Day %", "Total %"]):
            self.tree.heading(col, text=text)
            self.tree.column(col, anchor="e" if col != "symbol" else "w", width=80)
        self.tree.tag_configure("odd", background="#2a2a2a")

        # --- Create Right-Click Context Menu for Positions ---
        self.position_context_menu = tk.Menu(self.tree, tearoff=0, background=self.CARD_COLOR, foreground=self.TEXT_COLOR)
        self.position_context_menu.add_command(label="Edit Position", command=self._edit_position)
        self.position_context_menu.add_command(label="Remove Position", command=self._remove_position)
        
        self.tree.bind("<Button-3>", self._on_position_right_click) # Button-3 is the right mouse button

        # --- Diversification Card ---
        pie_frame = ttk.Frame(right_sidebar, style="Card.TFrame", padding=20)
        pie_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        pie_frame.rowconfigure(1, weight=1)
        pie_frame.columnconfigure(0, weight=1)
        ttk.Label(pie_frame, text="Sector Allocation", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w", pady=(0, 15))
        self.fig_pie, self.ax_pie = plt.subplots(dpi=100)
        self.canvas_pie = FigureCanvasTkAgg(self.fig_pie, pie_frame)
        self.canvas_pie.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        return view
    
    def _create_kpi_card(self, parent, title, value, col):
        """Create a professional KPI card."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=15)
        card.grid(row=0, column=col, sticky="nsew", padx=5)
        ttk.Label(card, text=title, style="Secondary.TLabel", background=self.CARD_COLOR).pack()
        value_lbl = ttk.Label(card, text=value, style="KPI.TLabel", background=self.CARD_COLOR)
        value_lbl.pack(pady=5)
        return value_lbl

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
    
        # --- Analysis Lab: Final Enhanced Methods ---
    # Replace the entire block of analysis methods in your file with this one.
    # This includes _build_analysis_view and all its helpers.

    def _build_analysis_view(self, parent):
        """
        Builds a completely revamped and professional Analysis Lab with advanced tools.
        """
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
        
        self.fig_factors, self.ax_factors = plt.subplots()
        self.canvas_factors = FigureCanvasTkAgg(self.fig_factors, chart_card)
        self.canvas_factors.get_tk_widget().grid(row=1, column=0, sticky="nsew")

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
        self.fig_risk, self.ax_risk = plt.subplots()
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
        self.fig_corr, self.ax_corr = plt.subplots()
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
        self.fig_stress, self.ax_stress = plt.subplots()
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
        self.fig_attr, self.ax_attr = plt.subplots()
        self.canvas_attr = FigureCanvasTkAgg(self.fig_attr, chart_card)
        self.canvas_attr.get_tk_widget().pack(fill="both", expand=True)
        
        return tab


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
            # Read the values directly from the DoubleVar associated with each slider
            market_shock = self.custom_shock_var.get() / 100.0
            rate_shock = self.custom_rate_var.get() / 100.0
        except (ValueError, TclError):
            # TclError can happen if the view is destroyed while trying to get the value
            messagebox.showerror("Invalid Input", "Could not read slider values.", parent=self)
            return

        # For custom scenarios, use a generic strong rebound rate
        rebound_rate = 0.18 
        scenario_name = "Custom Scenario"
        
        self._execute_and_plot_stress_test(market_shock, rate_shock, rebound_rate, scenario_name)

    def _execute_and_plot_stress_test(self, market_shock, rate_shock, rebound_annual_rate, scenario_name):
        """
        The shared engine for calculating and plotting any stress test scenario.
        This version fixes the calculation for the pre-crash value to ensure
        the recovery line and annotation are perfectly accurate.
        """
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
        if total_value == 0: return

        # Calculate total shock from market and rates
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
        
        # --- Recovery Calculation ---
        weights = {pos["symbol"]: (pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0)) / total_value for pos in self.portfolio["positions"]}
        portfolio_returns = (self.analysis_data['returns'][list(weights.keys())] * pd.Series(weights)).sum(axis=1)
        
        # --- CALCULATION FIX: The pre-crash value is the portfolio's current total value ---
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

        # --- Plotting ---
        self.ax_stress.clear()
        
        # --- PLOTTING FIX: Accurately generate the historical path leading up to the crash ---
        # 1. Get the historical returns for the 180 days leading up to the event.
        historical_returns = portfolio_returns.iloc[-180:]
        # 2. Create the growth factors for this period.
        growth_factors = (1 + historical_returns).cumprod()
        # 3. Normalize the factors so the last day equals 1. This ensures the path ends exactly at the pre-crash value.
        normalized_factors = growth_factors / growth_factors.iloc[-1]
        # 4. Generate the historical path by multiplying with the actual pre-crash value (last_val).
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

        # The plotting enhancements will now be perfectly aligned with the data
        self.ax_stress.plot(x_axis, path, color=self.ACCENT_COLOR, lw=1.5, zorder=10)
        self.ax_stress.axvline(x=0, color=self.NEGATIVE_COLOR, linestyle='--', label=f"Event: {scenario_name}", zorder=5)
        self.ax_stress.axhline(y=last_val, color=self.SECONDARY_TEXT, linestyle=':', label='Pre-Crash Value', zorder=5)

        recovery_point_x = None
        for i in range(181, len(path)):
            if path[i] >= last_val:
                recovery_point_x = x_axis[i] 
                break
        
        if recovery_point_x is not None:
            self.ax_stress.plot(recovery_point_x, last_val, 'o', color=self.POSITIVE_COLOR, markersize=8, zorder=20, label="Recovery Point")
            self.ax_stress.annotate(
                f'Recovered\nDay {recovery_point_x}',
                xy=(recovery_point_x, last_val),
                xytext=(recovery_point_x + 30, last_val + (self.ax_stress.get_ylim()[1] - self.ax_stress.get_ylim()[0]) * 0.05),
                arrowprops=dict(facecolor=self.TEXT_COLOR, shrink=0.05, width=1, headwidth=4),
                ha='center', va='bottom',
                bbox=dict(boxstyle="round,pad=0.3", fc=self.CARD_COLOR, ec=self.TEXT_COLOR, lw=0.5, alpha=0.9),
                zorder=30
            )
        
        self.ax_stress.set_title(f"Simulated Impact of {scenario_name}", fontsize=14, pad=20)
        self.fig_stress.suptitle("Simulated path showing the shock and a projected recovery.", fontsize=9, color=self.SECONDARY_TEXT, y=0.92)
        self.ax_stress.set_ylabel("Portfolio Value ($)")
        self.ax_stress.set_xlabel("Trading Days From Event")
        self.ax_stress.legend()
        self.ax_stress.grid(True, linestyle='--', alpha=0.5)
        self.fig_stress.tight_layout(rect=[0, 0, 1, 0.9])
        self.canvas_stress.draw()

    def _update_analysis_view_data(self):
        """Master function to generate mock data and update all analysis tabs."""
        if not self.portfolio["positions"]:
            # Handle empty portfolio case
            for ax in [self.ax_drivers, self.ax_risk, self.ax_corr, self.ax_attr, self.ax_stress]:
                if ax.figure.canvas.get_tk_widget().winfo_exists():
                    ax.clear()
                    ax.text(0.5, 0.5, "Add positions to see analysis", ha='center', va='center', transform=ax.transAxes, fontsize=12)
                    ax.figure.canvas.draw()
            return

        self.analysis_data['returns'] = self._generate_mock_historical_returns()
        self.analysis_data['analytics'] = self._calculate_portfolio_analytics(self.analysis_data['returns'])

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

        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in positions)
        if total_value == 0: return analytics

        weights = {pos["symbol"]: (pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0)) / total_value for pos in positions}
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
        
        # --- Value at Risk (VaR) at 95% confidence for 1 day ---
        # VaR = Portfolio Value * (Portfolio Volatility / sqrt(252)) * Z-score
        # Z-score for 95% confidence is 1.645
        daily_volatility = portfolio_returns.std()
        analytics['var_95'] = total_value * daily_volatility * 1.645

        # --- Diversification Score ---
        # Score = (1 - Average Correlation) * 100. Higher is better.
        corr_matrix = returns_df[portfolio_symbols].corr()
        if len(portfolio_symbols) > 1:
            avg_corr = corr_matrix.unstack().drop_duplicates().mean()
            analytics['diversification_score'] = (1 - avg_corr) * 100
        else:
            analytics['diversification_score'] = 0 # Not applicable for 1 stock

        # --- Fundamental Metrics ---
        # Portfolio fundamentals
        analytics['fundamentals']['pe_ratio'] = sum(self.market_data_cache.get(s, {}).get("trailingPE", 0) * w for s, w in weights.items())
        analytics['fundamentals']['dividend_yield'] = sum(self.market_data_cache.get(s, {}).get("dividendYield", 0) * w for s, w in weights.items())
        
        # Benchmark fundamentals
        benchmark_data = self.api.get_benchmark_details()
        analytics['fundamentals']['benchmark_pe'] = benchmark_data.get('trailingPE')
        analytics['fundamentals']['benchmark_yield'] = benchmark_data.get('dividendYield')

        # Factor Exposures
        weighted_factors = {"Value": 0, "Growth": 0, "Quality": 0}
        for s, w in weights.items():
            factors = self.market_data_cache.get(s, {}).get("factor_exposures", {})
            for factor, exposure in factors.items():
                weighted_factors[factor] += w * exposure
        analytics['fundamentals']['factor_exposures'] = weighted_factors
        
        return analytics


    def _update_key_drivers_view(self):
        """Populates the Key Drivers tab with the new treemap and benchmark KPIs."""
        analytics = self.analysis_data.get('analytics', {})
        fundamentals = analytics.get('fundamentals', {})
        
        # Update KPIs
        self.drivers_kpi_pe.config(text=f"{fundamentals.get('pe_ratio', 0):.2f}x")
        self.drivers_kpi_pe_bench.config(text=f"vs SPY: {fundamentals.get('benchmark_pe', 0):.2f}x")
        self.drivers_kpi_yield.config(text=f"{fundamentals.get('dividend_yield', 0):.2%}")
        self.drivers_kpi_yield_bench.config(text=f"vs SPY: {fundamentals.get('benchmark_yield', 0):.2%}")
        self.drivers_kpi_beta.config(text=f"{analytics.get('beta', 0):.2f}")

        # Plot Factor Exposure Treemap
        self.ax_factors.clear()
        factors = fundamentals.get('factor_exposures', {})
        labels = [f"{k}\n({v:.1%})" for k, v in factors.items()]
        sizes = list(factors.values())
        
        if not any(s > 0 for s in sizes):
            self.ax_factors.text(0.5, 0.5, "Data not available", ha='center', va='center')
        else:
            squarify.plot(sizes=sizes, label=labels, ax=self.ax_factors,
                          color=plt.cm.viridis(np.linspace(0.3, 0.9, len(labels))),
                          text_kwargs={'color': 'white', 'fontsize': 12, 'fontweight': 'bold'})
        
        self.ax_factors.set_title("Portfolio Factor Exposure", fontsize=12)
        self.ax_factors.axis('off')
        self.fig_factors.tight_layout()
        self.canvas_factors.draw()

    def _update_risk_volatility_view(self):
        """Populates the Risk & Volatility tab with calculated data, including VaR."""
        analytics = self.analysis_data.get('analytics', {})
        
        self.risk_kpi_vol.config(text=f"{analytics.get('volatility', 0):.2%}")
        self.risk_kpi_sharpe.config(text=f"{analytics.get('sharpe_ratio', 0):.2f}")
        self.risk_kpi_var.config(text=f"${analytics.get('var_95', 0):,.2f}")

        # Plot rolling volatility (no changes here)
        self.ax_risk.clear()
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
        
        self.ax_risk.set_title("1-Year Rolling Volatility", fontsize=12)
        self.ax_risk.set_ylabel("Annualized Volatility")
        self.ax_risk.legend()
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
        
        # Determine color based on score
        if score > 75: color = self.POSITIVE_COLOR
        elif score > 50: color = "#f0c420" # Warning yellow
        else: color = self.NEGATIVE_COLOR
        self.corr_kpi_score.config(foreground=color)

        # --- Plot Heatmap ---
        returns = self.analysis_data.get('returns')
        if returns is None: return
        
        portfolio_symbols = [pos['symbol'] for pos in self.portfolio['positions']]
        if len(portfolio_symbols) < 2:
            self.ax_corr.clear()
            self.ax_corr.text(0.5, 0.5, "Add more positions\nto see correlations", ha='center', va='center')
            self.canvas_corr.draw()
            self.corr_summary_text.config(state="normal")
            self.corr_summary_text.delete("1.0", tk.END)
            self.corr_summary_text.insert("1.0", "Add at least two positions to calculate correlations.")
            self.corr_summary_text.config(state="disabled")
            return
            
        corr_matrix = returns[portfolio_symbols].corr()
        self.fig_corr.clear()
        self.ax_corr = self.fig_corr.add_subplot(111)
        im = self.ax_corr.imshow(corr_matrix, cmap='coolwarm', interpolation='nearest', vmin=-1, vmax=1)
        self.fig_corr.colorbar(im, ax=self.ax_corr, label="Correlation Coefficient")
        self.ax_corr.set_xticks(np.arange(len(portfolio_symbols)))
        self.ax_corr.set_yticks(np.arange(len(portfolio_symbols)))
        self.ax_corr.set_xticklabels(portfolio_symbols, rotation=45, ha="right")
        self.ax_corr.set_yticklabels(portfolio_symbols)
        self.ax_corr.set_title("Asset Correlation Matrix", fontsize=12)
        self.fig_corr.tight_layout(pad=2.0)
        self.canvas_corr.draw()

        # --- Restore Detailed Text Insights ---
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
            corr_unstacked = corr_unstacked[corr_unstacked != 1.0] # Remove self-correlations
            max_corr = corr_unstacked.idxmax()
            min_corr = corr_unstacked.idxmin()
            summary.insert(tk.END, "Highest Correlation (Risk Concentrator):\n", "bold")
            summary.insert(tk.END, f"{max_corr[0]} & {max_corr[1]}: {corr_unstacked[max_corr]:.2f}\n\n", "bad")
            summary.insert(tk.END, "Lowest Correlation (Best Diversifier):\n", "bold")
            summary.insert(tk.END, f"{min_corr[0]} & {min_corr[1]}: {corr_unstacked[min_corr]:.2f}", "good")
        
        summary.config(state="disabled")


    def _update_attribution_view(self):
        """Calculates and plots contribution to return with correct colors."""
        returns = self.analysis_data.get('returns')
        if returns is None or returns.empty: return

        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])
        if total_value == 0: return
        weights = {pos["symbol"]: (pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0)) / total_value for pos in self.portfolio["positions"]}

        total_returns = (1 + returns).prod() - 1
        contributions = total_returns * pd.Series(weights)
        contributions_usd = contributions * total_value
        
        # FIX: Sort the values first, then generate colors based on the sorted data
        sorted_contributions = contributions_usd.sort_values()
        colors = [self.POSITIVE_COLOR if v >= 0 else self.NEGATIVE_COLOR for v in sorted_contributions]

        self.ax_attr.clear()
        sorted_contributions.plot(kind='barh', ax=self.ax_attr, color=colors)
        self.ax_attr.set_title("Contribution to Return ($)", fontsize=12)
        self.ax_attr.set_xlabel("Dollar Contribution")
        self.ax_attr.grid(True, axis='x', linestyle='--', alpha=0.5)
        self.fig_attr.tight_layout()
        self.canvas_attr.draw()


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
        """Build a tax view with three sections."""
        view = ttk.Frame(parent)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(1, weight=1)

        header = ttk.Frame(view)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ttk.Label(header, text="Tax Center", style="Title.TLabel").pack(side="left")

        content = ttk.Frame(view)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure((0, 1), weight=1)
        content.rowconfigure((0, 1), weight=1)

        # --- Tax Loss Harvesting ---
        tlh_frame = ttk.Frame(content, style="Card.TFrame", padding=15)
        tlh_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 10))
        ttk.Label(tlh_frame, text="Tax-Loss Harvesting", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w")
        self.tlh_label = ttk.Label(tlh_frame, text="Scanning...", wraplength=400, background=self.CARD_COLOR)
        self.tlh_label.pack(anchor="w", pady=10)

        # --- Asset Location ---
        loc_frame = ttk.Frame(content, style="Card.TFrame", padding=15)
        loc_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))
        ttk.Label(loc_frame, text="Asset Location", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w")
        ttk.Label(loc_frame, text="Place high-tax assets in tax-advantaged accounts.", wraplength=400, style="Secondary.TLabel", background=self.CARD_COLOR).pack(anchor="w", pady=10)

        # --- Tax Impact ---
        tax_frame = ttk.Frame(content, style="Card.TFrame", padding=15)
        tax_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 0))
        ttk.Label(tax_frame, text="Tax Impact Preview", style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w")
        controls = ttk.Frame(tax_frame, style="Card.TFrame")
        controls.pack(fill="x", pady=10)
        ttk.Label(controls, text="Position:", background=self.CARD_COLOR).grid(row=0, column=0, padx=5)
        self.tax_pos_var = tk.StringVar()
        self.tax_menu = ttk.Combobox(controls, textvariable=self.tax_pos_var, state="readonly")
        self.tax_menu.grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(controls, text="Shares:", background=self.CARD_COLOR).grid(row=1, column=0, padx=5, pady=5)
        self.tax_shares = ttk.Entry(controls)
        self.tax_shares.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(controls, text="Calculate", style="Accent.TButton", command=self._calculate_tax_impact).grid(row=2, column=1, sticky="e", pady=5)
        controls.columnconfigure(1, weight=1)
        self.tax_result = ttk.Label(tax_frame, text="$0.00", style="KPI.TLabel", background=self.CARD_COLOR)
        self.tax_result.pack(pady=10)

        return view
    
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
        print(f"Timeframe changed to: {self.active_timeframe}") # For debugging
        
        # Update button styles
        for tf, btn in self.timeframe_buttons.items():
            style = "ActiveTimeframe.TButton" if tf == timeframe else "Timeframe.TButton"
            btn.configure(style=style)
            
        # Re-plot the history chart with the new timeframe
        self._plot_history(timeframe)

    def _on_position_right_click(self, event):
        """Handle right-click event on the positions treeview."""
        # Identify the item clicked
        item_id = self.tree.identify_row(event.y)
        if item_id:
            # Select the clicked item
            self.tree.selection_set(item_id)
            # Post the context menu at the cursor's location
            self.position_context_menu.post(event.x_root, event.y_root)

    def _remove_position(self):
        """Remove the selected position from the portfolio."""
        selected_item = self.tree.selection()
        if not selected_item:
            return

        # Get symbol from the selected treeview row
        symbol_to_remove = self.tree.item(selected_item[0])["values"][0]
        
        # Ask for confirmation
        confirm = messagebox.askyesno(
            "Confirm Removal",
            f"Are you sure you want to remove {symbol_to_remove} from your portfolio?",
            parent=self
        )

        if confirm:
            # Filter out the position to be removed
            self.portfolio["positions"] = [
                pos for pos in self.portfolio["positions"] if pos["symbol"] != symbol_to_remove
            ]
            print(f"Removed position: {symbol_to_remove}")
            self._update_all_views() # Refresh the UI

    def _edit_position(self):
        """Open a dialog to edit the selected position."""
        selected_item = self.tree.selection()
        if not selected_item:
            return
            
        symbol_to_edit = self.tree.item(selected_item[0])["values"][0]
        
        # Find the full data for the position
        position_data = next((pos for pos in self.portfolio["positions"] if pos["symbol"] == symbol_to_edit), None)
        
        if position_data:
            dialog = PositionDialog(self, title=f"Edit {symbol_to_edit}", initial_data=position_data)
            
            if dialog.result:
                # Find the index and update the position data in the list
                for i, pos in enumerate(self.portfolio["positions"]):
                    if pos["symbol"] == symbol_to_edit:
                        self.portfolio["positions"][i] = dialog.result
                        break
                print(f"Edited position: {symbol_to_edit}")
                self._update_all_views() # Refresh the UI

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
    def load_portfolio_data(self):
        """Load initial mock data."""
        self.portfolio = {
            "positions": [
                {"symbol": "AAPL", "shares": 50, "entry_price": 150.0},
                {"symbol": "MSFT", "shares": 30, "entry_price": 280.0},
                {"symbol": "NVDA", "shares": 15, "entry_price": 850.0},
            ],
            "goals": []
        }
        self._fetch_market_data()

    def start_periodic_updates(self):
        """Start periodic data refresh."""
        self._fetch_market_data()
        self.after(60000, self.start_periodic_updates)

    def _fetch_market_data(self):
        """Fetch market data in a separate thread."""
        threading.Thread(target=self._fetch_worker, daemon=True).start()

    def _fetch_worker(self):
        """Worker for fetching data."""
        for pos in self.portfolio["positions"]:
            self.market_data_cache[pos["symbol"]] = self.api.get_stock_details(pos["symbol"])
        self.after(0, self._update_all_views)

    def _update_all_views(self):
        """Update the active view with latest data."""
        if not self.active_view_key or not self.winfo_exists():
            return
        if self.active_view_key == "dashboard":
            if hasattr(self, "kpi_total"): self._update_dashboard_kpis()
            if hasattr(self, "tree"): self._update_positions()
            if hasattr(self, "canvas_dash"): self._plot_history(self.active_timeframe)
            if hasattr(self, "canvas_pie"): self._plot_pie()
        elif self.active_view_key == "goals" and hasattr(self, "goals_container"):
            self._update_goals()
        elif self.active_view_key == "analysis":
            self._update_analysis_view_data()
        elif self.active_view_key == "tax":
            if hasattr(self, "tlh_label"): self._scan_tax_losses()
            if hasattr(self, "tax_menu"): self._update_tax_dropdown()

    def _update_dashboard_kpis(self):
        """Update KPI values."""
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", pos["entry_price"]) for pos in self.portfolio["positions"])
        total_cost = sum(pos["shares"] * pos["entry_price"] for pos in self.portfolio["positions"])
        day_change = sum(pos["shares"] * (self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", pos["entry_price"]) - self.market_data_cache.get(pos["symbol"], {}).get("previousClose", pos["entry_price"])) for pos in self.portfolio["positions"])
        
        self.kpi_total.config(text=f"${total_value:,.2f}")
        self.kpi_day.config(text=f"${day_change:+,.2f}", foreground=self.POSITIVE_COLOR if day_change >= 0 else self.NEGATIVE_COLOR)
        self.kpi_gain.config(text=f"${total_value - total_cost:+,.2f}", foreground=self.POSITIVE_COLOR if total_value >= total_cost else self.NEGATIVE_COLOR)

    def _update_positions(self):
        """Update positions table."""
        self.tree.delete(*self.tree.get_children())
        for i, pos in enumerate(self.portfolio["positions"]):
            data = self.market_data_cache.get(pos["symbol"], {})
            price = data.get("regularMarketPrice", pos["entry_price"])
            value = pos["shares"] * price
            day_pct = ((price / data.get("previousClose", pos["entry_price"])) - 1) * 100 if data.get("previousClose") else 0
            total_pct = ((price / pos["entry_price"]) - 1) * 100
            tags = ("odd",) if i % 2 else ()
            self.tree.insert("", "end", values=(pos["symbol"], f"{pos['shares']:.2f}", f"${price:,.2f}", f"${value:,.2f}", f"{day_pct:+.2f}%", f"{total_pct:+.2f}%"), tags=tags)

    def _plot_history(self, timeframe="6M"):
        """Plot portfolio value history based on the selected timeframe."""
        self.ax_dash.clear()
        
        # --- Generate mock data based on timeframe ---
        days_map = {"1M": 30, "6M": 180, "1Y": 365, "5Y": 365*5, "ALL": 365*10}
        num_days = days_map.get(timeframe, 180)
        
        dates = [datetime.now() - timedelta(days=x) for x in range(num_days)][::-1]
        values = np.cumsum(np.random.randn(num_days)) * (1000 / (num_days/30)) + 100000
        
        # --- Plotting ---
        self.ax_dash.plot(dates, values, color=self.ACCENT_COLOR, linewidth=2)
        self.ax_dash.fill_between(dates, values, alpha=0.1, color=self.ACCENT_COLOR)
        
        # --- Formatting ---
        self.ax_dash.set_ylabel("Portfolio Value ($)")
        
        min_val, max_val = self.ax_dash.get_ylim()
        self.ax_dash.set_ylim(min_val * 0.98, max_val * 1.02)
        
        self.ax_dash.xaxis.set_major_formatter(mdates.DateFormatter("%b '%y"))
        self.ax_dash.spines["top"].set_visible(False)
        self.ax_dash.spines["right"].set_visible(False)
        
        self.fig_dash.tight_layout(pad=1.5)
        self.canvas_dash.draw()

    def _plot_pie(self):
        """Plot sector diversification with an advanced, tooltip-style hover effect."""
        self.ax_pie.clear()
        self.sector_details.clear() # Clear previous data
        
        sectors = {}
        total_value = sum(pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0) for pos in self.portfolio["positions"])

        for pos in self.portfolio["positions"]:
            sector = self.market_data_cache.get(pos["symbol"], {}).get("sector", "Other")
            value = pos["shares"] * self.market_data_cache.get(pos["symbol"], {}).get("regularMarketPrice", 0)
            sectors[sector] = sectors.get(sector, 0) + value

        if sectors and total_value > 0:
            # Store details for the hover function
            for sector, value in sectors.items():
                self.sector_details[sector] = {
                    "value": value,
                    "percent": (value / total_value) * 100
                }

            # Create the pie chart and store the wedges
            wedges, texts = self.ax_pie.pie(
                sectors.values(), 
                startangle=140, 
                colors=plt.cm.Blues(np.linspace(0.4, 0.9, len(sectors)))
            )
            self.pie_wedges = wedges
            
            # Add a legend
            self.ax_pie.legend(wedges, sectors.keys(), title="Sectors", loc="center left", bbox_to_anchor=(0.95, 0, 0.5, 1))
            centre_circle = plt.Circle((0, 0), 0.70, fc=self.CARD_COLOR)
            self.ax_pie.add_artist(centre_circle)
        
        self.ax_pie.set_title("Sector Allocation")
        
        # Initialize the tooltip-style annotation (no arrow)
        self.pie_annot = self.ax_pie.annotate("", xy=(0,0), xytext=(15, -15),
            textcoords="offset points",
            bbox=dict(boxstyle="round,pad=0.5", fc="#333333", ec=self.BORDER_COLOR, alpha=0.9),
            color=self.TEXT_COLOR,
            fontsize=10,
            fontweight="bold")
        self.pie_annot.set_visible(False)
        
        # Connect the hover event
        self.canvas_pie.mpl_connect("motion_notify_event", self._on_pie_hover)

        self.fig_pie.tight_layout()
        self.canvas_pie.draw()

    def _on_pie_hover(self, event):
        """Handle hover events on the pie chart to show a detailed tooltip."""
        visible = False
        if event.inaxes == self.ax_pie:
            for i, wedge in enumerate(self.pie_wedges):
                if wedge.contains(event)[0]:
                    # Find the corresponding sector label from the legend
                    label = self.ax_pie.legend_.texts[i].get_text()
                    details = self.sector_details.get(label)

                    if details:
                        percent = details["percent"]
                        value = details["value"]
                        
                        # Determine concentration status and color
                        if percent > 30:
                            status = "High Concentration"
                            status_color = self.NEGATIVE_COLOR
                        elif percent > 15:
                            status = "Moderate Concentration"
                            status_color = "#f0c420" # A warning yellow
                        else:
                            status = "Well-Diversified"
                            status_color = self.POSITIVE_COLOR
                        
                        # Update annotation text and position
                        text = f"{label}\nValue: ${value:,.2f} ({percent:.1f}%)"
                        self.pie_annot.set_text(text)
                        
                        # Set the text of the status line with the dynamic color
                        # Note: This is a more complex way to color part of the text.
                        # For simplicity, we can color the whole box or just show text.
                        # A simpler approach is to change the bbox facecolor.
                        self.pie_annot.get_bbox_patch().set_facecolor(self.CARD_COLOR)
                        self.pie_annot.get_bbox_patch().set_edgecolor(status_color)

                        # Position the tooltip near the cursor
                        self.pie_annot.set_position((event.xdata, event.ydata))
                        self.pie_annot.set_visible(True)
                        visible = True
                        break
        
        # Hide annotation if the cursor is not over a wedge
        if not visible and self.pie_annot.get_visible():
            self.pie_annot.set_visible(False)
        
        self.canvas_pie.draw_idle()

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
        """Setup hover interaction for dashboard chart."""
        self.chart_hover_elements["line"] = self.ax_dash.axvline(color=self.ACCENT_COLOR, linestyle="--", visible=False)
        self.chart_hover_elements["text"] = self.ax_dash.text(0.05, 0.95, "", transform=self.ax_dash.transAxes, backgroundcolor=self.CARD_COLOR, bbox={"facecolor": self.CARD_COLOR, "edgecolor": self.BORDER_COLOR})
        self.canvas_dash.mpl_connect("motion_notify_event", self._on_chart_hover)
        self.canvas_dash.mpl_connect("axes_leave_event", self._on_chart_leave)

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
        self.analysis_data = self.goal_simulation_results.get(goal_id)
        if not self.analysis_data or 'data_cube' not in self.analysis_data:
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
        # Create figures and canvases, and embed them directly.
        # Tkinter's layout manager will handle sizing and resizing automatically.

        # --- Growth Projection Chart ---
        self.fig_interactive, self.ax_interactive = plt.subplots(dpi=100)
        # ADD THIS LINE:
        self.fig_interactive.subplots_adjust(left=0.15, bottom=0.18, right=0.95, top=0.90)
        self.canvas_interactive = FigureCanvasTkAgg(self.fig_interactive, master=proj_tab)
        self.canvas_interactive.get_tk_widget().pack(fill="both", expand=True)

        # --- Contribution Breakdown Chart ---
        self.fig_breakdown, self.ax_breakdown = plt.subplots(dpi=100)
        # ADD THIS LINE:
        self.fig_breakdown.subplots_adjust(left=0.15, bottom=0.18, right=0.95, top=0.90)
        self.canvas_breakdown = FigureCanvasTkAgg(self.fig_breakdown, master=breakdown_tab)
        self.canvas_breakdown.get_tk_widget().pack(fill="both", expand=True)

        # --- Outcomes Distribution Chart ---
        self.fig_dist, self.ax_dist = plt.subplots(dpi=100)
        # ADD THIS LINE:
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
        
        c_range = self.analysis_data['contrib_range']
        self.contrib_slider = self._create_slider(left_controls, "Monthly Contribution", c_range[0], c_range[-1], goal['monthly_contribution'], 0)
        h_range = self.analysis_data['horizon_range']
        self.horizon_slider = self._create_slider(left_controls, "Time Horizon (Years)", h_range[0]/12, h_range[-1]/12, self.analysis_data['base_months']/12, 1)

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
        # Force the entire application to process all pending events, including
        # the final geometry calculations. This is the programmatic equivalent
        # of a manual resize, ensuring a stable layout.
        self.update()
        
        # Now that the layout is guaranteed to be stable, draw the charts directly.
        self._on_what_if_update()


    def _on_what_if_update(self, *args):
        """
        REVISED: The single, robust handler for updating all 'What-If' analysis.
        It calculates data, then calls the stateless plotting functions, and finally draws.
        """
        if not all([self.active_analysis_goal, self.analysis_data, hasattr(self, 'contrib_slider')]):
            return

        try:
            # --- 1. Get current values from controls ---
            goal = self.active_analysis_goal
            contrib_val = self.contrib_slider.get()
            horizon_years = self.horizon_slider.get()
            horizon_months = int(horizon_years * 12)
            lump_sum = float(self.lump_sum_var.get() or "0")

            # --- 2. Find the closest pre-calculated data ---
            closest_contrib = min(self.analysis_data['contrib_range'], key=lambda x: abs(x - contrib_val))
            closest_horizon = min(self.analysis_data['horizon_range'], key=lambda x: abs(x - horizon_months))
            final_values = np.array(self.analysis_data['data_cube'][(closest_contrib, closest_horizon)]) + lump_sum

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
        """REWRITTEN: Stateless function to draw the growth projection chart."""
        ax = self.ax_interactive
        ax.clear()

        median = np.median(final_values)
        p10 = np.percentile(final_values, 10)
        p90 = np.percentile(final_values, 90)
        x_axis = np.arange(horizon_months + 1) / 12 if horizon_months > 0 else np.array([0])
        initial_value = goal['current_amount'] + lump_sum

        # Plot data
        ax.plot(x_axis, np.linspace(initial_value, median, len(x_axis)), color="#ffcc00", label="Median Path")
        ax.fill_between(x_axis, 
                        np.linspace(initial_value, p10, len(x_axis)), 
                        np.linspace(initial_value, p90, len(x_axis)), 
                        color=self.ACCENT_COLOR, alpha=0.2, label="10th-90th Percentile")
        ax.axhline(y=goal['target_amount'], color="red", linestyle=":", label=f"Target: ${goal['target_amount']:,.0f}")

        # Formatting
        ax.set_title("Growth Projection")
        ax.set_xlabel("Years")
        ax.set_ylabel("Portfolio Value ($)")
        ax.legend(loc="upper left")
        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.3)
        ax.set_xlim(0, max(1, x_axis[-1]) if len(x_axis) > 1 else 1) 
        ax.set_ylim(bottom=0) 
        
        self.canvas_interactive.draw()


    def _plot_contribution_breakdown(self, goal, final_values, horizon_months, lump_sum, contrib_val):
        """REWRITTEN: Stateless function to draw the contribution breakdown chart."""
        ax = self.ax_breakdown
        ax.clear()

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

        # Formatting
        ax.set_title("Source of Final Value (Median)")
        ax.set_xlabel("Years")
        ax.set_ylabel("Portfolio Value ($)")
        ax.legend(loc="upper left")
        ax.grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.3)
        ax.set_xlim(0, max(1, x_axis[-1]) if len(x_axis) > 1 else 1)
        ax.set_ylim(bottom=0)

        self.canvas_breakdown.draw()


    def _plot_outcomes_histogram(self, final_values, goal):
        """REWRITTEN: Stateless function to draw the outcomes distribution chart."""
        ax = self.ax_dist
        ax.clear()

        # Plot data
        ax.hist(final_values, bins=50, color=self.ACCENT_COLOR, alpha=0.75, density=True)
        
        median = np.median(final_values)
        ax.axvline(median, color="#ffcc00", lw=2, label=f"Median: ${median:,.0f}")
        ax.axvline(goal['target_amount'], color="white", linestyle=":", lw=2, label=f"Target: ${goal['target_amount']:,.0f}")

        # Formatting
        ax.set_title("Distribution of Final Portfolio Values")
        ax.set_xlabel("Final Value ($)")
        ax.set_ylabel("Probability Density")
        ax.legend(loc="upper right")
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


   
# --- Dialog Classes ---
class PositionDialog(simpledialog.Dialog):
    """Dialog for adding or editing positions."""
    def __init__(self, parent, title="Add Position", initial_data=None):
        self.initial_data = initial_data
        super().__init__(parent, title=title)

    def body(self, master):
        master.configure(bg=self.master.BG_COLOR)
        
        ttk.Label(master, text="Symbol:").grid(row=0, column=0, pady=5, sticky="w")
        self.symbol = ttk.Entry(master)
        self.symbol.grid(row=0, column=1, pady=5)
        
        ttk.Label(master, text="Shares:").grid(row=1, column=0, pady=5, sticky="w")
        self.shares = ttk.Entry(master)
        self.shares.grid(row=1, column=1, pady=5)
        
        ttk.Label(master, text="Entry Price:").grid(row=2, column=0, pady=5, sticky="w")
        self.price = ttk.Entry(master)
        self.price.grid(row=2, column=1, pady=5)
        
        # If editing, populate fields and disable symbol editing
        if self.initial_data:
            self.symbol.insert(0, self.initial_data["symbol"])
            self.symbol.config(state="readonly")
            self.shares.insert(0, self.initial_data["shares"])
            self.price.insert(0, self.initial_data["entry_price"])
            
        return self.symbol

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

# --- Main Execution (for launching) ---
if __name__ == "__main__":
    # This simulates your main application window
    main_app_root = tk.Tk()
    main_app_root.title("My Main Application")
    main_app_root.geometry("300x200")

    # Example button in your main app, notice its style is independent
    ttk.Button(
        main_app_root,
        text="Launch Portfolio",
        command=lambda: multiprocessing.Process(target=launch_portfolio_window, daemon=True).start()
    ).pack(pady=50)

    main_app_root.mainloop()