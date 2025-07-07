# idea_engine.py
from __future__ import annotations
import math, random, time, datetime as dt, queue
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
    category = "📈 Volatility" # Confirm category label

    def run(self, symbol: str, m: dict) -> Idea | None:
        iv_rank = float(m.get("IVRank_%", 0))
        
        # Require a high IV Rank to trigger this idea
        if iv_rank < 80: # Example threshold: only trigger if IV Rank is 80% or higher
            print(f"[{symbol}] UnusualIVDetector: Skipping (IV Rank {iv_rank:.0f}% < 80).") # Uncomment for debug
            return None
        
        # Decide strategy based on how extreme the IV Rank is
        if iv_rank > 90:
            # Extremely high IV Rank often suggests a short volatility play (selling premium)
            strat_type = "Short Strangle"
            risk_level = "High" # Selling premium is generally high risk
            title = f"Extreme IV Rank: {iv_rank:.0f}% - Volatility Sell"
            desc = "Implied volatility near 1-year extreme high. Market expects big moves, premium selling opportunities."
        else:
            # High IV Rank, could be a long volatility play if expecting more movement, or a short play
            # For simplicity, we'll keep it as long straddle if not extremely high for options.
            strat_type = "Long Straddle" # Or "Long Strangle"
            risk_level = "High" # Long volatility is also high risk
            title = f"High IV Rank: {iv_rank:.0f}% - Volatility Buy"
            desc = "Implied volatility significantly elevated, suggesting potential for large price swings. Consider buying volatility."
            
        return Idea(symbol, title, desc, self.category, iv_rank,
                    {"type": strat_type, "risk": risk_level},
                    m, risk=risk_level,
                    sparkline_data=m.get('IV_sparkline', []), sparkline_type='iv') # Ensure IV sparkline is passed

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
    category = "🧑‍🌾 Theta Farms" # Confirm category label

    def run(self, symbol: str, m: dict) -> Idea | None:
        iv_rank = float(m.get("IVRank_%", 0))
        price_sparkline = m.get("price_sparkline") # Get price history for volatility calculation

        # Require:
        # 1. High IV Rank (to get good premium)
        # 2. Sufficient price data for volatility calculation
        if iv_rank < 70 or not price_sparkline or len(price_sparkline) < 20:
            print(f"[{symbol}] ThetaFarmDetector: Skipping (IV Rank {iv_rank:.0f}% < 70 or insufficient price data).") # Uncomment for debug
            return None
            
        # Calculate historical volatility (daily standard deviation of returns)
        arr = np.array(price_sparkline, dtype=float)
        if len(arr) < 2: # Need at least 2 price points to calculate returns
            return None
            
        # Calculate daily returns and their standard deviation (historical volatility)
        returns = np.diff(arr) / arr[:-1]  # Daily returns
        # Annualize by multiplying by sqrt(252) if these are daily returns over short period
        # For a "quiet tape" check, often the raw daily std is more direct.
        pct_std_daily = np.std(returns)  # Standard deviation of daily returns

        # Define "quiet tape" thresholds:
        # For a premium capture strategy like Iron Condor, you want the stock to NOT move much.
        # This means low historical volatility. Example: daily std < 1.5% to 2.5%
        # The 0.03 (3%) was quite high. Let's aim for 0.005 (0.5%) to 0.015 (1.5%) daily.
        min_quiet_vol = 0.005 # 0.5% daily std
        max_quiet_vol = 0.015 # 1.5% daily std (adjust as needed for typical stock movement)

        if not (min_quiet_vol <= pct_std_daily <= max_quiet_vol):
            print(f"[{symbol}] ThetaFarmDetector: Skipping (Daily Std Dev {pct_std_daily:.2%} not in [{min_quiet_vol:.2%}-{max_quiet_vol:.2%}]).") # Uncomment for debug
            return None

        title = "Low-Risk Theta Farm Candidate"
        desc = (f"Quiet price action (Daily σ={pct_std_daily:.2%}) combined with high IV-Rank ({iv_rank:.0f}%). "
                "Ideal conditions for premium capture strategies like Iron Condors/Credit Spreads.")
        
        score = iv_rank + (100 - pct_std_daily * 1000) # Boost score for lower volatility
        score = max(50, min(100, score)) # Keep score within a reasonable range

        return Idea(symbol, title, desc, self.category, score,
                    {"type": "Iron Condor / Credit Spreads", "risk": "Low"},
                    m, risk="Low", sparkline_data=price_sparkline) # Pass price sparkline here

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
    
