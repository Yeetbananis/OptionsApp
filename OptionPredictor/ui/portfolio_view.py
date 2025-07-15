import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
from datetime import datetime, timedelta
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.dates as mdates

# --- Mock Data API for Demonstration ---
class MockFinancialDataAPI:
    """A mock API to simulate fetching financial data."""
    def get_stock_details(self, ticker):
        price = np.random.uniform(50, 500)
        prev_close = price * (1 + np.random.uniform(-0.05, 0.05))
        return {
            "symbol": ticker,
            "shortName": f"{ticker.capitalize()} Inc.",
            "regularMarketPrice": price,
            "previousClose": prev_close,
            "marketCap": np.random.randint(1e9, 2e12, dtype=np.int64),
            "trailingPE": np.random.uniform(10, 30),
            "sector": np.random.choice(["Technology", "Healthcare", "Financials", "Industrials", "Consumer Discretionary"]),
            "beta": np.random.uniform(0.5, 1.8)
        }

import multiprocessing

# --- Main Portfolio Application ---
class PortfolioApp(tk.Tk):
    """
    A standalone portfolio application with a professional, modern UI.
    Designed to be isolated from the main app, maintaining all original features with an enhanced look.
    """
    def __init__(self):
        super().__init__()
        # self.controller is no longer needed unless you use multiprocessing queues to communicate
        self.api = MockFinancialDataAPI()

        # --- Theme & Styling ---
        self.BG_COLOR = "#1a1a1a"         # Dark background
        self.CARD_COLOR = "#252525"       # Card background
        self.SIDEBAR_COLOR = "#141414"    # Sidebar background
        self.TEXT_COLOR = "#d9d9d9"       # Primary text
        self.SECONDARY_TEXT = "#8a8a8a"   # Secondary text
        self.ACCENT_COLOR = "#00aaff"     # Highlight color
        self.POSITIVE_COLOR = "#00cc66"   # Green for gains
        self.NEGATIVE_COLOR = "#ff4444"   # Red for losses
        self.BORDER_COLOR = "#404040"     # Subtle borders

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
        """Define consistent, professional styles using generic font families."""
        style = ttk.Style(self)
        style.theme_use('clam')

        # --- Fonts (Using common, cross-platform fonts) ---
        self.FONT_NORMAL = ("Calibri", 12)
        self.FONT_BOLD = ("Calibri", 12, "bold")
        self.FONT_HEADER = ("Calibri", 16, "bold")
        self.FONT_TITLE = ("Calibri", 24, "bold")
        self.FONT_KPI = ("Calibri", 28, "bold")
        self.FONT_SIDEBAR = ("Calibri", 14)

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
        style.configure("TButton", font=self.FONT_BOLD, padding=10, background=self.CARD_COLOR, foreground=self.TEXT_COLOR, relief="flat")
        style.map("TButton", background=[('active', '#333333')], foreground=[('active', self.TEXT_COLOR)])
        style.configure("Accent.TButton", background=self.ACCENT_COLOR, foreground="#ffffff")
        style.map("Accent.TButton", background=[('active', '#0088cc')])

        # --- Sidebar Buttons ---
        style.configure("Sidebar.TButton", background=self.SIDEBAR_COLOR, foreground=self.SECONDARY_TEXT, font=self.FONT_SIDEBAR, padding=(15, 10), relief="flat")
        style.map("Sidebar.TButton", background=[('active', self.BG_COLOR)], foreground=[('active', self.TEXT_COLOR)])
        style.configure("AccentIndicator.TFrame", background=self.ACCENT_COLOR)

        # --- Treeview ---
        style.configure("Treeview", background=self.CARD_COLOR, foreground=self.TEXT_COLOR, fieldbackground=self.CARD_COLOR, font=self.FONT_NORMAL, rowheight=30)
        style.configure("Treeview.Heading", background=self.BORDER_COLOR, foreground=self.TEXT_COLOR, font=self.FONT_BOLD, padding=8)
        style.map("Treeview", background=[('selected', '#333333')])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})])

        # --- Matplotlib ---
        plt.style.use('dark_background')
        plt.rcParams.update({
            "figure.facecolor": self.CARD_COLOR,
            "axes.facecolor": self.CARD_COLOR,
            "axes.edgecolor": self.BORDER_COLOR,
            "axes.labelcolor": self.SECONDARY_TEXT,
            "xtick.color": self.SECONDARY_TEXT,
            "ytick.color": self.SECONDARY_TEXT,
            "grid.color": self.BORDER_COLOR,
            "text.color": self.TEXT_COLOR,
            "font.family": "sans-serif", # Use the most generic family
            "axes.titlesize": 14,
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
        """Build a sleek dashboard view."""
        view = ttk.Frame(parent)
        view.columnconfigure((0, 1), weight=1)
        view.rowconfigure(1, weight=1)

        # --- Header ---
        header = ttk.Frame(view)
        header.grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky="ew")
        ttk.Label(header, text="Dashboard", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Add Position", style="Accent.TButton", command=self._open_add_position_dialog).pack(side="right")

        # --- Left Column: KPIs and Chart ---
        left_frame = ttk.Frame(view)
        left_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        left_frame.rowconfigure(1, weight=1)
        left_frame.columnconfigure(0, weight=1)

        kpi_frame = ttk.Frame(left_frame)
        kpi_frame.grid(row=0, column=0, pady=(0, 20), sticky="ew")
        kpi_frame.columnconfigure((0, 1, 2), weight=1)
        self.kpi_total = self._create_kpi_card(kpi_frame, "Total Value", "$0.00", 0)
        self.kpi_day = self._create_kpi_card(kpi_frame, "Day's Gain", "$0.00", 1)
        self.kpi_gain = self._create_kpi_card(kpi_frame, "Total Gain", "$0.00", 2)

        chart_frame = ttk.Frame(left_frame, style="Card.TFrame", padding=15)
        chart_frame.grid(row=1, column=0, sticky="nsew")
        chart_frame.rowconfigure(0, weight=1)
        chart_frame.columnconfigure(0, weight=1)
        self.fig_dash, self.ax_dash = plt.subplots()
        self.canvas_dash = FigureCanvasTkAgg(self.fig_dash, chart_frame)
        self.canvas_dash.get_tk_widget().grid(row=0, column=0, sticky="nsew")
        self._setup_chart_hover()

        # --- Right Column: Positions and Pie ---
        right_frame = ttk.Frame(view)
        right_frame.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        right_frame.rowconfigure((0, 1), weight=1)
        right_frame.columnconfigure(0, weight=1)

        pos_frame = ttk.Frame(right_frame, style="Card.TFrame", padding=15)
        pos_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        pos_frame.rowconfigure(1, weight=1)
        pos_frame.columnconfigure(0, weight=1)
        ttk.Label(pos_frame, text="Positions", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w")
        self.tree = ttk.Treeview(pos_frame, columns=("symbol", "shares", "price", "value", "day_pct", "total_pct"), show="headings")
        self.tree.grid(row=1, column=0, sticky="nsew")
        for col, text in zip(self.tree["columns"], ["Symbol", "Shares", "Price", "Value", "Day %", "Total %"]):
            self.tree.heading(col, text=text)
            self.tree.column(col, anchor="e" if col != "symbol" else "w", width=100)
        self.tree.tag_configure("odd", background="#2a2a2a")

        pie_frame = ttk.Frame(right_frame, style="Card.TFrame", padding=15)
        pie_frame.grid(row=1, column=0, sticky="nsew")
        pie_frame.rowconfigure(0, weight=1)
        pie_frame.columnconfigure(0, weight=1)
        ttk.Label(pie_frame, text="Diversification", style="Header.TLabel", background=self.CARD_COLOR).grid(row=0, column=0, sticky="w")
        self.fig_pie, self.ax_pie = plt.subplots()
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
        """Build a goals view with scrollable cards."""
        view = ttk.Frame(parent)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(1, weight=1)

        header = ttk.Frame(view)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ttk.Label(header, text="Financial Goals", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="+ Add Goal", style="Accent.TButton", command=self._open_add_goal_dialog).pack(side="right")

        canvas = tk.Canvas(view, bg=self.BG_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(view, orient="vertical", command=canvas.yview)
        self.goals_container = ttk.Frame(canvas)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.create_window((0, 0), window=self.goals_container, anchor="nw", width=canvas.winfo_reqwidth())
        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.goals_container.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        return view

    def _build_analysis_view(self, parent):
        """Build an analysis view with tabs."""
        view = ttk.Frame(parent)
        view.columnconfigure(0, weight=1)
        view.rowconfigure(1, weight=1)

        header = ttk.Frame(view)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        ttk.Label(header, text="Analysis Lab", style="Title.TLabel").pack(side="left")

        notebook = ttk.Notebook(view)
        notebook.grid(row=1, column=0, sticky="nsew")
        style = ttk.Style()
        style.configure("TNotebook", background=self.BG_COLOR)
        style.configure("TNotebook.Tab", background=self.CARD_COLOR, padding=(10, 5), font=self.FONT_BOLD)
        style.map("TNotebook.Tab", background=[("selected", self.BG_COLOR)], foreground=[("selected", self.ACCENT_COLOR)])

        # --- Attribution Tab ---
        attr_frame = ttk.Frame(notebook, padding=15)
        notebook.add(attr_frame, text="Performance Attribution")
        attr_frame.rowconfigure(1, weight=1)
        attr_frame.columnconfigure(0, weight=1)
        ttk.Label(attr_frame, text="Performance Breakdown", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        self.fig_attr, self.ax_attr = plt.subplots()
        self.canvas_attr = FigureCanvasTkAgg(self.fig_attr, attr_frame)
        self.canvas_attr.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        # --- Stress Test Tab ---
        stress_frame = ttk.Frame(notebook, padding=15)
        notebook.add(stress_frame, text="Stress Testing")
        stress_frame.rowconfigure(1, weight=1)
        stress_frame.columnconfigure(0, weight=1)
        stress_header = ttk.Frame(stress_frame)
        stress_header.grid(row=0, column=0, sticky="ew")
        ttk.Label(stress_header, text="Stress Test", style="Header.TLabel").pack(side="left")
        ttk.Label(stress_header, text="Scenario:", style="Secondary.TLabel").pack(side="left", padx=10)
        self.scenario_var = tk.StringVar(value="2008 Financial Crisis")
        ttk.Combobox(stress_header, textvariable=self.scenario_var, values=["2008 Financial Crisis", "2020 COVID Crash", "Dot-com Burst"], state="readonly").pack(side="left", padx=5)
        self.scenario_var.trace("w", lambda *args: self._run_stress_test(self.scenario_var.get()))
        self.fig_stress, self.ax_stress = plt.subplots()
        self.canvas_stress = FigureCanvasTkAgg(self.fig_stress, stress_frame)
        self.canvas_stress.get_tk_widget().grid(row=1, column=0, sticky="nsew")

        return view

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
            if hasattr(self, "canvas_dash"): self._plot_history()
            if hasattr(self, "canvas_pie"): self._plot_pie()
        elif self.active_view_key == "goals" and hasattr(self, "goals_container"):
            self._update_goals()
        elif self.active_view_key == "analysis":
            if hasattr(self, "canvas_attr"): self._run_performance_attribution()
            if hasattr(self, "canvas_stress") and self.scenario_var.get(): self._run_stress_test(self.scenario_var.get())
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

    def _plot_history(self):
        """Plot portfolio value history with improved layout and padding."""
        self.ax_dash.clear()
        
        # --- Generate mock data ---
        dates = [datetime.now() - timedelta(days=x) for x in range(180)][::-1]
        values = np.cumsum(np.random.randn(180)) * 1000 + 100000
        
        # --- Plotting ---
        self.ax_dash.plot(dates, values, color=self.ACCENT_COLOR, linewidth=2)
        self.ax_dash.fill_between(dates, values, alpha=0.1, color=self.ACCENT_COLOR)
        
        # --- Formatting ---
        self.ax_dash.set_title("Portfolio Value Over 180 Days", fontsize=14, weight='bold')
        self.ax_dash.set_ylabel("Portfolio Value ($)")
        
        # Add padding to the y-axis to prevent the line from touching the top/bottom
        min_val, max_val = self.ax_dash.get_ylim()
        self.ax_dash.set_ylim(min_val * 0.98, max_val * 1.02)
        
        # Format x-axis to show month and year
        self.ax_dash.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        self.ax_dash.spines["top"].set_visible(False)
        self.ax_dash.spines["right"].set_visible(False)
        
        # Use tight_layout with padding to ensure nothing is cut off
        self.fig_dash.tight_layout(pad=2.0)
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
        """Update goals display."""
        for widget in self.goals_container.winfo_children():
            widget.destroy()
        if not self.portfolio["goals"]:
            ttk.Label(self.goals_container, text="No goals set.", style="Secondary.TLabel").pack(pady=20)
            return
        for goal in self.portfolio["goals"]:
            card = ttk.Frame(self.goals_container, style="Card.TFrame", padding=15)
            card.pack(fill="x", pady=5)
            ttk.Label(card, text=goal["name"], style="Header.TLabel", background=self.CARD_COLOR).pack(anchor="w")
            ttk.Label(card, text=f"Target: ${goal['target_amount']:,.2f} by {goal['target_date']}", style="Secondary.TLabel", background=self.CARD_COLOR).pack(anchor="w")
            progress = (goal["current_amount"] / goal["target_amount"]) * 100 if goal["target_amount"] > 0 else 0
            ttk.Progressbar(card, value=progress, length=300).pack(pady=5)
            sim_btn = ttk.Button(card, text="Run Simulation", command=lambda g=goal, c=card: self._run_goal_simulation(g, c))
            sim_btn.pack(side="left", pady=5)
            card.result = ttk.Label(card, text="", style="Secondary.TLabel", background=self.CARD_COLOR)
            card.result.pack(side="left", padx=10)

    def _run_goal_simulation(self, goal, card):
        """Simulate goal success probability."""
        def worker():
            time.sleep(1)
            prob = np.random.uniform(40, 90)
            self.after(0, lambda: card.result.config(text=f"Success: {prob:.1f}%", foreground=self.POSITIVE_COLOR if prob > 70 else self.NEGATIVE_COLOR))
        threading.Thread(target=worker, daemon=True).start()

    def _run_performance_attribution(self):
        """Plot performance attribution."""
        self.ax_attr.clear()
        factors = {"Market": np.random.uniform(5, 10), "Sector": np.random.uniform(-2, 2), "Selection": np.random.uniform(-1, 3)}
        colors = [self.POSITIVE_COLOR if v >= 0 else self.NEGATIVE_COLOR for v in factors.values()]
        self.ax_attr.bar(factors.keys(), factors.values(), color=colors)
        self.ax_attr.set_title("Performance Attribution")
        self.ax_attr.spines["top"].set_visible(False)
        self.ax_attr.spines["right"].set_visible(False)
        self.fig_attr.tight_layout()
        self.canvas_attr.draw()

    def _run_stress_test(self, scenario):
        """Plot stress test results."""
        self.ax_stress.clear()
        impacts = {"2008 Financial Crisis": -40, "2020 COVID Crash": -30, "Dot-com Burst": -50}
        impact = impacts.get(scenario, 0) + np.random.uniform(-5, 5)
        self.ax_stress.barh(["Portfolio"], [impact], color=self.NEGATIVE_COLOR)
        self.ax_stress.set_title(f"{scenario} Impact")
        self.ax_stress.spines["top"].set_visible(False)
        self.ax_stress.spines["right"].set_visible(False)
        self.fig_stress.tight_layout()
        self.canvas_stress.draw()

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

    # --- Dialogs ---
    def _open_add_position_dialog(self):
        """Open dialog to add a position."""
        dialog = PositionDialog(self)
        if dialog.result:
            self.portfolio["positions"].append(dialog.result)
            self._fetch_market_data()

    def _open_add_goal_dialog(self):
        """Open dialog to add a goal."""
        dialog = GoalDialog(self)
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

# --- Dialog Classes ---
class PositionDialog(simpledialog.Dialog):
    """Dialog for adding positions."""
    def body(self, master):
        master.configure(bg=self.master.BG_COLOR)
        ttk.Label(master, text="Symbol:").grid(row=0, column=0, pady=5)
        self.symbol = ttk.Entry(master)
        self.symbol.grid(row=0, column=1, pady=5)
        ttk.Label(master, text="Shares:").grid(row=1, column=0, pady=5)
        self.shares = ttk.Entry(master)
        self.shares.grid(row=1, column=1, pady=5)
        ttk.Label(master, text="Entry Price:").grid(row=2, column=0, pady=5)
        self.price = ttk.Entry(master)
        self.price.grid(row=2, column=1, pady=5)
        return self.symbol

    def apply(self):
        try:
            self.result = {
                "symbol": self.symbol.get().upper(),
                "shares": float(self.shares.get()),
                "entry_price": float(self.price.get())
            }
        except ValueError:
            messagebox.showerror("Error", "Invalid input.")

class GoalDialog(simpledialog.Dialog):
    """Dialog for adding goals."""
    def body(self, master):
        master.configure(bg=self.master.BG_COLOR)
        ttk.Label(master, text="Name:").grid(row=0, column=0, pady=5)
        self.name = ttk.Entry(master)
        self.name.grid(row=0, column=1, pady=5)
        ttk.Label(master, text="Target Amount:").grid(row=1, column=0, pady=5)
        self.amount = ttk.Entry(master)
        self.amount.grid(row=1, column=1, pady=5)
        ttk.Label(master, text="Target Date (YYYY-MM-DD):").grid(row=2, column=0, pady=5)
        self.date = ttk.Entry(master)
        self.date.grid(row=2, column=1, pady=5)
        return self.name

    def apply(self):
        try:
            self.result = {
                "name": self.name.get(),
                "target_amount": float(self.amount.get()),
                "target_date": self.date.get(),
                "current_amount": 0
            }
        except ValueError:
            messagebox.showerror("Error", "Invalid input.")

def launch_portfolio_window():
    """Initializes and runs the PortfolioApp in a separate process."""
    app = PortfolioApp()
    app.mainloop()

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