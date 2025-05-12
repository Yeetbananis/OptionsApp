import tkinter as tk
from tkinter import ttk
import datetime as dt
from filters import FilterConfig

# ─── Example earnings calendar ────────────────────────────────────────────────
calendar_dict = {
    "SPY":  [dt.date(2025, 4, 16), dt.date(2025, 7, 16),  dt.date(2025, 10, 15)],
    "AAPL": [dt.date(2025, 4, 30), dt.date(2025, 7, 30),  dt.date(2025, 10, 29)],
    # … add more tickers here …
}

class FilterDialog(tk.Toplevel):
    """
    A comprehensive dialog for defining entry filters in backtests,
    including a built-in calendar_dict for corporate events.
    """
    def __init__(self, master, controller, theme="light"):
        super().__init__(master)
        self.controller     = controller
        self.calendar_dict  = calendar_dict
        # ensure this attribute always exists
        self.filter_config  = FilterConfig()
        self.transient(master)
        self.grab_set()
        self.title("Backtest Entry Filters")

        container = ttk.Frame(self, padding=15)
        container.pack(fill="both", expand=True)

        self._build_time_filters(container)
        self._build_corporate_filters(container)
        self._build_liquidity_filters(container)
        self._build_volatility_filters(container)
        self._build_technical_filters(container)

        # Control buttons
        btns = ttk.Frame(container, padding=(0,10))
        btns.pack(fill="x")
        ttk.Button(btns, text="Apply",  command=self._on_apply).pack(side="right", padx=5)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

    def _build_time_filters(self, parent):
        lf = ttk.LabelFrame(parent, text="1. Time-based Filters", padding=10)
        lf.pack(fill="x", pady=5)

        # Time-of-Day
        ttk.Label(lf, text="Trade only between:").grid(row=0, column=0, sticky="w")
        self.tod_from = ttk.Entry(lf, width=7); self.tod_from.insert(0, "09:30")
        self.tod_from.grid(row=0, column=1, padx=(5,2))
        ttk.Label(lf, text="and").grid(row=0, column=2)
        self.tod_to   = ttk.Entry(lf, width=7); self.tod_to.insert(0, "16:00")
        self.tod_to.grid(row=0, column=3, padx=(2,5))

        # Day-of-Week
        ttk.Label(lf, text="Allow on:").grid(row=1, column=0, sticky="w", pady=(8,0))
        self.dow_vars = {}
        days = ["Mon","Tue","Wed","Thu","Fri"]
        for i, day in enumerate(days):
            var = tk.BooleanVar(value=True)
            chk = ttk.Checkbutton(lf, text=day, variable=var)
            chk.grid(row=1, column=1+i, pady=(8,0), padx=2)
            self.dow_vars[day] = var

        # Seasonality
        ttk.Label(lf, text="Within last N days before expiry:")\
            .grid(row=2, column=0, sticky="w", pady=(8,0))
        self.season_days = ttk.Entry(lf, width=5); self.season_days.insert(0, "100")
        self.season_days.grid(row=2, column=1, pady=(8,0))

    def _build_corporate_filters(self, parent):
        lf = ttk.LabelFrame(parent, text="2. Corporate-Event Filters", padding=10)
        lf.pack(fill="x", pady=5)

        # Earnings buffer
        self.skip_earn      = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(lf, text="Skip entries within", variable=self.skip_earn)
        chk.grid(row=0, column=0, sticky="w")
        self.earn_buf       = ttk.Entry(lf, width=4); self.earn_buf.insert(0, "3")
        self.earn_buf.grid(row=0, column=1, padx=(5,2))
        ttk.Label(lf, text="days of earnings").grid(row=0, column=2, sticky="w")

        # Specific earnings date (from calendar_dict)
        ttk.Label(lf, text="Select earnings date:")\
            .grid(row=1, column=0, sticky="w", pady=(6,0))
        symbol = getattr(self.controller, 'config', {}).get('underlying', None)
        dates  = calendar_dict.get(symbol, [])
        display = [d.isoformat() for d in dates]
        self.earn_combo = ttk.Combobox(lf, values=display, state="readonly", width=12)
        if display:
            self.earn_combo.set(display[0])
        self.earn_combo.grid(row=1, column=1, columnspan=2, sticky="w", pady=(6,0))

        # Dividend
        self.skip_dividend = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Skip ex-dividend day", variable=self.skip_dividend)\
            .grid(row=2, column=0, columnspan=3, sticky="w", pady=(6,0))

        # Other corporate actions
        self.skip_actions  = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Exclude splits/mergers/spin-offs", variable=self.skip_actions)\
            .grid(row=3, column=0, columnspan=3, sticky="w", pady=(6,0))

    def _build_liquidity_filters(self, parent):
        lf = ttk.LabelFrame(parent, text="3. Liquidity & Market-Micro", padding=10)
        lf.pack(fill="x", pady=5)

        self.use_vol    = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Min avg daily volume ≥", variable=self.use_vol)\
            .grid(row=0, column=0, sticky="w")
        self.min_vol    = ttk.Entry(lf, width=8); self.min_vol.insert(0, "100000")
        self.min_vol.grid(row=0, column=1, padx=(5,2))

        self.use_spread = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Max bid-ask spread ≤", variable=self.use_spread)\
            .grid(row=1, column=0, sticky="w", pady=(6,0))
        self.max_spread = ttk.Entry(lf, width=5); self.max_spread.insert(0, "2")
        self.max_spread.grid(row=1, column=1, pady=(6,0))

        self.use_oi     = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Min option open interest ≥", variable=self.use_oi)\
            .grid(row=2, column=0, sticky="w", pady=(6,0))
        self.min_oi     = ttk.Entry(lf, width=6); self.min_oi.insert(0, "500")
        self.min_oi.grid(row=2, column=1, pady=(6,0))

    def _build_volatility_filters(self, parent):
        lf = ttk.LabelFrame(parent, text="4. Volatility & Skew Filters", padding=10)
        lf.pack(fill="x", pady=5)

        self.use_iv_pct       = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="IV percentile over N days ≥", variable=self.use_iv_pct)\
            .grid(row=0, column=0, sticky="w")
        self.iv_pct_days      = ttk.Entry(lf, width=4); self.iv_pct_days.insert(0, "30")
        self.iv_pct_days.grid(row=0, column=1, padx=(5,2))

        self.require_iv_gt_hv = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Require IV > HV", variable=self.require_iv_gt_hv)\
            .grid(row=1, column=0, columnspan=2, sticky="w", pady=(6,0))

        self.use_skew         = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Max front-back IV skew ≤", variable=self.use_skew)\
            .grid(row=2, column=0, sticky="w", pady=(6,0))
        self.max_skew        = ttk.Entry(lf, width=5); self.max_skew.insert(0, "5")
        self.max_skew.grid(row=2, column=1, pady=(6,0))

    def _build_technical_filters(self, parent):
        lf = ttk.LabelFrame(parent, text="5. Technical Filters", padding=10)
        lf.pack(fill="x", pady=5)

        self.use_ma    = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="Price above N-day MA", variable=self.use_ma)\
            .grid(row=0, column=0, sticky="w")
        self.ma_days  = ttk.Entry(lf, width=4); self.ma_days.insert(0, "50")
        self.ma_days.grid(row=0, column=1, padx=(5,2))
        ttk.Label(lf, text="days").grid(row=0, column=2)

        self.use_rsi  = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="RSI(14) between", variable=self.use_rsi)\
            .grid(row=1, column=0, sticky="w", pady=(6,0))
        self.rsi_lo   = ttk.Entry(lf, width=4); self.rsi_lo.insert(0, "30")
        self.rsi_lo.grid(row=1, column=1, pady=(6,0))
        ttk.Label(lf, text="and").grid(row=1, column=2)
        self.rsi_hi   = ttk.Entry(lf, width=4); self.rsi_hi.insert(0, "70")
        self.rsi_hi.grid(row=1, column=3, pady=(6,0))

        self.use_atr  = tk.BooleanVar(value=False)
        ttk.Checkbutton(lf, text="ATR(14) between", variable=self.use_atr)\
            .grid(row=2, column=0, sticky="w", pady=(6,0))
        self.atr_lo   = ttk.Entry(lf, width=4); self.atr_lo.insert(0, "1")
        self.atr_lo.grid(row=2, column=1, pady=(6,0))
        ttk.Label(lf, text="and").grid(row=2, column=2)
        self.atr_hi   = ttk.Entry(lf, width=4); self.atr_hi.insert(0, "5")
        self.atr_hi.grid(row=2, column=3, pady=(6,0))

    def _on_apply(self):
        # Build and store the new FilterConfig
        fc = FilterConfig(
            tod_from_str       = self.tod_from.get(),
            tod_to_str         = self.tod_to.get(),
            skip_weekdays = [
                i for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri"])
                if not self.dow_vars[d].get()
            ],
            days_before_expiry = int(self.season_days.get() or 60),
            earnings_buffer    = int(self.earn_buf.get() or 0),
            earnings_calendar  = self.calendar_dict,
        )


        self.filter_config = fc
        self.controller.filters = fc  # push to controller as well
        self.destroy()