# ---. Fundamental Value/Growth detectors ---
class FundamentalValueDetector(DetectorBase):
    category = "💰 Value/Growth"

    def run(self, symbol: str, m: dict) -> List[Idea] | None:
        ideas = []

        from core.models.providers import _to_float

        current_pe = _to_float(m.get("current_pe"))
        historical_pe_avg = _to_float(m.get("historical_pe_avg"))
        peg_ratio = _to_float(m.get("peg_ratio"))
        earnings_growth = _to_float(m.get("earningsGrowth"))
        revenue_growth = _to_float(m.get("revenueGrowth"))
        market_cap = _to_float(m.get("market_cap"))
        current_price = _to_float(m.get("last_price"))

        profit_margins = _to_float(m.get("profitMargins"))
        gross_margins = _to_float(m.get("grossMargins"))
        return_on_equity = _to_float(m.get("returnOnEquity"))
        debt_to_equity = _to_float(m.get("debtToEquity"))

        analyst_target_mean = _to_float(m.get("analyst_target_mean_price"))
        price_to_book = _to_float(m.get("priceToBook"))


        # Helper to avoid adding duplicate ideas based on a primary fundamental insight
        existing_fundamental_idea_titles = set()

        def add_idea_if_unique(idea: Idea):
            if not any(idea.title.startswith(prefix) for prefix in existing_fundamental_idea_titles):
                ideas.append(idea)
                existing_fundamental_idea_titles.add(idea.title.split(":")[0]) # Use prefix for uniqueness

        # --- Idea 1: Undervalued based on Historical P/E ---
        if (current_pe is not None and historical_pe_avg is not None and
            isinstance(current_pe, (int, float)) and isinstance(historical_pe_avg, (int, float))):
            
            if historical_pe_avg > 0.01 and current_pe > 0.01: 
                if current_pe < historical_pe_avg * 0.80: # 20% or more below average
                    title = f"Undervalued: {symbol} P/E Below Historical Avg"
                    desc = (f"Current P/E ({current_pe:.1f}) is significantly below its historical average ({historical_pe_avg:.1f}), "
                            "suggesting potential undervaluation relative to its own history.")
                    score = 80 + random.uniform(-5, 5) 
                    add_idea_if_unique(Idea(
                        symbol, title, desc, self.category, score,
                        {"type": "Long Stock / Bull Call Spread", "risk": "Moderate"},
                        m, risk="Moderate", sparkline_data=m.get('price_sparkline')
                    ))
                elif current_pe > historical_pe_avg * 1.20: # 20% or more above average
                     title = f"Overvalued: {symbol} P/E Above Historical Avg"
                     desc = (f"Current P/E ({current_pe:.1f}) is significantly above its historical average ({historical_pe_avg:.1f}), "
                             "suggesting potential overvaluation relative to its own history.")
                     score = 30 + random.uniform(-5, 5) 
                     add_idea_if_unique(Idea(
                         symbol, title, desc, self.category, score,
                         {"type": "Short Stock / Bear Call Spread", "risk": "Moderate"},
                         m, risk="Moderate", sparkline_data=m.get('price_sparkline')
                     ))


        # --- Idea 2: Growth at a Reasonable Price (GARP) ---
        if (peg_ratio is not None and isinstance(peg_ratio, (int, float)) and peg_ratio > 0 and
            earnings_growth is not None and isinstance(earnings_growth, (int, float)) and
            revenue_growth is not None and isinstance(revenue_growth, (int, float))):
            
            if peg_ratio <= 1.2: # Common GARP criteria
                if earnings_growth > 0.05 or revenue_growth > 0.05: # At least 5% quarterly growth
                    title = f"GARP Candidate: {symbol} Growth at Reasonable Price"
                    desc = (f"PEG Ratio ({peg_ratio:.2f}) indicates good value relative to earnings growth. "
                            f"Recent earnings growth: {earnings_growth:.1%}, Revenue growth: {revenue_growth:.1%}.")
                    score = 85 + random.uniform(-5, 5)
                    add_idea_if_unique(Idea(
                        symbol, title, desc, self.category, score,
                        {"type": "Long Stock / Bull Call Spread", "risk": "Low"},
                        m, risk="Low", sparkline_data=m.get('price_sparkline')
                    ))
        
        # --- Idea 3: Significant Upside to Analyst Target ---
        if (analyst_target_mean is not None and current_price is not None and current_price > 0 and
            isinstance(analyst_target_mean, (int, float)) and isinstance(current_price, (int, float))):
            
            upside_potential_pct = ((analyst_target_mean - current_price) / current_price) * 100
            if upside_potential_pct >= 15: # At least 15% upside
                title = f"Analyst Upside: {symbol} {upside_potential_pct:.1f}% to Target"
                desc = (f"Current price (${current_price:.2f}) significantly below average analyst target (${analyst_target_mean:.2f}), "
                        "suggesting strong upside potential according to Wall Street consensus.")
                score = 70 + min(upside_potential_pct / 2, 25) + random.uniform(-5, 5) 
                add_idea_if_unique(Idea(
                    symbol, title, desc, self.category, score,
                    {"type": "Long Stock / Long Call", "risk": "Moderate"},
                    m, risk="Moderate", sparkline_data=m.get('price_sparkline')
                ))

        # --- Idea 4: Undervalued by Price-to-Book ---
        if (price_to_book is not None and isinstance(price_to_book, (int, float))):
            if price_to_book > 0 and price_to_book < 1.5: # P/B < 1.5 for many industries suggests value
                title = f"Undervalued: {symbol} Low Price-to-Book ({price_to_book:.2f})"
                desc = "Stock trading at a low Price-to-Book ratio, potentially indicating undervaluation relative to its assets."
                score = 65 + random.uniform(-5, 5)
                add_idea_if_unique(Idea(
                    symbol, title, desc, self.category, score,
                    {"type": "Long Stock / Cash-Secured Put", "risk": "Low"},
                    m, risk="Low", sparkline_data=m.get('price_sparkline')
                ))

        # --- Idea 5: Quality at a Reasonable Price (QARP) --- NEW QARP
        # Combines reasonable valuation (P/E or P/B) with strong quality metrics
        if (current_pe is not None and current_pe > 0 and current_pe < 30 and # Reasonable P/E (<30)
            profit_margins is not None and profit_margins >= 0.15 and # Profit margin >= 15%
            gross_margins is not None and gross_margins >= 0.30 and # Gross margin >= 30%
            return_on_equity is not None and return_on_equity >= 0.10 and # ROE >= 10%
            (debt_to_equity is None or debt_to_equity < 1.0)): # D/E < 1.0 (or None if no debt)
            
            title = f"QARP Candidate: {symbol} Quality & Value"
            desc = (f"Strong margins (Profit: {profit_margins:.1%}, Gross: {gross_margins:.1%}) & ROE ({return_on_equity:.1%}) "
                    f"with reasonable P/E ({current_pe:.1f}). High quality at a fair price.")
            score = 90 + random.uniform(-5, 5)
            add_idea_if_unique(Idea(
                symbol, title, desc, self.category, score,
                {"type": "Long Stock / Long Call", "risk": "Low"},
                m, risk="Low", sparkline_data=m.get('price_sparkline')
            ))
            
        return ideas if ideas else None
    
