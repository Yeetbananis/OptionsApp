# tools/StockEventTracker.py (Corrected and Final Version)
import requests
import datetime as dt
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import feedparser
import re
import dateparser
import urllib.parse

class StockEventTracker:
    def __init__(self, alpha_api_key, finnhub_api_key):
        self.alpha_api_key = alpha_api_key
        self.finnhub_api_key = finnhub_api_key
        self.vader = SentimentIntensityAnalyzer()
        self.last_earnings_source = None

    def fetch_upcoming_events(self, ticker, earnings_date=None):
        articles = self.scrape_google_news_rss_articles_multiple_queries(ticker)
        upcoming_events = self.extract_and_group_events_by_date(articles, ticker, earnings_date=earnings_date)
        sorted_events = dict(sorted(upcoming_events.items(), key=lambda item: item[0]))

        formatted_events = []
        for date_key, articles_list in sorted_events.items():
            formatted_date_display = dt.datetime.strptime(date_key, "%Y-%m-%d").strftime("%B %d, %Y")
            formatted_events.append({
                "date_raw": date_key,
                "date_formatted": formatted_date_display,
                "articles": articles_list
            })
            
        return formatted_events

    def scrape_google_news_rss_articles_multiple_queries(self, ticker):
        queries = [
            f"{ticker} stock",
            f"{ticker} earnings",
            f"{ticker} news"
        ]
        all_articles = []
        for query in queries:
            try:
                encoded_query = urllib.parse.quote(query)
                url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
                feed = feedparser.parse(url)
                for entry in feed.entries:
                    all_articles.append({
                        "headline": entry.title,
                        "summary": entry.summary,
                        "url": entry.link,
                        "published": entry.get("published_parsed"),
                        "content": f"{entry.title} {entry.summary}"
                    })
            except Exception as e:
                print(f"Could not fetch Google News for query '{query}': {e}")
                continue
                
        unique_articles = {a["url"]: a for a in all_articles}.values()
        return list(unique_articles)

    def extract_and_group_events_by_date(self, articles, ticker, earnings_date=None):
        date_pattern = r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?\b"
        events_by_date = {}

        if earnings_date is None:
            earnings_date = self.get_confirmed_earnings_date(ticker)

        for article in articles:
            text = article["content"]
            matches = re.findall(date_pattern, text, re.IGNORECASE)
            for date_str in matches:
                parsed_date = dateparser.parse(date_str, settings={"PREFER_DATES_FROM": "future"})
                if parsed_date and parsed_date.date() > dt.datetime.now().date():
                    date_key = parsed_date.strftime("%Y-%m-%d")
                    is_earnings = earnings_date == date_key

                    if date_key not in events_by_date:
                        events_by_date[date_key] = []
                    if not any(existing["url"] == article["url"] for existing in events_by_date[date_key]):
                        events_by_date[date_key].append({
                            "headline": article["headline"],
                            "summary": article["summary"],
                            "url": article["url"],
                            "sentiment": self.get_sentiment_label(
                                self.vader.polarity_scores(article["content"])["compound"]
                            ),
                            "event_label": "Earnings" if is_earnings else "Mentioned in news"
                        })
        return events_by_date

    def get_confirmed_earnings_date(self, ticker):
        today = dt.datetime.now()
        six_months_later = today + dt.timedelta(days=180)
        from_date_str = today.strftime("%Y-%m-%d")
        to_date_str = six_months_later.strftime("%Y-%m-%d")

        try:
            url = (f"https://finnhub.io/api/v1/calendar/earnings?"
                   f"from={from_date_str}&to={to_date_str}&symbol={ticker}&token={self.finnhub_api_key}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("earningsCalendar"):
                future_earnings = [
                    entry for entry in data["earningsCalendar"]
                    if dt.datetime.strptime(entry.get("date"), "%Y-%m-%d").date() >= today.date()
                ]
                future_earnings.sort(key=lambda x: x.get("date"))
                if future_earnings:
                    return future_earnings[0].get("date")
        except Exception as e:
            print(f"[ERROR] Finnhub API request failed for {ticker}: {e}")
        
        return None

    def get_sentiment_label(self, score):
        if score >= 0.35: return "Strong Bullish"
        elif score >= 0.15: return "Bullish"
        elif score <= -0.35: return "Strong Bearish"
        elif score <= -0.15: return "Bearish"
        else: return "Neutral"