# ui/StockResearchSuite.py (Final Corrected and Polished Version)
import tkinter as tk
from tkinter import ttk, font as tkfont
import queue
import threading
import webbrowser
import pandas as pd
from PIL import Image, ImageTk
import requests
import io
import math
from curl_cffi import requests as cffi_requests

from nltk.sentiment.vader import SentimentIntensityAnalyzer
import mplfinance as mpf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from data.research_orchestrator import ResearchOrchestrator

# --- Helper Functions (No changes needed here) ---
def _tree(parent):
    wrap = ttk.Frame(parent)
    wrap.pack(fill="both", expand=True, padx=5, pady=5)
    tv = ttk.Treeview(wrap, show="headings")
    vsb = ttk.Scrollbar(wrap, orient="vertical", command=tv.yview)
    hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tv.xview)
    tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    wrap.grid_rowconfigure(0, weight=1)
    wrap.grid_columnconfigure(0, weight=1)
    tv.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    return tv

def _fill(tv, df):
    if df.empty:
        tv.delete(*tv.get_children())
        return
    tv.delete(*tv.get_children())
    tv["columns"] = list(df.columns)
    for col in df.columns:
        tv.heading(col, text=col)
    for _, row in df.iterrows():
        tv.insert("", "end", values=list(row))
    style = ttk.Style(tv.master)
    font_spec = style.lookup("Treeview", "font") or "TkDefaultFont"
    try: f = tkfont.nametofont(font_spec)
    except tk.TclError: f = tkfont.Font(tv, font=font_spec)
    pad = 15
    for col in df.columns:
        max_w = f.measure(col)
        for item in tv.get_children():
            try:
                cell_val = tv.set(item, col)
                max_w = max(max_w, f.measure(cell_val))
            except tk.TclError:
                continue
        tv.column(col, width=max_w + pad, stretch=False)

def get_sentiment_label(score):
    if score >= 0.35: return "Strong Bullish"
    elif score >= 0.15: return "Bullish"
    elif score <= -0.35: return "Strong Bearish"
    elif score <= -0.15: return "Bearish"
    else: return "Neutral"

def get_sentiment_color(score):
    if score >= 0.15: return "green"
    elif score <= -0.15: return "red"
    else: return "#888888"