class IVCrushDetector(DetectorBase):
    category = "📈 Volatility" # Use Volatility category, or create a new "IV Crush" category

    def run(self, symbol: str, m: dict) -> Idea | None:
        iv_rank = float(m.get("IVRank_%", 0))
        upcoming_earnings = m.get("UpcomingEarnings")
        
        if not upcoming_earnings or upcoming_earnings.get("error") or upcoming_earnings.get("days_until") is None:
            return None # No upcoming earnings data

        days_until_earnings = upcoming_earnings['days_until']

        # Conditions for IV Crush Play:
        # 1. High IV Rank (e.g., 80% or higher)
        # 2. Earnings announcement is very soon (e.g., 1 to 3 days away)
        if iv_rank >= 80 and 0 < days_until_earnings <= 3:
            title = f"IV Crush Play: {symbol} Earnings Imminent"
            desc = (f"Implied Volatility (IV Rank: {iv_rank:.0f}%) is very high just before earnings "
                    f"({days_until_earnings} day(s) away). Expect IV to 'crush' after announcement, benefiting sellers.")
            score = 90 + random.uniform(-5, 5) # High score for this unique setup
            return Idea(symbol, title, desc, self.category, score,
                        {"type": "Short Strangle / Iron Condor", "risk": "High"}, # Selling volatility
                        m, risk="High", sparkline_data=m.get('IV_sparkline'), sparkline_type='iv')
        
        return None
    
