from __future__ import annotations

class HomeDataManager:
    """Centralised, lightweight fetchers for the dashboard."""
    def __init__(self):
        from datetime import datetime
        self.now = datetime.now

    def get_latest_price(self, ticker: str) -> float | None:
        """
        Return the most-recent close for any ticker via yfinance (1d).
        """
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period="1d", auto_adjust=False)
            return float(h["Close"].iloc[-1])
        except Exception:
            return None

    def get_index_prices(self):
        """
        Return the latest SPY & VIX close prices as plain floats.
        Falls back to (None, None) if yfinance or the network is unavailable.
        """
        try:
            import yfinance as yf

            # Using Ticker().history keeps the columns simple (no MultiIndex)
            spy_price = yf.Ticker("SPY").history(period="1d")["Close"].iloc[-1]
            vix_price = yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]

            return float(spy_price), float(vix_price)
        except Exception:
            return None, None

    def get_ticker_details(self, ticker: str) -> dict | None:
        """
        Returns a dictionary with detailed quote info for a ticker.
        Fetches current price, previous close, and symbol.
        """
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker)
            info = stock.info
            # Primary method: Use the 'info' dictionary for real-time data
            if all(k in info for k in ['regularMarketPrice', 'previousClose', 'symbol']):
                # yfinance sometimes returns numbers as None, handle this
                if info['regularMarketPrice'] is not None and info['previousClose'] is not None:
                    return info

            # Fallback method: Use history for less common tickers or indices
            hist = stock.history(period="2d")
            if not hist.empty and len(hist) > 1:
                return {
                    'symbol': ticker,
                    'regularMarketPrice': hist['Close'].iloc[-1],
                    'previousClose': hist['Close'].iloc[-2]
                }
            return None
        except Exception:
            # If any error occurs (network, invalid ticker), return None
            return None

    # ── Fear & Greed (CNN index: 0‒100) ───────────────────────────────
    def get_fear_greed(self) -> int | None:
        """
        Fetch the latest CNN Fear & Greed index (0-100) using a headless
        browser (Playwright).  Returns None if the score cannot be obtained.
        """
        try:
            from playwright.sync_api import sync_playwright, TimeoutError
        except ImportError:
            print(
                "\n---\n"
                "Playwright is not installed. Install with:\n"
                "  pip install playwright && playwright install\n"
                "---\n"
            )
            return None

        page_url = "https://www.cnn.com/markets/fear-and-greed"
        score_selector = "//*[contains(@class, 'market-fng-gauge__dial-number-value')]"

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(page_url, timeout=15_000)              # 15 s page load
                page.wait_for_selector(score_selector, timeout=10_000)

                score_text = page.locator(score_selector).first.inner_text().strip()
                browser.close()

                return int(score_text) if score_text.isdigit() else None

        except TimeoutError:
            print("Timeout: score element did not appear in time.")
            return None
        except Exception as e:
            print(f"Playwright error: {e}")
            return None

    
    # ── News  ────────────────────────────────────────────────────────────
    def get_news_headlines(self, n: int = 20) -> tuple[list[tuple[str, float | None, str]], float | None]:
        """
        Return (headlines_list, overall_score)

        headlines_list : up to *n* entries of (headline, sentiment, url)
        overall_score  : average sentiment of the last 50 stories (or None)

        Sentiment scores are –1 … +1 (positive = bullish).
        """
        import datetime as dt, time, math, webbrowser

        # ── nested scorer (prefer your in-house analyser) ────────────────
        def _score(txt: str) -> float | None:
            try:
                from ui.NewsSentimentAnalyzer import score_text
                return float(score_text(txt))
            except Exception:
                try:
                    from nltk.sentiment import SentimentIntensityAnalyzer
                    return SentimentIntensityAnalyzer().polarity_scores(txt)["compound"]
                except Exception:
                    return None

        cutoff_ts = dt.datetime.now().timestamp() - 86_400         # last 24 h
        rows: list[tuple[str, float | None, str]] = []             # table rows
        scores: list[float] = []                                   # for overall

        def _append(title: str, link: str):
            s = _score(title)
            rows.append((title, s, link))
            if s is not None:
                scores.append(s)

        # ── news feed via yfinance first ────────────────────────────────
        try:
            import yfinance as yf
            for item in (yf.Ticker("SPY").news or []):
                ts = item.get("providerPublishTime", 0)
                if ts >= cutoff_ts:
                    _append(item["title"], item.get("link", ""))
        except Exception:
            pass

        # ── fallback RSS if needed ──────────────────────────────────────
        if not rows:
            try:
                import feedparser
                rss = feedparser.parse(
                    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US"
                )
                for entry in rss.entries:
                    ts = time.mktime(getattr(entry, "published_parsed", time.gmtime(0)))
                    if ts >= cutoff_ts:
                        _append(entry.title, entry.link)
            except Exception:
                pass

                # newest first
        rows.sort(key=lambda x: x[0])     # already time-ordered
        if len(rows) < n:
            # ----- TOP-UP with older stories until we reach *n* --------------  NEW
            leftovers = []
            try:
                import yfinance as yf
                leftovers = yf.Ticker("SPY").news or []
            except Exception:
                pass
            try:
                import feedparser, time as _t
                rss2 = feedparser.parse(
                    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US"
                ).entries
                leftovers += rss2
            except Exception:
                pass

            # iterate oldest→newest so we don't duplicate
            for item in sorted(leftovers, key=lambda d: d.get("providerPublishTime", 0)):
                title = item.get("title") or getattr(item, "title", "")
                link  = item.get("link")  or getattr(item, "link", "")
                if any(r[0] == title for r in rows):      # already added
                    continue
                rows.append((title, _score(title), link))
                if len(rows) >= n:
                    break
        # ---------------------------------------------------------------------

        top_rows = rows[:n]
        overall  = sum(scores) / len(scores) if scores else None
        return top_rows, overall

