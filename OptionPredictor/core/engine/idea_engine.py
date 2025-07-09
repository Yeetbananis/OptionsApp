# idea_engine.py
from __future__ import annotations
import math, random, time, datetime as dt, queue
from typing import Iterable, List, Sequence
import numpy as np  # Added this import at the top
from concurrent.futures import ThreadPoolExecutor

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
        try:
            # --- REPLACEMENT START ---
            iv_rank = float(m.get("IVRank_%", 0))
            if iv_rank < 80:
                return None
            
            strat_type = "Iron Condor" # Clean name
            risk_level = "High"
            title = f"High IV Rank: {iv_rank:.0f}% - Volatility Overpriced?"
            desc = "Implied volatility near 1-year high. Options are expensive, creating opportunities to sell premium."
                
            return Idea(symbol, title, desc, self.category, iv_rank,
                        {"type": strat_type, "risk": risk_level},
                        m, risk=risk_level,
                        sparkline_data=m.get('IV_sparkline', []), sparkline_type='iv')
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
        
        # --- REPLACEMENT END ---
class EarningsVolPlayDetector(DetectorBase):
    category = "🗓 Earnings"
    def run(self, symbol: str, m: dict) -> Idea | None:
        try:
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
            expected_move_str = f"{earnings.get('expected_move_pct', 0.0) * 100:.1f}%"
            desc = f"Expected move is {expected_move_str}. Consider a volatility play."

            try:
                event_timestamp = int(time.mktime(dt.datetime.strptime(earnings['date'], "%Y-%m-%d").timetuple()))
            except (ValueError, TypeError):
                return None

            return Idea(symbol, title, desc, self.category,
                        80 - days + random.random(), {"type": "Straddle", "risk": "High"}, # FIX: "Long Straddle" -> "Straddle"
                        m, risk="High", event_ts=event_timestamp, sparkline_data=m.get('price_sparkline'))
    
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
    

class MomentumDetector(DetectorBase):
    category = "🚀 Momentum"
    # In class MomentumDetector:
    def run(self, symbol: str, m: dict) -> Idea | None:
        try: 
            # --- REPLACEMENT START ---
            golden_cross = m.get("GoldenCross", False)
            death_cross = m.get("DeathCross", False)
            bollinger_squeeze = m.get("BollingerBandSqueeze", False)
            rsi_overbought = m.get("RSI_Overbought", False)
            rsi_oversold = m.get("RSI_Oversold", False)
            
            title, desc, score, strat_type, risk_level = "", "", 0, "", "Moderate"

            if golden_cross:
                title = f"Golden Cross: {symbol} Long-Term Bullish"
                desc = "The 50-day SMA has crossed above the 200-day SMA, a strong long-term bullish signal."
                score, strat_type, risk_level = 95, "Long Call", "Moderate"
            elif death_cross:
                title = f"Death Cross: {symbol} Long-Term Bearish"
                desc = "The 50-day SMA has crossed below the 200-day SMA, a strong long-term bearish signal."
                score, strat_type, risk_level = 90, "Put", "Moderate"
            elif bollinger_squeeze:
                title = f"Volatility Squeeze: {symbol} Breakout Imminent"
                desc = "Bollinger Bands are historically tight, signaling a potential for a significant price breakout. Direction is unknown."
                score, strat_type, risk_level = 85, "Straddle", "High"
            elif rsi_overbought:
                title = f"RSI Overbought: {symbol} Reversal Candidate"
                desc = "RSI is above 70, suggesting the stock may be overbought and due for a pullback."
                # FIX: A Bear Call Spread is a good strategy here, but the simple template is "Bear Put".
                score, strat_type, risk_level = 75, "Bear Put", "High"
            elif rsi_oversold:
                title = f"RSI Oversold: {symbol} Bounce Candidate"
                desc = "RSI is below 30, suggesting the stock may be oversold and due for a bounce."
                # FIX: A Bull Put Spread is a good strategy here, but the simple template is "Bull Call".
                score, strat_type, risk_level = 75, "Bull Call", "High"
            else:
                return None

            return Idea(symbol, title, desc, self.category, score + random.uniform(0, 5),
                        {"type": strat_type, "risk": risk_level},
                        m, risk=risk_level, sparkline_data=m.get('price_sparkline'))
        
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
   
       
      

