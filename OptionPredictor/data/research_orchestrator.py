# data/research_orchestrator.py
import threading
import queue
import yfinance as yf
from core.models.providers import ProviderHub, FundamentalDataProvider
from tools.StockEventTracker import StockEventTracker
from core.models.providers import OptionsChainProvider
class ResearchOrchestrator:
    """
    Manages the asynchronous fetching of all data required for the Stock Research Suite.
    """
    def __init__(self, finnhub_key: str):
        # Instantiate providers
        self.fundamental_provider = FundamentalDataProvider()
        self.options_provider = OptionsChainProvider()
        self.event_tracker = StockEventTracker(alpha_api_key="JJDYBMACWY5SUU7M", finnhub_api_key=finnhub_key)

    def fetch_all_data(self, ticker: str) -> tuple[queue.Queue, int]:
        """
        Kicks off the data fetching process for a given ticker.

        Returns a tuple containing:
        1. A queue that the UI can poll for results.
        2. The total number of tasks initiated.
        """
        if not ticker:
            raise ValueError("Ticker symbol cannot be empty.")

        q = queue.Queue()
        ticker = ticker.strip().upper()
        yf_ticker = yf.Ticker(ticker)

        tasks = {
            "provider_hub": lambda: ProviderHub.get(ticker),
            "fundamentals": lambda: self.fundamental_provider.fetch(ticker),
            "events": lambda: self.event_tracker.fetch_upcoming_events(ticker),
            "financials": lambda: {
                "income": yf_ticker.income_stmt,
                "balance": yf_ticker.balance_sheet,
                "cashflow": yf_ticker.cashflow
            },
            "news": lambda: self.event_tracker.scrape_google_news_rss_articles_multiple_queries(ticker),
            "options": lambda: self.options_provider.fetch(ticker),
            "profile": lambda: yf_ticker.info,
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