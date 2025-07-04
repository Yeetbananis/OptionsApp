# financial_chatbot_gui.py
# ===============================================================
# FinBot  –  GUI chatbot for free stock analysis
# cleaned + curl-cffi session + robust retries  (June 2025)
# ===============================================================

import os, threading, time, random, functools, webbrowser, tkinter as tk
from datetime import datetime
from tkinter import ttk
# StockChartWindow import is already handled below

# ↓ UI / plotting
import customtkinter as ctk
import mplfinance as mpf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import pandas as pd

# ─── chart  (TradingView) in a separate process ───────────────
import tempfile, webbrowser, pathlib
from tkinter import filedialog
try:
    from ui import StockChartWindow  # Try relative import first
except ImportError:
    # Fall back to importing from the same directory
    import sys
    import os
    sys.path.append(os.path.dirname(__file__))
    import StockChartWindow

# ↓ Data & news
import yfinance as yf
# yfinance ≤ 0.2.17 doesn’t define YFRateLimitError – fall back to plain Exception
RateErr = getattr(yf.utils, "YFRateLimitError", Exception)
from curl_cffi import requests as curl_requests      # ⭐ new
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from dateutil.parser import parse as _dateparse

# ───────────────────────────────────────────────────────────────
# QUICK Stooq downloader   (CSV → DataFrame)
# ───────────────────────────────────────────────────────────────
import io, csv
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # <-- ① use non-GUI backend, thread-safe
# ---------------------------------------------------------------------------

# ↓ UI / plotting
import customtkinter as ctk
import mplfinance as mpf
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ─── Stooq downloader (robust) ───────────────────────────────────────────
import io, zipfile, pandas as pd
from curl_cffi import requests as curl_requests




# ─── Colours identical to the original stand-alone FinBot ──────────
def _palette(theme: str):
    if theme == "dark":
        return dict(
            bg       ="#0f0f0f", fg="#ffffff",
            entry_bg ="#3c3c3c",
            user_bg  ="#2c3e50", bot_bg="#444444",
            tree_bg  ="#2B2B2B", tree_fg="#ffffff", tree_sel="#1F6AA5")
    else:                           # light
        return dict(
            bg       ="#f0f0f0", fg="#000000",
            entry_bg ="#ffffff",
            user_bg  ="#dfe6e9", bot_bg="#e0e0e0",
            tree_bg  ="#ffffff", tree_fg="#000000", tree_sel="#007acc")




_STOOQ_PERIOD_MAP = {           # how many calendar days to keep
    "1mo": 30,  "3mo": 90,  "6mo": 180,
    "1y": 365, "2y": 730,  "5y": 1825,
    "10y": 3650, "ytd": 366, "max": None,
}

class StooqNoDataError(RuntimeError): pass     # clean exception

def _stooq_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    # ---------- map symbols to Stooq convention -------------------------
    if symbol.isalpha() and len(symbol) <= 5:          # simple US ticker?
        stooq_sym = f"{symbol.lower()}.us"            #  → append .us
    else:
        stooq_sym = symbol.lower()                    # e.g. ^spx, eurusd
    days = _STOOQ_PERIOD_MAP.get(period, 365)
    url  = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d"


    raw_bytes = curl_requests.get(url, timeout=20).content

    # ① sometimes Stooq sends a tiny zip, sometimes bare CSV  ------------
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            csv_bytes = zf.read(zf.namelist()[0])
    except zipfile.BadZipFile:
        csv_bytes = raw_bytes

    if not csv_bytes.lstrip().startswith(b"Date,"):
        raise StooqNoDataError(f"Stooq returned no data for {symbol}")

    df = (pd.read_csv(io.BytesIO(csv_bytes), parse_dates=["Date"])
            .rename(columns=str.title)        # open→Open etc.
            .set_index("Date").sort_index())

    if days is not None:
        df = df.iloc[-days:]

    return df

# ───────────────────────────────────────────────────────────────
# 1)  BUILD ONE  curl-cffi  SESSION  AND SAFE WRAPPERS
# ───────────────────────────────────────────────────────────────
YF_SESSION = curl_requests.Session(
    impersonate="chrome",    # looks like latest Chrome / Win10
    timeout=30
)

