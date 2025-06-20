# config.py

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict
from core.models.filters import FilterConfig

@dataclass
class StrategyConfig:
    """Holds and validates all backtest inputs."""
    underlying: str
    start: str
    end: str
    strategy_type: str
    capital: float
    allocation_pct: float
    profit_target_pct: float
    stop_loss_mult: float
    dte_target: int
    commission_per_contract: float

    risk_free_rate: float = 0.03
    strategy_params: Dict       = field(default_factory=dict)
    custom_legs: Optional[List[Dict]] = None
    benchmark_ticker: str       = 'SPY'
    use_benchmark: bool         = True

    # <-- changed here: use default_factory instead of a mutable default
    filters: FilterConfig       = field(default_factory=FilterConfig)

    def __post_init__(self):
        # --- Symbol ---
        self.underlying = self.underlying.strip().upper()
        if not self.underlying:
            raise ValueError("Underlying symbol cannot be empty.")

        # --- Dates ---
        try:
            dt_start = datetime.strptime(self.start, "%Y-%m-%d")
            dt_end   = datetime.strptime(self.end,   "%Y-%m-%d")
        except Exception:
            raise ValueError("Dates must be in YYYY-MM-DD format.")
        if dt_start >= dt_end:
            raise ValueError("Start date must be before end date.")

        # --- Numeric Ranges ---
        checks = [
            ('capital', self.capital, 0, None),
            ('allocation_pct', self.allocation_pct, 0, 100),
            ('profit_target_pct', self.profit_target_pct, 0, None),
            ('stop_loss_mult', self.stop_loss_mult, 0, None),
            ('dte_target', self.dte_target, 1, None),
            ('commission_per_contract', self.commission_per_contract, 0, None),
        ]
        for name, val, mn, mx in checks:
            if val <= mn or (mx is not None and val > mx):
                rng = f"> {mn}" + (f" and ≤ {mx}" if mx else "")
                raise ValueError(f"{name} must be {rng}.")

        # --- Custom legs required for manual strategy ---
        if self.strategy_type == 'custom_manual':
            if not isinstance(self.custom_legs, list) or len(self.custom_legs) == 0:
                raise ValueError("custom_legs list required for custom_manual strategy.")

    def to_dict(self) -> Dict:
        """Convert back to the dict shape expected by Backtester.run."""
        cfg = {
            "underlying": self.underlying,
            "start": self.start,
            "end": self.end,
            "strategy_type": self.strategy_type,
            "capital": self.capital,
            "allocation_pct": self.allocation_pct,
            "profit_target_pct": self.profit_target_pct,
            "stop_loss_mult": self.stop_loss_mult,
            "dte_target": self.dte_target,
            "commission_per_contract": self.commission_per_contract,
            "risk_free_rate": self.risk_free_rate,
            "strategy_params": self.strategy_params,
            "benchmark_ticker": self.benchmark_ticker,
            "use_benchmark": self.use_benchmark,
            # you may also want to inject filters here if your engine supports them
        }
        if self.strategy_type == "custom_manual":
            cfg["custom_legs"] = self.custom_legs
        return cfg

    def with_overrides(self, **overrides) -> "StrategyConfig":
        cfg = asdict(self)
        cfg.update(overrides)

        # Immediately wrap filters back into FilterConfig if it's a dict
        if isinstance(cfg.get("filters"), dict):
            cfg["filters"] = FilterConfig(**cfg["filters"])
            
        return StrategyConfig(**cfg)
