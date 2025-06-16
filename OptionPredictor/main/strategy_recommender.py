# strategy_recommender.py

import math
try:
    # local, sibling module import
    from MonteCarloSimulation import cached_binomial_price
except ImportError:
        try:
            # if using package structure
            from .MonteCarloSimulation import cached_binomial_price
        except ImportError:
            print("Warning: Could not import cached_binomial_price. Profit potential scoring will be limited.")
            def cached_binomial_price(*args, **kwargs):
                return 0.0

class StrategyRecommender:
    """
    Analyzes market view inputs, scores potential option strategies based on
    heuristics (including profit potential estimates & predicted vol change)
    and user preferences, and recommends a ranked list.
    """
    # STRATEGIES Dictionary remains the same as before...
    STRATEGIES = {
        #                               Direction                  Vol View         Risk                     Reward      Complexity   WidthFactor
        "Long Call":        {"direction": "Bullish",              "vol_view": "Increase",    "risk": "Defined",             "reward": "Unlimited", "complexity": 1, "WidthFactor": 0},
        "Long Put":         {"direction": "Bearish",              "vol_view": "Increase",    "risk": "Defined",             "reward": "Large",     "complexity": 1, "WidthFactor": 0},
        "Covered Call":     {"direction": "Neutral/Mod Bullish",  "vol_view": "Decrease/Flat","risk": "Reduced Stock Risk",  "reward": "Limited",   "complexity": 2, "WidthFactor": 0.05, "requires_stock": True}, # Typical OTM %
        "Protective Put":   {"direction": "Any (Insurance)",      "vol_view": "Increase",    "risk": "Limited Stock Risk",  "reward": "Stock Upside","complexity": 2, "WidthFactor": 0.05, "requires_stock": True}, # Typical OTM %
        "Bull Call Spread": {"direction": "Bullish",              "vol_view": "Any/Decrease","risk": "Defined",             "reward": "Defined",   "complexity": 3, "WidthFactor": 0.05}, # e.g., 5 points on 100
        "Bear Put Spread":  {"direction": "Bearish",              "vol_view": "Any/Decrease","risk": "Defined",             "reward": "Defined",   "complexity": 3, "WidthFactor": 0.05},
        "Iron Condor":      {"direction": "Neutral (low move)",   "vol_view": "Decrease/Flat","risk": "Defined",             "reward": "Defined",   "complexity": 4, "WidthFactor": 0.05}, # Width of each spread
        "Straddle":         {"direction": "Neutral (large move)", "vol_view": "Increase",    "risk": "Defined",             "reward": "Unlimited", "complexity": 3, "WidthFactor": 0}, # Uses ATM
        "Strangle":         {"direction": "Neutral (large move)", "vol_view": "Increase",    "risk": "Defined",             "reward": "Unlimited", "complexity": 3, "WidthFactor": 0.05}, # Distance from ATM
        "Butterfly Spread": {"direction": "Neutral (low move)",   "vol_view": "Decrease/Flat","risk": "Defined",             "reward": "Defined",   "complexity": 4, "WidthFactor": 0.05}, # Wing width
        "Calendar Spread":  {"direction": "Neutral/Directional",  "vol_view": "Any/Shift/Incr","risk": "Defined",             "reward": "Defined",   "complexity": 5, "WidthFactor": 0},  # Uses same strike
        "Diagonal Spread":  {"direction": "Neutral/Directional",  "vol_view": "Shift/Incr",     "risk": "Defined",              "reward": "Defined",   "complexity": 5, "WidthFactor": 0},
        "Ratio Spread":     {"direction": "Directional",          "vol_view": "Decrease/Flat",  "risk": "Undefined",           "reward": "Unlimited", "complexity": 4, "WidthFactor": 0.05},
        "Backspread":       {"direction": "Directional",          "vol_view": "Increase",        "risk": "Undefined",           "reward": "Unlimited", "complexity": 4, "WidthFactor": 0.05},
        "Jade Lizard":      {"direction": "Mod Bullish",          "vol_view": "Flat/Decrease",  "risk": "Defined",              "reward": "Defined",   "complexity": 4, "WidthFactor": 0.05},
        "Iron Butterfly":   {"direction": "Neutral (pinning)",    "vol_view": "Flat/Decrease",  "risk": "Defined",              "reward": "Defined",   "complexity": 4, "WidthFactor": 0.05},
        "Broken Wing Butterfly": {"direction": "Neutral/Bullish", "vol_view": "Flat/Decrease",  "risk": "Defined",              "reward": "Defined",   "complexity": 5, "WidthFactor": 0.05}
    }
    # STRATEGY_DESCRIPTIONS Dictionary remains the same as before...
    STRATEGY_DESCRIPTIONS = {
        "Long Call": "Simple bullish bet. Profits if the stock price rises significantly above the strike price before expiration. Max loss is the premium paid.",
        "Long Put": "Simple bearish bet. Profits if the stock price falls significantly below the strike price before expiration. Max loss is the premium paid.",
        "Covered Call": "Generates income by selling a call against stock you own. Profits if the stock stays below the strike. Limits upside potential of the stock.",
        "Protective Put": "Acts like insurance for stock you own. Buy a put to protect against a large drop in price. Reduces potential profit by the cost of the put.",
        "Bull Call Spread": "Defined risk/reward bullish strategy. Buy a lower strike call, sell a higher strike call. Profits if the stock rises moderately.",
        "Bear Put Spread": "Defined risk/reward bearish strategy. Buy a higher strike put, sell a lower strike put. Profits if the stock falls moderately.",
        "Iron Condor": "Neutral strategy profiting from low volatility. Sell an OTM put spread and an OTM call spread. Max profit is the net credit received if the price stays between the short strikes.",
        "Straddle": "Neutral strategy profiting from a large price move in either direction. Buy a call and a put at the same strike. Requires a significant move to overcome the high premium cost.",
        "Strangle": "Similar to Straddle but uses OTM options (cheaper premium). Buy an OTM call and an OTM put. Requires an even larger price move than a straddle to be profitable.",
        "Butterfly Spread": "Neutral strategy profiting if the price pins the middle strike at expiration. Limited risk and reward. Often used for low volatility bets on a specific price point.",
        "Calendar Spread": "Profits from time decay differences and volatility changes. Sell a near-term option and buy a longer-term option at the same strike. Complex payoff, often neutral to mildly directional.",
        "Diagonal Spread": "Combines elements of vertical and calendar spreads. Buy a long-term option and sell a short-term option at a different strike. Useful for directional bets with a time component.",
        "Ratio Spread": "Sell more options than you buy, often directional with undefined risk. Gains if movement is moderate. Risk if movement is too large in one direction.",
        "Backspread": "Buy more options than you sell, usually for high-volatility bets. Profits from strong movement in one direction, with limited loss if flat.",
        "Jade Lizard": "Short call spread plus short put. Net credit, no upside risk. Profits from neutral to moderately bullish outlook.",
        "Iron Butterfly": "Sell ATM straddle and buy wings. Profits if price pins near the short strike. Narrower range than iron condor but higher payout.",
        "Broken Wing Butterfly": "Like a butterfly but with one wing wider. Allows for a directional bias and a potential no-loss setup if done for credit."
    }
    # Thresholds remain the same...
    HIGH_IV_THRESHOLD = 0.50
    LOW_IV_THRESHOLD = 0.20
    VERY_LARGE_MOVE_PCT = 30.0
    LARGE_MOVE_PCT = 10.0
    SMALL_MOVE_PCT = 2.5
    SHORT_DTE_THRESHOLD = 15
    REASONABLE_CONFIDENCE = 60
    # ---> NEW: Threshold for significant predicted vol change <---
    VOL_CHANGE_THRESHOLD = 0.03 # e.g., a 3% absolute change in IV (0.20 -> 0.23)

    # Fallback Table remains the same...
    FALLBACK_TABLE = {
        ("Bullish", True): "Bull Call Spread",
        ("Bullish", False): "Long Call",
        ("Bearish", True): "Bear Put Spread",
        ("Bearish", False): "Long Put",
        ("Neutral", True): "Iron Condor",
        ("Neutral", False): "Strangle"
    }

    def __init__(self, inputs):
        """ Initializes the recommender with user inputs and assesses volatility levels and predicted change."""
        self.inputs = inputs
        self.inputs['S0_rounded'] = round(inputs['current_price'] / 5.0) * 5.0
        self.inputs['T_years'] = inputs['dte'] / 365.0

        self.candidate_strategies = [
            s for s, d in self.STRATEGIES.items() if not d.get("requires_stock", False)
        ]
        self._assess_volatility_level()       # Assess current IV level
        self._assess_volatility_prediction()  # Assess predicted IV change

    def _assess_volatility_level(self):
        """Sets self.vol_level based on CURRENT input IV."""
        # Renamed from _assess_volatility to be clear it's about the level
        iv = self.inputs['iv']
        if iv > self.HIGH_IV_THRESHOLD:
             self.vol_level = "High"
        elif iv < self.LOW_IV_THRESHOLD:
             self.vol_level = "Low"
        else:
             self.vol_level = "Moderate"

    def _assess_volatility_prediction(self):
        """Sets self.vol_change_expectation based on predicted vs current IV."""
        current_iv = self.inputs['iv']
        predicted_iv = self.inputs['predicted_iv']
        diff = predicted_iv - current_iv

        if diff > self.VOL_CHANGE_THRESHOLD:
            self.vol_change_expectation = "Increase"
        elif diff < -self.VOL_CHANGE_THRESHOLD:
            self.vol_change_expectation = "Decrease"
        else:
            self.vol_change_expectation = "Flat"

    def recommend_top_strategies(self, n=3):
        """ Calculates scores for all candidate strategies and returns the top N. """
        # High Confidence Shortcut Logic remains the same...
        move_pct = self.inputs['move_percent']
        confidence = self.inputs['confidence']
        direction = self.inputs['direction']

        is_shortcut = False
        shortcut_strat = None
        if abs(move_pct) > 15 and confidence > 80:
             if direction == "Bullish" and "Long Call" in self.candidate_strategies:
                 shortcut_strat = "Long Call"
                 is_shortcut = True
             elif direction == "Bearish" and "Long Put" in self.candidate_strategies:
                 shortcut_strat = "Long Put"
                 is_shortcut = True

        scored_strategies = []
        if is_shortcut:
             score, notes, desc = self.calculate_score(shortcut_strat, self.inputs)
             scored_strategies.append((score + 50, shortcut_strat, notes + " [High Confidence Shortcut]", desc))
        else:
            # Regular scoring
            for strategy_name in self.candidate_strategies:
                score, justification_notes, description = self.calculate_score(strategy_name, self.inputs)
                if score > -math.inf:
                     scored_strategies.append((score, strategy_name, justification_notes, description))

        # Sort and Fallback Logic remains the same...
        scored_strategies.sort(key=lambda x: x[0], reverse=True)

        if not scored_strategies:
            prefer_defined_risk = self.inputs['prefer_defined_risk']
            fallback_key = (direction, prefer_defined_risk)
            fallback_name = self.FALLBACK_TABLE.get(fallback_key)
            if fallback_name and fallback_name in self.STRATEGIES:
                 score, notes, desc = self.calculate_score(fallback_name, self.inputs)
                 notes += " [Fallback Recommendation]"
                 scored_strategies.append((score, fallback_name, notes, desc))
            else:
                 return [(0, "No Suitable Strategy", "Could not identify a suitable standard strategy based on inputs.", "")]

        return scored_strategies[:n]


    def _estimate_profit_potential(self, strategy_name, inputs):
        """ Crude estimation of profit potential vs risk using binomial pricing """
        # This method remains the same as before
        try:
            details = self.STRATEGIES[strategy_name]
            S0 = inputs['current_price']
            target = inputs['target_price']
            T_years = inputs['T_years']
            r = inputs.get('r', 0.04) # Use default rate if not provided elsewhere
            sigma = inputs['iv'] # Use CURRENT IV for pricing estimate
            width_factor = details.get('WidthFactor', 0.05)
            atm_strike = inputs['S0_rounded']

            potential_profit = 0
            estimated_risk = 1

            price_func = cached_binomial_price

            if strategy_name == "Long Call":
                strike = atm_strike + (5 if S0 > 50 else 1)
                if target > strike * 1.2: strike = atm_strike
                premium = price_func(S0, strike, T_years, r, sigma, N=100, option_type='call', american=False)
                if premium > 0:
                    payoff_at_target = max(0, target - strike)
                    potential_profit = payoff_at_target - premium
                    estimated_risk = premium

            elif strategy_name == "Long Put":
                strike = atm_strike - (5 if S0 > 50 else 1)
                if target < strike * 0.8: strike = atm_strike
                premium = price_func(S0, strike, T_years, r, sigma, N=100, option_type='put', american=False)
                if premium > 0:
                    payoff_at_target = max(0, strike - target)
                    potential_profit = payoff_at_target - premium
                    estimated_risk = premium

            elif strategy_name == "Bull Call Spread":
                long_strike = atm_strike
                spread_width = max(5, round(S0 * width_factor / 5) * 5)
                short_strike = long_strike + spread_width
                long_prem = price_func(S0, long_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                short_prem = price_func(S0, short_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                net_debit = long_prem - short_prem
                if net_debit > 0:
                    max_profit = spread_width - net_debit
                    payoff_at_target = min(max(0, target - long_strike), spread_width)
                    potential_profit = min(max_profit, payoff_at_target - net_debit if target > long_strike else -net_debit)
                    estimated_risk = net_debit

            elif strategy_name == "Bear Put Spread":
                long_strike = atm_strike
                spread_width = max(5, round(S0 * width_factor / 5) * 5)
                short_strike = long_strike - spread_width
                long_prem = price_func(S0, long_strike, T_years, r, sigma, N=100, option_type='put', american=False)
                short_prem = price_func(S0, short_strike, T_years, r, sigma, N=100, option_type='put', american=False)
                net_debit = long_prem - short_prem
                if net_debit > 0:
                    max_profit = spread_width - net_debit
                    payoff_at_target = min(max(0, long_strike - target), spread_width)
                    potential_profit = min(max_profit, payoff_at_target - net_debit if target < long_strike else -net_debit)
                    estimated_risk = net_debit

            elif strategy_name == "Diagonal Spread":
                long_strike = atm_strike
                short_strike = atm_strike + (5 if S0 > 50 else 1)
                long_prem = price_func(S0, long_strike, T_years * 2, r, sigma, N=100, option_type='call', american=False)
                short_prem = price_func(S0, short_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                net_debit = long_prem - short_prem
                if net_debit > 0:
                    payoff_at_target = max(0, target - long_strike)
                    potential_profit = payoff_at_target - net_debit
                    estimated_risk = net_debit

            elif strategy_name == "Ratio Spread":
                long_strike = atm_strike
                short_strike = atm_strike + (5 if S0 > 50 else 1)
                long_prem = price_func(S0, long_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                short_prem = price_func(S0, short_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                net_credit = 2 * short_prem - long_prem
                if net_credit > 0:
                    potential_profit = net_credit
                    estimated_risk = max(1, S0 * 0.05)  # crude assumption

            elif strategy_name == "Backspread":
                short_strike = atm_strike
                long_strike = atm_strike + (5 if S0 > 50 else 1)
                short_prem = price_func(S0, short_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                long_prem = price_func(S0, long_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                net_debit = 2 * long_prem - short_prem
                if net_debit > 0:
                    payoff = max(0, target - long_strike) * 2 - max(0, target - short_strike)
                    potential_profit = payoff - net_debit
                    estimated_risk = net_debit

            elif strategy_name == "Jade Lizard":
                short_put_strike = atm_strike - (5 if S0 > 50 else 1)
                short_call_strike = atm_strike + (5 if S0 > 50 else 1)
                long_call_strike = short_call_strike + (5 if S0 > 50 else 1)
                short_put = price_func(S0, short_put_strike, T_years, r, sigma, N=100, option_type='put', american=False)
                short_call = price_func(S0, short_call_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                long_call = price_func(S0, long_call_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                net_credit = short_put + short_call - long_call
                if net_credit > 0:
                    potential_profit = net_credit
                    estimated_risk = S0 - short_put_strike - net_credit  # crude

            elif strategy_name == "Iron Butterfly":
                short_strike = atm_strike
                wing_width = max(5, round(S0 * width_factor / 5) * 5)
                long_put_strike = short_strike - wing_width
                long_call_strike = short_strike + wing_width
                short_put = price_func(S0, short_strike, T_years, r, sigma, N=100, option_type='put', american=False)
                short_call = price_func(S0, short_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                long_put = price_func(S0, long_put_strike, T_years, r, sigma, N=100, option_type='put', american=False)
                long_call = price_func(S0, long_call_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                net_credit = short_put + short_call - long_put - long_call
                if net_credit > 0:
                    potential_profit = net_credit
                    estimated_risk = wing_width - net_credit

            elif strategy_name == "Broken Wing Butterfly":
                # Similar to Iron Butterfly but one wing is wider
                center_strike = atm_strike
                lower_strike = center_strike - (5 if S0 > 50 else 1)
                upper_strike = center_strike + 2 * (5 if S0 > 50 else 1)
                long_put = price_func(S0, lower_strike, T_years, r, sigma, N=100, option_type='put', american=False)
                short_put = price_func(S0, center_strike, T_years, r, sigma, N=100, option_type='put', american=False)
                long_call = price_func(S0, upper_strike, T_years, r, sigma, N=100, option_type='call', american=False)
                net_debit = long_put + long_call - short_put
                if net_debit > 0:
                    potential_profit = max(0, center_strike - S0) - net_debit  # approximate
                    estimated_risk = net_debit


            if estimated_risk > 0:
                profit_risk_ratio = potential_profit / estimated_risk
                profit_score = min(max(profit_risk_ratio * 20, -30), 50)
                return profit_score, potential_profit, estimated_risk
            else:
                return 0, 0, 0

        except Exception as e:
            # print(f"Warning: Could not estimate profit potential for {strategy_name}: {e}")
            return 0, 0, 0


    def calculate_score(self, strategy_name, inputs):
        """ Calculates a heuristic score including predicted vol change and profit potential. """
        score = 0
        justification = []
        details = self.STRATEGIES[strategy_name]
        strat_dir_info = details["direction"]
        strat_vol_view = details["vol_view"] # How the strategy *reacts* to vol
        strat_risk = details["risk"]
        is_defined_risk_strat = strat_risk.startswith("Defined")
        reward_type = details["reward"]

        user_dir = inputs["direction"]
        move_pct_abs = abs(inputs["move_percent"])
        confidence = inputs["confidence"]
        dte = inputs["dte"]
        defined_risk_pref = inputs["prefer_defined_risk"]

        # 1. Direction Match - Score remains same
        dir_score = -math.inf
        if user_dir in strat_dir_info or "Any" in strat_dir_info:
            dir_score = 50; justification.append(f"✅ Aligns with {user_dir} view.")
        elif (user_dir == "Bullish" and "Mod Bullish" in strat_dir_info) or \
             (user_dir == "Bearish" and "Mod Bearish" in strat_dir_info) or \
             (user_dir == "Neutral" and ("Mod Bullish" in strat_dir_info or "Mod Bearish" in strat_dir_info)):
            dir_score = 15; justification.append(f"~ Partially aligns with {user_dir} view.")
        else:
            justification.append(f"❌ Direction Mismatch ({strat_dir_info}).")
            return -math.inf, " ".join(justification), self.STRATEGY_DESCRIPTIONS.get(strategy_name, "")
        score += dir_score


        # 2. ---> MODIFIED: Volatility PREDICTION Match <---
        #    Compare strategy's desired vol environment ('vol_view')
        #    with the user's prediction ('self.vol_change_expectation').
        vol_score = 0
        if self.vol_change_expectation == "Increase":
            if "Increase" in strat_vol_view: # Long vol strategies
                vol_score = 25; justification.append(f"✅ Benefits from predicted Vol Increase.")
            elif "Decrease" in strat_vol_view or "Flat" in strat_vol_view: # Short vol strategies
                vol_score = -20; justification.append(f"❌ Hurt by predicted Vol Increase.")
            else: # Strategies flexible on vol ("Any", "Shift")
                vol_score = 5; justification.append(f"~ Flexible on Vol change.")
        elif self.vol_change_expectation == "Decrease":
            if "Decrease" in strat_vol_view or "Flat" in strat_vol_view: # Short vol strategies
                vol_score = 25; justification.append(f"✅ Benefits from predicted Vol Decrease.")
            elif "Increase" in strat_vol_view: # Long vol strategies
                vol_score = -20; justification.append(f"❌ Hurt by predicted Vol Decrease.")
            else: # Flexible strategies
                vol_score = 5; justification.append(f"~ Flexible on Vol change.")
        else: # Vol Flat prediction
            if "Flat" in strat_vol_view or "Decrease" in strat_vol_view: # Theta decay strategies
                 vol_score = 15; justification.append(f"✅ Benefits from predicted Flat Vol (Theta).")
            elif "Increase" in strat_vol_view: # Needs vol expansion
                 vol_score = -10; justification.append(f"⚠️ Predicted Flat Vol may hinder this strategy.")
            else: # Flexible
                 vol_score = 5; justification.append(f"~ Flexible on Vol change.")
        score += vol_score


        # 3. Risk Profile Preference - Score remains same
        risk_penalty = 0
        if defined_risk_pref:
            if is_defined_risk_strat:
                score += 20; justification.append("✅ Matches defined risk preference.")
            else:
                if move_pct_abs > self.VERY_LARGE_MOVE_PCT and confidence > self.REASONABLE_CONFIDENCE:
                     risk_penalty = -10; justification.append("~ Undefined risk ok given large move/confidence.")
                else:
                     risk_penalty = -25; justification.append("❌ Risk profile mismatch (Strategy risk undefined).")
        else:
             if not is_defined_risk_strat:
                 score += 10; justification.append("✅ Matches undefined risk preference.")
        score += risk_penalty

        # 4. Move Size Suitability - Score remains same
        move_score = 0
        if move_pct_abs > self.VERY_LARGE_MOVE_PCT and reward_type in ["Unlimited", "Large"]:
             move_score += 35; justification.append(f"✅ Exploits very large move ({inputs['move_percent']:.0f}%) potential.")
        elif "large move" in strat_dir_info and move_pct_abs < self.LARGE_MOVE_PCT:
            move_score -= 20; justification.append(f"⚠️ Expected move ({inputs['move_percent']:.1f}%) may be too small for '{strategy_name}'.")
        elif "low move" in strat_dir_info and move_pct_abs > self.SMALL_MOVE_PCT:
            move_score -= 20; justification.append(f"⚠️ Expected move ({inputs['move_percent']:.1f}%) may be too large for '{strategy_name}'.")
        elif move_pct_abs >= self.LARGE_MOVE_PCT and reward_type not in ["Unlimited", "Large"]:
             move_score -= 10; justification.append(f"~ Move ({inputs['move_percent']:.1f}%) may exceed strategy's max profit potential.")
        elif move_pct_abs <= self.SMALL_MOVE_PCT and strategy_name in ["Iron Condor", "Covered Call", "Butterfly Spread"]:
             move_score += 15
        score += move_score

        # 5. Confidence Adjustment - Score remains same
        if confidence < 60 and not is_defined_risk_strat and user_dir != "Neutral":
             score -= 30; justification.append(f"⚠️ Low confidence ({confidence}%) makes undefined risk strategy less suitable.")

        # 6. DTE Considerations - Score remains same
        dte_score = 0
        if dte < self.SHORT_DTE_THRESHOLD:
            if strategy_name in ["Long Call", "Long Put", "Straddle", "Strangle"]:
                dte_score -= 15; justification.append(f"⚠️ Short DTE ({dte} days) increases theta decay risk.")
            elif strategy_name in ["Iron Condor", "Butterfly Spread", "Covered Call"]:
                dte_score += 10; justification.append(f"~ Short DTE ({dte} days) can accelerate theta profit.")
        score += dte_score

        # 7. ---> MODIFIED: IV LEVEL Considerations (Now separate from vol change prediction) <---
        # This score/warning is purely about the current cost of premium based on IV level.
        iv_level_score = 0
        long_premium_strats = ["Long Call", "Long Put", "Straddle", "Strangle", "Protective Put", "Calendar Spread"]
        short_premium_strats = ["Covered Call", "Iron Condor", "Butterfly Spread", "Bull Call Spread", "Bear Put Spread"]
        if self.vol_level == "High":
            if strategy_name in long_premium_strats:
                iv_level_score -= 10; justification.append(f"ℹ️ Note: High Current IV ({inputs['iv_percent']:.1f}%) makes premium expensive.")
            elif strategy_name in short_premium_strats:
                 iv_level_score += 10; justification.append(f"ℹ️ Note: High Current IV ({inputs['iv_percent']:.1f}%) good for selling premium.")
        elif self.vol_level == "Low":
            if strategy_name in short_premium_strats:
                iv_level_score -= 10; justification.append(f"ℹ️ Note: Low Current IV ({inputs['iv_percent']:.1f}%) offers less premium for selling.")
            elif strategy_name in long_premium_strats:
                 iv_level_score += 10; justification.append(f"ℹ️ Note: Low Current IV ({inputs['iv_percent']:.1f}%) makes premium cheaper.")
        score += iv_level_score


        # 8. Profit Potential Score - Calculation remains same, score added
        profit_score, potential_profit, estimated_risk = self._estimate_profit_potential(strategy_name, inputs)
        if potential_profit != 0 or estimated_risk != 0:
            justification.append(f"~ Est. Profit/Risk: {potential_profit:.2f} / {estimated_risk:.2f}")
        score += profit_score


        # Get educational description
        description = self.STRATEGY_DESCRIPTIONS.get(strategy_name, "No description available.")

        final_score = max(score, -1000) # Floor score

        return final_score, " ".join(justification), description