def _raw_ticker(symbol: str | list[str], **kw) -> yf.Ticker:
    """Return a yfinance.Ticker that uses the curl-cffi session."""
    return yf.Ticker(symbol, session=YF_SESSION, **kw)


# ─── helper that returns a ticker with retry wrappers ───────────
def _safe_ticker(symbol: str,
                 *, retries: int = 3, pause: float = 1.3) -> yf.Ticker:
    """
    Returns a yfinance.Ticker whose network-hitting calls are retried.
    Properties such as .balance_sheet or .options are left untouched;
    we expose `safe_*` helper methods for them instead.
    """
    base = _raw_ticker(symbol)               # ← curl-cffi session already

    # ---- generic retry decorator -------------------------------------
    def _wrap(func):
        @functools.wraps(func)
        def inner(*a, **kw):
            last = None
            for _ in range(retries):
                try:
                    return func(*a, **kw)
                except RateErr as e:
                    last = e
                    time.sleep(pause + random.random()*0.6)
            raise last
        return inner

    # ---- wrap the *methods* only -------------------------------------
    for name in ("history", "option_chain"):
        setattr(base, name, _wrap(getattr(base, name)))

    # ---- safe helpers for properties ---------------------------------
    base.safe_options       = lambda: _wrap(lambda: base.options)()
    base.safe_balance_sheet = lambda: _wrap(lambda: base.balance_sheet)()
    base.safe_income_stmt   = lambda: _wrap(lambda: base.income_stmt)()
    base.safe_cashflow      = lambda: _wrap(lambda: base.cashflow)()
    base.safe_info          = lambda: _wrap(lambda: base.info)()
    base.safe_calendar      = lambda: _wrap(lambda: base.calendar)()
    return base


def _fetch_info(tkr: yf.Ticker, retries: int = 3, pause: float = 1.2):
    last = None
    for _ in range(retries):
        try:
            return tkr.info          # property access does the request
        except RateErr as e:
            last = e
            time.sleep(pause + random.random()*0.6)
    raise last

# ───────────────────────────────────────────────────────────────
FINNHUB_API_KEY = os.getenv(
    "FINNHUB_API_KEY", "d114k6hr01qse6lf8c1gd114k6hr01qse6lf8c20")

