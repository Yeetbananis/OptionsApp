"""position.py
────────────────────────────────────────────────────────────────────────────
Defines Leg and Position objects for tracking options trades.

Leg: Represents a single option contract (put or call) with its attributes.
Position: Represents a multi-leg options position, managing its lifecycle,
          valuation (mark-to-market), and exit conditions (PT/SL/Expiry).
"""

from __future__ import annotations
import math, logging
import datetime as _dt
from dataclasses import dataclass, field
from typing import Literal
import numpy as np

# ════════════════════════════════════════════════════════════════════════════
# Pricing Model (Imported or defined here)
# For consistency, let's reuse the one potentially defined in backtester
# If running standalone, define a copy or import appropriately.
try:
    from core.engine.backtester import _black_scholes
except ImportError:
    # Fallback definition if not run via backtester
    def _black_scholes(S: float, K: float, T: float, r: float, sigma: float, option_type: str) -> float:
        """Calculate Black-Scholes price for a European option."""
        if sigma <= 1e-6 or T <= 1e-6:
            intrinsic = max(0.0, K * math.exp(-r * T) - S) if option_type == 'P' else max(0.0, S - K * math.exp(-r * T))
            return intrinsic
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T) + 1e-9)
        d2 = d1 - sigma * math.sqrt(T)
        nd = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))
        if option_type == 'P':
            price = K * math.exp(-r * T) * nd(-d2) - S * nd(-d1)
        elif option_type == 'C':
            price = S * nd(d1) - K * math.exp(-r * T) * nd(d2)
        else: raise ValueError("option_type must be 'P' or 'C'")
        return max(0.0, price)

# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Leg:
    """Represents a single leg of an options position."""
    strike: float
    option_type: Literal['P', 'C'] # 'P' for Put, 'C' for Call
    direction: Literal[1, -1]     # +1 for long, -1 for short
    qty: int = 1                  # Number of contracts (1 contract = 100 shares)
    entry_price: float | None = None # Per-share price at entry (set by Position)

    def current_price(self, S: float, T: float, r: float, sigma: float) -> float:
        """
        Black-Scholes price with:
         • Moneyness skew (OTM puts more expensive, calls cheaper)
         • Tiny execution slippage (±0.05%)
        """
        # 1) Apply crude skew to vol
        vol = sigma * (1 + 0.4 * ((self.strike - S) / S))
        # 2) Model mid price
        price = _black_scholes(S, self.strike, T, r, vol, self.option_type)
        # 3) Simulate micro-slippage
        price *= (1 + np.random.uniform(-0.0005, 0.0005))
        return price


    def current_value(self, S: float, T: float, r: float, sigma: float) -> float:
        """
        Calculates the current dollar value of this leg.
        Value = direction * price_per_share * 100 * quantity
        Positive for long positions, negative for short positions (representing liability).
        """
        price = self.current_price(S, T, r, sigma)
        return self.direction * price * 100 * self.qty