class PostEarningsReactionDetector(DetectorBase):
    category = "🗓 Earnings" # Use Earnings category

    def run(self, symbol: str, m: dict) -> Idea | None:
        latest_report = m.get("latest_earnings_report")
        one_day_change = m.get("earnings_1d_price_change_pct")
        three_day_change = m.get("earnings_3d_price_change_pct")

        if not latest_report or latest_report.get("reported_eps") is None or latest_report.get("estimated_eps") is None:
            return None # No recent earnings report details available

        reported_eps = latest_report["reported_eps"]
        estimated_eps = latest_report["estimated_eps"]
        surprise_pct = latest_report.get("surprise_pct")
        
        # Ensure EPS values are valid numbers before comparison
        if not isinstance(reported_eps, (int, float)) or not isinstance(estimated_eps, (int, float)):
            return None

        title = ""
        desc = ""
        score = 0
        suggested_type = ""
        risk_level = "Moderate"

        # Determine if it was a beat or miss
        is_beat = reported_eps > estimated_eps
        is_miss = reported_eps < estimated_eps
        is_in_line = reported_eps == estimated_eps
        
        # Focus on a significant beat or miss
        significant_surprise = (surprise_pct is not None and abs(surprise_pct) >= 5) # 5% surprise

        # --- Idea 1: Strong Post-Earnings Drift (Beat + Positive Reaction) ---
        if is_beat and significant_surprise and one_day_change is not None and one_day_change > 2: # 2%+ move up
            title = f"Earnings Beat: {symbol} Post-Report Drift Up"
            desc = (f"Stock beat EPS estimates ({surprise_pct:.1f}% surprise) and reacted strongly positively "
                    f"({one_day_change:.1f}% next day). Potential for continued drift.")
            score = 88 + random.uniform(-5, 5)
            suggested_type = "Long Stock / Bull Call Spread"
            risk_level = "Low" # If drift is known anomaly
        
        # --- Idea 2: Strong Post-Earnings Reversal (Miss + Positive Reaction) OR (Beat + Negative Reaction) ---
        # This is for situations where market initial reaction is counter-intuitive
        elif is_miss and significant_surprise and one_day_change is not None and one_day_change > 0 and one_day_change <= 2: # Small positive move after miss
             title = f"Earnings Miss: {symbol} Counter-Intuitive Bounce"
             desc = (f"Stock missed EPS estimates ({surprise_pct:.1f}% surprise) but saw a slight positive bounce "
                     f"({one_day_change:.1f}% next day), suggesting short-term reversal or 'buy the dip' action.")
             score = 70 + random.uniform(-5, 5)
             suggested_type = "Long Stock / Bull Put Spread"
             risk_level = "High" # Counter-intuitive is high risk

        elif is_miss and significant_surprise and one_day_change is not None and one_day_change < -2: # Strong negative reaction after miss
            title = f"Earnings Miss: {symbol} Post-Report Drift Down"
            desc = (f"Stock missed EPS estimates ({surprise_pct:.1f}% surprise) and reacted strongly negatively "
                    f"({one_day_change:.1f}% next day). Potential for continued sell-off.")
            score = 85 + random.uniform(-5, 5)
            suggested_type = "Short Stock / Bear Put Spread"
            risk_level = "Low" # If drift is known anomaly

        if score > 0: # Only create idea if a condition was met
            return Idea(symbol, title, desc, self.category, score,
                        {"type": suggested_type, "risk": risk_level},
                        m, risk=risk_level, sparkline_data=m.get('price_sparkline'))
        
        return None
    
