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
        # Ensure earnings data is valid and not an error dictionary
        if not earnings or earnings.get("error") or earnings.get("days_until") is None: 
            return None

        days = earnings['days_until']

        # Only proceed if earnings date is in the near future (e.g., within 60 days)
        # and is actually in the future (days_until >= 0)
        if not (0 <= days <= 60): 
            return None

        title = f"Earnings in {days} {'day' if days == 1 else 'days'}"

        # Handle expected_move_pct potentially being None
        expected_move_str = "n/a"
        if earnings.get('expected_move_pct') is not None: # This check is key!
            expected_move_str = f"{earnings['expected_move_pct']:.1f}%"

        desc = f"Expected move is {expected_move_str}. Consider a volatility play."

        # Ensure earnings['date'] exists and is a string for strptime
        if not isinstance(earnings.get('date'), str):
            print(f"Warning: Invalid earnings date format for {symbol}: {earnings.get('date')}")
            return None

        try:
            event_timestamp = int(time.mktime(dt.datetime.strptime(earnings['date'], "%Y-%m-%d").timetuple()))
        except ValueError:
            # Fallback if date parsing fails
            # Using 7 days as a default if calculation fails or days_until is problematic
            event_timestamp = int(time.time()) + 7 * 24 * 3600 

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
        # For debugging: Print the metrics dictionary received by the detector
        # (Comment out or remove in production for less console spam)
        # print(f"[{symbol}] Momentum Detector received metrics: {m.keys()}")
        # print(f"[{symbol}] Detector values: GC={m.get('GoldenCross', 'N/A')}, DC={m.get('DeathCross', 'N/A')}, Squeeze={m.get('BollingerBandSqueeze', 'N/A')}, RSI_OB={m.get('RSI_Overbought', 'N/A')}, RSI_OS={m.get('RSI_Oversold', 'N/A')}, SMA50={m.get('price_above_sma50', 'N/A')}")
        
        # Get the new data directly from metrics
        golden_cross = m.get("GoldenCross", False)
        death_cross = m.get("DeathCross", False)
        bollinger_squeeze = m.get("BollingerBandSqueeze", False)
        rsi_overbought = m.get("RSI_Overbought", False)
        rsi_oversold = m.get("RSI_Oversold", False)
        price_above_sma50 = m.get("price_above_sma50", False)
        
        # Determine the strongest signal and generate idea
        title = ""
        desc = ""
        score_value = 0
        risk_level = "Moderate"
        suggested_type = "" # Will be set by specific signal

        # --- Prioritize the strongest/unique signals first ---
        if golden_cross:
            title = f"Golden Cross: {symbol} Bullish Long-Term Crossover"
            desc = "The 50-day SMA has crossed above the 200-day SMA, indicating strong long-term bullish momentum. This is a classic buy signal."
            score_value = 95 # Very high score for this strong signal
            suggested_type = "Long Stock / Long Call"
            risk_level = "Low" 
        elif death_cross:
            title = f"Death Cross: {symbol} Bearish Long-Term Crossover"
            desc = "The 50-day SMA has crossed below the 200-day SMA, indicating strong long-term bearish momentum. A classic sell signal."
            score_value = 90 # High score for this strong signal
            suggested_type = "Short Stock / Long Put"
            risk_level = "Low" 
        elif bollinger_squeeze:
            title = f"Volatility Squeeze: {symbol} Imminent Big Move Expected"
            desc = "Bollinger Bands are within Keltner Channels, signaling a period of extreme low volatility often preceding a significant price breakout. Direction unknown."
            score_value = 85 # High score for a unique pattern signal
            suggested_type = "Long Straddle / Long Strangle" # Volatility expansion play
            risk_level = "High" 
        elif rsi_overbought:
            title = f"RSI Overbought: {symbol} Due for Pullback"
            desc = "The Relative Strength Index is above 70, suggesting the stock is overbought and a pullback or consolidation is likely."
            score_value = 75 # Strong signal for potential reversal
            suggested_type = "Bear Call Spread / Short Stock" 
            risk_level = "High" 
        elif rsi_oversold:
            title = f"RSI Oversold: {symbol} Potential Bounce Coming"
            desc = "The Relative Strength Index is below 30, suggesting the stock is oversold and a bounce or reversal upwards is likely."
            score_value = 75 # Strong signal for potential reversal
            suggested_type = "Bull Put Spread / Long Stock"
            risk_level = "High" 
        # --- Lower priority for simple SMA signal ---
        elif price_above_sma50:
            title = f"Uptrend: {symbol} Consistently Above 50-Day SMA"
            desc = "Stock price is maintaining above its 50-day Simple Moving Average, indicating a sustained intermediate-term uptrend."
            score_value = 40 # Reduced score as it's a less 'unique' or 'actionable' signal
            suggested_type = "Long Call / Bull Call Spread"
            risk_level = "Moderate"
        else:
            return None # No significant momentum signal detected

        # Add a small random component to the score for variety
        final_score = score_value + random.uniform(0, 5)

        return Idea(symbol, title, desc, self.category, final_score,
                    {"type": suggested_type, "risk": risk_level},
                    m, risk=risk_level, sparkline_data=m.get('price_sparkline'))

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
            # Always target broad market ETFs for macro events
            if symbol not in ["SPY", "QQQ", "IWM", "DIA"]: # Added DIA for Dow
                continue

            event_name = event.get('event_name', '').lower()
            event_date = event.get('date')
            event_ts = None
            try:
                if event_date:
                    event_ts = int(time.mktime(dt.datetime.strptime(event_date, "%Y-%m-%d").timetuple()))
            except ValueError:
                event_ts = int(time.time()) + 86400 # Default to tomorrow if date parse fails

            # Common high-impact events from Investing.com
            if "cpi" in event_name or "consumer price index" in event_name:
                title = f"CPI Report: {symbol} Volatility Expected"
                desc = f"Upcoming inflation data ({event.get('date')}). Actual: {event.get('actual')}, Forecast: {event.get('forecast')}. Potential market-wide volatility."
                score = 80 # Higher score for CPI
                suggested_strat = "Long Straddle"
                risk_level = "High"
            elif "fomc" in event_name or "federal funds rate" in event_name or "interest rate" in event_name:
                title = f"FOMC Decision: {symbol} Interest Rate Impact"
                desc = f"Federal Reserve's upcoming rate decision ({event.get('date')}). Actual: {event.get('actual')}, Forecast: {event.get('forecast')}. Major market implications."
                score = 85 # Even higher score for FOMC
                suggested_strat = "Iron Condor" if event.get('actual') == event.get('forecast') else "Long Straddle" # Condor if no surprise, Straddle if surprise
                risk_level = "Moderate" if suggested_strat == "Iron Condor" else "High"
            elif "non-farm payrolls" in event_name or "unemployment rate" in event_name:
                title = f"NFP Report: {symbol} Jobs Data Impact"
                desc = f"Key employment data release ({event.get('date')}). Actual: {event.get('actual')}, Forecast: {event.get('forecast')}. Strong market mover."
                score = 75
                suggested_strat = "Long Strangle"
                risk_level = "High"
            elif "gdp" in event_name or "gross domestic product" in event_name:
                title = f"GDP Release: {symbol} Economic Growth Outlook"
                desc = f"Latest GDP figures ({event.get('date')}). Actual: {event.get('actual')}, Forecast: {event.get('forecast')}. Indicates economic health."
                score = 65
                suggested_strat = "Long Call / Long Put" # Directional depending on data
                risk_level = "Moderate"
            elif "retail sales" in event_name:
                title = f"Retail Sales: {symbol} Consumer Spending Insight"
                desc = f"Consumer spending data release ({event.get('date')}). Actual: {event.get('actual')}, Forecast: {event.get('forecast')}. Proxy for consumer demand."
                score = 60
                suggested_strat = "Long Call / Long Put"
                risk_level = "Moderate"
            else:
                continue # Skip other events not explicitly handled

            ideas.append(Idea(
                symbol, title, desc, self.category, score,
                {"type": suggested_strat, "risk": risk_level}, 
                m, risk=risk_level, event_ts=event_ts,
                sparkline_data=m.get('price_sparkline', [])
            ))
        return ideas if ideas else None

# --- C. Crowd-powered detectors ---
class RedditSpikeDetector(DetectorBase):
    category = "💬 Social"
    def run(self, symbol: str, m: dict) -> Idea | None:
        mentions = int(m.get("RedditMentions_24h", 0)) # This will now get real scrape count
        if mentions < 50: return None # Threshold might need adjustment with real data

        score = math.log(mentions + 1) * 10
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