# --- Main Class ---
class StockResearchSuite(tk.Toplevel):
    def __init__(self, parent, app_controller, theme="light", finnhub_key="d114k6hr01qse6lf8c1gd114k6hr01qse6lf8c20"):
        super().__init__(parent)
        self.title("Stock Research Suite")
        self.geometry("1600x950")
        self.minsize(1366, 768)
        self.withdraw()

        self.app_controller = app_controller
        self.current_theme = theme
        self.orchestrator = ResearchOrchestrator(finnhub_key)
        self.vader = SentimentIntensityAnalyzer()
        
        self.data_queue = queue.Queue()
        self.tasks_to_complete = 0
        self.tasks_completed = 0
        self.after_id = None
        self.news_articles = []
        self.company_logo = None
        self.current_session = None # Add this line

        self._build_ui()
        self.app_controller.apply_theme_to_window(self)
        self.deiconify()
        self.focus_force()

    # In StockResearchSuite.py, REPLACE this method
    def _build_ui(self):
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(2, weight=1)
        main_frame.columnconfigure(0, weight=1)

        # Header and Snapshot bar (no changes needed)
        header_frame = self._create_header(main_frame)
        header_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))

        self.snapshot_frame = self._create_snapshot_bar(main_frame)
        self.snapshot_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self.snapshot_frame.grid_remove()

        # --- Main Content Area ---
        # The main content frame now only contains the notebook.
        content_frame = ttk.Frame(main_frame)
        content_frame.grid(row=2, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(content_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # Build the content for the tabs
        self._build_tabs()

    def _build_tabs(self):
        self.overview_tab = ttk.Frame(self.notebook, padding=5)
        self.financials_tab = ttk.Frame(self.notebook, padding=5)
        self.news_tab = ttk.Frame(self.notebook, padding=5)
        self.options_tab = ttk.Frame(self.notebook, padding=5)
        self.technicals_tab = ttk.Frame(self.notebook, padding=5)

        self.notebook.add(self.overview_tab, text="🔍 Overview")
        self.notebook.add(self.financials_tab, text="📊 Financials")
        self.notebook.add(self.news_tab, text="📰 News & Sentiment")
        self.notebook.add(self.options_tab, text="⛓️ Options")
        self.notebook.add(self.technicals_tab, text="📈 Technicals & Fundamentals")

        self._build_overview_tab()
        self._build_financials_tab()
        self._build_news_tab()
        self._build_options_tab()
        self._build_technicals_tab()


    def _create_snapshot_bar(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.columnconfigure(2, weight=1)
        self.logo_label = ttk.Label(frame)
        self.logo_label.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, 10))
        self.company_label = ttk.Label(frame, text="Company Name (TICKER)", font=tkfont.Font(size=14, weight="bold"))
        self.company_label.grid(row=0, column=1, sticky="w")
        self.sector_label = ttk.Label(frame, text="Sector | Industry", font=tkfont.Font(size=9))
        self.sector_label.grid(row=1, column=1, sticky="w")
        self.price_label = ttk.Label(frame, text="$0.00", font=tkfont.Font(size=14))
        self.price_label.grid(row=0, column=3, sticky="e")
        self.change_label = ttk.Label(frame, text="+0.00 (0.00%)", font=tkfont.Font(size=10))
        self.change_label.grid(row=1, column=3, sticky="e")
        return frame
    

    def _create_header(self, parent):
        frame = ttk.Frame(parent)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Ticker:").pack(side="left", padx=(0, 5))
        self.ticker_entry = ttk.Entry(frame, width=15)
        self.ticker_entry.pack(side="left", padx=5)
        self.ticker_entry.bind("<Return>", self._on_research_click)
        self.research_button = ttk.Button(frame, text="Research", command=self._on_research_click)
        self.research_button.pack(side="left", padx=5)
        self.progress_bar = ttk.Progressbar(frame, mode='determinate')
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=10)
        self.progress_bar.pack_forget()
        return frame

    # In ui/StockResearchSuite.py, REPLACE this method
    def _build_overview_tab(self):
        # --- Create a single scrollable container for the entire tab ---
        canvas = tk.Canvas(self.overview_tab, borderwidth=0, highlightthickness=0)
        self.overview_canvas = canvas # Save a reference to the canvas
        vsb = ttk.Scrollbar(self.overview_tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        scrollable_frame = ttk.Frame(canvas)
        frame_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        # --- Configure scrolling behavior ---
        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(frame_id, width=event.width)

        def _on_mousewheel(event):
            if event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")

        canvas.bind("<Configure>", _on_canvas_configure)
        scrollable_frame.bind("<Configure>", _on_frame_configure)
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        canvas.bind_all("<Button-4>", _on_mousewheel)
        canvas.bind_all("<Button-5>", _on_mousewheel)

        # --- Build content vertically inside the scrollable_frame ---
        scrollable_frame.columnconfigure(0, weight=1)

        # 1. Chart Frame
        self.chart_frame = ttk.LabelFrame(scrollable_frame, text="Price Chart", padding=5)
        self.chart_frame.config(height=500)
        self.chart_frame.grid(row=0, column=0, sticky="ew")
        self.chart_frame.grid_propagate(False)

        # 2. --- FIX: Frame for the timeframe buttons, placed INSIDE the scrollable frame ---
        button_bar = ttk.Frame(scrollable_frame)
        button_bar.grid(row=1, column=0, sticky="ew", pady=(5, 10))
        
        # 3. --- FIX: Create the buttons ---
        timeframes = {"1M": 30, "1Y": 252, "5Y": 252*5, "All": None}
        for text, days in timeframes.items():
            btn = ttk.Button(button_bar, text=text, width=4, command=lambda d=days: self._redraw_chart_with_period(d))
            btn.pack(side="left", padx=2)

        # 4. Key Metrics & Profile Frame (now at row 2)
        info_frame = ttk.Frame(scrollable_frame)
        info_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        info_frame.columnconfigure(0, weight=1)
        info_frame.columnconfigure(1, weight=2)
        
        self.perf_frame = ttk.LabelFrame(info_frame, text="Key Metrics", padding=10)
        self.perf_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        self.profile_frame = ttk.LabelFrame(info_frame, text="Company Profile", padding=10)
        self.profile_frame.grid(row=0, column=1, sticky="nsew")
        
        self.profile_text = tk.Text(self.profile_frame, wrap="word", height=10, relief="flat")
        self.profile_text.pack(fill="both", expand=True)
        self.profile_text.config(state="disabled")

        # 5. Former Sidebar Panels at the bottom (now at row 3)
        bottom_panels_frame = ttk.Frame(scrollable_frame)
        bottom_panels_frame.grid(row=3, column=0, sticky="ew", pady=(10, 10))
        bottom_panels_frame.columnconfigure(0, weight=1)
        bottom_panels_frame.columnconfigure(1, weight=1)
        bottom_panels_frame.columnconfigure(2, weight=1)

        self.analyst_frame = ttk.LabelFrame(bottom_panels_frame, text="👨‍⚖️ Analyst Ratings", padding=10)
        self.analyst_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        self.events_frame = ttk.LabelFrame(bottom_panels_frame, text="🗓️ Upcoming Events", padding=10)
        self.events_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        
        self.insider_frame = ttk.LabelFrame(bottom_panels_frame, text="💼 Insider Transactions", padding=10)
        self.insider_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        
        self.analyst_tree = _tree(self.analyst_frame)
        self.events_tree = _tree(self.events_frame)
        self.insider_tree = _tree(self.insider_frame)

    def _build_financials_tab(self):
        self.financials_tab.rowconfigure(0, weight=1)
        self.financials_tab.rowconfigure(1, weight=2)
        self.financials_tab.columnconfigure(0, weight=1)
        visual_frame = ttk.Frame(self.financials_tab)
        visual_frame.grid(row=0, column=0, sticky="nsew", pady=(0,10))
        self.financial_chart_frame = ttk.LabelFrame(visual_frame, text="Annual Trends", padding=10)
        self.financial_chart_frame.pack(fill="both", expand=True)
        table_frame = ttk.Frame(self.financials_tab)
        table_frame.grid(row=1, column=0, sticky="nsew")
        self.financials_notebook = ttk.Notebook(table_frame)
        self.financials_notebook.pack(fill="both", expand=True)
        self.income_tab = ttk.Frame(self.financials_notebook)
        self.balance_tab = ttk.Frame(self.financials_notebook)
        self.cash_tab = ttk.Frame(self.financials_notebook)
        self.financials_notebook.add(self.income_tab, text="Income Statement")
        self.financials_notebook.add(self.balance_tab, text="Balance Sheet")
        self.financials_notebook.add(self.cash_tab, text="Cash Flow")
        self.income_tv = _tree(self.income_tab)
        self.balance_tv = _tree(self.balance_tab)
        self.cash_tv = _tree(self.cash_tab)
        
    def _build_news_tab(self):
        left_frame = ttk.Frame(self.news_tab)
        left_frame.pack(side="left", fill="both", expand=True, padx=(0,10))
        right_frame = ttk.Frame(self.news_tab, width=200)
        right_frame.pack(side="right", fill="y", pady=(10,0))
        
        # This is the Treeview for news articles
        self.news_tree = _tree(left_frame)
        self.news_tree.bind("<Double-1>", self._open_article)
        
        # --- FIX: Configure the columns for the news treeview ---
        self.news_tree["columns"] = ("headline", "sentiment", "score")
        self.news_tree.heading("headline", text="Headline")
        self.news_tree.heading("sentiment", text="Sentiment")
        self.news_tree.heading("score", text="Score")
        self.news_tree.column("headline", width=600, anchor="w", stretch=True)
        self.news_tree.column("sentiment", width=100, anchor="center")
        self.news_tree.column("score", width=80, anchor="center")
        
        self.sentiment_gauge_frame = ttk.LabelFrame(right_frame, text="Overall Sentiment", padding=10)
        self.sentiment_gauge_frame.pack(fill="x", pady=5)
        self.sentiment_canvas = tk.Canvas(self.sentiment_gauge_frame, width=180, height=120, highlightthickness=0)
        self.sentiment_canvas.pack()
        self.news_sentiment_label = ttk.Label(self.sentiment_gauge_frame, text="Fetching...", font=("Segoe UI", 12, "bold"))
        self.news_sentiment_label.pack(pady=5)

    def _build_options_tab(self):
        top_frame = ttk.Frame(self.options_tab, padding=(0,0,0,10))
        top_frame.pack(fill="x")
        ttk.Label(top_frame, text="Expiration:").pack(side="left")
        self.exp_combo = ttk.Combobox(top_frame, state="readonly", width=20)
        self.exp_combo.pack(side="left", padx=5)
        self.exp_combo.bind("<<ComboboxSelected>>", self._on_expiry_selected)
        self.option_type_var = tk.StringVar(value="calls")
        ttk.Radiobutton(top_frame, text="Calls", variable=self.option_type_var, value="calls", command=self._on_expiry_selected).pack(side="left", padx=(20, 5))
        ttk.Radiobutton(top_frame, text="Puts", variable=self.option_type_var, value="puts", command=self._on_expiry_selected).pack(side="left")
        self.options_tree = _tree(self.options_tab)

    def _build_technicals_tab(self):
        self.technicals_tab.rowconfigure(0, weight=1)
        self.technicals_tab.columnconfigure(0, weight=1)
        self.technicals_tab.columnconfigure(1, weight=1)
        tech_frame = ttk.LabelFrame(self.technicals_tab, text="Technical Indicators", padding=10)
        tech_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.tech_tree = _tree(tech_frame)
        funda_frame = ttk.LabelFrame(self.technicals_tab, text="Fundamental Ratios", padding=10)
        funda_frame.grid(row=0, column=1, sticky="nsew")
        self.funda_tree = _tree(funda_frame)


    def _on_research_click(self, event=None):
        # FIX: Change the boolean flag to a counter, reset it on each manual click.
        self.auto_retry_count = getattr(self, 'auto_retry_count', 0) if event is None else 0

        ticker = self.ticker_entry.get()
        if not ticker: return
        
        self._clear_all_data_views()
        self.research_button.config(state="disabled")
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=10)
        
        self.data_queue, self.tasks_to_complete = self.orchestrator.fetch_all_data(ticker, self.current_session)
        
        self.tasks_completed = 0
        self.progress_bar.config(maximum=self.tasks_to_complete, value=0)
        self.snapshot_frame.grid()
        
        if self.after_id: self.after_cancel(self.after_id)
        self._poll_data_queue()


    def _poll_data_queue(self):
        try:
            while True:
                key, payload = self.data_queue.get_nowait()
                self.tasks_completed += 1
                self.progress_bar['value'] = self.tasks_completed
                self._update_ui_component(key, payload)
        except queue.Empty:
            if self.tasks_completed >= self.tasks_to_complete:
                self.progress_bar.pack_forget()

                # --- FIX: Check the counter before retrying, and limit to 5 attempts ---
                profile_is_blank = "No company profile available." in self.profile_text.get("1.0", "3.0")
                
                # If it failed AND our retry count is less than 5...
                if profile_is_blank and getattr(self, 'auto_retry_count', 0) < 5:
                    self.auto_retry_count += 1 # Increment the counter
                    print(f"Critical data missing. Auto-retrying... (Attempt {self.auto_retry_count}/5)")
                    self.after(50, self._on_research_click)
                    return # Exit to let the new fetch start
                
                # If the fetch was successful OR we've hit the retry limit, finish normally.
                self.research_button.config(state="normal")
                self.update_idletasks()
                if hasattr(self, 'overview_canvas'):
                    self.overview_canvas.configure(scrollregion=self.overview_canvas.bbox("all"))
            else:
                self.after_id = self.after(100, self._poll_data_queue)

    # In ui/StockResearchSuite.py, REPLACE this method
    def _update_ui_component(self, key, payload):
        if payload is None: return
        if isinstance(payload, dict) and payload.get("error"):
            print(f"Error received for {key}: {payload['error']}")
            return
        try:
            if key == "profile": self._update_profile(payload)
            elif key == "provider_hub":
                # --- FIX: Store the full price DataFrame and trigger the initial chart draw ---
                self.price_df = payload.get("price_df")
                self._redraw_chart_with_period(252) # Draw initial 1-year chart
                
                self._update_snapshot_bar(payload)
                self._update_insider_transactions(payload.get("insider_transactions", []))
                self._update_technicals_tab(payload)
            elif key == "fundamentals":
                 self._update_fundamentals_tab(payload)
                 self._update_performance_snapshot(payload)
                 self._update_analyst_ratings(payload.get('recommendations'))
            elif key == "events": self._update_events(payload)
            elif key == "financials": self._update_financials(payload)
            elif key == "news": self._update_news_and_sentiment(payload)
            elif key == "options": self._update_options_tab(payload)
        except Exception as e:
            import traceback
            print(f"Error updating UI for component '{key}': {e}")
            traceback.print_exc()

    def _update_profile(self, data):
        self.sector_label.config(text=f"{data.get('sector', 'N/A')} | {data.get('industry', 'N/A')}")
        self.profile_text.config(state="normal")
        self.profile_text.delete("1.0", tk.END)
        self.profile_text.insert("1.0", data.get('longBusinessSummary', 'No company profile available.'))
        self.profile_text.config(state="disabled")
        if logo_url := data.get('logo_url'):
            threading.Thread(target=self._load_logo, args=(logo_url,), daemon=True).start()

    def _load_logo(self, url):
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).resize((48, 48), Image.Resampling.LANCZOS)
            self.company_logo = ImageTk.PhotoImage(image)
            self.logo_label.config(image=self.company_logo)
        except Exception as e:
            print(f"Failed to load company logo: {e}")

    def _update_snapshot_bar(self, data):
        ticker = self.ticker_entry.get().upper()
        name = data.get('shortName', ticker)
        price = data.get('last_price', 0.0)
        prev_close = data.get('previousClose', 0.0)
        change = price - prev_close if price and prev_close else 0.0
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        color = "green" if change >= 0 else "red"
        sign = "+" if change >= 0 else ""
        self.company_label.config(text=f"{name} ({ticker})")
        self.price_label.config(text=f"${price:,.2f}")
        self.change_label.config(text=f"{sign}{change:,.2f} ({sign}{change_pct:.2f}%)", foreground=color)
        
    def _update_performance_snapshot(self, data):
        def fmt_num(value, format_str="{:,.2f}"):
            return format_str.format(value) if isinstance(value, (int, float)) else "N/A"
        def fmt_large_num(n):
            if not isinstance(n, (int, float)): return "N/A"
            if n > 1e12: return f"${n/1e12:.2f} T"
            if n > 1e9: return f"${n/1e9:.2f} B"
            if n > 1e6: return f"${n/1e6:.2f} M"
            return f"${n:,.2f}"

        for widget in self.perf_frame.winfo_children(): widget.destroy()
        
        # --- FIX: Use safe .get() with defaults for all values ---
        low_52 = data.get('fiftyTwoWeekLow')
        high_52 = data.get('fiftyTwoWeekHigh')
        range_52_str = f"{fmt_num(low_52)} - {fmt_num(high_52)}" if low_52 and high_52 else "N/A"
        
        div_yield = data.get('dividendYield')
        yield_str = f"{div_yield * 100:.2f}%" if isinstance(div_yield, (int, float)) else "N/A"

        metrics = {
            "Market Cap": fmt_large_num(data.get("marketCap")),
            "Avg. Volume": fmt_num(data.get('averageVolume'), format_str="{:,.0f}"),
            "52 Week Range": range_52_str,
            "P/E Ratio": fmt_num(data.get('current_pe')),
            "EPS": fmt_num(data.get('trailingEps')),
            "Dividend Yield": yield_str 
        }
        
        for i, (label, value) in enumerate(metrics.items()):
            ttk.Label(self.perf_frame, text=f"{label}:", font=("Segoe UI", 9, "bold")).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(self.perf_frame, text=value).grid(row=i, column=1, sticky="w", padx=5)

    def _redraw_chart_with_period(self, days: int | None):
        """Slices the main DataFrame and calls the plot function."""
        if self.price_df is None or self.price_df.empty:
            return

        # If days is None, use the whole dataframe ("All" button)
        # Otherwise, get the last N days.
        df_to_plot = self.price_df if days is None else self.price_df.tail(days)
        
        self._update_chart(df_to_plot)

    def _update_chart(self, df):
        """The actual plotting function that draws the mplfinance chart."""
        for widget in self.chart_frame.winfo_children():
            widget.destroy()

        if df is None or df.empty:
            ttk.Label(self.chart_frame, text="Price data not available.").pack(pady=20)
            return
            
        style = 'nightclouds' if self.current_theme == 'dark' else 'yahoo'
        
        try:
            fig, _ = mpf.plot(df,
                              type='candle',
                              style=style,
                              title=f"\n{self.ticker_entry.get().upper()} Price Chart",
                              ylabel='Price ($)',
                              volume=False, # Set to False for a cleaner look
                              mav=(50, 200),
                              returnfig=True,
                              figsize=(12, 6),
                              figratio=(16, 7),
                              tight_layout=True,
                              xrotation=0)
                              
            canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)
        except Exception as e:
            print(f"Chart plotting error: {e}")
            ttk.Label(self.chart_frame, text="Could not plot chart.").pack(pady=20)

    def _update_financials(self, data):
        def _format_df(df):
            if df.empty: return pd.DataFrame()
            return (df.transpose().pipe(lambda d: d.map(lambda x: f"{x/1e6:,.0f}M" if isinstance(x, (int, float)) else x)).rename_axis("Date").reset_index())
        try:
            _fill(self.income_tv, _format_df(data["income"]))
            _fill(self.balance_tv, _format_df(data["balance"]))
            _fill(self.cash_tv, _format_df(data["cashflow"]))
            self._plot_financial_charts(data["income"])
        except Exception as e:
            print(f"Error processing financial data: {e}")

    # In ui/StockResearchSuite.py, REPLACE this method
    def _plot_financial_charts(self, income_stmt):
        for widget in self.financial_chart_frame.winfo_children(): widget.destroy()
        if income_stmt.empty: return

        df = income_stmt.transpose()
        df.index = pd.to_datetime(df.index)
        df_annual = df[df.index.month == df.index.month[-1]].sort_index().tail(5)
        
        theme = self.app_controller.theme_settings()
        fig = Figure(figsize=(12, 3.5), dpi=100, facecolor=theme['bg'])
        fig.subplots_adjust(bottom=0.2)
        axes = [fig.add_subplot(121), fig.add_subplot(122)]
        
        def style_ax(ax, title):
            ax.set_title(title, color=theme['fg'])
            ax.tick_params(axis='y', colors=theme['fg'])
            ax.tick_params(axis='x', colors=theme['fg'], rotation=30, labelsize=9)
            ax.set_facecolor(theme['bg'])
            ax.get_yaxis().set_major_formatter(lambda x, p: f'{x/1e6:,.0f}M')
            for spine in ax.spines.values(): spine.set_edgecolor(theme['fg'])

        if "Total Revenue" in df_annual:
            bars1 = axes[0].bar(df_annual.index.strftime('%Y'), df_annual["Total Revenue"], color='#2980b9', width=0.6)
            style_ax(axes[0], "Annual Revenue")
            
        if "Net Income" in df_annual:
            colors = ['#27ae60' if x >= 0 else '#c0392b' for x in df_annual["Net Income"]]
            bars2 = axes[1].bar(df_annual.index.strftime('%Y'), df_annual["Net Income"], color=colors, width=0.6)
            style_ax(axes[1], "Annual Net Income")

        canvas = FigureCanvasTkAgg(fig, master=self.financial_chart_frame)
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(fill="both", expand=True)

        # --- START OF FIX: Use theme colors for the tooltip ---
        annot1 = axes[0].annotate("", xy=(0,0), xytext=(-20,20), textcoords="offset points",
                                  bbox=dict(boxstyle="round", fc=theme['entry_bg'], ec=theme['fg'], lw=1),
                                  arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.1", color=theme['fg']),
                                  color=theme['fg']) # Set text color
        annot2 = axes[1].annotate("", xy=(0,0), xytext=(-20,20), textcoords="offset points",
                                  bbox=dict(boxstyle="round", fc=theme['entry_bg'], ec=theme['fg'], lw=1),
                                  arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.1", color=theme['fg']),
                                  color=theme['fg']) # Set text color
        # --- END OF FIX ---
                                  
        annot1.set_visible(False)
        annot2.set_visible(False)

        def update_annot(bar_container, annot, event):
            for bar in bar_container:
                cont, _ = bar.contains(event)
                if cont:
                    height = bar.get_height()
                    annot.xy = (bar.get_x() + bar.get_width() / 2, height)
                    annot.set_text(f"${height/1e6:,.1f} M")
                    annot.set_visible(True)
                    fig.canvas.draw_idle()
                    return
            
            if annot.get_visible():
                annot.set_visible(False)
                fig.canvas.draw_idle()

        def on_hover(event):
            if event.inaxes == axes[0] and "bars1" in locals():
                update_annot(bars1, annot1, event)
            elif event.inaxes == axes[1] and "bars2" in locals():
                update_annot(bars2, annot2, event)
            else: # If mouse is not over any axes with bars, hide tooltips
                if annot1.get_visible(): annot1.set_visible(False); fig.canvas.draw_idle()
                if annot2.get_visible(): annot2.set_visible(False); fig.canvas.draw_idle()

        fig.canvas.mpl_connect("motion_notify_event", on_hover)
        canvas.draw()

    def _update_news_and_sentiment(self, articles):
        self.news_articles = sorted(articles, key=lambda x: x.get('published', {})) # Safe get
        if not articles:
            self._draw_sentiment_gauge(0, "No News")
            self.news_sentiment_label.config(text="No news found.")
            return
        analyzed_articles = [{"headline": a['headline'], "score": self.vader.polarity_scores(f"{a['headline']} {a.get('summary', '')}")["compound"], "url": a['url']} for a in articles]
        self.news_tree.delete(*self.news_tree.get_children())
        if not analyzed_articles: return
        avg_score = sum(a["score"] for a in analyzed_articles) / len(analyzed_articles)
        overall_label = get_sentiment_label(avg_score)
        self._draw_sentiment_gauge(avg_score, overall_label)
        self.news_sentiment_label.config(text=f"{overall_label} ({avg_score:.2f})")
        for article in analyzed_articles:
            score_color = get_sentiment_color(article['score'])
            self.news_tree.tag_configure(score_color, foreground=score_color)
            self.news_tree.insert("", "end", values=(article["headline"], get_sentiment_label(article['score']), f"{article['score']:.2f}"), tags=(score_color,))

    def _draw_sentiment_gauge(self, score, label):
        canvas = self.sentiment_canvas
        canvas.delete("all")
        theme = self.app_controller.theme_settings()
        canvas.config(bg=theme['bg'])
        w, h, cx, cy = 180, 120, 90, 90
        for i in range(101):
            angle = 180 - (i * 1.8)
            x1, y1 = cx + 70 * math.cos(math.radians(angle)), cy - 70 * math.sin(math.radians(angle))
            x2, y2 = cx + 80 * math.cos(math.radians(angle)), cy - 80 * math.sin(math.radians(angle))
            if i<25: color="#c0392b"
            elif i<45: color="#e67e22"
            elif i<55: color="#f1c40f"
            elif i<75: color="#2ecc71"
            else: color="#27ae60"
            canvas.create_line(x1, y1, x2, y2, fill=color, width=2)
        angle = 180 - ((score + 1) * 90)
        nx, ny = cx + 65 * math.cos(math.radians(angle)), cy - 65 * math.sin(math.radians(angle))
        canvas.create_line(cx, cy, nx, ny, fill=theme['fg'], width=3, arrow=tk.LAST)
        canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=theme['fg'])

    def _update_options_tab(self, data):
        self.options_data = data
        expirations = list(data.keys())
        self.exp_combo['values'] = expirations
        if expirations: self.exp_combo.set(expirations[0]); self._on_expiry_selected()
    
    def _on_expiry_selected(self, event=None):
        expiry = self.exp_combo.get()
        if not expiry: return
        # This safer .get() prevents errors if data is malformed
        df = self.options_data.get(expiry, {}).get(self.option_type_var.get())

        # This new block checks for None BEFORE trying to access .empty
        if df is None:
            _fill(self.options_tree, pd.DataFrame(columns=['Message']))
            if self.options_tree.get_children(): self.options_tree.item(self.options_tree.get_children()[0], values=("Data not available for this type.",))
            return
            
        if df.empty:
            _fill(self.options_tree, pd.DataFrame(columns=['Message']))
            if self.options_tree.get_children(): self.options_tree.item(self.options_tree.get_children()[0], values=("No options data for this expiry.",))
            return
        cols = ['strike', 'lastPrice', 'bid', 'ask', 'change', 'percentChange', 'volume', 'openInterest', 'impliedVolatility']
        df_display = df[cols].copy()
        df_display.columns = ['Strike','Last','Bid','Ask','Chg','% Chg','Volume','Open Int','IV']
        for col in ['Last','Bid','Ask','Chg']: df_display[col] = df_display[col].apply(lambda x: f"{x:.2f}" if isinstance(x, (int,float)) else 'N/A')
        df_display['% Chg'] = df_display['% Chg'].apply(lambda x: f"{x:+.2f}%" if isinstance(x, (int,float)) else 'N/A')
        df_display['IV'] = df_display['IV'].apply(lambda x: f"{x*100:.1f}%" if isinstance(x, (int,float)) else 'N/A')
        _fill(self.options_tree, df_display)
        
    def _update_technicals_tab(self, data):
        tech_data = {"Price vs 50D SMA": "Above" if data.get('price_above_sma50') else "Below", "Golden Cross": "Yes" if data.get('GoldenCross') else "No", "Death Cross": "Yes" if data.get('DeathCross') else "No", "RSI Overbought": "Yes" if data.get('RSI_Overbought') else "No", "RSI Oversold": "Yes" if data.get('RSI_Oversold') else "No", "Bollinger Squeeze": "Yes" if data.get('BollingerBandSqueeze') else "No", "IV Rank": f"{data.get('IVRank_%', 0):.1f}%", "IV (30d)": f"{data.get('IV_σ', 0):.2f}%"}
        _fill(self.tech_tree, pd.DataFrame(list(tech_data.items()), columns=["Indicator", "Status"]))

    def _update_fundamentals_tab(self, data):
        def fmt(val, mult=1, suffix=""): 
            return f"{val*mult:.2f}{suffix}" if isinstance(val, (int, float)) else "N/A"
        
        # --- FIX: Use safe .get() for all fundamental data points ---
        funda_data = {
            "P/E Ratio": fmt(data.get('trailingPE')),
            "Price/Book": fmt(data.get('priceToBook')),
            "Revenue Growth (Q)": fmt(data.get('revenueGrowth'), 100, '%'),
            "Earnings Growth (Q)": fmt(data.get('earningsGrowth'), 100, '%'),
            "Return on Equity": fmt(data.get('returnOnEquity'), 100, '%'),
            "Debt to Equity": fmt(data.get('debtToEquity')),
            "Gross Margins": fmt(data.get('grossMargins'), 100, '%'),
            "Profit Margins": fmt(data.get('profitMargins'), 100, '%')
        }
        _fill(self.funda_tree, pd.DataFrame(list(funda_data.items()), columns=["Ratio", "Value"]))

    def _update_events(self, events):
        self.events_tree.delete(*self.events_tree.get_children())
        if not events: self.events_tree.insert("", "end", values=("No upcoming events found.", "")); return
        self.events_tree['columns'] = ("Date", "Event")
        self.events_tree.heading("Date", text="Date"); self.events_tree.heading("Event", text="Event")
        self.events_tree.column("Date", width=100); self.events_tree.column("Event", width=250)
        for event in events:
            for article in event['articles']: self.events_tree.insert("", "end", values=(event['date_formatted'], article['headline']))

    def _update_insider_transactions(self, transactions):
        self.insider_tree.delete(*self.insider_tree.get_children())
        if not transactions: self.insider_tree.insert("", "end", values=("No recent transactions.", "", "", "")); return
        df = pd.DataFrame(transactions)
        _fill(self.insider_tree, df[['date', 'name', 'change', 'price']].rename(columns={'date':'Date', 'name':'Insider', 'change':'Shares', 'price':'Price'}))

    def _update_analyst_ratings(self, recs):
        self.analyst_tree.delete(*self.analyst_tree.get_children())
        
        # Check if recs is None or an empty list
        # A list does not have '.empty', so check its length instead.
        if recs is None or not recs: # 'not recs' handles empty list []
            self.analyst_tree.insert("", "end", values=("No ratings available.", "")); 
            return

        # recs is now a list of dictionaries.
        # We need to ensure we're getting the *latest* rating from this list.
        # If the list is sorted by date (most recent last, as from .to_dict(orient='records')),
        # then the last item is the latest. Assuming the sorting from yfinance.
        if isinstance(recs, list) and recs:
            latest_ratings_dict = recs[-1] # Get the last dictionary (latest rating)
        else: # Fallback if for some reason recs isn't a list or is malformed
            self.analyst_tree.insert("", "end", values=("No ratings available.", "")); 
            return

        rating_columns = ['strongBuy', 'buy', 'hold', 'sell', 'strongSell']
        
        ratings_data = []
        for col in rating_columns:
            # Safely get the value from the dictionary
            if col in latest_ratings_dict and latest_ratings_dict[col] is not None:
                rating_name = col.replace('strong', 'Strong ').capitalize()
                analysts_count = latest_ratings_dict[col]
                ratings_data.append((rating_name, analysts_count))

        # Create DataFrame for display
        recs_df = pd.DataFrame(ratings_data, columns=["Rating", "Analysts"])
        _fill(self.analyst_tree, recs_df)
        
    def _open_article(self, event):
        selection = self.news_tree.selection()
        if not selection: return
        selected_headline = self.news_tree.item(selection[0], "values")[0]
        for article in self.news_articles:
            if article.get("headline") == selected_headline and article.get("url"):
                webbrowser.open(article["url"]); break

    # In StockResearchSuite.py, REPLACE this method
    def _clear_all_data_views(self):
        # Reset labels and images
        self.snapshot_frame.grid_remove()
        self.company_label.config(text="Company Name (TICKER)")
        self.sector_label.config(text="Sector | Industry")
        self.news_sentiment_label.config(text="Fetching...")
        if self.company_logo: self.logo_label.config(image=''); self.company_logo = None

        # --- FIX: Only clear frames that hold dynamically generated content ---
        frames_to_clear = [self.chart_frame, self.financial_chart_frame, self.perf_frame]
        for frame in frames_to_clear:
            for widget in frame.winfo_children():
                widget.destroy()
        
        # Clear text widgets
        self.profile_text.config(state="normal"); self.profile_text.delete("1.0", tk.END); self.profile_text.config(state="disabled")

        # --- FIX: Safely clear all Treeviews without destroying them ---
        # The sidebar frames are no longer touched, only the Treeviews inside them.
        for tv in [self.income_tv, self.balance_tv, self.cash_tv, self.news_tree, 
                   self.options_tree, self.tech_tree, self.funda_tree, 
                   self.analyst_tree, self.events_tree, self.insider_tree]:
            if tv.winfo_exists():
                tv.delete(*tv.get_children())
        
        # Reset combobox
        self.exp_combo.set(''); self.exp_combo['values'] = []