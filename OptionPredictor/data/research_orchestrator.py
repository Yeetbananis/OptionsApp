# data/research_orchestrator.py (Final, Most Reliable Version)
import threading
import queue
import time
import yfinance as yf
from curl_cffi import requests as cffi_requests
import functools

from core.models.providers import ProviderHub, FundamentalDataProvider, OptionsChainProvider, FinnhubProfileProvider, FinnhubFundamentalsProvider, PeerComparisonProvider
from tools.StockEventTracker import StockEventTracker

# In data/research_orchestrator.py, REPLACE the decorator
def retry_on_failure(retries=2, delay=0.75, default_value=None):
    if default_value is None:
        default_value = {}

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # First, try with the default session
            for i in range(retries):
                try:
                    result = func(*args, **kwargs)
                    if result is not None and (not isinstance(result, dict) or result):
                        return result
                except Exception:
                    pass # Ignore errors on normal retries, we will try again
                time.sleep(delay)
            
            # --- LAST RESORT: Create a fresh, browser-impersonating session ---
            print(f"All {retries} retries failed for '{func.__name__}'. Trying one last time with a fresh session...")
            try:
                session = cffi_requests.Session(impersonate="chrome110")
                kwargs['session'] = session # Pass the new session to the function
                result = func(*args, **kwargs)
                if result is not None and (not isinstance(result, dict) or result):
                    return result
            except Exception as e:
                 print(f"Final attempt for '{func.__name__}' failed with error: {e}.")

            return default_value
        return wrapper
    return decorator


class ResearchOrchestrator:
    """
    Manages the asynchronous fetching of all data required for the Stock Research Suite.
    """
    def __init__(self, finnhub_key: str):
        self.fundamental_provider = FundamentalDataProvider()
        self.options_provider = OptionsChainProvider()
        # --- FIX: Instantiate Finnhub provider for reliable logo fetching ---
        self.finnhub_profile_provider = FinnhubProfileProvider(finnhub_key)
        self.event_tracker = StockEventTracker(alpha_api_key="JJDYBMACWY5SUU7M", finnhub_api_key=finnhub_key)
        self.finnhub_fundamentals_provider = FinnhubFundamentalsProvider(finnhub_key)
        self.peer_provider = PeerComparisonProvider(finnhub_key)

    @retry_on_failure(retries=3, delay=1, default_value={})
    def _fetch_profile_data(self, ticker, session=None):
        """
        Fetches profile info from yfinance and merges the logo URL from Finnhub for reliability.
        """
        yf_ticker = yf.Ticker(ticker, session=session)
        info = yf_ticker.info
        
        if info and len(info) > 5:
            # --- FIX: Reliably add the logo URL back ---
            # Make a quick, separate call to the reliable Finnhub API just for the logo.
            try:
                finnhub_profile = self.finnhub_profile_provider.fetch(ticker)
                if finnhub_profile and finnhub_profile.get('logo_url'):
                    info['logo_url'] = finnhub_profile['logo_url']
            except Exception as e:
                print(f"Could not fetch logo from Finnhub: {e}")

            return info
        return None

    @retry_on_failure(retries=3, delay=0.5, default_value={})
    def _fetch_options_data(self, ticker, session=None):
        """Fetches options chain data with retries."""
        return self.options_provider.fetch(ticker, session=session)
    
    # In data/research_orchestrator.py, REPLACE this method

    @retry_on_failure(retries=1, default_value={})
    def _fetch_fundamentals_data(self, ticker, session=None):
        """
        Creates a hybrid of fundamental data: fetches everything from yfinance first,
        then overwrites the most important (and least reliable) metrics with data
        from the more stable Finnhub API.
        """
        # 1. Fetch the comprehensive dataset from yfinance first, as it worked before.
        yfinance_funda = self.fundamental_provider.fetch(ticker, session=session)
        if yfinance_funda is None:
            yfinance_funda = {}

        # 2. Fetch the small set of reliable metrics from Finnhub.
        finnhub_funda = self.finnhub_fundamentals_provider.fetch(ticker)

        # 3. If the Finnhub data is available, use it to update/patch the main dataset.
        if finnhub_funda:
            print(f"Patching fundamentals for {ticker} with reliable Finnhub data.")
            # The .update() method will overwrite keys in yfinance_funda with values
            # from finnhub_funda if the keys are the same.
            yfinance_funda.update(finnhub_funda)
        
        return yfinance_funda

    def fetch_all_data(self, ticker: str, session) -> tuple[queue.Queue, int]:
        """
        Kicks off the data fetching process for a given ticker.
        """
        if not ticker:
            raise ValueError("Ticker symbol cannot be empty.")

        q = queue.Queue()
        ticker = ticker.strip().upper()

        # --- FIX: Create a single, powerful session to be used by all tasks ---
        yf_ticker = yf.Ticker(ticker, session=session)

        tasks = {
            "provider_hub": lambda: ProviderHub.get(ticker),
            # Pass the session to each function that makes a yfinance call
            "fundamentals": lambda: self._fetch_fundamentals_data(ticker, session=session),
            "events": lambda: self.event_tracker.fetch_upcoming_events(ticker),
            "financials": lambda: {
                "income": yf_ticker.income_stmt,
                "balance": yf_ticker.balance_sheet,
                "cashflow": yf_ticker.cashflow
            },
            "news": lambda: self.event_tracker.scrape_google_news_rss_articles_multiple_queries(ticker),
            "options": lambda: self._fetch_options_data(ticker, session=session),
            "profile": lambda: self._fetch_profile_data(ticker, session=session),
            "peers": lambda: self.peer_provider.fetch(ticker),
        }

        self.threads = []
        for key, task_func in tasks.items():
            thread = threading.Thread(target=self._worker, args=(key, task_func, q), daemon=True)
            self.threads.append(thread)
            thread.start()

        return q, len(tasks)

    def _worker(self, key: str, task_func, q: queue.Queue):
        """The function that each thread will execute."""
        try:
            result = task_func()
            q.put((key, result))
        except Exception as e:
            error_message = f"Failed to fetch {key} data: {e}"
            print(error_message)
            q.put((key, {"error": error_message}))