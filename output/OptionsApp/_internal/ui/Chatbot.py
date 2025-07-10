# financial_chatbot_gui.py
# ===============================================================
# FinBot  –  GUI chatbot for free stock analysis
# cleaned + curl-cffi session + robust retries  (June 2025)
# ===============================================================

import os, threading, time, random, functools, webbrowser, tkinter as tk, json
from datetime import datetime
from tkinter import ttk, messagebox
import tkinter.messagebox
import os
import google.generativeai as genai
# StockChartWindow import is already handled below

# ↓ UI / plotting
import customtkinter as ctk
import mplfinance as mpf
import matplotlib
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


# ─── Stooq downloader (robust) ───────────────────────────────────────────
import io, zipfile, pandas as pd
from curl_cffi import requests as curl_requests

import sys
import os

# Determine the current file's directory, even when frozen by PyInstaller
if getattr(sys, 'frozen', False):  # If bundled as .exe
    base_dir = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

# Append the ui module directory to sys.path
ui_path = os.path.join(base_dir, "ui")
if ui_path not in sys.path:
    sys.path.insert(0, ui_path)

try:
    import StockChartWindow
    from TokenTracker import TokenUsageTracker
except ImportError as e:
    raise ImportError(f"Failed to import required modules. Ensure StockChartWindow.py and TokenTracker.py exist in: {ui_path}\nOriginal error: {e}")



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
        ctk.set_appearance_mode("Dark" if self.current_theme == "dark" else "Light")
        self.configure(bg=self.clr["bg"])
        self.geometry("920x760")
        self._shutdown = False


        # --- State Management ---
        self.conversation_history = []
        self.current_chat_path = None
        self.is_dirty = False
        self.title("FinBot – New Chat")
        self.side_panel_open = False
        self.history_dir = os.path.join(os.getcwd(), "chat_history")
        os.makedirs(self.history_dir, exist_ok=True)

        # --- Class Attributes ---
        self.sentiment = SentimentIntensityAnalyzer()
        self.token_tracker = TokenUsageTracker(daily_limit=33000)
        self.gemini_model = None
        
        # --- Configure Styles, AI, and Window Closing Protocol ---
        self._configure_styles()
        self._configure_ai()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        # --- Main Layout ---
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
        self.main_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(0, weight=1)

        self.chat_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color=self.clr["bg"])
        self.chat_frame.grid(row=0, column=0, columnspan=2, padx=12, pady=12, sticky="nsew")

        entry_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        entry_frame.grid(row=1, column=0, columnspan=2, padx=12, pady=(0, 12), sticky="ew")
        entry_frame.grid_columnconfigure(1, weight=1)

        self.hamburger_button = ctk.CTkButton(entry_frame, text="☰", width=40, height=40, command=self._toggle_side_panel)
        self.hamburger_button.grid(row=0, column=0, sticky="w")
        self.user_entry = ctk.CTkEntry(entry_frame, placeholder_text="Type a command...", fg_color=self.clr["entry_bg"], height=40, corner_radius=12)
        self.user_entry.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        self.user_entry.bind("<Return>", self._on_submit)
        ctk.CTkButton(entry_frame, text="Send", width=80, height=40, command=self._on_submit).grid(row=0, column=2, padx=(8,0))



        # --- Side Panel ---
        self.side_panel = ctk.CTkFrame(self, fg_color=self.clr["bot_bg"], corner_radius=0)
        self.side_panel.place(relx=-0.27, rely=0, relwidth=0.27, relheight=1)
        side_panel_header = ctk.CTkFrame(self.side_panel, fg_color="transparent")
        side_panel_header.pack(pady=10, padx=10, fill="x")
        side_panel_header.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(side_panel_header, text="➕ New Chat", command=self._new_chat, height=40).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(side_panel_header, text="« Close", width=80, height=40, command=self._toggle_side_panel).grid(row=0, column=1, padx=(8,0))
        self.chat_list_frame = ctk.CTkScrollableFrame(self.side_panel, fg_color="transparent")
        self.chat_list_frame.pack(expand=True, fill="both", padx=10, pady=(0, 10))
        self.bind_all("<Button-1>", self._check_close_panel)

        # --- Final Setup ---
        self._populate_side_panel()
        self._bubble("Welcome! Type 'help' to see commands.", align="w", role="bot")

    def apply_custom_theme(self):
        """
        Called by OptionsApp.apply_theme_to_window().
        Re-applies Fin-Bot’s own colours after the global styles might have
        been changed by the main program.
        """
        if self._shutdown: return
        new_theme = getattr(self.master, "current_theme", self.current_theme)
        
        if new_theme == self.current_theme:
            return

        self.current_theme = new_theme
        self.clr = _palette(self.current_theme)
        
        ctk.set_appearance_mode("Dark" if self.current_theme == "dark" else "Light")

        try:
            self.configure(bg=self.clr['bg'])
            self.chat_frame.configure(bg_color=self.clr['bg'])
            self.user_entry.configure(fg_color=self.clr["entry_bg"])
            self.side_panel.configure(fg_color=self.clr["bot_bg"])
        except tk.TclError as e:
            print(f"Chatbot theme error (TclError): {e}")

        for outer_frame in self.chat_frame.winfo_children():
            if isinstance(outer_frame, ctk.CTkFrame) and outer_frame.winfo_children():
                inner_frame = outer_frame.winfo_children()[0]
                anchor = inner_frame.pack_info().get("anchor")
                if anchor == 'e':
                    inner_frame.configure(fg_color=self.clr['user_bg'])
                elif anchor == 'w':
                    inner_frame.configure(fg_color=self.clr['bot_bg'])

        style = ttk.Style(self)
        style.configure("Treeview", background=self.clr['tree_bg'],
                        fieldbackground=self.clr['tree_bg'],
                        foreground=self.clr['tree_fg'])
        style.configure("Treeview.Heading", background=self.clr['bot_bg'],
                        foreground=self.clr['fg'])
        style.map("Treeview",
                background=[("selected", self.clr['tree_sel'])],
                foreground=[("selected", self.clr['fg'])])
        
        self._populate_side_panel()
        
    def _cmd_ai_fallback(self, query: str) -> str:
        """Handles any unknown command by sending it to the Gemini AI, respecting token limits."""
        if not self.gemini_model:
            return ("⚠️ **AI Assistant is offline.**\n\n"
                    "This is likely because the `GOOGLE_API_KEY` environment variable "
                    "is missing or incorrect.")

        if self.token_tracker.is_limit_reached():
            usage = self.token_tracker.tokens_used
            limit = self.token_tracker.daily_limit
            return (f"⚠️ **Daily free token limit reached.**\n\n"
                    f"You have used {usage:,}/{limit:,} tokens today. "
                    "The limit will reset tomorrow.")

        prompt = (
            "You are FinBot, a helpful and concise financial assistant. "
            "The user entered a command for which you don't have a specific function. "
            "Answer their query clearly. If you are asked about a specific stock, "
            "assume you do not have live data and provide general knowledge.\n\n"
            f"User Query: \"{query}\""
        )

        try:
            response = self.gemini_model.generate_content(prompt)
            self.token_tracker.update_usage(response)
            return response.text
        except Exception as e:
            return f"An error occurred with the AI assistant: {e}"
        
    def _cmd_tokens(self, _):
        """Displays the current daily token usage."""
        if not self.token_tracker:
            return "Token tracker is not initialized."
            
        used = self.token_tracker.tokens_used
        limit = self.token_tracker.daily_limit
        percentage = (used / limit) * 100 if limit > 0 else 0
        
        return (
            f"### AI Token Usage (Today)\n\n"
            f"**Used:** {used:,} / {limit:,} tokens\n"
            f"**Usage:** {percentage:.2f}%\n\n"
            f"The limit resets daily."
        )
            
    def _user(self, text:str):
        self._add_to_history("user", text, render=True)

    def _bot(self, payload):
        self._add_to_history("bot", payload, render=True)

    def _bubble(self, payload, *, align, role):
        color = self.clr[f"{role}_bg"]

        outer = ctk.CTkFrame(self.chat_frame, fg_color="transparent")
        outer.pack(fill="x", padx=8, pady=4, anchor=align)

        inner = ctk.CTkFrame(outer, corner_radius=14, fg_color=color, bg_color="transparent")

        if isinstance(payload, str):
            ctk.CTkLabel(inner, text=payload, wraplength=540,
                         justify="left").pack(padx=16, pady=10)
        else:
            self._render_complex(inner, payload)

        inner.pack(anchor=align, padx=6)
        
        self.after(60, self._smooth_scroll_bottom)
        return outer  

    def _smooth_scroll_bottom(self, steps: int = 15, delay: int = 15):
        if self._shutdown: return
        self.update_idletasks()
        canvas = self.chat_frame._parent_canvas
        start_y = canvas.yview()[0]
        def _step(i=1):
            if self._shutdown or i > steps: return
            canvas.yview_moveto(start_y + (1.0 - start_y) * i / steps)
            self.after(delay, lambda: _step(i + 1))
        _step()

    def _on_submit(self, *_):
        txt = self.user_entry.get().strip()
        if not txt: return
        self.user_entry.delete(0, "end")
        
        self._add_to_history("user", txt, render=True)
        
        if not self.current_chat_path:
            self._save_chat(is_auto=True) 
        
        ph = self._bot_placeholder()
        threading.Thread(target=self._dispatch, args=(txt.lower(), ph), daemon=True).start()

    def _dispatch(self, cmdline: str, ph):
        """Executes the command and prepares the final payload for the UI."""
        parts = cmdline.split()
        cmd, args = parts[0], parts[1:]
        try:
            command_function = getattr(self, f"_cmd_{cmd}", self._cmd_ai_fallback)
            if command_function == self._cmd_ai_fallback:
                out = command_function(cmdline)
            else:
                out = command_function(args)

            if isinstance(out, dict) and out.get("type") == "chart_data":
                self.after(0, lambda: self._render_chart_data(ph, out))
                return
                
        except Exception as e:
            out = f"⚠️ An error occurred: {type(e).__name__}: {e}"

        self.after(0, lambda: self._update_placeholder(ph, out))
        
    def _bot_placeholder(self):
        return self._bubble("...", align="w", role="bot")

    def _update_placeholder(self, placeholder_frame, new_payload):
        if self._shutdown: return
        
        for widget in placeholder_frame.winfo_children():
            widget.destroy()

        self._render_complex(placeholder_frame, new_payload)
        self._add_to_history("bot", new_payload)
        self.after(60, self._smooth_scroll_bottom)

    def _render_chart_data(self, placeholder_frame, chart_data):
        if self._shutdown: return
        
        fig, _ = mpf.plot(chart_data["df"], type="candle", volume=True,
                        style=chart_data["style"], figsize=(8, 4.2), returnfig=True)
        fig.set_facecolor(self.clr["bg"])
        
        final_payload = {
            "type": "chart", # Use a distinct type for the rendered chart
            "chart": fig,
            "symbol": chart_data["symbol"],
            "period": chart_data["period"]
        }
        self._update_placeholder(placeholder_frame, final_payload)

    def _configure_ai(self):
        try:
            api_key = "AIzaSyAt67ZI4vacvCacjzFbrXoeIsKTG__qaCI" #os.getenv("GOOGLE_API_KEY")
            if not api_key:
                print("WARNING: GOOGLE_API_KEY not set. AI fallback will be disabled.")
                return
            genai.configure(api_key=api_key)
            self.gemini_model = genai.GenerativeModel('gemini-1.5-pro-latest')
            print("Gemini AI model configured successfully.")
        except Exception as e:
            print(f"Error configuring Gemini AI: {e}")

    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Treeview", background=self.clr["tree_bg"],
                        fieldbackground=self.clr["tree_bg"],
                        foreground=self.clr["tree_fg"],
                        rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background=self.clr["bot_bg"],
                        foreground=self.clr["fg"],
                        relief="flat", font=('Calibri', 10, 'bold'))
        style.map("Treeview", background=[('selected', self.clr["tree_sel"])],
                            foreground=[('selected', self.clr["fg"])])

    def _set_dirty(self, state=True):
        if self.is_dirty == state: return
        self.is_dirty = state
        title = self.title()
        if state and not title.endswith("*"):
            self.title(title + "*")
        elif not state and title.endswith("*"):
            self.title(title[:-1])

    def _add_to_history(self, role, payload, render=False):
        # Don't add placeholder messages to history
        if role == "bot" and payload == "...":
            return
            
        self.conversation_history.append({"role": role, "payload": payload})
        if role == "user" or role == "bot":
            self._set_dirty(True)
            
        if render:
            align = "e" if role == "user" else "w"
            self._bubble(payload, align=align, role=role)

    def _new_chat(self):
        """Starts a new, empty chat session, auto-saving the current one if needed."""
        if self.is_dirty and self.current_chat_path:
            self._save_chat(is_auto=True)
        elif self.is_dirty:
            if not messagebox.askyesno("Unsaved Changes", "You have an unsaved chat. Are you sure you want to start a new one?"):
                return
        
        self.conversation_history.clear()
        for widget in self.chat_frame.winfo_children():
            widget.destroy()
        
        self.current_chat_path = None
        self.is_dirty = False
        self.title("FinBot – New Chat")
        self._bubble("Welcome! Type 'help' to see commands.", align="w", role="bot")
        if self.side_panel_open:
            self._toggle_side_panel()
        self._populate_side_panel()

    def _get_chat_name_from_user(self, default_name=""):
        dialog = ctk.CTkInputDialog(text="Enter a name for this chat:", title="Save Chat",)
        # The following line is needed to make the dialog appear on top of the main window.
        input_name = dialog.get_input()
        return input_name.strip() if input_name else None

    def _save_chat(self, save_as=False, is_auto=False):
        path = self.current_chat_path
        
        if save_as or not path:
            # If it's an automatic save of an unnamed chat, don't prompt. Just skip.
            if is_auto and not self.current_chat_path:
                 # Try to get a name from the first user message for the file
                try:
                    first_msg = next(entry["payload"] for entry in self.conversation_history if entry["role"] == "user")
                    base_name = "".join(c for c in first_msg if c.isalnum() or c in " _-").strip()[:40]
                except StopIteration:
                    base_name = f"chat_{datetime.now():%Y%m%d_%H%M%S}"
                path = os.path.join(self.history_dir, f"{base_name}.json")
            else:
                chat_name = self._get_chat_name_from_user()
                if not chat_name:
                    return False # User cancelled
                # Sanitize filename
                safe_filename = "".join(c for c in chat_name if c.isalnum() or c in " _-").strip()
                path = os.path.join(self.history_dir, f"{safe_filename}.json")

        serializable_history = []
        for entry in self.conversation_history:
            role, payload = entry["role"], entry["payload"]
            serializable_payload = payload
            try:
                if isinstance(payload, dict):
                    # For charts, save the parameters needed to regenerate them
                    if payload.get("type") == "chart":
                        serializable_payload = {
                            "type": "chart_placeholder",
                            "symbol": payload.get("symbol", "?"),
                            "period": payload.get("period", "1y")
                        }
                    # For financial statements, save ticker and type
                    elif payload.get("type") == "table_data":
                        serializable_payload = {
                            "type": "table_placeholder",
                            "title": payload.get("title", "table"),
                            "statement_type": payload.get("statement_type"),
                            "symbol": payload.get("symbol")
                        }
                json.dumps(serializable_payload) # Test serializability
                serializable_history.append({"role": role, "payload": serializable_payload})
            except (TypeError, OverflowError):
                serializable_history.append({"role": role, "payload": {"type": "unserializable"}})

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(serializable_history, f, indent=2)
            self.current_chat_path = path
            self.title(f"FinBot – {os.path.splitext(os.path.basename(path))[0]}")
            self._set_dirty(False)
            self._populate_side_panel()
            return True
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not save chat:\n{e}")
            return False

    def _load_chat(self, file_path: str):
        if self.is_dirty:
            # Auto-save current chat before loading new one
            if self.current_chat_path:
                self._save_chat(is_auto=True)
            else: # Unnamed, dirty chat
                res = messagebox.askyesnocancel("Unsaved Chat", "Save the current unnamed chat first?")
                if res is True:
                    if not self._save_chat(): # if user cancels save
                        return
                elif res is None: # if user cancels load
                    return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                loaded_history = json.load(f)
        except Exception as e:
            messagebox.showerror("Load Error", f"Could not load chat file.\n\n{e}")
            return

        self.current_chat_path = file_path
        self.title(f"FinBot – {os.path.splitext(os.path.basename(file_path))[0]}")

        self.conversation_history.clear()
        for w in self.chat_frame.winfo_children():
            w.destroy()

        for entry in loaded_history:
            role, payload = entry["role"], entry["payload"]
            restored_payload = payload
            
            if isinstance(payload, dict) and "type" in payload:
                typ = payload["type"]
                try:
                    if typ == "chart_placeholder":
                        # Regenerate the chart data synchronously for simplicity
                        restored_payload = self._cmd_chart([payload.get("symbol"), payload.get("period")])
                    elif typ == "table_placeholder":
                        # Regenerate the financial statement data
                        restored_payload = self._fin(payload.get("statement_type"), [payload.get("symbol")])
                except Exception as e:
                    restored_payload = f"⚠️ Failed to reload content: {e}"

            self._add_to_history(role, restored_payload, render=True)

        self._set_dirty(False)
        self.update_idletasks()
        self.after(100, self._smooth_scroll_bottom)
        if self.side_panel_open:
            self._toggle_side_panel()
        self._populate_side_panel()


    def _on_closing(self):
        self._shutdown = True # Signal background threads to stop
        if self.is_dirty:
            if self.current_chat_path:
                self._save_chat(is_auto=True)
            else: # Prompt for unsaved new chat
                if messagebox.askyesno("Quit", "You have an unsaved chat. Save before quitting?"):
                    if not self._save_chat():
                        return # Abort close if user cancels save dialog
        
        try:
            matplotlib._pylab_helpers.Gcf.destroy_all()
        except Exception:
            pass
        self.destroy()

    def _toggle_side_panel(self):
        if self.side_panel_open:
            self.side_panel_open = False
            self._animate_panel(target_relx=-0.27)
        else:
            self.side_panel_open = True
            self.side_panel.lift()
            self._populate_side_panel()
            self._animate_panel(target_relx=0)

    def _animate_panel(self, target_relx):
        if self._shutdown: return
        current_relx = float(self.side_panel.place_info().get('relx', -0.27))
        distance = target_relx - current_relx
        
        if abs(distance) < 0.001:
            self.side_panel.place(relx=target_relx)
            if not self.side_panel_open:
                self.side_panel.lower()
            return

        new_relx = current_relx + distance * 0.2 # Easing
        self.side_panel.place(relx=new_relx)
        self.after(15, lambda: self._animate_panel(target_relx))

    def _check_close_panel(self, event):
        if not self.side_panel_open: return
        try:
            if (self.side_panel.winfo_containing(event.x_root, event.y_root) is not None or
                self.hamburger_button.winfo_containing(event.x_root, event.y_root) is not None):
                return
        except (KeyError, tk.TclError):
            return
        self._toggle_side_panel()

    def _populate_side_panel(self):
        if self._shutdown: return
        for widget in self.chat_list_frame.winfo_children():
            widget.destroy()

        try:
            files = sorted(
                [f for f in os.listdir(self.history_dir) if f.endswith(".json")],
                key=lambda f: os.path.getmtime(os.path.join(self.history_dir, f)),
                reverse=True
            )
            for filename in files:
                full_path = os.path.join(self.history_dir, filename)
                display_name = os.path.splitext(filename)[0]

                is_current = self.current_chat_path == full_path
                fg_color = self.clr['tree_sel'] if is_current else "transparent"

                chat_button = ctk.CTkButton(
                    self.chat_list_frame,
                    text=display_name,
                    fg_color=fg_color,
                    anchor="w",
                    command=lambda p=full_path: self._load_chat(p)
                )
                chat_button.pack(fill="x", pady=2)
                
                # --- This inner function is the part that's updated ---
                def show_context_menu(event, path=full_path):
                    menu = tk.Menu(self, tearoff=0, bg=self.clr['bg'], fg=self.clr['fg'])
                    menu.add_command(label="Rename", command=lambda: self._rename_chat(path))
                    menu.add_command(label="Delete", command=lambda: self._delete_chat(path))
                    menu.tk_popup(event.x_root, event.y_root)

                chat_button.bind("<Button-3>", show_context_menu)

        except Exception as e:
            print(f"Side panel population error: {e}")

    def _rename_chat(self, old_path: str):
        """Prompts the user to rename a specific chat file."""
        old_name_no_ext = os.path.splitext(os.path.basename(old_path))[0]

        dialog = ctk.CTkInputDialog(text="Enter a new name for the chat:", title="Rename Chat")
        new_name = dialog.get_input()

        if not new_name or not new_name.strip():
            return  # User cancelled or entered an empty name

        new_name = new_name.strip()
        if new_name == old_name_no_ext:
            return  # Name is unchanged

        # Sanitize the new name to create a valid filename
        safe_new_filename = "".join(c for c in new_name if c.isalnum() or c in " _-").strip()
        new_path = os.path.join(self.history_dir, f"{safe_new_filename}.json")

        if os.path.exists(new_path):
            messagebox.showerror("Rename Failed", "A chat with that name already exists.", parent=self)
            return

        try:
            os.rename(old_path, new_path)

            # If the currently open chat was the one renamed, update its path and title
            if self.current_chat_path == old_path:
                self.current_chat_path = new_path
                self.title(f"FinBot – {new_name}")

            self._populate_side_panel()  # Refresh the list to show the new name
        except Exception as e:
            messagebox.showerror("Rename Failed", f"Could not rename the chat file.\n{e}", parent=self)

    def _delete_chat(self, path_to_delete):
        base_name = os.path.basename(path_to_delete)
        if messagebox.askyesno("Delete Chat", f"Are you sure you want to permanently delete '{base_name}'?"):
            try:
                os.remove(path_to_delete)
                # If the deleted chat was the current one, start a new chat
                if self.current_chat_path == path_to_delete:
                    self._new_chat()
                self._populate_side_panel()
            except Exception as e:
                messagebox.showerror("Delete Failed", f"Could not delete chat file.\n{e}")

    # ===============================================================
    #  COMMANDS
    # ===============================================================
    def _cmd_unknown(self, *_):
        return "Unknown command.  Type  help  for a list."

    def _cmd_help(self, _):
        return (
            "### FinBot Command Reference\n\n"
            "**AI Assistant**\n"
            "If your command isn't listed below, the AI assistant will try to answer it. "
            "You can ask general financial questions like `what is a covered call?` or `explain theta decay`.\n\n"
            "--- **Built-in Commands** ---\n"
            "• **price TICKER**\n"
            "  *Latest quote & key stats.*\n\n"
            "• **info TICKER**\n"
            "  *Company profile and business summary.*\n\n"
            "• **chart TICKER [period]**\n"
            "  *Candle chart. Period can be: 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max.*\n\n"
            "• **news TICKER**\n"
            "  *Recent headlines with sentiment analysis.*\n\n"
            "• **options TICKER [DATE]**\n"
            "  *Lists expiry dates or shows the option chain for a specific date.*\n\n"
            "• **earnings TICKER**\n"
            "  *Shows the next earnings date and previous quarter's results.*\n\n"
            "• **income / balance / cashflow TICKER**\n"
            "  *Annual financial statements.*\n\n"
            "• **tokens**\n"
            "  *Check your daily AI token usage.*\n"
        )
    
    def _cmd_price(self, a):
        if not a: return "Usage: price TICKER"
        tkr = _safe_ticker(a[0])
        info = tkr.safe_info()
        if not info: return f"Could not fetch info for {a[0].upper()}."
        cp = info.get('currentPrice')
        pc = info.get('previousClose')
        if cp is None or pc is None: return "Price data unavailable."
        ch, chpct = cp-pc, (cp-pc)/pc*100
        return (f"**{info.get('shortName')} ({a[0].upper()})**\n"
                f"Price ${cp:,.2f}   "
                f"Δ {ch:+.2f} ({chpct:+.2f} %)  "
                f"Vol {info.get('volume', 0):,}")

    def _cmd_info(self, a):
        if not a: return "Usage: info TICKER"
        info = _safe_ticker(a[0]).safe_info()
        if not info or not info.get('longBusinessSummary'): return "No profile found."
        txt = (f"**{info.get('shortName', a[0].upper())}** –  {info.get('sector','')}\n\n"
               f"{info['longBusinessSummary']}")
        return txt

    def _cmd_chart(self, args):
        if not args: return "Usage: chart TICKER [period]"
        sym = args[0].upper()
        period = args[1] if len(args) > 1 else "1y"

        try:
            df = _stooq_history(sym, period)
        except Exception as e:
            return f"Could not download chart data for {sym}: {e}"

        base_style = "nightclouds" if self.current_theme == "dark" else "yahoo"
        up, down = ("#26a69a", "#ef5350") if self.current_theme == "dark" else ("#2ca02c", "#d62728")
        mc = mpf.make_marketcolors(up=up, down=down, inherit=True, edge='inherit', wick='inherit', volume='inherit')
        st = mpf.make_mpf_style(base_mpf_style=base_style, marketcolors=mc, gridstyle="-", facecolor=self.clr["bg"])

        return {"type": "chart_data", "df": df, "style": st, "symbol": sym, "period": period}

    def _cmd_news(self, a):
        if not a: return "Usage: news TICKER"
        sym = a[0].upper()
        # Note: Finnhub 'from' date needs to be recent for free tier.
        from_date = (datetime.now() - pd.Timedelta(days=30)).strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
        url = (f"https://finnhub.io/api/v1/company-news?symbol={sym}"
               f"&from={from_date}&to={to_date}&token={FINNHUB_API_KEY}")
        try:
            articles = curl_requests.get(url, timeout=20).json()[:10]
            if not articles: return f"No recent news found for {sym}."
            
            def sent(h):
                s = self.sentiment.polarity_scores(h)['compound']
                return "Bullish" if s > 0.3 else "Bearish" if s < -0.3 else "Neutral"
            
            return {"type": "news", "news": [{"headline": x['headline'], "url": x['url'], "sentiment": sent(x['headline'])} for x in articles]}
        except Exception as e:
            return f"Failed to fetch news: {e}"

    def _cmd_income (self,a): return self._fin("income",  a)
    def _cmd_balance(self,a): return self._fin("balance", a)
    def _cmd_cashflow(self,a): return self._fin("cashflow",a)

    def _fin(self, typ, a):
        if not a: return f"Usage: {typ} TICKER"
        sym = a[0].upper()
        tk = _safe_ticker(sym)
        
        df_func_map = {
            "income": tk.safe_income_stmt,
            "balance": tk.safe_balance_sheet,
            "cashflow": tk.safe_cashflow
        }
        df = df_func_map[typ]()

        if df.empty: return f"No {typ} data found for {sym}."
        
        # Format the dataframe for display
        df_display = (df.transpose()
            .pipe(lambda d: d.map(
                lambda x: f"{x/1e6:,.0f} M" if isinstance(x, (int, float)) and x != 0 else ('-' if isinstance(x, (int,float)) else x)
            ))
            .rename_axis('Date').reset_index()
        )
        # Convert date column to string for display
        df_display['Date'] = pd.to_datetime(df_display['Date']).dt.strftime('%Y-%m-%d')

        return {"type": "table_data",
                "title": f"{sym} – {typ.title()} Statement",
                "data": df_display,
                "fullscreen": True,
                "statement_type": typ, # For reloading
                "symbol": sym}       # For reloading

    def _cmd_options(self, a):
        if not a: return "Usage: options TICKER [DATE]"
        sym = a[0].upper(); tk = _safe_ticker(sym)
        
        try:
            expiries = tk.safe_options()
            if not expiries: return f"No options expiries found for {sym}."
        except Exception as e:
            return f"Could not fetch options data for {sym}: {e}"

        if len(a)==1:
            return ("**Available Expiries for " f"{sym}**:\n" + "\n".join(f"- `{d}`" for d in expiries) +
                    f"\n\nUse `options {sym} YYYY-MM-DD` to see a specific chain.")
        
        try:
            wanted_date = _dateparse(" ".join(a[1:])).strftime("%Y-%m-%d")
        except Exception: return "Invalid date format. Please use YYYY-MM-DD."
        
        if wanted_date not in expiries:
            # Find the nearest available date
            later_dates = [d for d in expiries if d >= wanted_date]
            if later_dates:
                wanted_date = later_dates[0]
            else: # If no later dates, take the last available one
                wanted_date = expiries[-1]

        chain = tk.option_chain(wanted_date)
        def _prep(df):
            keep = ['strike','lastPrice','bid','ask','volume','openInterest','impliedVolatility']
            df_out = df[keep].rename(columns={'lastPrice':'Last', 'openInterest':'OI', 'impliedVolatility':'IV'})
            # Format IV as percentage
            df_out['IV'] = df_out['IV'].apply(lambda x: f"{x:.1%}" if pd.notnull(x) else '-')
            return df_out.head(15)

        return {"type": "options_data",
                "options": {"date": wanted_date,
                            "calls": _prep(chain.calls),
                            "puts": _prep(chain.puts)}}
    

    def _cmd_earnings(self, args):
        if not args: return "Usage: earnings TICKER"
        sym = args[0].upper()
        tk  = _safe_ticker(sym)

        try:
            cal = tk.safe_calendar()
        except Exception:
            cal = None

        def _parse_next(cal_obj):
            # --- DEFINITIVE FIX: This check now handles both DataFrames and dictionaries ---
            if cal_obj is None or (isinstance(cal_obj, pd.DataFrame) and cal_obj.empty) or (isinstance(cal_obj, dict) and not cal_obj):
                return None
            # --- END FIX ---
            try:
                # yfinance format can vary
                if isinstance(cal_obj, pd.DataFrame) and 'Earnings Date' in cal_obj.index:
                    raw_date = cal_obj.loc['Earnings Date'].iloc[0]
                    return pd.to_datetime(raw_date).strftime("%d %b %Y")
                elif isinstance(cal_obj, dict) and (cal_obj.get('Earnings Date') or cal_obj.get('earningsDate')):
                    raw_date = (cal_obj.get('Earnings Date') or cal_obj.get('earningsDate'))[0]
                    return pd.to_datetime(raw_date).strftime("%d %b %Y")
            except (IndexError, KeyError, TypeError):
                return None
            return None

        next_date_str = _parse_next(cal) or "Not scheduled"

        AV_KEY = os.getenv("AV_API_KEY", "demo")
        eps_line, rev_line = "Last quarter EPS data unavailable.", ""
        
        try:
            # Use curl-cffi for robustness
            eps_js = curl_requests.get("https://www.alphavantage.co/query", params={"function": "EARNINGS", "symbol": sym, "apikey": AV_KEY}, timeout=20).json()
            if eps_js and eps_js.get("quarterlyEarnings"):
                last = eps_js["quarterlyEarnings"][0]
                qtr, act, est, surpr = last.get("fiscalDateEnding"), last.get("reportedEPS"), last.get("estimatedEPS"), last.get("surprisePercentage")
                if all(v is not None for v in [qtr, act, est, surpr]):
                     eps_line = (f"Last ({qtr})  ·  EPS **{float(act):.2f}** vs est **{float(est):.2f}**"
                                 f"  → surprise **{float(surpr):+.1f}%**")

            inc_js = curl_requests.get("https://www.alphavantage.co/query", params={"function": "INCOME_STATEMENT", "symbol": sym, "apikey": AV_KEY}, timeout=20).json()
            if inc_js and inc_js.get("quarterlyReports"):
                rev = inc_js["quarterlyReports"][0].get("totalRevenue")
                if rev and rev != "None":
                    rev_line = f"\n Revenue: **{float(rev)/1e6:,.0f} M**"
        except Exception as e:
            print(f"Alpha Vantage fetch failed for {sym}: {e}")

        return (
            f"### {sym} — Earnings Snapshot\n\n"
            f"Next report  ·  **{next_date_str}**\n"
            f"{eps_line}{rev_line}"
        )

    # ===============================================================
    # 3)  RENDERERS  (charts, tables, options …)
    # ===============================================================
    def _render_complex(self, frame, obj):
        if self._shutdown: return
        
        if isinstance(obj, str):
            ctk.CTkLabel(frame, text=obj, wraplength=540, justify="left").pack(padx=16, pady=10)
            return

        obj_type = obj.get("type", "")

        # --- Enhanced Chart Rendering ---
        # This block now handles both live-rendered charts ('chart') and
        # data reloaded from a saved file ('chart_data').
        if obj_type == "chart" or obj_type == "chart_data":
            fig = None
            sym = obj.get("symbol", "chart")
            
            # If it's a 'chart_data' payload from a loaded file, render the figure now.
            if obj_type == "chart_data":
                try:
                    fig, _ = mpf.plot(obj["df"], type="candle", volume=True,
                                    style=obj["style"], figsize=(8, 4.2), returnfig=True)
                    fig.set_facecolor(self.clr["bg"])
                except Exception as e:
                    # If rendering fails, show an error in the bubble instead of a blank box.
                    ctk.CTkLabel(frame, text=f"⚠️ Failed to re-render chart for {sym}:\n{e}", wraplength=520, justify="left").pack(padx=16, pady=10)
                    return
            # If it's an already-rendered 'chart' payload, just use the figure.
            else:
                fig = obj["chart"]

            # Common UI rendering logic for the figure.
            if fig:
                cvs = FigureCanvasTkAgg(fig, master=frame)
                cvs.draw()
                cvs.get_tk_widget().pack(padx=8, pady=8, fill="both", expand=True)
                bar = ctk.CTkFrame(frame, fg_color="transparent")
                bar.pack(pady=(0,6))
                ctk.CTkButton(bar, text="💾 Save…", command=lambda f=fig, s=sym: self._save_chart_dialog(f, f"{s}_{datetime.now():%Y%m%d}.png")).pack(side="left", padx=4)
                ctk.CTkButton(bar, text="📈 Live Chart", command=lambda s=sym: self._open_tradingview(s)).pack(side="left", padx=4)

        elif obj_type == "news":
            for n in obj["news"]:
                clr = {"Bullish":"#26a69a", "Bearish":"#ef5350", "Neutral":"gray"}[n['sentiment']]
                lbl = ctk.CTkLabel(frame, text="• " + n['headline'], wraplength=520, cursor="hand2", anchor="w", justify="left")
                lbl.pack(fill="x", padx=10, pady=(4,0))
                lbl.bind("<Button-1>", lambda e, u=n['url']: webbrowser.open(u))
                ctk.CTkLabel(frame, text=n['sentiment'], text_color=clr, font=("Arial",10)).pack(anchor="w", padx=22)

        elif obj_type in ["table_data", "table_placeholder"]:
            title = obj.get("title", "Table")
            data = obj.get("data")
            ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(weight="bold")).pack(pady=(8,2))
            if obj.get("fullscreen"):
                ctk.CTkButton(frame, text="Full-Screen", command=lambda d=data, t=title: self._show_full_table(t,d)).pack(pady=(0,6))
            if data is not None:
                self._small_table(frame, data)

        elif obj_type == "options_data":
            options_info = obj['options']
            date = datetime.strptime(options_info['date'], '%Y-%m-%d').strftime('%b %d, %Y')
            ctk.CTkLabel(frame, text=f"Option Chain • {date}", font=ctk.CTkFont(weight="bold")).pack(pady=(8,4))
            ctk.CTkLabel(frame, text="CALLS").pack()
            self._small_table(frame, options_info['calls'])
            ctk.CTkLabel(frame, text="PUTS").pack(pady=(6,0))
            self._small_table(frame, options_info['puts'])

    def _small_table(self, parent, df):
        if df.empty:
            ctk.CTkLabel(parent, text="No data").pack()
            return
        
        # Limit rows displayed in chat bubble
        display_df = df.head(min(len(df), 7))
        
        tv = ttk.Treeview(parent, style="Treeview",
                        columns=list(display_df.columns), show='headings',
                        height=len(display_df))
        for c in display_df.columns:
            tv.heading(c, text=c)
            tv.column(c, width=80, anchor='center') # Adjust width
        for _, r in display_df.iterrows():
            tv.insert("", "end", values=list(r))
        tv.pack(fill="x", padx=10, pady=4)

    def _show_full_table(self, title, df):
        if df is None or df.empty:
            messagebox.showinfo("No Data", "The data for this table is not available.", parent=self)
            return
        win = ctk.CTkToplevel(self); win.title(title); win.geometry("1040x640")
        win.transient(self); win.grab_set()

        tv = ttk.Treeview(win, columns=list(df.columns), show='headings')
        vsb = ttk.Scrollbar(win, orient="vertical", command=tv.yview)
        hsb = ttk.Scrollbar(win, orient="horizontal", command=tv.xview)
        tv.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        tv.pack(side="left", fill="both", expand=True)
        
        for c in df.columns:
            tv.heading(c, text=c)
            tv.column(c, anchor='w', width=120)
        for _,r in df.iterrows(): tv.insert("", "end", values=list(r))

    def _save_chart_dialog(self, fig, default_name: str):
        ftypes = [("PNG image" , "*.png"), ("PDF file"  , "*.pdf"), ("SVG vector", "*.svg")]
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".png", filetypes=ftypes,
            initialfile=default_name)
        if not path: return
        fig.savefig(path, dpi=180, bbox_inches="tight")

    def _open_tradingview(self, sym: str):
        try:
            StockChartWindow.StockChartWindow(self, sym, theme=self.current_theme)
        except Exception as exc:
            tk.messagebox.showerror("TradingView Error", f"Could not launch chart:\n{exc}", parent=self)

    def _show_fullscreen_chart(self, fig, title):
        win = ctk.CTkToplevel(self)
        win.title(f"{title} – Full-Screen"); win.geometry("1100x700")
        win.transient(self); win.grab_set()
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