# ════════════════════════════════════════════════════════════════════════════
@dataclass
class Position:
    # --- Required fields first ---
    open_date: _dt.date
    expiry_date: _dt.date
    legs: list[Leg]
    entry_S: float = field(repr=False)      # Moved up
    entry_sigma: float = field(repr=False)  # Moved up
    entry_r: float = field(repr=False)      # Moved up

    # --- Optional fields with defaults next ---
    profit_target_pct: float = 0.50
    stop_loss_mult: float = 2.00

    # --- Fields calculated or managed internally (init=False or have defaults) ---
    entry_value: float = field(init=False)
    initial_credit: float = field(init=False)
    closed: bool = field(default=False, init=False)
    close_date: _dt.date | None = field(default=None, init=False)
    pnl: float | None = field(default=None, init=False)
    close_reason: str = field(default="", init=False)
    
    def __post_init__(self):
        """Calculate initial values after dataclass initialization."""
        # Calculate time to expiry at entry
        T_entry = max(1e-6, (self.expiry_date - self.open_date).days / 365.25)

        # Calculate net value at entry based on market conditions *at entry*
        self.entry_value = 0
        for leg in self.legs:
             # Ensure entry price is set for each leg if not already
             if leg.entry_price is None:
                  leg.entry_price = leg.current_price(self.entry_S, T_entry, self.entry_r, self.entry_sigma)
                  logging.debug(f"Leg K={leg.strike}{leg.option_type} Dir={leg.direction}: Calculated entry_price=${leg.entry_price:.4f}")

             # Value = direction * price * 100 * qty
             self.entry_value += leg.direction * leg.entry_price * 100 * leg.qty

        # For short premium strategies, entry_value will be negative.
        # Initial Credit is the absolute cash received (always positive).
        self.initial_credit = abs(self.entry_value)

        if self.initial_credit < 1e-6:
             # This might happen with far OTM options or data issues.
             logging.warning(f"Position opened on {self.open_date} for {self.expiry_date} has near-zero initial credit (${self.initial_credit:.4f}). Risk controls may not function as expected.")
             # Avoid division by zero later - set a minimum credit for calculation?
             # Or maybe the backtester should prevent opening such trades.
             # For now, we'll proceed but SL/PT might trigger immediately if PnL moves slightly.

        logging.debug(f"Position Init: Open={self.open_date}, Exp={self.expiry_date}, EntryValue=${self.entry_value:.2f}, InitialCredit=${self.initial_credit:.2f}")


    def get_current_value(self, S: float, today: _dt.date, r: float, sigma: float) -> float:
        """Calculates the current mark-to-market dollar value of the position."""
        if self.closed:
            # Once closed, the value is fixed by the PnL. Technically value is 0.
            # Returning PnL might be confusing. Let's return 0.
            return 0.0

        remaining_days = (self.expiry_date - today).days
        # Handle expiry day or past expiry
        if remaining_days <= 0:
             T_remaining = 0.0
        else:
             T_remaining = remaining_days / 365.25

        current_pos_value = 0.0
        for leg in self.legs:
            current_pos_value += leg.current_value(S, T_remaining, r, sigma)

        return current_pos_value

    def get_current_pnl(self, S: float, today: _dt.date, r: float, sigma: float) -> float:
        """Calculates the current unrealized PnL based on MTM value."""
        if self.closed:
            return self.pnl if self.pnl is not None else 0.0 # Return realized PnL if closed

        current_mtm_value = self.get_current_value(S, today, r, sigma)

        # PnL = Current Value - Entry Value
        # For a short premium trade: entry_value is negative (e.g., -$50).
        # If current_value becomes less negative (e.g., -$20), PnL = -20 - (-50) = +$30 (profit)
        # If current_value becomes more negative (e.g., -$150), PnL = -150 - (-50) = -$100 (loss)
        unrealized_pnl = current_mtm_value - self.entry_value
        return unrealized_pnl


    def update_and_maybe_close(self, S: float, today: _dt.date, r: float, sigma: float):
        """
        Recalculates PnL and checks exit conditions (PT, SL, Expiry).
        Sets internal state (closed, pnl, close_date, close_reason) if an exit is triggered.
        """
        if self.closed:
            return # Already closed, nothing to do

        # --- Check for Expiration ---
        if today >= self.expiry_date:
            self.closed = True
            self.close_date = min(today, self.expiry_date) # Close on expiry date itself
            self.close_reason = "Expired"
            # Final PnL at expiry (T=0)
            self.pnl = self.get_current_pnl(S, self.expiry_date, r, sigma)
            logging.debug(f"Pos {self.open_date} expired on {self.close_date}. Final PnL={self.pnl:.2f}")
            return

        # --- Calculate Current PnL ---
        running_pnl = self.get_current_pnl(S, today, r, sigma)

        # --- Check Exit Rules (only if credit is meaningful) ---
        if self.initial_credit > 1e-6: # Avoid division by zero / weird behavior
            # Profit Target Check: PnL >= Target % * Initial Credit
            pt_target_pnl = self.profit_target_pct * self.initial_credit
            if running_pnl >= pt_target_pnl:
                self.closed = True
                self.close_date = today
                self.close_reason = f"Profit Target ({self.profit_target_pct*100:.0f}%)"
                # Lock in PnL at the target level
                self.pnl = pt_target_pnl
                logging.debug(f"Pos {self.open_date} hit PT on {self.close_date}. Target PnL={self.pnl:.2f}")
                return

            # Stop Loss Check: PnL <= - (Stop Multiplier * Initial Credit)
            sl_target_pnl = -self.stop_loss_mult * self.initial_credit
            if running_pnl <= sl_target_pnl:
                self.closed = True
                self.close_date = today
                self.close_reason = f"Stop Loss ({self.stop_loss_mult:.1f}x)"
                # Lock in PnL at the stop loss level
                self.pnl = sl_target_pnl
                logging.debug(f"Pos {self.open_date} hit SL on {self.close_date}. Stop PnL={self.pnl:.2f}")
                return

    def dict_summary(self) -> dict:
        """Returns a dictionary summarizing the trade details and outcome."""
        short_legs = [l for l in self.legs if l.direction == -1]
        long_legs = [l for l in self.legs if l.direction == 1]

        # Find primary short strike (usually lowest for puts, highest for calls)
        # This logic might need refinement for complex strategies
        primary_short_k = min((l.strike for l in short_legs), default=None) if any(l.option_type == 'P' for l in short_legs) else max((l.strike for l in short_legs), default=None)

        # Find primary long strike (hedge)
        primary_long_k = max((l.strike for l in long_legs), default=None) if any(l.option_type == 'P' for l in long_legs) else min((l.strike for l in long_legs), default=None)


        return {
            "open": self.open_date,
            "close": self.close_date,
            "expiry": self.expiry_date,
            "K_short": primary_short_k, # Representing the main short strike
            "K_long": primary_long_k,   # Representing the main long/hedge strike
            "contracts": self.legs[0].qty if self.legs else 0, # Assume uniform qty across legs
            "credit": self.initial_credit, # Original potential credit (positive)
            "pnl": self.pnl if self.pnl is not None else 0.0, # Final realized PnL
            "close_reason": self.close_reason,
            # Could add more details like entry/exit spot prices, vol, etc.
        }