import requests
import json
import re

class LLMHelper:
    def __init__(self, model="llama3"):
        self.api_url = "http://localhost:11434/api/generate"
        self.model = model

    def explain_option_strategy(self, ticker, option_type, strike, S0, premium, T_days, prob, educational=False):
        if educational:
            prompt = (
                f"Explain options like you're talking to a clever 5-year-old. Use metaphors about bunnies and carrots.\n"
                f"\nTicker: {ticker}, Type: {option_type}, Strike: ${strike:.2f}, Spot: ${S0:.2f}, Premium: ${premium:.2f}, Days to Expiry: {T_days}, Probability: {prob*100:.1f}%\n"
                f"Make it fun and slightly wrong on purpose. End with a carrot rating from 1 to 10."
            )
        else:
            prompt = (
                f"Act like a confused quant hedge fund manager using made-up financial words.\n"
                f"Asset: {ticker}, Option Type: {option_type}, Strike: ${strike:.2f}, Spot: ${S0:.2f}, Premium: ${premium:.2f}, Expiry: {T_days} days, Barrier hit chance: {prob*100:.1f}%\n"
                f"Give a chaotic but confident breakdown and end with a 'Sharpened Cognitive Convexity Quotient' score from 1 to 10."
            )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }

        response = requests.post(self.api_url, json=payload)

        if response.status_code != 200:
            raise Exception(f"Local LLM failed: {response.status_code} - {response.text}")

        result = response.json()
        return result.get("response", "").strip()

    def build_structured_prompt(self, *, ticker, spot, target, iv, dte, direction, risk, preference="Any"):
        return (
            f"You are a professional options strategist working for a trading desk.\n"
            f"Based on the trader's structured view, recommend an optimal options strategy.\n"
            f"All values below are accurate and realistic.\n\n"
            f"Ticker: {ticker}\n"
            f"Current Price: ${spot:.2f}\n"
            f"Target Price: ${target:.2f}\n"
            f"Implied Volatility: {iv:.1f}%\n"
            f"Days to Expiration: {dte}\n"
            f"Market Direction: {direction}\n"
            f"Risk Tolerance: {risk}\n"
            f"Strategy Preference: {preference}\n\n"
            f"Output constraints:\n"
            f"- Use only 1 to 3 option legs.\n"
            f"- Do not return legs with premiums <= 0.00. Use realistic premiums (e.g., 0.50 – 20.00).\n"
            f"- Output MUST be JSON wrapped in <json> ... </json>\n"
            f"- Do NOT include any explanation or text outside the JSON.\n\n"
            f"Example format:\n"
            f"<json>\n"
            f'{{"legs": [{{"action": "Buy", "type": "Call", "strike": 100, "premium": 2.50, "quantity": 1}}], '
            f'"dte": 30, "note": "Brief rationale here"}}\n'
            f"</json>"
        )

    def recommend_strategy_structured(self, ticker, current_price, direction, target_price, dte, iv, risk_tolerance, prefer_defined_risk):
        prompt = self.build_structured_prompt(
            ticker=ticker,
            spot=current_price,
            target=target_price,
            iv=iv,
            dte=dte,
            direction=direction,
            risk=risk_tolerance,
            preference="Defined Risk" if prefer_defined_risk else "Any"
        )

        payload = {
            "model": self.model,
            "prompt": prompt.strip(),
            "stream": False
        }

        response = requests.post(self.api_url, json=payload)
        if response.status_code != 200:
            raise Exception(f"LLM request failed: {response.status_code} - {response.text}")

        raw = response.json().get("response", "")
        print("LLM raw response:", raw)  # Optional debug output

        match = re.search(r"<json>(.*?)</json>", raw, re.DOTALL)
        if not match:
            raise ValueError("No valid <json>...</json> block found in LLM response")

        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError as e:
            raise ValueError("LLM returned invalid JSON.") from e
