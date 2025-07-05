import requests
import datetime as dt
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import feedparser
import re
import dateparser
import urllib.parse

class StockEventTracker:
    def __init__(self, alpha_api_key, finnhub_api_key):
        self.alpha_api_key = alpha_api_key  # Alpha Vantage API key
        self.finnhub_api_key = finnhub_api_key      # Financial Modeling Prep API key
        self.vader = SentimentIntensityAnalyzer()
        self.last_earnings_source = None  # track if earnings date is from Nasdaq or Finnhub


    def fetch_upcoming_events(self, ticker, earnings_date=None):
        """
        Fetches, processes, and formats upcoming events for a given stock ticker.

        This method now returns a list of dictionaries, each containing:
        - 'date_raw': The event date as a 'YYYY-MM-DD' string (for logic and comparison).
        - 'date_formatted': A user-friendly "Month Day, Year" string (for display).
        - 'articles': A list of articles related to that date.
        """
        # Step 1: Get articles from multiple queries
        articles = self.scrape_google_news_rss_articles_multiple_queries(ticker)        

        # Step 2: Extract and organize upcoming events
        upcoming_events = self.extract_and_group_events_by_date(articles, ticker, earnings_date=earnings_date)

        # Step 3: Sort by date, from nearest to furthest
        sorted_events = dict(sorted(upcoming_events.items(), key=lambda item: item[0]))

        # Step 4: Convert to a display-friendly format
        formatted_events = []
        for date_key, articles_list in sorted_events.items():  # date_key is in "YYYY-MM-DD" format
            # Create the formatted date string for display
            formatted_date_display = dt.datetime.strptime(date_key, "%Y-%m-%d").strftime("%B %d, %Y")

            # **FIX:** Append a dictionary with both raw and formatted dates.
            # This makes the raw 'YYYY-MM-DD' date available to the UI for comparison,
            # while the formatted date is ready for display.
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
            encoded_query = urllib.parse.quote(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}"
            feed = feedparser.parse(url)
            for entry in feed.entries:
                all_articles.append({
                    "headline": entry.title,
                    "summary": entry.summary,
                    "url": entry.link,
                    "content": f"{entry.title} {entry.summary}"
                })
        # Deduplicate by URL
        unique_articles = {a["url"]: a for a in all_articles}.values()
        print(f"Total unique articles from Google News RSS: {len(unique_articles)}")
        return list(unique_articles)

    def extract_and_group_events_by_date(self, articles, ticker, earnings_date=None):
        date_pattern = r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?\b"
        events_by_date = {}

        # Fetch confirmed earnings date
        if earnings_date is None:
            earnings_date = self.get_confirmed_earnings_date(ticker)   
            print(f"[DEBUG] Using earnings date for matching: {earnings_date}")

        for article in articles:
            text = article["content"]
            matches = re.findall(date_pattern, text, re.IGNORECASE)
            for date_str in matches:
                parsed_date = dateparser.parse(date_str, settings={"PREFER_DATES_FROM": "future"})
                if parsed_date and parsed_date.date() > dt.datetime.now().date():
                    date_key = parsed_date.strftime("%Y-%m-%d")
                    is_earnings = earnings_date == date_key
                    if is_earnings:
                        print(f"[DEBUG] Article matched earnings date: {article['headline']} -> {date_key}")

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
                            "event_label": "Earnings" if is_earnings else "Mentioned in headline/news"
                        })
        return events_by_date
    
   




    def get_confirmed_earnings_date(self, ticker):
        """
        Fetches the next confirmed earnings date for the given ticker using Finnhub API.
        We prioritize Finnhub as it's typically reliable for upcoming earnings.
        """
        finnhub_api_key = self.finnhub_api_key
        today = dt.datetime.now()
        # Fetch up to 6 months in the future to capture upcoming earnings
        six_months_later = today + dt.timedelta(days=180)
        from_date_str = today.strftime("%Y-%m-%d")
        to_date_str = six_months_later.strftime("%Y-%m-%d")

        finnhub_date = None
        try:
            url = (f"https://finnhub.io/api/v1/calendar/earnings?"
                f"from={from_date_str}&to={to_date_str}&symbol={ticker}&token={finnhub_api_key}")
            response = requests.get(url)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            data = response.json()
            
            # Finnhub returns a list of upcoming earnings, usually sorted by date.
            # We want the *next* one.
            if data.get("earningsCalendar"):
                # Filter for dates strictly in the future relative to today
                future_earnings = [
                    entry for entry in data["earningsCalendar"]
                    if dt.datetime.strptime(entry.get("date"), "%Y-%m-%d").date() >= today.date()
                ]
                # Sort them to ensure we pick the earliest
                future_earnings.sort(key=lambda x: x.get("date"))

                if future_earnings:
                    earnings_entry = future_earnings[0]
                    finnhub_date = earnings_entry.get("date")
                    self.last_earnings_source = "finnhub"
                    print(f"[INFO] Finnhub earnings date for {ticker}: {finnhub_date}")
                    return finnhub_date
                else:
                    print(f"[WARN] No future earnings found for {ticker} via Finnhub within 6 months.")
            else:
                print(f"[WARN] Finnhub API returned no earnings calendar for {ticker}.")
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Finnhub API request failed for {ticker}: {e}")
        except ValueError as e: # JSON decoding error
            print(f"[ERROR] Finnhub API response for {ticker} not valid JSON: {e}")
        except Exception as e:
            print(f"[ERROR] Unexpected error fetching Finnhub earnings for {ticker}: {e}")

        # If Finnhub fails to provide a date, return None
        return None
    
    
    def is_likely_estimate(date_str):
        today = dt.datetime.now().date()
        parsed_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        delta_days = (parsed_date - today).days
        return delta_days > 40  # heuristic: confirmed dates typically <1–2 months ahead



    def get_related_articles(self, ticker, event_date):
        url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={ticker}&apikey={self.alpha_api_key}"
        response = requests.get(url)
        try:
            data = response.json()
        except Exception:
            print("Failed to parse JSON:", response.text)
            return []

        articles = []
        for article in data.get("feed", []):
            published_raw = article.get("time_published", "N/A")
            try:
                published = dt.datetime.strptime(published_raw, "%Y%m%dT%H%M%S").strftime("%Y-%m-%d %H:%M")
            except Exception:
                published = "N/A"
            articles.append({
                "headline": article.get("title", ""),
                "summary": article.get("summary", ""),
                "url": article.get("url", ""),
                "published": published,
                "content": f"{article.get('title', '')} {article.get('summary', '')}"
            })
        return articles

    def analyze_sentiment(self, articles):
        for article in articles:
            score = self.vader.polarity_scores(article["content"])["compound"]
            article["score"] = score
            article["sentiment"] = self.get_sentiment_label(score)
        return articles

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
