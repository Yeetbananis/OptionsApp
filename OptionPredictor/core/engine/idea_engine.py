# idea_engine.py
from __future__ import annotations
import math, random, time, datetime as dt
from typing import Iterable, List, Sequence
import numpy as np  # Added this import at the top

from core.storage.idea_cache import IdeaCache
from core.models.idea_models import Idea
from core.engine.market_data_service import MarketDataService

# --- Detector base ---
class DetectorBase:
    category: str = "Other"
    def run(self, symbol: str, metrics: dict) -> Idea | List[Idea] | None: ...

# --- A. Data-Driven detectors ---
class UnusualIVDetector(DetectorBase):
    category = "📈 Volatility"
    def run(self, symbol: str, m: dict) -> Idea | None:
        iv_rank = float(m.get("IVRank_%", 0))
        if iv_rank < 80: return None
        
        strat_type = "Short Strangle" if iv_rank > 90 else "Long Straddle"
        risk_level = "High" if strat_type == "Long Straddle" else "Moderate"
        
        return Idea(symbol, f"IV Rank {iv_rank:.0f}%", "Implied volatility near 1-year high.",
                    self.category, iv_rank, {"type": strat_type, "risk": risk_level},
                    m, risk=risk_level, sparkline_data=m.get('IV_sparkline', []), sparkline_type='iv')

class EarningsVolPlayDetector(DetectorBase):
    category = "🗓 Earnings"
    def run(self, symbol: str, m: dict) -> Idea | None:
        earnings = m.get("UpcomingEarnings")
        if not earnings or earnings.get("days_until", 99) > 7: return None
        
        days = earnings['days_until']
        title = f"Earnings in {days} {'day' if days == 1 else 'days'}"
        desc = f"Expected move is {earnings['expected_move_pct']:.1f}%. Consider a volatility play."
        event_timestamp = int(time.mktime(dt.datetime.strptime(earnings['date'], "%Y-%m-%d").timetuple()))
        
        return Idea(symbol, title, desc, self.category,
                    80 - days + random.random(), {"type": "Long Straddle", "risk": "High"},
                    m, risk="High", event_ts=event_timestamp, sparkline_data=m.get('price_sparkline'))

class UnusualOptionsActivityDetector(DetectorBase):
    category = "🌊 Options Flow"
    def run(self, symbol: str, m: dict) -> Idea | None:
        activity = m.get("UnusualActivity")
        if not activity: return None

        sentiment = activity['sentiment'].capitalize()
        title = f"{sentiment} {activity['aggressor'].title()} Detected"
        desc = f"${activity['premium']:,} in premium traded. Open interest jumped {activity['oi_change_pct']}%."
        strat_type = "Bull Call Spread" if sentiment == "Bullish" else "Bear Put Spread"
        
        return Idea(symbol, title, desc, self.category, activity['premium'] / 20000,
                    {"type": strat_type, "risk": "High"}, m, risk="High", sparkline_data=m.get('price_sparkline'))

class MomentumDetector(DetectorBase):
    category = "🚀 Momentum"
    def run(self, symbol: str, m: dict) -> Idea | None:
        momentum = m.get("MomentumSignal")
        price_above_sma = m.get("price_above_sma50", False)
        if not momentum or not price_above_sma: return None
        
        title = f"Price Breakout Over {momentum['consecutive_days']}-Day High"
        desc = f"Stock crossed its {momentum['price_sma_crossed']}D SMA with strong momentum."
        
        return Idea(symbol, title, desc, self.category, momentum['consecutive_days'] * 10,
                    {"type": "Bull Call Spread", "risk": "Moderate"}, m, risk="Moderate", sparkline_data=m.get('price_sparkline'))

class ThetaFarmDetector(DetectorBase):
    category = "🧑‍🌾 Theta Farms"
    def run(self, symbol: str, m: dict) -> Idea | None:
        iv_rank = float(m.get("IVRank_%", 0))
        prices = m.get("price_sparkline") or []
        if iv_rank < 70 or len(prices) < 20:
            return None  # need high IV and at least 20 data-points

        # Convert to numpy array and calculate volatility
        arr = np.array(prices, dtype=float)
        if len(arr) < 2:
            return None
            
        # Calculate percentage standard deviation of daily returns
        returns = np.diff(arr) / arr[:-1]  # Daily returns
        pct_std = np.std(returns)  # Standard deviation of returns

        if pct_std > 0.03:  # not "stable" enough (>3% daily volatility)
            return None

        return Idea(
            symbol,
            "Low-Risk Theta Farm",
            f"Quiet tape (σ={pct_std:.2%}) & IV-Rank {iv_rank:.0f}%.",
            self.category,
            iv_rank,
            {"type": "Iron Condor", "risk": "Low"},
            m,
            risk="Low",
            sparkline_data=prices,
        )