# ===============================================================
# 2)  GUI  CLASS
# ===============================================================
class FinancialChatbotApp(ctk.CTk):
    """ A standalone chatbot application that runs in its own process. """
    def __init__(self, theme: str = "dark"):
        super().__init__()
        self.current_theme = theme
        self.clr = _palette(theme)

        # This now ONLY affects this standalone app instance
        ctk.set_appearance_mode("Dark" if self.current_theme == "dark" else "Light")
        self.configure(bg=self.clr["bg"])

        self.title("FinBot – Finance Chatbot")
        self.geometry("920x760")

        # --- Class Attributes ---
        self.sentiment = SentimentIntensityAnalyzer()

        # --- Main Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.chat_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", bg_color=self.clr["bg"])
        self.chat_frame.grid(row=0, column=0, padx=12, pady=12, sticky="nsew")

        entry_frame = ctk.CTkFrame(self, fg_color="transparent")
        entry_frame.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="ew")
        entry_frame.grid_columnconfigure(0, weight=1)

        self.user_entry = ctk.CTkEntry(
            entry_frame,
            placeholder_text="Type a command...",
            fg_color=self.clr["entry_bg"],
            height=40,
            corner_radius=12
        )
        self.user_entry.grid(row=0, column=0, sticky="ew")
        self.user_entry.bind("<Return>", self._on_submit)

        submit_btn = ctk.CTkButton(entry_frame, text="Send", width=80, height=40, command=self._on_submit)
        submit_btn.grid(row=0, column=1, padx=(8,0))

        # --- Configure Local Styles for internal ttk widgets ---
        # This is safe because it only applies to this separate application instance.
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Treeview", background=self.clr["tree_bg"], fieldbackground=self.clr["tree_bg"], foreground=self.clr["tree_fg"], rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background=self.clr["bot_bg"], foreground=self.clr["fg"], relief="flat", font=('Calibri', 10, 'bold'))
        style.map("Treeview", background=[('selected', self.clr["tree_sel"])], foreground=[('selected', self.clr["fg"])])
        style.layout("FinBot.Tree", style.layout("Treeview"))
        style.layout("FinBot.Tree.Heading", style.layout("Treeview.Heading"))
        style.configure("FinBot.Tree", background=self.clr["tree_bg"], fieldbackground=self.clr["tree_bg"], foreground=self.clr["tree_fg"])
        style.configure("FinBot.Tree.Heading", background=self.clr["bot_bg"], foreground=self.clr["fg"])
        style.map("FinBot.Tree", background=[('selected', self.clr["tree_sel"])], foreground=[('selected', self.clr["fg"])])

        self._bot("Welcome! Type 'help' to see commands.")
    # ------------------------------------------------------------------
    def apply_custom_theme(self):
        """
        Called by OptionsApp.apply_theme_to_window().
        Re-applies Fin-Bot’s own colours after the global styles might have
        been changed by the main program.
        """
        # The master is the root Tk window of OptionsApp
        new_theme = getattr(self.master, "current_theme", self.current_theme)
        
        # If the theme hasn't actually changed, do nothing.
        if new_theme == self.current_theme:
            return

        self.current_theme = new_theme
        self.clr = _palette(self.current_theme)
        
        # Set the appearance mode for this window specifically
        ctk.set_appearance_mode("Dark" if self.current_theme == "dark" else "Light")

        # 1) basic container colours
        try:
            self.configure(bg=self.clr['bg'])
            self.chat_frame.configure(bg_color=self.clr['bg'])
            self.user_entry.configure(fg_color=self.clr["entry_bg"])
        except tk.TclError as e:
            # This can happen if the window is being destroyed
            print(f"Chatbot theme error (TclError): {e}")


        # 2) recolour every existing bubble
        for outer_frame in self.chat_frame.winfo_children():
            # Check if the widget is a valid frame with children
            if isinstance(outer_frame, ctk.CTkFrame) and outer_frame.winfo_children():
                inner_frame = outer_frame.winfo_children()[0]
                
                # Determine role by the anchor property of its pack layout
                anchor = inner_frame.pack_info().get("anchor")
                if anchor == 'e': # User bubble
                    inner_frame.configure(fg_color=self.clr['user_bg'])
                elif anchor == 'w': # Bot bubble
                    inner_frame.configure(fg_color=self.clr['bot_bg'])

        # 3) refresh ttk Treeview style **locally**
        style = ttk.Style(self) # Get style object associated with this window
        style.configure("Treeview", background=self.clr['tree_bg'],
                        fieldbackground=self.clr['tree_bg'],
                        foreground=self.clr['tree_fg'])
        style.configure("Treeview.Heading", background=self.clr['bot_bg'],
                        foreground=self.clr['fg'])
        style.map("Treeview",
                background=[("selected", self.clr['tree_sel'])],
                foreground=[("selected", self.clr['fg'])])
        
      # ────────────────────────────────────────────────────────────
    #  LOW-LEVEL  CHAT HELPERS
    # ────────────────────────────────────────────────────────────
    def _user(self, text:str):
        self._bubble(text, align="e", role="user")

    def _bot(self, payload, *, placeholder=False):
        return self._bubble(payload, align="w", role="bot")

    # ------ revised bubble helper --------------------------------------
    def _bubble(self, payload, *, align, role):
        """
        Colour is now determined by the theme-aware palette.
        """
        color = self.clr[f"{role}_bg"]

        outer = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        outer.pack(fill="x", padx=8, pady=4, anchor=align)

        inner = ctk.CTkFrame(
            outer, corner_radius=14, fg_color=color, bg_color="transparent")

        if isinstance(payload, str):
            ctk.CTkLabel(inner, text=payload, wraplength=540,
                         justify="left").pack(padx=16, pady=10)
        else:
            self._render_complex(inner, payload)

        inner.pack(anchor=align, padx=6)
        
        # Smoothly scroll to bottom
        self.after(60, self._smooth_scroll_bottom)

        return outer  

    # ─── smooth canvas scroll helper ───────────────────────────────
    def _smooth_scroll_bottom(self, steps: int = 15, delay: int = 15):
        """Animate chat canvas to the bottom in `steps` increments."""
        self.update_idletasks()                  # ensure scroll-region is fresh
        canvas  = self.chat_frame._parent_canvas
        start_y = canvas.yview()[0]
        def _step(i=1):
            if i > steps:
                return
            canvas.yview_moveto(start_y + (1.0 - start_y) * i / steps)
            self.after(delay, lambda: _step(i + 1))
        _step()

    # ────────────────────────────────────────────────────────────
    #  INPUT HANDLING  (threaded)
    # ────────────────────────────────────────────────────────────
    def _on_submit(self, *_):
        txt = self.user_entry.get().strip()
        if not txt: return
        self.user_entry.delete(0,"end"); self._user(txt)
        ph = self._bot("…", placeholder=True)
        threading.Thread(target=self._dispatch,
                         args=(txt.lower(), ph), daemon=True).start()

    def _dispatch(self, cmdline:str, ph):
        parts = cmdline.split()
        cmd, args = parts[0], parts[1:]
        try:
            out = getattr(self, f"_cmd_{cmd}", self._cmd_unknown)(args)
        except Exception as e:
            out = f"⚠️ {type(e).__name__}: {e}"
        self.after(0, lambda: self._update(ph, out))

    def _update(self, ph, new):
        for w in ph.winfo_children(): w.destroy()
        self._render_complex(ph, new) if isinstance(new, dict) else \
            ctk.CTkLabel(ph, text=new, wraplength=540, justify="left")\
               .pack(padx=16, pady=10)
        
        self.after(60, self._smooth_scroll_bottom)

    # ────────────────────────────────────────────────────────────
    #  COMMANDS
    # ────────────────────────────────────────────────────────────
    def _cmd_unknown(self, *_):
        return "Unknown command.  Type  help  for a list."

    # ────────────────────────────────────────────────────────────
    #  HELP 
    # ────────────────────────────────────────────────────────────
    HELP_TIPS = [
        "You can estimate an option’s break-even by simply adding the call premium to the strike (calls) or subtracting it (puts).",
        "When volume < open-interest, most option contracts are still held rather than freshly opened.",
        "If the 30-day implied volatility is far above the 30-day historical volatility, markets are pricing in a surprise.",
        "The VIX roughly equals the S&P 500’s expected 30-day move (in %) ÷ √12.",
        "Put-call ratios spike before many macro events—check `options SPY` around Fed days.",
        "Weekly options (0 DTE/1 DTE) decay almost completely in the last hour—watch the theta burn!",
        "Earnings IV crush: implied volatility often drops 30-60 % the morning after earnings.",
        "LEAPS (options > 1 year out) behave much more like the underlying stock due to low theta.",
        "A 70 Δ call + a -30 Δ put ≈ a synthetic long stock position with far less capital.",
        "Open-interest > 10 × average volume can telegraph pinning at that strike on expiration Friday.",
        "Dividend dates matter: deep ITM calls can be assigned early if the dividend beats remaining extrinsic value.",
        "Gamma is highest for at-the-money, near-expiry options—great for quick scalps, risky for writing.",
        "Skew watch: if puts are far pricier than equidistant calls, the market fears a drop more than a pop.",
        "IV percentiles put today’s volatility in context—an IV of 90 % means it’s higher than 90 % of the past year.",
        "Covered calls convert upside into steady yield; just mind ex-div dates to avoid early assignment.",
        "Calendar spreads thrive when near-term IV is cheap and back-month IV is rich.",
        "SPX options are European-style (no early assignment) and cash-settled—handy for avoiding pin risk.",
        "Look at option volume *relative* to stock volume (> 1 % is unusual and often news-driven).",
        "Max-pain theory: stocks sometimes gravitate toward the strike where options sellers lose least—check on expiry morning.",
        "Theta isn’t linear: it accelerates as expiration approaches—half the time to expiry often means *more* than half the remaining extrinsic value lost."
        ]


    def _cmd_help(self, _):
        """Neat, easy-to-read help panel with a random bonus tip."""
        import random
        tip = random.choice(self.HELP_TIPS)

        return (
            "###  FinBot – Quick Reference  ###\n\n"
            "• **price  TICKER**\n"
            "    Latest quote & key stats\n\n"
            "• **info   TICKER**\n"
            "    Company profile / long summary\n\n"
            "• **chart  TICKER  [period]**\n"
            "    Daily candle chart + volume (period: 1mo 3mo 6mo 1y 2y 5y 10y ytd max)\n\n"
            "• **news   TICKER**\n"
            "    Ten freshest headlines with sentiment colour-coding\n\n"
            "• **income / balance / cashflow  TICKER**\n"
            "    Annual financial statements (click *Full-Screen* to enlarge)\n\n"
            "• **options TICKER**\n"
            "    List all expiration dates\n"
            "• **options TICKER  DATE**\n"
            "    Option chain for that date (fuzzy dates accepted)\n"
            "•  `earnings TICKER`   – next / last earnings dates\n\n"
            "———————————————\n"
            f"💡  {tip}"
        )

    # ---- price / info ------------------------------------------------------
    def _cmd_price(self, a):
        if not a: return "Usage: price TICKER"
        tkr = _safe_ticker(a[0])
        info = _fetch_info(tkr) 
        cp = info.get('currentPrice'); pc = info.get('previousClose')
        if cp is None: return "No price."
        ch, chpct = cp-pc, (cp-pc)/pc*100 if pc else 0
        return (f"**{info.get('shortName')} ({a[0].upper()})**\n"
                f"Price ${cp:,.2f}   "
                f"Δ {ch:+.2f} ({chpct:+.2f} %)  "
                f"Vol {info.get('volume'):,}")

    def _cmd_info(self, a):
        if not a: return "Usage: info TICKER"
        info = _fetch_info(_safe_ticker(a[0])) 
        if not info.get('longBusinessSummary'): return "No profile."
        txt = (f"**{info['shortName']}**  –  {info.get('sector','')} / "
               f"{info.get('industry','')}\n{info['longBusinessSummary']}")
        return txt


    # ────────────────────────────────────────────────────────────
    #  chart  (candles + volume)
    # ────────────────────────────────────────────────────────────
        # —— chart  command  (Stooq backend, drawn in main thread) ——————————
    def _cmd_chart(self, args):
        """`chart TICKER [period]`   period defaults to 1y"""
        if not args:
            return "Usage: chart TICKER [period]"

        sym    = args[0].upper()
        period = args[1] if len(args) > 1 else "1y"

        try:
            df = _stooq_history(sym, period)
        except StooqNoDataError as e:
            return str(e)
        except Exception as e:
            return f"Could not download Stooq data: {e}"

        # theme-aware style ---------------------------------------------
        if self.current_theme == "dark":
            base_style  = "nightclouds"
            face_colour = "#2B2B2B"
            up, down    = "#26a69a", "#ef5350"
        else:
            base_style  = "yahoo"          # clean white background
            face_colour = "#ffffff"
            up, down    = "#2ca02c", "#d62728"

        mc = mpf.make_marketcolors(up=up, down=down, inherit=True)
        st = mpf.make_mpf_style(base_mpf_style=base_style,
                                marketcolors=mc, gridstyle="-",
                                facecolor=face_colour, edgecolor=face_colour)

        # ── create the figure *in the worker thread* but rendering (draw)
        #    is done later in the Tk main-thread → thread-safe  ───────────
        fig, _ = mpf.plot(
            df,  type="candle", volume=True, mav=(20, 50),
            style=st,  figsize=(8, 4.2),
            warn_too_much_data=len(df)+1,   # silence mplfinance warning
            returnfig=True
        )
        fig.set_facecolor(face_colour)
        return {"chart": fig, "symbol": sym}   # <- include ticker




    # ---- news --------------------------------------------------------------
    def _cmd_news(self, a):
        if not a: return "Usage: news TICKER"
        sym = a[0].upper()
        url = (f"https://finnhub.io/api/v1/company-news?symbol={sym}"
               f"&from=2024-01-01&to=2025-12-31&token={FINNHUB_API_KEY}")
        art = curl_requests.get(url, timeout=20).json()[:10]
        if not art: return "No news."
        def sent(h):
            s = self.sentiment.polarity_scores(h)['compound']
            return "Bullish" if s> .3 else "Bearish" if s<-.3 else "Neutral"
        return {"news":[{"headline":x['headline'],
                         "url":x['url'], "sentiment":sent(x['headline'])}
                        for x in art]}

    # ---- statements --------------------------------------------------------
    def _cmd_income (self,a): return self._fin("income",  a)
    def _cmd_balance(self,a): return self._fin("balance", a)
    def _cmd_cashflow(self,a): return self._fin("cashflow",a)

    def _fin(self, typ, a):
        if not a: return f"Usage: {typ} TICKER"
        tk = _safe_ticker(a[0])
        df = getattr(tk, {"income":"income_stmt",
                          "balance":"balance_sheet",
                          "cashflow":"cashflow"}[typ])
        if df.empty: return "No data."
        df = (df.transpose()
                .pipe(lambda d: d.map(
                    lambda x: f"{x/1e6:,.0f} M" if isinstance(x, (int, float)) else x))
                .rename_axis('Date').reset_index())
        return {"table":{"title":f"{a[0].upper()} – {typ.title()}",
                         "data":df, "fullscreen":True}}

    # ---- options -----------------------------------------------------------
    def _cmd_options(self, a):
        if not a: return "Usage: options TICKER [DATE]"
        sym = a[0].upper(); tk = _safe_ticker(sym)
        exp = tk.options
        if not exp: return "No expiries."
        if len(a)==1:          # list dates
            return ("Expiries:\n" + "\n".join(f"- `{d}`" for d in exp) +
                    f"\nUse `options {sym} DATE` for a chain.")
        # fuzzy date → nearest available
        try:
            wanted = _dateparse(" ".join(a[1:])).strftime("%Y-%m-%d")
        except Exception: return "Bad date."
        if wanted not in exp:
            later = [d for d in exp if d>=wanted]; wanted = later[0] if later else exp[-1]
        chain = tk.option_chain(wanted)
        def _prep(df):
            keep = ['strike','lastPrice','bid','ask','volume',
                    'openInterest','impliedVolatility']
            return (df[keep].rename(columns={'lastPrice':'Last',
                                             'openInterest':'OI',
                                             'impliedVolatility':'IV'})
                            .head(15))
        return {"options":{"date":wanted,
                           "calls":_prep(chain.calls),
                           "puts": _prep(chain.puts)}}
    
   
    # ────────────────────────────────────────────────────────────
    #  earnings  – next report date (YF)  +  last EPS & revenue (AV)
    # ────────────────────────────────────────────────────────────
    def _cmd_earnings(self, args):
        """
        earnings TICKER   →  nicely formatted snapshot

            • Next scheduled earnings date       (yfinance calendar)
            • Previous quarter: EPS vs estimate  (Alpha-Vantage EARNINGS)
            • Previous quarter: total revenue    (Alpha-Vantage IS)

        Alpha-Vantage key is read from  ALPHAVANTAGE_API_KEY  env-var,
        or defaults to the “demo” key (works for IBM only).
        """
        if not args:
            return "Usage: earnings TICKER"

        import pandas as pd, os, math
        sym = args[0].upper()
        tk  = _safe_ticker(sym)

        # ── 1)  NEXT EARNINGS DATE  – yfinance calendar ──────────────────
        try:
            cal = tk.safe_calendar()           # our retry-wrapped helper
        except Exception:
            cal = None

        def _parse_next(cal_obj):
            if cal_obj is None:
                return None
            if isinstance(cal_obj, pd.DataFrame):
                if cal_obj.empty:
                    return None
                # old style: index 'Earnings Date'
                if "Earnings Date" in cal_obj.index:
                    raw = cal_obj.loc["Earnings Date"].dropna().iloc[0]
                else:                   # fallback
                    raw = cal_obj.iloc[0, 0]
            elif isinstance(cal_obj, dict):
                arr = cal_obj.get("Earnings Date") or cal_obj.get("earningsDate")
                raw = arr[0] if arr else None
            else:
                raw = None
            try:
                return pd.to_datetime(raw).strftime("%d %b %Y")
            except Exception:
                return None

        next_date = _parse_next(cal) or "n/a"

        # ── 2)  PREVIOUS QUARTER EPS  – Alpha Vantage  ────────────────────
        AV_KEY = os.getenv("AV_API_KEY", "HHFA73KA7RDGGB3O")  # Alpha Vantage key, default to demo
        base_url = "https://www.alphavantage.co/query"

        def _av_json(params):
            """tiny helper that returns json or None (never raises)."""
            try:
                r = curl_requests.get(base_url, params=params, timeout=20)
                if r.status_code >= 400 or not r.text.strip():
                    return None
                return r.json()
            except Exception:
                return None

        # EPS surprise
        eps_js = _av_json({"function": "EARNINGS", "symbol": sym, "apikey": AV_KEY})
        if eps_js and eps_js.get("quarterlyEarnings"):
            last   = eps_js["quarterlyEarnings"][0]
            qtr    = last["fiscalDateEnding"]
            act    = float(last["reportedEPS"])
            est    = float(last["estimatedEPS"])
            surpr  = float(last["surprisePercentage"])
            eps_line = (f"Last ({qtr})  ·  EPS **{act:.2f}** vs est **{est:.2f}**"
                        f"  → surprise **{surpr:+.1f}%**")
        else:
            eps_line = "Last quarter EPS data unavailable."

        # Revenue
        inc_js = _av_json({"function": "INCOME_STATEMENT", "symbol": sym,
                        "apikey": AV_KEY})
        rev_line = ""
        if inc_js and inc_js.get("quarterlyReports"):
            qr = inc_js["quarterlyReports"]
            try:
                rev = float(qr[0]["totalRevenue"])
                rev_line = f" Revenue: **{rev/1e6:,.0f} M**"
            except (KeyError, ValueError):
                pass

        # ── 3)  Assemble & return ────────────────────────────────────────
        return (
            f"### {sym} — Earnings Snapshot\n\n"
            f"Next report  ·  **{next_date}**\n"
            f"{eps_line}{rev_line}"
        )


    # ===============================================================
    # 3)  RENDERERS  (charts, tables, options …)
    # ===============================================================
    def _render_complex(self, frame, obj):
        if "chart" in obj:
            fig   = obj["chart"]              # Matplotlib figure
            sym   = obj.get("symbol", "chart")
            cvs   = FigureCanvasTkAgg(fig, master=frame)
            cvs.draw()
            cvs.get_tk_widget().pack(padx=8, pady=8,
                                     fill="both", expand=True)

            # ---- extra toolbar ---------------------------------------
            bar = ctk.CTkFrame(frame, fg_color="transparent")
            bar.pack(pady=(0,6))

            ctk.CTkButton(bar, text="🔍 Full-Screen",
                command=lambda f=fig, s=sym: self._show_fullscreen_chart(f,s)
            ).pack(side="left", padx=4)

            ctk.CTkButton(bar, text="💾 Save…",
                command=lambda f=fig, s=sym: self._save_chart_dialog(f,f"{s}_{datetime.now():%Y%m%d}.png")
            ).pack(side="left", padx=4)

            ctk.CTkButton(bar, text="📈 Live Chart",
                        command=lambda s=sym: self._open_tradingview(s)
            ).pack(side="left", padx=4)



        elif "news" in obj:
            for n in obj["news"]:
                clr = {"Bullish":"#26a69a","Bearish":"#ef5350","Neutral":"gray"}[n['sentiment']]
                lbl = ctk.CTkLabel(frame, text="• "+n['headline'],
                                   wraplength=520, cursor="hand2")
                lbl.pack(anchor="w", padx=10, pady=(4,0))
                lbl.bind("<Button-1>", lambda e,u=n['url']: webbrowser.open(u))
                ctk.CTkLabel(frame, text=n['sentiment'], text_color=clr,
                             font=("Arial",10)).pack(anchor="w", padx=22)
        elif "table" in obj:
            ttl = ctk.CTkLabel(frame, text=obj["table"]["title"],
                               font=ctk.CTkFont(weight="bold"))
            ttl.pack(pady=(8,2))
            if obj["table"].get("fullscreen"):
                ctk.CTkButton(frame, text="Full-Screen",
                    command=lambda d=obj["table"]["data"],
                                   t=obj["table"]["title"]:
                        self._show_full_table(t,d)).pack(pady=(0,6))
            self._small_table(frame, obj["table"]["data"])
        elif "options" in obj:
            date = datetime.strptime(obj['options']['date'],'%Y-%m-%d')\
                         .strftime('%b %d %Y')
            ctk.CTkLabel(frame, text=f"Option Chain • {date}",
                         font=ctk.CTkFont(weight="bold")).pack(pady=(8,4))
            ctk.CTkLabel(frame, text="Calls").pack()
            self._small_table(frame, obj['options']['calls'])
            ctk.CTkLabel(frame, text="Puts").pack(pady=(6,0))
            self._small_table(frame, obj['options']['puts'])

    def _small_table(self, parent, df):
        if df.empty:
            ctk.CTkLabel(parent, text="No data").pack(); return
        tv = ttk.Treeview(parent, style="FinBot.Tree",   # add style=
                  columns=list(df.columns), show='headings',
                  height=min(len(df), 10))
        for c in df.columns:
            tv.heading(c, text=c)            # Tk 8.6 headings don’t take “style”
        for _,r in df.iterrows(): tv.insert("", "end", values=list(r))
        tv.pack(fill="x", padx=10, pady=4)

    def _show_full_table(self, title, df):
        win = ctk.CTkToplevel(self); win.title(title); win.geometry("1040x640")
        tv = ttk.Treeview(win, columns=list(df.columns), show='headings')
        vsb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=vsb.set); tv.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        for c in df.columns:
            tv.heading(c, text=c); tv.column(c, anchor='center', width=120)
        for _,r in df.iterrows(): tv.insert("", "end", values=list(r))


    def _save_chart_dialog(self, fig, default_name: str):
        """Ask for a filename & format; save the Matplotlib figure."""
        ftypes = [("PNG image" , "*.png"),
                ("PDF file"  , "*.pdf"),
                ("SVG vector", "*.svg")]
        path = filedialog.asksaveasfilename(
            defaultextension=".png", filetypes=ftypes,
            initialfile=default_name)
        if not path:
            return                              # cancelled
        fig.savefig(path, dpi=180, bbox_inches="tight")

    # ────────────────────────────────────────────────────────────
    #  open TradingView in separate process
    # ────────────────────────────────────────────────────────────
    def _open_tradingview(self, sym: str):
        """
        Launch a stand-alone pywebview window that shows a TradingView chart
        for `sym`.  Runs in a separate Python process so it never blocks Tk.
        """
        try:
            StockChartWindow.StockChartWindow(self, sym, theme=self.current_theme)
        except Exception as exc:
            tk.messagebox.showerror("TradingView error",
                                    f"Could not launch chart:\n{exc}",
                                    parent=self)



    # ────────────────────────────────────────────────────────────
    #  full-screen chart window
    # ────────────────────────────────────────────────────────────
    def _show_fullscreen_chart(self, fig, title):
        win = ctk.CTkToplevel(self)
        win.title(f"{title} – full-screen")
        win.geometry("1100x700")
        cvs = FigureCanvasTkAgg(fig, master=win)
        cvs.draw()
        cvs.get_tk_widget().pack(fill="both", expand=True)


# ===============================================================
#  MAIN EXECUTION BLOCK
# ===============================================================
if __name__ == "__main__":
    import sys
    theme = sys.argv[1] if len(sys.argv) > 1 else "dark"
    app = FinancialChatbotApp(theme=theme)
    app.mainloop()