class ThetaFarmDetector(DetectorBase):
    category = "🧑‍🌾 Theta Farms" # Confirm category label

    def run(self, symbol: str, m: dict) -> Idea | None:
        try: 

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
                        {"type": "Iron Condor", "risk": "Low"}, # FIX: Simplified name
                        m, risk="Low", sparkline_data=price_sparkline)
        
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None

# --- B. Thematic / Narrative Ideas ---
class MacroNarrativeDetector(DetectorBase):
    category = "🌎 Thematic"
    # In class MacroNarrativeDetector:
    def run(self, symbol: str, m: dict) -> List[Idea] | None:
        try: 
            events = m.get("MacroEvents", [])
            if not events: return None
            ideas = []
            for event in events:
                if symbol not in ["SPY", "QQQ", "IWM", "DIA"]: continue
                event_name = event.get('event_name', '').lower()
                try:
                    event_ts = int(time.mktime(dt.datetime.strptime(event.get('date'), "%Y-%m-%d").timetuple()))
                except (ValueError, TypeError): continue

                title, desc, score, strat_type, risk_level = "", "", 0, "", "High"

                if "cpi" in event_name or "consumer price index" in event_name:
                    title, desc, score, strat_type = f"CPI Report: Volatility Expected", f"Upcoming inflation data on {event.get('date')}.", 80, "Straddle"
                elif "fomc" in event_name or "federal funds rate" in event_name:
                    title, desc, score = f"FOMC Decision: Rate Impact", f"Federal Reserve rate decision on {event.get('date')}.", 85
                    strat_type = "Iron Condor" if event.get('actual') == event.get('forecast') else "Straddle"
                elif "non-farm payrolls" in event_name or "unemployment rate" in event_name:
                    title, desc, score, strat_type = f"NFP Report: Jobs Data Impact", f"Key employment data on {event.get('date')}.", 75, "Strangle"
                elif "gdp" in event_name:
                    title, desc, score, strat_type = f"GDP Release: Economic Outlook", f"Latest GDP figures on {event.get('date')}.", 65, "Long Call" # Simplified to one direction
                elif "retail sales" in event_name:
                    title, desc, score, strat_type = f"Retail Sales: Consumer Insight", f"Consumer spending data on {event.get('date')}.", 60, "Long Call" # Simplified to one direction
                else:
                    continue
                
                risk_level = "High" if strat_type in ["Straddle", "Strangle"] else "Moderate"
                ideas.append(Idea(symbol, title, desc, self.category, score, {"type": strat_type, "risk": risk_level}, m, risk=risk_level, event_ts=event_ts))
            return ideas if ideas else None
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
    
    
# ---. Fundamental Value/Growth detectors ---
class FundamentalValueDetector(DetectorBase):
    category = "💰 Value/Growth"

    def run(self, symbol: str, m: dict) -> List[Idea] | None:
        try: 
            # --- REPLACEMENT START ---
            ideas = []
            from core.models.providers import _to_float

            # ... (all the metric fetching code remains the same) ...
            current_pe = _to_float(m.get("current_pe"))
            historical_pe_avg = _to_float(m.get("historical_pe_avg"))
            peg_ratio = _to_float(m.get("peg_ratio"))
            earnings_growth = _to_float(m.get("earningsGrowth"))
            revenue_growth = _to_float(m.get("revenueGrowth"))
            analyst_target_mean = _to_float(m.get("analyst_target_mean_price"))
            current_price = _to_float(m.get("last_price"))
            price_to_book = _to_float(m.get("priceToBook"))
            profit_margins = _to_float(m.get("profitMargins"))
            gross_margins = _to_float(m.get("grossMargins"))
            return_on_equity = _to_float(m.get("returnOnEquity"))
            debt_to_equity = _to_float(m.get("debtToEquity"))

            existing_fundamental_idea_titles = set()

            def add_idea_if_unique(idea: Idea):
                if not any(idea.title.startswith(prefix) for prefix in existing_fundamental_idea_titles):
                    ideas.append(idea)
                    existing_fundamental_idea_titles.add(idea.title.split(":")[0])

            # Idea 1: Undervalued based on Historical P/E
            if current_pe is not None and historical_pe_avg is not None and current_pe > 0 and historical_pe_avg > 0:
                if current_pe < historical_pe_avg * 0.80:
                    title = f"Undervalued: P/E Below Historical Avg"
                    desc = f"Current P/E ({current_pe:.1f}) is below its historical average ({historical_pe_avg:.1f})."
                    add_idea_if_unique(Idea(symbol, title, desc, self.category, 80, {"type": "Bull Call", "risk": "Moderate"}, m, risk="Moderate", sparkline_data=m.get('price_sparkline')))
                elif current_pe > historical_pe_avg * 1.20:
                    title = f"Overvalued: P/E Above Historical Avg"
                    desc = f"Current P/E ({current_pe:.1f}) is above its historical average ({historical_pe_avg:.1f})."
                    add_idea_if_unique(Idea(symbol, title, desc, self.category, 30, {"type": "Bear Put", "risk": "Moderate"}, m, risk="Moderate", sparkline_data=m.get('price_sparkline')))

            # Idea 2: GARP
            if peg_ratio is not None and peg_ratio > 0 and peg_ratio <= 1.2 and (earnings_growth or revenue_growth):
                title = f"GARP Candidate: Growth at Reasonable Price"
                desc = f"PEG Ratio ({peg_ratio:.2f}) indicates good value relative to growth."
                add_idea_if_unique(Idea(symbol, title, desc, self.category, 85, {"type": "Long Call", "risk": "Low"}, m, risk="Low", sparkline_data=m.get('price_sparkline')))

            # Idea 3: Analyst Upside
            if analyst_target_mean is not None and current_price is not None and current_price > 0:
                upside_potential_pct = ((analyst_target_mean - current_price) / current_price) * 100
                if upside_potential_pct >= 15:
                    title = f"Analyst Upside: {upside_potential_pct:.0f}% to Target"
                    desc = f"Current price (${current_price:.2f}) is below avg. analyst target (${analyst_target_mean:.2f})."
                    add_idea_if_unique(Idea(symbol, title, desc, self.category, 70, {"type": "Long Call", "risk": "Moderate"}, m, risk="Moderate", sparkline_data=m.get('price_sparkline')))

            # Idea 4: Low Price-to-Book
            if price_to_book is not None and 0 < price_to_book < 1.5:
                title = f"Value: Low Price-to-Book ({price_to_book:.2f})"
                desc = "Stock trading at a low Price-to-Book ratio, suggesting potential undervaluation."
                add_idea_if_unique(Idea(symbol, title, desc, self.category, 65, {"type": "Covered Call", "risk": "Low"}, m, risk="Low", sparkline_data=m.get('price_sparkline')))

            # Idea 5: QARP
            if (current_pe and 0 < current_pe < 30 and profit_margins and profit_margins >= 0.15 and return_on_equity and return_on_equity >= 0.10):
                title = f"QARP Candidate: Quality & Value"
                desc = f"Strong margins (Profit: {profit_margins:.1%}) & ROE ({return_on_equity:.1%}) with a reasonable P/E ({current_pe:.1f})."
                add_idea_if_unique(Idea(symbol, title, desc, self.category, 90, {"type": "Long Call", "risk": "Low"}, m, risk="Low", sparkline_data=m.get('price_sparkline')))

            return ideas if ideas else None
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
    