# --- B. Thematic / Narrative Ideas ---
class MacroNarrativeDetector(DetectorBase):
    category = "🌎 Thematic"
    def run(self, symbol: str, m: dict) -> List[Idea] | None:
        events = m.get("MacroEvents", [])
        if not events: return None
        
        ideas = []
        for event in events:
            # Generate a macro-based idea for broad market ETFs
            if event['event_name'] == "CPI Report" and symbol in ["SPY", "QQQ", "IWM"]:
                title = "CPI Report Catalyst"
                desc = "Potential market-wide volatility around the upcoming inflation report."
                try:
                    event_ts = int(time.mktime(dt.datetime.strptime(event['date'], "%Y-%m-%d").timetuple()))
                except (ValueError, KeyError):
                    event_ts = int(time.time()) + 86400  # Default to tomorrow
                    
                ideas.append(Idea(
                    symbol, title, desc, self.category, 75,
                    {"type": "Long Straddle", "risk": "High"}, 
                    m, risk="High", event_ts=event_ts,
                    sparkline_data=m.get('price_sparkline', [])
                ))
            elif event['event_name'] == "FOMC Meeting" and symbol in ["SPY", "QQQ", "IWM"]:
                title = "FOMC Volatility Play"
                desc = "Federal Reserve meeting may cause market-wide volatility."
                try:
                    event_ts = int(time.mktime(dt.datetime.strptime(event['date'], "%Y-%m-%d").timetuple()))
                except (ValueError, KeyError):
                    event_ts = int(time.time()) + 172800  # Default to day after tomorrow
                    
                ideas.append(Idea(
                    symbol, title, desc, self.category, 70,
                    {"type": "Iron Condor", "risk": "Moderate"}, 
                    m, risk="Moderate", event_ts=event_ts,
                    sparkline_data=m.get('price_sparkline', [])
                ))
        return ideas if ideas else None

# --- C. Crowd-powered detectors ---
class RedditSpikeDetector(DetectorBase):
    category = "💬 Social"
    def run(self, symbol: str, m: dict) -> Idea | None:
        mentions = int(m.get("RedditMentions_24h", 0))
        if mentions < 50: return None  # Lowered threshold since we're using mock data
        
        score = math.log(mentions + 1) * 10  # Added +1 to avoid log(0)
        return Idea(symbol, f"Reddit Spike ({mentions} mentions)", "Mentions surged on r/wallstreetbets.",
                    self.category, score, {"type": "Bull Call Spread", "risk": "High"},
                    m, risk="High", sparkline_data=m.get('price_sparkline'))

class GoogleTrendsDetector(DetectorBase):
    category = "💬 Social"
    def run(self, symbol: str, m: dict) -> Idea | None:
        trends = float(m.get("GoogleTrendScore", 0))
        if trends < 30: return None  # Lowered threshold for mock data
        
        return Idea(symbol, f"Google Search Interest: {trends:.0f}", "Retail search traffic is rising.",
                    self.category, trends, {"type": "Bull Put Spread", "risk": "Low"},
                    m, risk="Low", sparkline_data=m.get('price_sparkline'))

# --- D. Strategy-based setups ---
class PremiumCaptureDetector(DetectorBase):
    category = "🎯 Setups"
    def run(self, symbol: str, m: dict) -> Idea | None:
        if float(m.get("IVRank_%", 0)) < 80: return None
        
        return Idea(symbol, "Covered Strangle Candidate", "High IV & stable trend, ideal for premium capture.",
                    self.category, m["IVRank_%"] / 2, {"type": "Covered Strangle", "risk": "Moderate"},
                    m, risk="Moderate", sparkline_data=m.get('IV_sparkline'), sparkline_type='iv')

# --- Register all detectors ---
DETECTORS: Sequence[DetectorBase] = (
    UnusualIVDetector(),
    EarningsVolPlayDetector(),
    UnusualOptionsActivityDetector(),
    MomentumDetector(),
    ThetaFarmDetector(),
    MacroNarrativeDetector(),
    RedditSpikeDetector(),
    GoogleTrendsDetector(),
    PremiumCaptureDetector(),
)

# Category labels for the UI - updated to match detector categories
CATEGORY_LABELS = {
    "📈 Volatility": "📈 Volatility",
    "🗓 Earnings": "🗓 Earnings",
    "🌊 Options Flow": "🌊 Options Flow",
    "🚀 Momentum": "🚀 Momentum",
    "🧑‍🌾 Theta Farms": "🧑‍🌾 Theta Farms",
    "🌎 Thematic": "🌎 Thematic",
    "💬 Social": "💬 Social",
    "🎯 Setups": "🎯 Setups",
    "🧪 Experimental": "🧪 Experimental"
}

# --- Idea Engine façade ---
class IdeaEngine:
    def __init__(self, market_data: MarketDataService | None = None, cache: IdeaCache | None = None) -> None:
        self.market_data = market_data or MarketDataService()
        self.cache = cache or IdeaCache(ttl_sec=900)

    def generate(self, universe: Iterable[str]) -> list[Idea]:
        """
        Create ideas for every ticker in *universe*.

        * Fetches macro metrics only if they exist in the cache -- avoids
          hitting yfinance with a fake "GLOBAL" symbol.
        * If the macro cache is empty, we just use {} so no network call
          can fail.
        """
        ideas: list[Idea] = []

        # get cached macro snapshot, bypass ProviderHub for 'GLOBAL'
        try:
            macro_metrics = self.market_data._read("GLOBAL") or {}
        except Exception:
            macro_metrics = {}

        for sym in universe:
            try:
                if cached := self.cache.read(sym):
                    ideas.extend(cached)
                    continue

                metrics = self.market_data.get_metrics(sym)
                if metrics.get("error"):
                    print(f"Skipping {sym} due to data error: {metrics['error']}")
                    continue

                full = {**metrics, **macro_metrics}

                sym_ideas: list[Idea] = []
                for det in DETECTORS:
                    try:
                        res = det.run(sym, full)
                        if isinstance(res, list):
                            sym_ideas.extend(res)
                        elif res:
                            sym_ideas.append(res)
                    except Exception as de:
                        print(f"Detector {det.__class__.__name__} failed on {sym}: {de}")

                if sym_ideas:
                    self.cache.write(sym, sym_ideas)
                    ideas.extend(sym_ideas)

            except Exception as e:
                print(f"Error processing {sym}: {e}")
                continue
        return ideas