class ShortSqueezeDetector(DetectorBase):
    category = "🚀 Momentum" # Use Momentum category, or new "Special Situations"

    def run(self, symbol: str, m: dict) -> Idea | None:
        short_percent_of_float = m.get("short_percent_of_float")
        last_price = m.get("last_price")
        price_sparkline = m.get("price_sparkline")

        # Get momentum signals to check for an "uptick"
        price_above_sma50 = m.get("price_above_sma50", False)
        rsi_oversold = m.get("RSI_Oversold", False) # Often precedes a bounce
        bollinger_squeeze = m.get("BollingerBandSqueeze", False) # Can precede big move

        # Conditions for Short Squeeze Potential:
        # 1. High Short Interest (e.g., > 10% or 15% of float)
        # 2. Some form of bullish catalyst or recent uptick / oversold condition
        
        if (short_percent_of_float is None or 
            not isinstance(short_percent_of_float, (int, float)) or 
            short_percent_of_float < 0.10): # Requires at least 10% short interest
            return None

        # Check for a recent uptick or potential catalyst.
        # This is a heuristic.
        is_uptick_catalyst = False
        if price_above_sma50: # Basic uptrend
            is_uptick_catalyst = True
        if rsi_oversold and last_price and price_sparkline and len(price_sparkline) > 1:
            # If oversold and price has ticked up recently (e.g., last day)
            if price_sparkline[-1] > price_sparkline[-2]:
                is_uptick_catalyst = True
        if bollinger_squeeze: # Squeeze can lead to a big move, including short squeeze
            is_uptick_catalyst = True

        if is_uptick_catalyst:
            title = f"Short Squeeze Alert: {symbol} ({short_percent_of_float:.1%})"
            desc = (f"High short interest ({short_percent_of_float:.1%}) combined with a recent bullish signal "
                    "suggests potential for a short squeeze. Watch for price acceleration.")
            score = 85 + random.uniform(-5, 5) # High score for a specific market dynamic
            return Idea(symbol, title, desc, self.category, score,
                        {"type": "Long Stock / Long Call", "risk": "High"},
                        m, risk="High", sparkline_data=m.get('price_sparkline'))
        
        return None
    
# --- C. Crowd-powered detectors ---


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
    category = "🎯 Setups" # Confirm category label

    def run(self, symbol: str, m: dict) -> Idea | None:
        iv_rank = float(m.get("IVRank_%", 0))
        price_sparkline = m.get("price_sparkline") # Get price history for volatility calculation
        
        # Get momentum signals to ensure stock is NOT strongly trending
        golden_cross = m.get("GoldenCross", False)
        death_cross = m.get("DeathCross", False)
        bollinger_squeeze = m.get("BollingerBandSqueeze", False)
        rsi_overbought = m.get("RSI_Overbought", False)
        rsi_oversold = m.get("RSI_Oversold", False)

        # Conditions for Premium Capture:
        # 1. High IV Rank (need good premium)
        # 2. Not a "Theta Farm" (i.e., historical vol not extremely low, but still reasonable)
        # 3. No strong directional momentum signals (to avoid getting run over)
        if iv_rank < 70: # Must have high IV Rank for premium
            return None
        
        # If any strong directional/volatility expansion signal is present, this is not a "neutral" premium capture setup
        if golden_cross or death_cross or bollinger_squeeze or rsi_overbought or rsi_oversold:
            print(f"[{symbol}] PremiumCaptureDetector: Skipping (Strong momentum/volatility signal present).") # Uncomment for debug
            return None

        # Calculate historical volatility for context
        pct_std_daily = 0.0 # Default if no sparkline
        if price_sparkline and len(price_sparkline) >= 20:
            arr = np.array(price_sparkline, dtype=float)
            if len(arr) >= 2:
                returns = np.diff(arr) / arr[:-1]
                pct_std_daily = np.std(returns)
        
        # This condition distinguishes it from Theta Farm: here, historical volatility can be moderate.
        # It's not about "quiet tape" but "neutral to moderate volatility with high IV".
        # Example: daily std between 1.5% and 3.5%
        min_moderate_vol = 0.015 # 1.5% daily std
        max_moderate_vol = 0.035 # 3.5% daily std
        
        if not (min_moderate_vol <= pct_std_daily <= max_moderate_vol):
            print(f"[{symbol}] PremiumCaptureDetector: Skipping (Daily Std Dev {pct_std_daily:.2%} not in [{min_moderate_vol:.2%}-{max_moderate_vol:.2%}]).") # Uncomment for debug
            return None

        title = "High IV Premium Capture Setup"
        desc = (f"Elevated IV-Rank ({iv_rank:.0f}%) with moderate historical volatility (Daily σ={pct_std_daily:.2%}) "
                "and no strong directional signals. Good for selling strategies.")
        
        score = iv_rank + (100 - pct_std_daily * 500) # Score based on IV and moderate volatility
        score = max(50, min(100, score))

        return Idea(symbol, title, desc, self.category, score,
                    {"type": "Short Strangle / Iron Condor", "risk": "Moderate"},
                    m, risk="Moderate", sparkline_data=m.get('IV_sparkline'), sparkline_type='iv') # Use IV sparkline for context

