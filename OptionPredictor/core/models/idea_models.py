# idea_models.py
from __future__ import annotations
import time, hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List



def _stable_id(symbol: str, title: str, category: str) -> str:
    """
    Build a repeatable 16-char hex id from deterministic fields.
    If any of those fields change (e.g. a different detector fires)
    we intentionally get a new UID – that’s desirable.
    """
    key = f"{symbol}|{title}|{category}".lower().strip()
    return hashlib.md5(key.encode()).hexdigest()[:16]  # 16 chars is plenty


@dataclass(slots=True)
class Idea:
    # core meta -----------------------------------------------------------------
    symbol: str = ""
    title:  str = ""
    description: str = ""
    category: str = ""
    score: float = 0.0
    suggested_strategy: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any]            = field(default_factory=dict)

    # user / UI ---------------------------------------------------------------
    risk:      str  = "Moderate"
    event_ts:  int | None = None
    ts:        int  = field(default_factory=lambda: int(time.time()))

    # mini-chart
    sparkline_data: List[float] | None = None
    sparkline_type: str = "price"

    # state flags
    is_saved:    bool = False
    is_explored: bool = False

    # uid can be supplied (e.g. loaded from cache) or auto-derived
    uid: str | None = None

     # ── User metadata ──────────────────────────────
    notes: str = ""
    tags: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def __post_init__(self):
        if not self.uid:                    # freshly built object
            self.uid = _stable_id(self.symbol, self.title, self.category)

    # handy for caching / JSON --------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {f.name: getattr(self, f.name)
                for f in self.__class__.__dataclass_fields__.values()}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Idea":
        return cls(**d)