class IVCrushDetector(DetectorBase):
    category = "📈 Volatility" # Use Volatility category, or create a new "IV Crush" category

    def run(self, symbol: str, m: dict) -> Idea | None:
        try: 
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
                        {"type": "Iron Condor", "risk": "High"}, # FIX: Simplified from "Short Strangle / Iron Condor"
                        m, risk="High", sparkline_data=m.get('IV_sparkline'), sparkline_type='iv')

            
            return None
        
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
    
class PostEarningsReactionDetector(DetectorBase):
    category = "🗓 Earnings" # Use Earnings category

    def run(self, symbol: str, m: dict) -> Idea | None:
        try: 
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

            if is_beat and significant_surprise and one_day_change is not None and one_day_change > 2:
                title, desc, score, suggested_type, risk_level = f"Earnings Beat: Post-Report Drift Up", f"Beat EPS ({surprise_pct:.1f}% surprise) and reacted strongly.", 88, "Bull Call", "Low"
            elif is_miss and significant_surprise and one_day_change is not None and one_day_change > 0 and one_day_change <= 2:
                title, desc, score, suggested_type, risk_level = f"Earnings Miss: Counter-Intuitive Bounce", f"Missed EPS ({surprise_pct:.1f}% surprise) but still bounced.", 70, "Bull Call", "High"
            elif is_miss and significant_surprise and one_day_change is not None and one_day_change < -2:
                title, desc, score, suggested_type, risk_level = f"Earnings Miss: Post-Report Drift Down", f"Missed EPS ({surprise_pct:.1f}% surprise) and reacted negatively.", 85, "Bear Put", "Low"
        

            if score > 0: # Only create idea if a condition was met
                return Idea(symbol, title, desc, self.category, score,
                            {"type": suggested_type, "risk": risk_level},
                            m, risk=risk_level, sparkline_data=m.get('price_sparkline'))
            
            return None
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
    