# --- Register all detectors ---
DETECTORS: Sequence[DetectorBase] = (
    UnusualIVDetector(),
    EarningsVolPlayDetector(),
    MomentumDetector(),
    ThetaFarmDetector(),
    MacroNarrativeDetector(),
    GoogleTrendsDetector(),
    PremiumCaptureDetector(),
    FundamentalValueDetector(),
    IVCrushDetector(),
    PostEarningsReactionDetector(), 
    ShortSqueezeDetector(),
)

# Category labels for the UI - updated to match detector categories
# Category labels for the UI - updated to match detector categories
CATEGORY_LABELS = {
    "📈 Volatility": "📈 Volatility",
    "🗓 Earnings": "🗓 Earnings",
    "🚀 Momentum": "🚀 Momentum",
    "🧑‍🌾 Theta Farms": "🧑‍🌾 Theta Farms",
    "🌎 Thematic": "🌎 Thematic",
    "💬 Social": "💬 Social",
    "🎯 Setups": "🎯 Setups",
    "💰 Value/Growth": "💰 Value/Growth"
}

# --- Idea Engine façade ---
class IdeaEngine:
    def __init__(self, market_data: 'MarketDataService' | None = None, cache: 'IdeaCache' | None = None, progress_sink: queue.Queue | None = None) -> None: # Fix: Add progress_sink as a parameter with default None
        self.market_data = market_data or MarketDataService()
        self.cache = cache or IdeaCache(ttl_sec=900)
        self.progress_sink = progress_sink 

    # In idea_engine.py, inside IdeaEngine.generate method
    def generate(self, universe: Iterable[str]) -> list[Idea]:
        ideas: list[Idea] = []
        total_symbols = len(list(universe))
        processed_symbols = 0

        try:
            macro_metrics = self.market_data._read("GLOBAL") or {}
        except Exception:
            macro_metrics = {}

        for sym in universe:
            try:
                if cached := self.cache.read(sym):
                    ideas.extend(cached)
                    processed_symbols += 1
                    if self.progress_sink:
                        self.progress_sink.put((processed_symbols, total_symbols))
                    continue

                metrics = self.market_data.get_metrics(sym)
                if metrics.get("error"):
                    print(f"Skipping {sym} due to data error: {metrics['error']}")
                    processed_symbols += 1
                    if self.progress_sink:
                        self.progress_sink.put((processed_symbols, total_symbols))
                    continue

                full = {**metrics, **macro_metrics}

                # --- NEW DEBUG PRINT ---
                # Print the entire 'full' metrics dictionary for inspection
                # This will show if '0m' exists in any field *after* ProviderHub.get
                print(f"DEBUG: Full metrics for {sym} before detectors: {full}")
                # --- END NEW DEBUG PRINT ---

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
                        # If the error is still 'could not convert string to float: '0m'',
                        # this print will show which detector fails.

                if sym_ideas:
                    self.cache.write(sym, sym_ideas)
                    ideas.extend(sym_ideas)

            except Exception as e:
                print(f"Error processing {sym} in IdeaEngine.generate: {e}")
                import traceback
                traceback.print_exc() # Print full traceback for this high-level error

            processed_symbols += 1
            if self.progress_sink:
                self.progress_sink.put((processed_symbols, total_symbols))

        return ideas