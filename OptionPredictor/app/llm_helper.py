# llm_helper.py
from __future__ import annotations
import json, re, requests
from typing import Any, Dict, List

# ─────────────────────────────────────────────────────────────────────────────
class LLMHelper:
    def __init__(self, model: str = "llama3", temperature: float = 0.7):
        self.api_url     = "http://localhost:11434/api/generate"
        self.model       = model
        self.temperature = temperature

    # ── public façade ────────────────────────────────────────────────────────
    def explain_option_strategy(self, **kwargs) -> str:
        prompt = self._build_explanation_prompt(**kwargs)
        return self._query_llm(prompt)

    def recommend_strategy_structured(self, **kwargs) -> Dict[str, Any]:
        prompt = self._build_structured_prompt(**kwargs)
        raw    = self._query_llm(prompt)

        m = re.search(r"<json>(.*?)</json>", raw, re.DOTALL | re.IGNORECASE)
        if not m:
            raise ValueError("LLM did not return the expected <json> block.")

        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError as exc:
            raise ValueError("LLM returned invalid JSON.") from exc

    def answer_query_with_context(self, user_query: str, context: str) -> str:
        prompt = (
            "You are an AI financial assistant. Answer the user's question "
            "using ONLY the information in the context below. "
            "If the answer is not in the context, reply: 'Information not found in current ideas.'\n\n"
            "--- CONTEXT START ---\n"
            f"{context}\n"
            "--- CONTEXT END ---\n\n"
            f"Question: {user_query}\nAnswer:"
        )
        return self._query_llm(prompt)

    # ── internal ----------------------------------------------------------------
    def _query_llm(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt.strip(),
            "temperature": self.temperature,
            "stream": False,
        }
        try:
            r = requests.post(self.api_url, json=payload, timeout=45)
            r.raise_for_status()
            return r.json().get("response", "").strip()
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(
                f"Cannot reach LLM service at {self.api_url}. Is Ollama running?"
            ) from exc

    # ── prompt builders ----------------------------------------------------------
    def _build_explanation_prompt(
        self,
        ticker: str,
        option_type: str,
        strike: Any,
        S0: Any,
        premium: Any,
        T_days: Any,
        prob: Any,
        metrics: Dict[str, Any] | None = None,
        **__,
    ) -> str:
        """Return a professional, data-rich prompt for the LLM."""

        # numeric-safe formatter --------------------------------------------------
        def _f(val, fmt=".2f") -> str:
            try:
                return format(float(val), fmt)
            except (ValueError, TypeError):
                return str(val)

        def _pct(val) -> str:
            try:
                return f"{float(val) * 100:.1f}%"
            except (ValueError, TypeError):
                return str(val)

        metric_lines: List[str] = []
        for k, v in (metrics or {}).items():
            if isinstance(v, (int, float)):
                metric_lines.append(f"• {k}: {_f(v)}")
            else:
                metric_lines.append(f"• {k}: {v}")

        metrics_block = "\n".join(metric_lines) if metric_lines else "• (no extra metrics provided)"

        prompt = (
            "You are a seasoned options strategist. Provide a clear, data-driven "
            "explanation of the suggested trade. Structure your answer with "
            "the following sections:\n"
            "1️⃣  Thesis  – why this strategy makes sense now\n"
            "2️⃣  Risk / Reward profile (max loss, max gain, breakeven)\n"
            "3️⃣  Key Greeks impact (Delta, Theta, Vega) in one sentence each\n"
            "4️⃣  Probability commentary – relate to barrier-hit probability\n"
            "5️⃣  2-line takeaway\n\n"
            "Trade details:\n"
            f"• Ticker: {ticker}\n• Option Type: {option_type}\n"
            f"• Strike: ${_f(strike)}\n• Spot Price: ${_f(S0)}\n"
            f"• Premium: ${_f(premium)}\n• Days to Expiry: {T_days}\n"
            f"• Barrier-hit Probability: {_pct(prob)}\n\n"
            "Additional Metrics:\n"
            f"{metrics_block}\n\n"
            "Respond in crisp, professional language. Avoid filler."
        )
        return prompt

    def _build_structured_prompt(
        self,
        ticker: str,
        spot: Any,
        direction: str,
        target: Any,
        dte: Any,
        iv: Any,
        risk: str,
        preference: str,
    ) -> str:
        def _num(x):  # safe numeric formatter
            try:
                return f"{float(x):.2f}"
            except (ValueError, TypeError):
                return str(x)

        example_strike = _num(float(spot) * 1.05 if isinstance(spot, (int, float)) else 100)

        return (
            "You are an options strategy recommender. Return **exactly one** "
            "<json> block following this schema:\n"
            "{'legs':[{'action':'Buy|Sell','type':'Call|Put','strike':float,'quantity':int}],"
            "'note':string}\n\n"
            "Use the inputs below. Choose the single most appropriate "
            "multi-leg or single-leg strategy for the user's view, risk "
            "tolerance, IV environment, and preference.\n\n"
            f"Inputs:\nTicker: {ticker}\nSpot: {_num(spot)}\nDirection: {direction}\n"
            f"Target: {_num(target)}\nDTE: {dte}\nIV: {_num(iv)}\n"
            f"Risk tolerance: {risk}\nPreference: {preference}\n\n"
            f"Example output: <json>{{\"legs\":[{{\"action\":\"Buy\",\"type\":\"Call\",\"strike\":{example_strike},\"quantity\":1}}]}}</json>"
        )
