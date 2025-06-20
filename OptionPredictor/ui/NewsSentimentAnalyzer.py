import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont
import requests
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import webbrowser
import datetime as dt
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import pandas as pd
import yfinance as yf

# yfinance ≤ 0.2.17 lacks the rate-limit class ─ make a safe alias
RateErr = getattr(yf.utils, "YFRateLimitError", Exception)

def _tree(parent):
    """Return a Treeview wired to always-visible vertical + horizontal scrollbars."""
    wrap = ttk.Frame(parent)
    wrap.pack(fill="both", expand=True, padx=10, pady=5)

    tv  = ttk.Treeview(wrap, show="headings")
    vsb = ttk.Scrollbar(wrap, orient="vertical",   command=tv.yview)
    hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tv.xview)

    tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    # --- grid layout -------------------------------------------------
    wrap.grid_rowconfigure(0, weight=1)
    wrap.grid_columnconfigure(0, weight=1)

    tv .grid(row=0, column=0, sticky="nsew")   # fills frame
    vsb.grid(row=0, column=1, sticky="ns")     # right edge
    hsb.grid(row=1, column=0, sticky="ew")     # bottom edge

    return tv


def _fill(tv, df):
    """Populate a Treeview and auto-size each column to its widest cell."""
    tv.delete(*tv.get_children())

    # configure columns
    tv["columns"] = list(df.columns)
    for col in df.columns:
        tv.heading(col, text=col)

    # insert rows
    for _, row in df.iterrows():
        tv.insert("", "end", values=list(row))

    # ── determine the font used by the Treeview ───────────────────────
    style = ttk.Style(tv)
    font_spec = style.lookup("Treeview", "font") or "TkDefaultFont"

    try:
        f = tkfont.nametofont(font_spec)          # succeeds for named fonts
    except tk.TclError:
        # font_spec is a family/size string ("Segoe UI 9"); build a Font object
        f = tkfont.Font(tv, font=font_spec)


    pad = 10  # extra pixels for neatness

    # auto-width each column
    for col in df.columns:
        max_w = f.measure(col)               # start with header width
        for item in tv.get_children():       # check every cell in column
            cell_val = tv.set(item, col)
            max_w = max(max_w, f.measure(cell_val))
        tv.column(col, width=max_w + pad, stretch=False)


from tools.StockEventTracker import StockEventTracker

