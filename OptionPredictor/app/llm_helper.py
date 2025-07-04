from __future__ import annotations
import json, re, requests
from typing import Any, Dict, List
try:
    import demjson3
except ImportError:
    demjson3 = None # Fallback if library is not installed

class LLMHelper:
    def __init__(self, model: str = "llama3", temperature: float = 0.7):
        self.api_url = "http://localhost:11434/api/generate"
        self.model = model
        self.temperature = temperature

    def explain_option_strategy(self, **kwargs) -> str:
        prompt = self._build_explanation_prompt(**kwargs)
        return self._query_llm(prompt)

    def recommend_strategy_structured(self, **kwargs) -> Dict[str, Any]:
        """
        Queries the LLM and uses robust REGEX EXTRACTION to build the
        strategy object, making it immune to most JSON syntax errors.
        """
        prompt = self._build_structured_prompt(**kwargs)
        raw_response = self._query_llm(prompt)

        try:
            # **FOOLPROOF FIX**: Use regex to find all data points individually
            actions = re.findall(r'"action"\s*:\s*"(Buy|Sell)"', raw_response, re.IGNORECASE)
            types = re.findall(r'"type"\s*:\s*"(Call|Put)"', raw_response, re.IGNORECASE)
            strikes = [float(f) for f in re.findall(r'"strike"\s*:\s*([\d.]+)', raw_response)]
            quantities = [int(i) for i in re.findall(r'"quantity"\s*:\s*(\d+)', raw_response)]
            premiums = [float(f) for f in re.findall(r'"premium"\s*:\s*([\d.]+)', raw_response)]
            
            note_match = re.search(r'"note"\s*:\s*"(.*?)"', raw_response, re.DOTALL)
            note = note_match.group(1) if note_match else "No rationale provided."

            # Verify that we found a consistent number of parts for each leg
            num_legs = len(actions)
            if not (num_legs == len(types) == len(strikes) == len(quantities) == len(premiums)):
                raise ValueError("Inconsistent number of leg components found in LLM response.")
            
            if num_legs == 0:
                raise ValueError("No valid legs were found in the LLM response.")

            # Reconstruct the legs list
            legs = []
            for i in range(num_legs):
                legs.append({
                    "action": actions[i].capitalize(),
                    "type": types[i].capitalize(),
                    "strike": strikes[i],
                    "quantity": quantities[i],
                    "premium": premiums[i]
                })

            return {"legs": legs, "note": note}

        except Exception as e:
            # If regex extraction fails, the format is truly unreadable
            error_message = (
                f"LLM response could not be parsed even with robust extraction.\n\n"
                f"Error: {e}\n\n"
                f"--- Raw Response ---\n{raw_response}\n"
                f"--------------------"
            )
            raise ValueError(error_message)
        
    def answer_query_with_context(self, user_query: str, context: str) -> str:
        prompt = (
            "You are an AI financial assistant. Answer the user's question "
            "using ONLY the information in the context below. "
            "If the answer is not in the context, reply: 'Information not found in current ideas.'\n\n"
            f"--- CONTEXT START ---\n{context}\n--- CONTEXT END ---\n\n"
            f"Question: {user_query}\nAnswer:"
        )
        return self._query_llm(prompt)

    def _query_llm(self, prompt: str) -> str:
        payload = {"model": self.model, "prompt": prompt.strip(), "stream": False}
        try:
            r = requests.post(self.api_url, json=payload, timeout=60)
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(f"Cannot reach LLM service at {self.api_url}. Is Ollama running?") from exc

    def _build_explanation_prompt(self, **kwargs) -> str:
        """Return a professional, data-rich prompt for the LLM."""
        def _f(val, fmt=".2f"):
            try: return format(float(val), fmt)
            except: return str(val)
        def _pct(val):
            try: return f"{float(val) * 100:.1f}%"
            except: return str(val)

        # **FOOLPROOF FIX**: Intelligently find the premium from different possible data structures.
        premium = kwargs.get('premium')
        if not isinstance(premium, (int, float)):
            # If not found directly, check inside the 'metrics' dictionary
            metrics = kwargs.get('metrics')
            if isinstance(metrics, dict):
                premium = metrics.get('premium')

        premium_line = f"• Premium: ${_f(premium)}\n" if isinstance(premium, (int, float)) else ""

        metrics_block = "\n".join([f"• {k}: {v}" for k, v in (kwargs.get('metrics') or {}).items()]) or "• (no extra metrics)"

        prompt = (
            "You are a seasoned options strategist. Provide a clear, data-driven "
            "explanation of the suggested trade. Structure your answer with "
            "these sections: 1. Thesis, 2. Risk/Reward, 3. Key Greeks, "
            "4. Probability, 5. Takeaway.\n\n"
            "Trade details:\n"
            f"• Ticker: {kwargs.get('ticker', 'N/A')}\n"
            f"• Option Type: {kwargs.get('option_type', 'N/A')}\n"
            f"• Strike: ${_f(kwargs.get('strike', 'N/A'))}\n"
            f"• Spot Price: ${_f(kwargs.get('S0', 'N/A'))}\n"
            f"{premium_line}"
            f"• Days to Expiry: {kwargs.get('T_days', 'N/A')}\n"
            f"• Barrier-hit Probability: {_pct(kwargs.get('prob', 'N/A'))}\n\n"
            f"Additional Metrics:\n{metrics_block}\n\n"
            "Respond in crisp, professional language. Avoid filler."
        )
        return prompt

    def _build_structured_prompt(self, **kwargs) -> str:
        """
        Builds a more explicit structured prompt for the LLM, demanding
        perfect JSON syntax and providing a multi-leg example.
        """
        def _num(x):
            try: return f"{float(x):.2f}"
            except (ValueError, TypeError): return "N/A"

        ticker = str(kwargs.get('ticker', 'N/A')).upper()
        spot_price = kwargs.get('spot') or kwargs.get('current_price')
        # ... (rest of variable extraction is the same)
        direction = str(kwargs.get('direction', 'Neutral'))
        target = kwargs.get('target') or kwargs.get('target_price')
        dte = kwargs.get('dte', 30)
        iv = kwargs.get('iv', 25.0) / 100.0
        risk = str(kwargs.get('risk_tolerance', 'Medium'))
        preference = str(kwargs.get('preference', 'Growth'))

        try:
            k1, k2 = f"{float(spot_price) * 1.05:.2f}", f"{float(spot_price) * 1.10:.2f}"
        except (ValueError, TypeError):
            k1, k2 = "105.00", "110.00"

        # **FIX**: Added critical instructions and a better example for the AI
        return (
            "You are an options strategy recommender. Return **exactly one** "
            "<json> block. CRITICAL: The JSON must be perfectly formatted. Pay "
            "close attention to commas between list and dictionary elements, "
            "and use double quotes for all keys and string values. The schema is:\n"
            "{'legs':[{'action':'Buy|Sell','type':'Call|Put','strike':float,'quantity':int,'premium':float}],"
            "'note':string}\n\n"
            "Use the inputs below. Choose the single most appropriate strategy. "
            "You MUST calculate and include a realistic 'premium' for each leg.\n\n"
            f"Inputs:\nTicker: {ticker}\nSpot: {_num(spot_price)}\nDirection: {direction}\n"
            f"Target: {_num(target)}\nDTE: {dte}\nIV: {_num(iv)}\n"
            f"Risk tolerance: {risk}\nPreference: {preference}\n\n"
            f"Example for a multi-leg strategy: <json>{{\"legs\":[{{\"action\":\"Buy\",\"type\":\"Call\",\"strike\":{k1},\"quantity\":1,\"premium\":2.50}},{{\"action\":\"Sell\",\"type\":\"Call\",\"strike\":{k2},\"quantity\":1,\"premium\":1.20}}], \"note\":\"A Bull Call Spread.\"}}</json>"
        )

    