class ShortSqueezeDetector(DetectorBase):
    category = "🚀 Momentum" # Use Momentum category, or new "Special Situations"

    def run(self, symbol: str, m: dict) -> Idea | None:
        try:

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
                            {"type": "Long Call", "risk": "High"}, # FIX: Simplified from "Long Stock / Long Call"
                            m, risk="High", sparkline_data=m.get('price_sparkline'))
            
            return None
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None
    
# --- C. Crowd-powered detectors ---


class GoogleTrendsDetector(DetectorBase):
    category = "💬 Social"
    # In class GoogleTrendsDetector:
    def run(self, symbol: str, m: dict) -> Idea | None:
        try:

            # --- REPLACEMENT START ---
            trends = float(m.get("GoogleTrendScore", 0))
            if trends < 30: return None
            
            strat_type = "Straddle" # Changed from "Long Straddle / Strangle"
            risk_level = "High"
            title = f"High Search Interest: {trends:.0f}"
            desc = "Retail search traffic is spiking, which can precede a significant volatility event. Direction is uncertain."

            return Idea(symbol, title, desc, self.category, trends,
                        {"type": strat_type, "risk": risk_level},
                        m, risk=risk_level, sparkline_data=m.get('price_sparkline'))
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None

# --- D. Strategy-based setups ---
class PremiumCaptureDetector(DetectorBase):
    category = "🎯 Setups" # Confirm category label

    def run(self, symbol: str, m: dict) -> Idea | None:
        try:

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
                        {"type": "Iron Condor", "risk": "Moderate"}, # FIX: Simplified name
                        m, risk="Moderate", sparkline_data=m.get('IV_sparkline'), sparkline_type='iv')
        except Exception as e:
                # If ANY error occurs inside this specific detector, we log it
                # and return None, allowing the IdeaEngine to continue safely.
                print(f"[{symbol}] Error in {self.__class__.__name__}: {e}")
                return None

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

# In idea_engine.py

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
                # print(f"DEBUG: Full metrics for {sym} before detectors: {full}")
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