class NewsSentimentAnalyzerWindow:
    def __init__(self, parent, theme="light"):
        self.parent = parent
        self.current_theme = theme
        self.vantageapi_key = "JJDYBMACWY5SUU7M"
        self.finnhub_key = "d114k6hr01qse6lf8c1gd114k6hr01qse6lf8c20"
        self.vader = SentimentIntensityAnalyzer()
        self.articles = []
        self.event_tracker = StockEventTracker(self.vantageapi_key, self.finnhub_key)

        self.win = tk.Toplevel(parent)
        self.win.focus_force()
        self.win.attributes("-topmost", False)


        self.win.title("News Sentiment Analyzer")
        self.win.geometry("1050x750")
        self.parent.apply_theme_to_window(self.win)


        # --- Top button area ---
        topbar = ttk.Frame(self.win)
        topbar.pack(fill="x", side=tk.TOP)
        
        fullscreen_btn = ttk.Button(topbar, text="⛶", width=3, command=self.toggle_fullscreen)
        fullscreen_btn.pack(side=tk.RIGHT)

        # --- Notebook and tabs below ---
        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(fill="both", expand=True)

        self.news_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.news_tab, text="News Sentiment")
        self.setup_news_tab()

        self.events_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.events_tab, text="Upcoming Events (Google News RSS)")
        self.setup_events_tab()

        self.setup_financials_tab()


        # 🌟 Loading label for event fetching
        self.event_loading_label = ttk.Label(self.events_tab, text="", foreground="blue")
        self.event_loading_label.pack(fill="x", padx=10, pady=5)




    def setup_news_tab(self):
        top_frame = ttk.Frame(self.news_tab)
        top_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(top_frame, text="Ticker:").pack(side="left")
        self.ticker_entry = ttk.Entry(top_frame, width=10)
        self.ticker_entry.pack(side="left", padx=5)

        ttk.Button(top_frame, text="Analyze", command=self.analyze_sentiment).pack(side="left", padx=5)

        self.loading_label = ttk.Label(self.news_tab, text="", foreground="blue")
        self.loading_label.pack()

        columns = ("headline", "published", "sentiment", "score")
        self.tree = ttk.Treeview(self.news_tab, columns=columns, show="headings", height=25)
        for col in columns:
            self.tree.heading(col, text=col.capitalize(), command=lambda c=col: self.sort_treeview(c, False))
            self.tree.column(col, width=250 if col == "headline" else 150, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self.open_article)

        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

    def setup_events_tab(self):
        top_frame = ttk.Frame(self.events_tab)
        top_frame.pack(fill="x", padx=10, pady=5)

        # Earnings Date Display Area
        self.earnings_date_frame = ttk.Frame(self.events_tab)
        self.earnings_date_frame.pack(fill="x", padx=10, pady=(5, 0))

        self.earnings_date_label = ttk.Label(self.earnings_date_frame, text="Earnings Date: N/A", font=("Helvetica", 10, "bold"), foreground="blue")
        self.earnings_date_label.pack(side="left")

        self.earnings_article_link = ttk.Label(self.earnings_date_frame, text="", foreground="blue", cursor="hand2")
        self.earnings_article_link.pack(side="left", padx=5)
        self.earnings_article_link.bind("<Button-1>", lambda e: self.open_earnings_article())


        ttk.Label(top_frame, text="Ticker:").pack(side="left")
        self.event_ticker_entry = ttk.Entry(top_frame, width=10)
        self.event_ticker_entry.pack(side="left", padx=5)

        ttk.Button(top_frame, text="Fetch Events", command=self.display_upcoming_events).pack(side="left", padx=5)

        self.event_tree = ttk.Treeview(self.events_tab, columns=("date", "event", "details", "link"),
                                       show="headings", height=25)
        for col in ("date", "event", "details", "link"):
            self.event_tree.heading(col, text=col.capitalize())
            self.event_tree.column(col, width=250, anchor="w")
        self.event_tree.pack(fill="both", expand=True, padx=10, pady=5)

        self.event_tree.bind("<Double-1>", self.open_event_article)

    def setup_financials_tab(self):
        # parent tab
        self.financials_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.financials_tab, text="Financials")

        # ── top bar ────────────────────────────────────────────────────
        top = ttk.Frame(self.financials_tab)
        top.pack(fill="x", padx=10, pady=5)

        ttk.Label(top, text="Ticker:").pack(side="left")
        self.fin_ticker = ttk.Entry(top, width=10)
        self.fin_ticker.pack(side="left", padx=5)

        fetch_btn = ttk.Button(top, text="Fetch Statements",
                            command=self.load_financials_from_yf)
        fetch_btn.pack(side="left", padx=5)

        self.fin_status = ttk.Label(self.financials_tab, text="", foreground="blue")
        self.fin_status.pack(fill="x", padx=10)

        # ── notebook with 3 statement tabs ─────────────────────────────
        self.fin_nb = ttk.Notebook(self.financials_tab)
        self.fin_nb.pack(fill="both", expand=True)

        self.income_tab = ttk.Frame(self.fin_nb)
        self.balance_tab = ttk.Frame(self.fin_nb)
        self.cash_tab = ttk.Frame(self.fin_nb)

        self.fin_nb.add(self.income_tab, text="Income")
        self.fin_nb.add(self.balance_tab, text="Balance")
        self.fin_nb.add(self.cash_tab, text="Cash-flow")

        self.income_tv  = _tree(self.income_tab)    # uses the GLOBAL helper
        self.balance_tv = _tree(self.balance_tab)
        self.cash_tv    = _tree(self.cash_tab)


    # ─── helpers & loader ──────────────────────────────────────────────

    def _format_df(self, df):
        """Transpose & format numbers as ‘x M’ (millions)."""
        return (
            df.transpose()
            .pipe(lambda d: d.map(
                lambda x: f"{x/1e6:,.0f} M" if isinstance(x, (int, float)) else x))
            .rename_axis("Date")
            .reset_index()
        )

    def display_upcoming_events(self):
        ticker = self.event_ticker_entry.get().strip().upper()
        if not ticker:
            messagebox.showwarning("Input Error", "Please enter a stock ticker.")
            return

        # 🌟 Show loading label
        self.event_loading_label.config(text="Fetching events, please wait...")
        self.win.update_idletasks()

        earnings_date = self.event_tracker.get_confirmed_earnings_date(ticker)
        print(f"[DEBUG] Final earnings date for {ticker}: {earnings_date}")

        events = self.event_tracker.fetch_upcoming_events(ticker, earnings_date=earnings_date)
        self.event_tree.delete(*self.event_tree.get_children())

        self.earnings_date_label.config(text="Earnings Date: N/A")
        self.earnings_article_link.config(text="", cursor="arrow")
        self.earnings_article_url = None

        if earnings_date:
            earnings_dt = dt.datetime.strptime(earnings_date, "%Y-%m-%d")
            earnings_date_pretty = earnings_dt.strftime("%B %d, %Y")
            if self.event_tracker.last_earnings_source == "nasdaq":
                label_text = f"Earnings Date: {earnings_date_pretty} (confirmed)"
                label_color = "green"
            else:
                label_text = f"Earnings Date: {earnings_date_pretty} (estimate/double check)"
                label_color = "blue"
            self.earnings_date_label.config(text=label_text, foreground=label_color)
            for event in events:
                if event["date_raw"] == earnings_date and event["articles"]:
                    self.earnings_article_url = event["articles"][0]["url"]
                    self.earnings_article_link.config(text="(View Article)", foreground="blue", cursor="hand2")
                    break

        for event in events:
            date_display = event["date_formatted"]
            date_id = self.event_tree.insert("", "end", values=(date_display, "", "", ""))
            self.event_tree.item(date_id, open=True)
            for article in event["articles"]:
                label = f" ({article.get('event_label', '')})" if article.get("event_label") else ""
                self.event_tree.insert(
                    date_id, "end",
                    values=("", f"{article['headline']}{label}", article["sentiment"], article["url"])
                )

        # 🌟 Clear loading label when done
        self.event_loading_label.config(text="")

        # 🌟 Delay to re-lift after Selenium closes
        self.win.after(1, self._force_focus_back)



    def _force_focus_back(self):
        self.win.lift()
        self.win.focus_force()
        self.event_tree.focus_set()
        self.event_tree.event_generate("<Button-1>", x=1, y=1)




    def toggle_fullscreen(self):
        is_fullscreen = self.win.attributes("-fullscreen")
        self.win.attributes("-fullscreen", not is_fullscreen)


    def open_earnings_article(self):
        if self.earnings_article_url:
            webbrowser.open(self.earnings_article_url)


    def open_event_article(self, event):
        selection = self.event_tree.selection()
        if not selection:
            return
        item = selection[0]
        url = self.event_tree.item(item, "values")[3]
        if url:
            webbrowser.open(url)

    def analyze_sentiment(self):
        ticker = self.ticker_entry.get().strip().upper()
        if not ticker:
            messagebox.showwarning("Input Error", "Please enter a stock ticker.")
            return

        self.loading_label.config(text="Fetching news, please wait...")
        self.win.update_idletasks()

        try:
            url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={self.vantageapi_key}"
            response = requests.get(url)
            data = response.json()
            self.loading_label.config(text="")

            if "feed" not in data or not data["feed"]:
                self.loading_label.config(text="No news data found.", foreground="gray")
                return

            self.articles = []
            for article in data["feed"]:
                published_raw = article.get("time_published", "N/A")
                published_date = dt.datetime.strptime(published_raw, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M")
                headline = article.get("title", "No Title")
                summary = article.get("summary", "")
                url_link = article.get("url", "")
                full_text = f"{headline} {summary}"
                local_score = self.vader.polarity_scores(full_text)["compound"]
                sentiment_label = self.get_sentiment_label(local_score)
                self.articles.append({
                    "headline": headline,
                    "summary": summary,
                    "url": url_link,
                    "published": published_date,
                    "score": local_score,
                    "sentiment": sentiment_label
                })

            avg_score = sum(a["score"] for a in self.articles) / len(self.articles)
            overall_label = self.get_sentiment_label(avg_score)
            color = self.get_sentiment_color(avg_score)
            self.loading_label.config(text=f"Overall Sentiment: {overall_label} ({avg_score:.2f})", foreground=color)
            self.update_treeview()
        except Exception as e:
            self.loading_label.config(text="")
            messagebox.showerror("Error", f"Error fetching news: {e}")

    def update_treeview(self):
        for i in self.tree.get_children():
            self.tree.delete(i)

        for article in self.articles:
            self.tree.insert("", "end",
                             values=(article["headline"], article["published"], article["sentiment"],
                                     f"{article['score']:.2f}"))

        for child in self.tree.get_children():
            item_values = self.tree.item(child)["values"]
            score = float(item_values[3])
            color = self.get_sentiment_color(score)
            self.tree.tag_configure(color, foreground=color)
            self.tree.item(child, tags=(color,))

    def sort_treeview(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children("")]
        l.sort(reverse=reverse)
        for index, (val, k) in enumerate(l):
            self.tree.move(k, "", index)
        self.tree.heading(col, command=lambda: self.sort_treeview(col, not reverse))

    def open_article(self, event):
        selection = self.tree.selection()
        if not selection:
            return
        item = selection[0]
        headline = self.tree.item(item, "values")[0]
        for article in self.articles:
            if article["headline"] == headline and article["url"]:
                webbrowser.open(article["url"])
                break

    def get_sentiment_label(self, score):
        if score >= 0.35:
            return "Strong Bullish"
        elif score >= 0.15:
            return "Bullish"
        elif score <= -0.35:
            return "Strong Bearish"
        elif score <= -0.15:
            return "Bearish"
        else:
            return "Neutral"

    def get_sentiment_color(self, score):
        if score >= 0.15:
            return "green"
        elif score <= -0.15:
            return "red"
        else:
            return "gray"
        
    def fetch_nasdaq_financials(self, ticker):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        url = f"https://www.nasdaq.com/market-activity/stocks/{ticker}/financials"
        print(f"[INFO] Fetching financials from: {url}")
        driver.get(url)

        try:
            # Wait for a key element that confirms the tables are loaded
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.financials__data-container"))
            )
            html = driver.page_source
            soup = BeautifulSoup(html, "html.parser")

            # Find all tables
            tables = soup.find_all("table")
            if not tables:
                print("[WARN] No tables found on Nasdaq financials page.")
                return None

            # Grab the first table
            table = tables[0]
            headers = [th.text.strip() for th in table.find("thead").find_all("th")]
            rows = []
            for tr in table.find("tbody").find_all("tr"):
                cells = [td.text.strip() for td in tr.find_all("td")]
                rows.append(cells)
            df = pd.DataFrame(rows, columns=headers)
            return df

        except Exception as e:
            print(f"[ERROR] Selenium scraping error: {e}")
            return None
        finally:
            driver.quit()

    def load_financials_from_yf(self):
        """Fetch income, balance, cash-flow via yfinance and display them."""
        sym = self.fin_ticker.get().strip().upper()
        if not sym:
            messagebox.showerror("Input Error", "Enter a ticker.")
            return

        self.fin_status.config(text="Loading…", foreground="blue")
        self.fin_status.update_idletasks()

        try:
            tk = yf.Ticker(sym)
            income_df   = self._format_df(tk.income_stmt)
            balance_df  = self._format_df(tk.balance_sheet)
            cashflow_df = self._format_df(tk.cashflow)
        except RateErr:
            self.fin_status.config(text="Rate-limited – try again.", foreground="red")
            return
        except Exception as e:
            self.fin_status.config(text=f"Error: {e}", foreground="red")
            return

        _fill(self.income_tv,  income_df)    # auto-sizes columns
        _fill(self.balance_tv, balance_df)
        _fill(self.cash_tv,    cashflow_df)

        self.fin_status.config(text="Loaded.", foreground="green")
        