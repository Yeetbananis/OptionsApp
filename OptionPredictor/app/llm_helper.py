# --- REPLACEMENT START ---
from __future__ import annotations
import os
import re
import json
import traceback
from typing import Any, Dict

import google.generativeai as genai
from ui.TokenTracker import TokenUsageTracker

class LLMHelper:
    def __init__(self, token_tracker: TokenUsageTracker, model: str = "gemini-1.5-pro-latest"):
        self.model_name = model
        self.token_tracker = token_tracker
        self.api_key = "AIzaSyBdDbT1I_kfLQ_-I85E2qx2BvwyV2-PHqY"  #os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ConnectionError("GOOGLE_API_KEY environment variable not set. The AI features will be disabled.")
        genai.configure(api_key=self.api_key)
        self.model = genai.GenerativeModel(self.model_name)

    def _query_gemini(self, prompt: str) -> str:
        if self.token_tracker.is_limit_reached():
            usage = self.token_tracker.tokens_used
            limit = self.token_tracker.daily_limit
            raise PermissionError(f"Daily token limit reached ({usage:,}/{limit:,}). Please try again tomorrow.")
        try:
            response = self.model.generate_content(prompt.strip())
            self.token_tracker.update_usage(response)
            return response.text.strip()
        except Exception as e:
            print(f"Gemini API Error: {traceback.format_exc()}")
            raise ConnectionError(f"Failed to communicate with the Gemini API: {e}") from e

    def explain_option_strategy(self, **kwargs) -> str:
        prompt = self._build_explanation_prompt(**kwargs)
        return self._query_gemini(prompt)

    def recommend_strategy_structured(self, **kwargs) -> Dict[str, Any]:
        prompt = self._build_structured_prompt(**kwargs)
        raw_response = self._query_gemini(prompt)
        try:
            match = re.search(r'```json\s*([\s\S]+?)\s*```', raw_response)
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
            raise ValueError("No JSON block found in the LLM response.")
        except Exception as e:
            error_message = f"LLM response could not be parsed.\n\nError: {e}\n\n--- Raw Response ---\n{raw_response}"
            raise ValueError(error_message)

    def answer_query_with_context(self, user_query: str, context: str) -> str:
        prompt = (
            "You are a helpful AI financial assistant. Your goal is to answer the user's question. "
            "Use the following list of investment ideas as the primary context for your answer, but you can also use your general financial knowledge. "
            "Keep your answer concise and to the point.\n\n"
            "--- CONTEXT: CURRENT INVESTMENT IDEAS ---\n"
            f"{context}\n"
            "--- END CONTEXT ---\n\n"
            f"User Question: {user_query}\n\nAnswer:"
        )
        return self._query_gemini(prompt)

    # In class LLMHelper:

    def _build_explanation_prompt(self, **kwargs) -> str:
        # --- REPLACEMENT START ---
        """
        Return a professional, data-rich prompt that asks for a cohesive, actionable analysis
        and gracefully handles missing data.
        """
        def _f(val, fmt=".2f"):
            try:
                if val is None or not isinstance(val, (int, float)): return "N/A"
                return format(float(val), fmt)
            except (ValueError, TypeError):
                return "N/A"

        # This block now formats all data safely, returning 'N/A' for missing values.
        premium_line = f"• Net Premium: ${_f(kwargs.get('premium'))}\n"
        mc_prob_val = kwargs.get('prob')
        mc_prob_line = f"• Monte Carlo Probability of touching Barrier (H): {_f(mc_prob_val * 100, '.1f')}%\n" if mc_prob_val is not None else ""

        metrics = kwargs.get('metrics') or {}
        metrics_block = "\n".join([f"  • {k}: {v}" for k, v in metrics.items()]) or "  • (no extra metrics)"

        # Format Greeks safely
        greeks = kwargs.get('greek_inputs')
        greeks_str = ", ".join([f"{k.capitalize()}: {_f(v)}" for k, v in greeks.items()]) if isinstance(greeks, dict) else "N/A"

        prompt = (
            "You are a quantitative options analyst. Your task is to synthesize the user's inputs and the model's calculated outputs "
            "into a cohesive, data-driven analysis of the position. **Focus on the strategic implications of the data provided.**\n\n"
            "CRITICAL INSTRUCTION: Assume the provided data is for a valid, tradable instrument. **If a specific data point is missing or marked 'N/A', "
            "simply omit that part of the analysis without mentioning its absence.**\n\n"
            "--- DATA PROVIDED ---\n"
            "**User Inputs:**\n"
            f"• Ticker: {kwargs.get('ticker', 'N/A')}\n"
            f"• Strategy: {str(kwargs.get('option_type', 'N/A')).title()} @ ${_f(kwargs.get('strike'))}\n"
            f"• Premise: {kwargs.get('title', 'N/A')}\n"
            f"• Days to Expiry: {kwargs.get('T_days', 'N/A')}\n"
            f"• Implied Volatility (User's Assumption): {_f(kwargs.get('sigma', 0) * 100, '.1f')}%\n\n"
            "**Model Calculation Outputs:**\n"
            f"• Historical Realized Volatility: {_f(kwargs.get('realized_vol', 0) * 100, '.1f')}%\n"
            f"• Calculated Fair Value (Binomial): ${_f(kwargs.get('fair_price'))}\n"
            f"{mc_prob_line}"
            f"• Greeks: {greeks_str}\n"
            "--- END OF DATA ---\n\n"
            "Please provide your analysis in the following structure:\n"
            "1.  **Volatility Analysis:** Compare the Implied vs. Realized Volatility. Is the option theoretically cheap or expensive based on this? How does this affect the trade's outlook?\n"
            "2.  **Probability & Risk/Reward:** Using the Fair Value, state the break-even price at expiration. Then, comment on the Monte Carlo Probability. What does this percentage imply about the trade's likelihood of success?\n"
            "3.  **Position Dynamics (Greeks):** Briefly interpret the provided Greeks. What do the Delta, Theta, and Vega values reveal about the primary risks and sensitivities of this position?\n"
            "4.  **Synthesis & Key Factors:** Synthesize the points above into a concluding thought. What is the most critical factor for this trade's success and what should the trader monitor closely?"
        )
        return prompt
     

    def _build_structured_prompt(self, **kwargs) -> str:
        """Builds a more explicit structured prompt for the LLM."""
        ticker = str(kwargs.get('ticker', 'N/A')).upper()
        spot_price = kwargs.get('spot') or kwargs.get('current_price', 100)
        direction = str(kwargs.get('direction', 'Neutral'))
        target = kwargs.get('target') or kwargs.get('target_price', spot_price)
        dte = kwargs.get('dte', 30)
        iv = kwargs.get('iv', 25.0) / 100.0
        risk = str(kwargs.get('risk_tolerance', 'Medium'))

        return (
            "You are an options strategy recommender. Your task is to return a single, perfectly formatted JSON object "
            "representing the most appropriate options strategy based on the user's inputs. "
            "The JSON response should be enclosed in a markdown code block like ```json ... ```.\n\n"
            "The JSON schema MUST be:\n"
            "{'legs':[{'action':'Buy'|'Sell','type':'Call'|'Put','strike':float,'quantity':int,'premium':float}],'note':string}\n\n"
            "CRITICAL: You must calculate a realistic 'premium' for each leg of the strategy. "
            "Base the premium on the provided implied volatility (IV), days to expiration (DTE), and the distance of the strike from the spot price.\n\n"
            "--- User Inputs ---\n"
            f"Ticker: {ticker}\n"
            f"Spot Price: {spot_price:.2f}\n"
            f"Directional View: {direction}\n"
            f"Target Price: {target:.2f}\n"
            f"Days to Expiration (DTE): {dte}\n"
            f"Implied Volatility (IV): {iv*100:.1f}%\n"
            f"Risk Tolerance: {risk}\n"
            "--- End Inputs ---\n\n"
            "Now, provide the JSON response for the best strategy."
        )


    def explain_idea_card(self, **kwargs) -> str:
        """
        Generates a qualitative, strategic analysis for an Idea Card.
        """
        prompt = self._build_idea_card_prompt(**kwargs)
        return self._query_gemini(prompt)

    def _build_idea_card_prompt(self, **kwargs) -> str:
        """
        Builds a prompt that asks for a strategic review of a trading idea,
        focusing on the concept rather than just the numbers.
        """
        prompt = (
            "You are a seasoned trading strategist and mentor. Your task is to provide concise, strategic commentary "
            "on the trading idea below. Focus on the **concept** and the **chosen strategy's fit for the premise.** "
            "Assume the metrics provided are context, but your analysis should be qualitative.\n\n"
            "--- Trading Idea Details ---\n"
            f"• Ticker: {kwargs.get('ticker', 'N/A')}\n"
            f"• Idea Premise: \"{kwargs.get('title', 'N/A')}\"\n"
            f"• Signal Category: {kwargs.get('category', 'N/A')}\n"
            f"• Suggested Strategy: {kwargs.get('strategy_name', 'N/A')}\n"
            f"• Key Metrics: DTE: {kwargs.get('dte', 'N/A')}, Risk: {kwargs.get('risk', 'N/A')}\n"
            "--- End of Details ---\n\n"
            "Please provide your commentary in the following structure:\n"
            "1.  **Strategic Rationale:** Why is the suggested strategy a good or bad fit for the premise? What is the core logic behind this pairing?\n"
            "2.  **Key Considerations:** What are the most important things a trader should think about before placing this trade (e.g., timing, volatility, market conditions)?\n"
            "3.  **Alternative Strategy:** Briefly suggest one alternative strategy that could also trade this premise and explain its primary trade-off."
        )
        return prompt