import tkinter as tk
from tkinter import ttk, messagebox
import requests
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import webbrowser
import datetime as dt

from StockEventTracker import StockEventTracker

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
        self.win.title("News Sentiment Analyzer")
        self.win.geometry("1050x750")
        self.parent.apply_theme_to_window(self.win)

        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(fill="both", expand=True)

        self.news_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.news_tab, text="News Sentiment")
        self.setup_news_tab()

        self.events_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.events_tab, text="Upcoming Events (Google News RSS)")
        self.setup_events_tab()

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

    def display_upcoming_events(self):
        ticker = self.event_ticker_entry.get().strip().upper()
        if not ticker:
            messagebox.showwarning("Input Error", "Please enter a stock ticker.")
            return

        # Only call once and reuse
        earnings_date = self.event_tracker.get_confirmed_earnings_date(ticker)
        print(f"[DEBUG] Final earnings date for {ticker}: {earnings_date}")

        # Pass the earnings date to avoid duplicate Selenium execution
        events = self.event_tracker.fetch_upcoming_events(ticker, earnings_date=earnings_date)
        self.event_tree.delete(*self.event_tree.get_children())

        # Clear earnings date display by default
        self.earnings_date_label.config(text="Earnings Date: N/A")
        self.earnings_article_link.config(text="", cursor="arrow")
        self.earnings_article_url = None

        if earnings_date:
            # Format for pretty display
            earnings_dt = dt.datetime.strptime(earnings_date, "%Y-%m-%d")
            earnings_date_pretty = earnings_dt.strftime("%B %d, %Y")
            self.earnings_date_label.config(text=f"Earnings Date: {earnings_date_pretty}")

            # Find the first relevant article link for that date
            for event in events:
                if event["date_raw"] == earnings_date and event["articles"]:
                    self.earnings_article_url = event["articles"][0]["url"]
                    self.earnings_article_link.config(text="(View Article)", foreground="blue", cursor="hand2")
                    break

        # Insert the events normally
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
