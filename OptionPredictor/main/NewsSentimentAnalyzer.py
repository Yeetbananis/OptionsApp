import tkinter as tk
from tkinter import ttk, messagebox
import requests
import json
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import nltk
import webbrowser
import datetime as dt

#nltk.download("vader_lexicon")


class NewsSentimentAnalyzerWindow:
    def __init__(self, parent, theme="light"):
        self.parent = parent
        self.current_theme = theme
        self.api_key = "JJDYBMACWY5SUU7M"
        self.vader = SentimentIntensityAnalyzer()
        self.articles = []

        self.win = tk.Toplevel(parent)
        self.win.title("News Sentiment Analyzer")
        self.win.geometry("1050x750")
        self.parent.apply_theme_to_window(self.win)

        top_frame = ttk.Frame(self.win)
        top_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(top_frame, text="Ticker:").pack(side="left")
        self.ticker_entry = ttk.Entry(top_frame, width=10)
        self.ticker_entry.pack(side="left", padx=5)

        self.enable_filter = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_frame, text="Enable Timeframe Filter", variable=self.enable_filter,
                         command=self.toggle_timeframe_filter).pack(side="left", padx=5)

        ttk.Label(top_frame, text="Timeframe:").pack(side="left")
        self.time_unit = tk.StringVar(value="Hours")
        time_unit_menu = ttk.Combobox(top_frame, textvariable=self.time_unit, values=["Hours", "Days"],
                                       state="readonly", width=8)
        time_unit_menu.pack(side="left", padx=5)
        time_unit_menu.bind("<<ComboboxSelected>>", self.update_slider_range)

        # Create slider label before slider
        self.slider_label = ttk.Label(top_frame, text="1 Hour")
        self.slider_label.pack(side="left", padx=5)
        self.time_slider = ttk.Scale(top_frame, from_=1, to=24, orient="horizontal", length=100,
                                     command=self.update_treeview_from_slider)
        self.time_slider.set(1)
        self.time_slider.pack(side="left", padx=5)

        ttk.Label(top_frame, text="Search:").pack(side="left")
        self.search_entry = ttk.Entry(top_frame, width=20)
        self.search_entry.pack(side="left", padx=5)
        self.search_entry.bind("<KeyRelease>", lambda e: self.update_treeview())

        ttk.Button(top_frame, text="Analyze", command=self.analyze_sentiment).pack(side="left", padx=5)

        info_frame = ttk.Frame(self.win)
        info_frame.pack(fill="x", padx=10, pady=2)
        self.sentiment_label = ttk.Label(info_frame, text="", font=("Helvetica", 10, "bold"))
        self.sentiment_label.pack(side="left")
        info_note = ttk.Label(info_frame, text="Double-click a news article to read further.",
                               font=("Helvetica", 9, "italic"), foreground="gray")
        info_note.pack(side="right")

        self.loading_label = ttk.Label(self.win, text="", foreground="blue")
        self.loading_label.pack()

        columns = ("headline", "published", "sentiment", "score")
        self.tree = ttk.Treeview(self.win, columns=columns, show="headings", height=25)
        for col in columns:
            self.tree.heading(col, text=col.capitalize(), command=lambda c=col: self.sort_treeview(c, False))
            self.tree.column(col, width=250 if col == "headline" else 150, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        self.tree.bind("<Double-1>", self.open_article)

        scrollbar = ttk.Scrollbar(self.tree, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        self.toggle_timeframe_filter()

    def toggle_timeframe_filter(self):
        state = "normal" if self.enable_filter.get() else "disabled"
        self.time_slider.configure(state=state)
        self.slider_label.configure(state=state)
        self.update_treeview()

    def update_slider_range(self, event=None):
        if self.time_unit.get() == "Hours":
            self.time_slider.config(from_=1, to=24)
        else:
            self.time_slider.config(from_=1, to=365)
        self.update_slider_label(self.time_slider.get())

    def update_slider_label(self, val):
        unit = self.time_unit.get()
        value = int(float(val))
        text = f"{value} {unit[:-1] if value==1 else unit}"
        self.slider_label.config(text=text)

    def update_treeview_from_slider(self, val):
        self.update_slider_label(val)
        if self.enable_filter.get():
            self.update_treeview()

    def analyze_sentiment(self):
        ticker = self.ticker_entry.get().strip().upper()
        if not ticker:
            messagebox.showwarning("Input Error", "Please enter a stock ticker.")
            return

        self.loading_label.config(text="Fetching news, please wait...")
        self.win.update_idletasks()

        try:
            url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={self.api_key}"
            response = requests.get(url)
            data = response.json()
            self.loading_label.config(text="")

            if "Note" in data:
                self.loading_label.config(text=f"API limit reached: {data['Note']}", foreground="red")
                return
            if "Information" in data:
                self.loading_label.config(text=f"API info: {data['Information']}", foreground="red")
                return
            if "feed" not in data or not data["feed"]:
                self.loading_label.config(text="No news data found.", foreground="gray")
                return

            self.articles = []
            for article in data["feed"]:
                published_raw = article.get("time_published", "N/A")
                published_date = self.format_date(published_raw)
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
                    "published_raw": published_raw,
                    "published": published_date,
                    "score": local_score,
                    "sentiment": sentiment_label
                })

            avg_score = sum(a["score"] for a in self.articles) / len(self.articles)
            overall_label = self.get_sentiment_label(avg_score)
            color = self.get_sentiment_color(avg_score)
            self.sentiment_label.config(text=f"Overall Sentiment: {overall_label} ({avg_score:.2f})", foreground=color)
            self.update_treeview()

        except Exception as e:
            self.loading_label.config(text="")
            messagebox.showerror("Error", f"Error fetching news: {e}")

    def update_treeview(self):
        search_term = self.search_entry.get().lower()
        unit = self.time_unit.get()
        duration = self.time_slider.get()

        for i in self.tree.get_children():
            self.tree.delete(i)

        now = dt.datetime.now()
        for article in self.articles:
            published = dt.datetime.strptime(article["published_raw"], "%Y%m%dT%H%M%S")
            delta_hours = (now - published).total_seconds() / 3600

            if self.enable_filter.get():
                if unit == "Hours" and delta_hours > duration:
                    continue
                if unit == "Days" and delta_hours > duration * 24:
                    continue

            if search_term and search_term not in article["headline"].lower():
                continue

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

    def format_date(self, raw):
        try:
            return dt.datetime.strptime(raw, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "N/A"

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
