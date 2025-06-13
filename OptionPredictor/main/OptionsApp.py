# app.py
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, simpledialog
import threading
import numpy as np # Import numpy if needed for default values or checks
import time # For small delay in animation
import traceback # Import traceback for detailed error logging
import pandas as pd
import sys
import os # Import os for path operations
import logging # For error logging
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo  # Import ZoneInfo for timezone handling
import subprocess # For launching external processes
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.lines import Line2D # Needed for Line2D used in educational mode
import matplotlib.dates as mdates  # Import matplotlib dates module for date formatting
import json, pathlib
from pathlib import Path
import webbrowser  # Add import for opening URLs
import threading, webview, textwrap, time, queue
# Using ttk from tkinter import ttk instead of ttkbootstrap
from functools import partial
import threading
from strategy_tester import load_icon, ICON_DIR
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="mplfinance")



from llm_helper import LLMHelper
from StockChartWindow import StockChartWindow
try:
    from strategy_tester import StrategyTesterWindow
except ImportError:
    StrategyTesterWindow = None
    print("Warning: strategy_tester.py not found.")

try:
    from NewsSentimentAnalyzer import NewsSentimentAnalyzerWindow
except ImportError:
    NewsSentimentAnalyzerWindow = None
    print("Warning: NewsSentimentAnalyzer.py not found.")

try:
    from Chatbot import FinancialChatbotApp as ChatBot
except ImportError:
    ChatBot = None
    print("Warning: ChatBot.py not found.")

def configure_global_styles(theme: str):
    """
    Apply *every* ttk style rule for light vs dark.
    Must be called *before* you re-skin each window.
    """
    style = ttk.Style()
    style.theme_use('clam')

    if theme == 'dark':
        bg, fg           = "#0f0f0f", '#ffffff'
        entry_bg         = '#0f0f0f'
        button_bg        = "#3B3939"
        header_bg        = "#0f0f0f"
        combobox_bg      = entry_bg
        notebook_sel_bg  = "#0f0f0f"
        tree_bg, field_bg= entry_bg, entry_bg
        calendar_bg      = "#0f0f0f"
        calendar_fg      = "#ffffff"
        calendar_select  = "#2e7d32"
        progressbar_trough_color = "#3c3c3c"
        progressbar_bar_color = "#138317" # Example green
        #profit_bg        = "#2e7d32"  # Trade log profit color
        #loss_bg          = "#c62828"  # Trade log loss color
    else:
        bg, fg           = '#f0f0f0', '#000000'
        entry_bg         = '#ffffff'
        button_bg        = '#e0e0e0'
        header_bg        = '#d9d9d9'
        combobox_bg      = entry_bg
        notebook_sel_bg  = '#ffffff'
        tree_bg, field_bg= entry_bg, entry_bg
        calendar_bg      = "#ffffff"
        calendar_fg      = "#000000"
        calendar_select  = "#1976d2"
        progressbar_trough_color = "#e0e0e0"
        progressbar_bar_color = "#4caf50" # Example green
        #profit_bg        = "#a5d6a7"  # Trade log profit color
        #loss_bg          = "#ef9a9a"  # Trade log loss color

    # Base
    style.configure('.', background=bg, foreground=fg, font=('Segoe UI', 9))

    # Frames & Labelframes
    style.configure('TFrame', background=bg)
    style.configure('TLabelframe', background=bg, foreground=fg)
    style.configure('TLabelframe.Label', background=bg, foreground=fg)

    # Labels
    style.configure('TLabel', background=bg, foreground=fg)

    # Buttons
    style.configure('TButton', background=button_bg, foreground=fg)
    style.map('TButton', background=[('active', header_bg)])

    # Checkbuttons & Radiobuttons
    style.configure('TCheckbutton', background=bg, foreground=fg)
    style.configure('TRadiobutton', background=bg, foreground=fg)

    style.configure(".", background=bg, foreground=fg) # Sets default for all ttk
    style.configure("TFrame", background=bg)
    style.configure("TLabelframe", background=bg, foreground=fg)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)

    # Entries
    style.configure('TEntry', fieldbackground=entry_bg, foreground=fg)

    # Comboboxes
    style.configure('TCombobox', fieldbackground=combobox_bg, foreground=fg, arrowcolor=fg)
    style.map('TCombobox',
              fieldbackground=[('readonly', combobox_bg)],
              foreground=[('readonly', fg)])

    # Notebook tabs
    style.configure('TNotebook', background=bg)
    style.configure('TNotebook.Tab', background=bg, foreground=fg)
    style.map('TNotebook.Tab',
              background=[('selected', notebook_sel_bg)],
              foreground=[('selected', fg)])

    # Treeview
    style.configure('Treeview', background=tree_bg, fieldbackground=field_bg, foreground=fg)
    style.configure('Treeview.Heading', background=header_bg, foreground=fg)
    style.map('Treeview.Heading', background=[('active', header_bg)])
    style.map('Treeview', background=[('selected', '#007acc')], foreground=[('selected', '#ffffff')])
    # Trade log profit/loss tags
    #style.configure('profit.Treeview', background=profit_bg)
    #style.configure('loss.Treeview', background=loss_bg)

    # Calendar (tkcalendar)
    style.configure('Calendar', background=calendar_bg, foreground=calendar_fg)
    style.configure('Calendar.Month', background=calendar_bg, foreground=calendar_fg)
    style.configure('Calendar.Selected', background=calendar_select, foreground=fg)
    style.map('Calendar', selectbackground=[('selected', calendar_select)])

    
    # --- TProgressbar (or modify if you have it) ---
    style.configure("TProgressbar",
                troughcolor=progressbar_trough_color,
                bordercolor=progressbar_trough_color,
                background=progressbar_bar_color
               )
    # -----------------------------------------------------------


def calculate_binomial_greeks(S, K, T, r, sigma, option_type='call', N=500):
    from MonteCarloSimulation import cached_binomial_price
    
    # Adjust N based on T to avoid tiny dt
    N = min(N, max(50, int(T * 365 * 10)))  # At least 50 steps, scale with T
    eps = 0.01 * S           # small change in price
    eps_vol = 0.01           # small change in volatility
    eps_rate = 0.0001        # small change in rate
    eps_time = min(1 / 365, T / 10)  # Dynamic eps_time to avoid negative T
    
    # Clear cache to prevent stale results
    cached_binomial_price.cache_clear()
    
    def price(s, k, t, r_, sig):
        t = max(t, 1e-3)  # Larger minimum time to avoid numerical issues
        print(f"Calling cached_binomial_price(s={s:.6f}, k={k:.6f}, t={t:.6f}, r={r_:.6f}, sig={sig:.6f}, N={N}, option_type={option_type}, american=True)")
        result = cached_binomial_price(s, k, t, r_, sig, N=N, option_type=option_type, american=True)
        if np.isnan(result):
            print("Warning: NaN result from cached_binomial_price")
        return result

    base = price(S, K, T, r, sigma)
    print(f"Base Price: {base:.6f}")

    price_up = price(S + eps, K, T, r, sigma)
    price_down = price(S - eps, K, T, r, sigma)
    delta = (price_up - price_down) / (2 * eps)
    print(f"Delta Calculation: ({price_up:.6f} - {price_down:.6f}) / (2*{eps:.4f}) = {delta:.6f}")

    gamma = (price_up - 2 * base + price_down) / (eps ** 2)
    print(f"Gamma Calculation: ({price_up:.6f} - 2*{base:.6f} + {price_down:.6f}) / ({eps:.4f}^2) = {gamma:.6f}")

    price_vega_up = price(S, K, T, r, sigma + eps_vol)
    price_vega_down = price(S, K, T, r, sigma - eps_vol)
    vega = (price_vega_up - price_vega_down) / (2 * eps_vol) / 100
    print(f"Vega Calculation: ({price_vega_up:.6f} - {price_vega_down:.6f}) / (2*{eps_vol:.4f}) = {vega:.6f}")

    price_theta = price(S, K, T - eps_time, r, sigma)
    theta = (price_theta - base) / eps_time / 100
    print(f"Theta Calculation: ({price_theta:.6f} - {base:.6f}) / ({eps_time:.6f}) = {theta:.6f}")

    price_rho_up = price(S, K, T, r + eps_rate, sigma)
    price_rho_down = price(S, K, T, r - eps_rate, sigma)
    rho = (price_rho_up - price_rho_down) / (2 * eps_rate) 
    print(f"Rho Calculation: ({price_rho_up:.6f} - {price_rho_down:.6f}) / (2*{eps_rate:.6f}) = {rho:.6f}")

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 4),
        "vega": round(vega, 4),
        "theta": round(theta, 4),
        "rho": round(rho / 100, 4)  # scaled to per 1% rate move
    }


class Tooltip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tooltip)
        widget.bind("<Leave>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.geometry(f"+{x}+{y}")
        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT,
            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
            font=("Helvetica", 9), wraplength=220
        )
        label.pack(ipadx=6, ipady=3)

    def hide_tooltip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None



import tkinter as tk
from tkinter import ttk, colorchooser, simpledialog, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.lines import Line2D
import pandas as pd
import yfinance as yf
import mplfinance as mpf
import requests
import io
import zipfile

class CandlestickChartPane(ttk.Frame):
    """
    A chart pane with always-visible timeframe buttons and an 
    expandable “Tools” panel for chart-type toggle, annotations,
    save/load/clear, undo, erase, and zoom.
    """
    def __init__(self, parent, theme, ticker="SPY"):
        super().__init__(parent, padding=0)
        self.theme = theme
        self.ticker = ticker
        self._last_period = "365d"
        self._chart_type = "candle"
        self.type_var = tk.StringVar(value=self._chart_type)

        # Annotation state & history
        self._annotations = []
        self._history = [list(self._annotations)]
        # Saved charts persistence
        self._saved_charts = {}
        self._saved_file = Path(__file__).with_name("saved_charts.json")
        if self._saved_file.exists():
            try:
                self._saved_charts = json.loads(self._saved_file.read_text())
            except:
                self._saved_charts = {}

        # Drawing defaults
        self._brush_color = "#ff0000"
        self._mode = None
        self._current_line = None

        # ── Figure & Canvas ──────────────────────────────────
        self.figure = Figure()
        self.ax = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        # ── Timeframe bar ────────────────────────────────────
        tf_bar = ttk.Frame(self, padding=2)
        tf_bar.grid(row=1, column=0, sticky="ew")
        for lbl, per in [("1W","7d"),("1M","30d"),("1Y","365d"),("5Y","5y"),("All","max")]:
            ttk.Button(tf_bar, text=lbl, width=4, command=lambda p=per: self.draw(p)).pack(side="left", padx=2)

        # Tools expand/collapse
        self._adv_visible = False
        self._adv_btn = ttk.Button(tf_bar, text="Tools ▾", width=8, command=self._toggle_advanced)
        self._adv_btn.pack(side="right", padx=2)

        # Advanced tools panel (hidden initially)
        self.advanced_frame = ttk.Frame(self, padding=2)
        self.advanced_frame.grid(row=2, column=0, sticky="ew")
        self.advanced_frame.grid_remove()
        self._build_advanced()

        # Initial draw
        self.draw(self._last_period)

    def _toggle_advanced(self):
        if self._adv_visible:
            self.advanced_frame.grid_remove()
            self._adv_btn.config(text="Tools ▾")
        else:
            self.advanced_frame.grid()
            self._adv_btn.config(text="Tools ▴")
        self._adv_visible = not self._adv_visible

    def _build_advanced(self):
        # Chart type toggles
        ttk.Radiobutton(self.advanced_frame, text="C", variable=self.type_var, value="candle",
                        command=self._on_type_change, width=2).pack(side="left", padx=2)
        ttk.Radiobutton(self.advanced_frame, text="L", variable=self.type_var, value="line",
                        command=self._on_type_change, width=2).pack(side="left", padx=2)
        ttk.Separator(self.advanced_frame, orient="vertical").pack(side="left", fill="y", padx=4)

        # Brush & Text
        ttk.Button(self.advanced_frame, text="🖌", command=self._activate_brush, width=3).pack(side="left", padx=2)
        ttk.Button(self.advanced_frame, text="🅰", command=self._activate_text,  width=3).pack(side="left", padx=2)
        ttk.Button(self.advanced_frame, text="🎨", command=self._pick_color,   width=3).pack(side="left", padx=2)
        self.size_slider = ttk.Scale(self.advanced_frame, from_=1, to=20, orient="horizontal", length=80)
        self.size_slider.set(3)
        self.size_slider.pack(side="left", padx=4)
        ttk.Separator(self.advanced_frame, orient="vertical").pack(side="left", fill="y", padx=4)

        # Save / Load / Clear
        ttk.Button(self.advanced_frame, text="💾", command=self._on_save, width=3).pack(side="left", padx=2)
        ttk.Button(self.advanced_frame, text="Load", command=self._open_load_window, width=6).pack(side="left", padx=2)
        ttk.Button(self.advanced_frame, text="🗑", command=self._clear_chart, width=3).pack(side="left", padx=2)
        ttk.Separator(self.advanced_frame, orient="vertical").pack(side="left", fill="y", padx=4)

        # Undo / Erase / Zoom
        ttk.Button(self.advanced_frame, text="↶ Undo", command=self._undo, width=6).pack(side="left", padx=2)
        ttk.Button(self.advanced_frame, text="🧹 Erase", command=self._activate_erase, width=8).pack(side="left", padx=2)
        ttk.Button(self.advanced_frame, text="🔍", command=self._activate_zoom, width=3).pack(side="left", padx=2)

    # ── Core functionality ────────────────────────────────────

    def _save_to_file(self):
        try:
            self._saved_file.write_text(json.dumps(self._saved_charts))
        except Exception as e:
            messagebox.showerror("Save Error", f"Could not persist charts:\n{e}")

    def _on_type_change(self):
        self._chart_type = self.type_var.get()
        self.draw(self._last_period)

    def set_ticker(self, ticker):
        self.ticker = ticker
        self.draw(self._last_period)

    def draw(self, period):
        self.ax.clear()
        self._last_period = period
        bg = "#0f0f0f" if self.theme=="dark" else "#ffffff"
        fg = "#ffffff" if self.theme=="dark" else "#000000"
        self.figure.patch.set_facecolor(bg)
        self.ax.set_facecolor(bg)
        self.ax.tick_params(colors=fg)
        for spine in self.ax.spines.values():
            spine.set_color(fg)

        # Data fetch
        df = self._fetch_data_from_yf(period) 
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            df = self._fetch_data_from_stooq(period)
        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            self.ax.text(0.5,0.5,"Chart unavailable", ha="center", va="center", color=fg)
        else:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df.columns = [str(c).lower() for c in df.columns]
            for col in ("open","high","low","close"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            subset = [c for c in ("open","high","low","close") if c in df.columns]
            if subset:
                df.dropna(subset=subset, inplace=True)

            mpf.plot(df,
                     type=("line" if self._chart_type=="line" else "candle"),
                     ax=self.ax, volume=False,
                     style=("nightclouds" if self.theme=="dark" else "charles"),
                     datetime_format="%Y-%m-%d",
                     warn_too_much_data=len(df))

        self.figure.tight_layout()
        self.canvas.draw_idle()

    def set_theme(self, theme: str):
        if theme in ("light","dark") and theme != self.theme:
            self.theme = theme
            self.draw(self._last_period)

    def _fetch_data_from_yf(self, period):
        try:
            df = yf.download(self.ticker, period=period, interval="1d",
                             auto_adjust=False, progress=False)
            return df if isinstance(df, pd.DataFrame) and not df.empty else None
        except:
            return None

    def _fetch_data_from_stooq(self, period):
        try:
            url = f"https://stooq.com/q/d/l/?s={self.ticker.lower()}.us&i=d"
            raw = requests.get(url, timeout=15).content
            if raw[:2]==b"PK":
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    raw = zf.read(zf.namelist()[0])
            df = (pd.read_csv(io.BytesIO(raw), parse_dates=["Date"])
                    .set_index("Date").sort_index())
            if period=="7d":    df = df.iloc[-7:]
            elif period=="30d": df = df.iloc[-30:]
            elif period=="365d":df = df.iloc[-252:]
            return df
        except:
            return None

    # ── Annotation & Undo ─────────────────────────────────────

    def _disable_current_mode(self):
        if self._mode=="brush":
            for cid in (self._cid_press, self._cid_move, getattr(self, "_cid_release", None)):
                if cid: self.canvas.mpl_disconnect(cid)
        elif self._mode=="text":
            self.canvas.mpl_disconnect(getattr(self, "_cid_press", None))
        elif self._mode=="erase":
            for cid in (self._er_press, self._er_move, self._er_rel):
                if cid: self.canvas.mpl_disconnect(cid)
            if hasattr(self, "_erase_rect"):
                self._erase_rect.remove()
                del self._erase_rect
            self.canvas_widget.configure(cursor="")
        self._mode = None

    def _undo(self):
        if len(self._history)<=1:
            return
        self._history.pop()
        last = self._history[-1]
        for art in list(self._annotations):
            if art not in last:
                try: art.remove()
                except: pass
        self._annotations = list(last)
        self.canvas.draw_idle()

    def _activate_brush(self):
        if self._mode=="brush":
            self._disable_current_mode(); return
        self._disable_current_mode()
        self._mode="brush"; self.canvas_widget.focus_set()
        self._cid_press   = self.canvas.mpl_connect("button_press_event",   self._brush_press)
        self._cid_move    = self.canvas.mpl_connect("motion_notify_event",  self._brush_move)
        self._cid_release = self.canvas.mpl_connect("button_release_event", self._brush_release)

    def _brush_press(self, evt):
        if evt.inaxes!=self.ax or self._mode!="brush": return
        self._history.append(list(self._annotations))
        lw = int(float(self.size_slider.get()))
        line = Line2D([evt.xdata],[evt.ydata], color=self._brush_color, linewidth=lw, solid_capstyle="round")
        self.ax.add_line(line)
        self._annotations.append(line)
        self._current_line=line; self.canvas.draw_idle()

    def _brush_move(self, evt):
        if evt.inaxes!=self.ax or self._mode!="brush" or not self._current_line: return
        xs,ys=self._current_line.get_data(); xs.append(evt.xdata); ys.append(evt.ydata)
        self._current_line.set_data(xs,ys); self.canvas.draw_idle()

    def _brush_release(self, evt):
        if self._mode=="brush": self._current_line=None

    def _activate_text(self):
        if self._mode=="text":
            self._disable_current_mode(); return
        self._disable_current_mode()
        self._mode="text"; self.canvas_widget.focus_set()
        self._cid_press=self.canvas.mpl_connect("button_press_event", self._add_text)

    def _add_text(self, evt):
        if evt.inaxes!=self.ax or self._mode!="text": return
        self._history.append(list(self._annotations))
        txt=simpledialog.askstring("Text","Annotation text:")
        if not txt: return
        fs=int(float(self.size_slider.get()))
        text=self.ax.text(evt.xdata,evt.ydata,txt, color=self._brush_color,fontsize=fs,
                          va="center",ha="center")
        self._annotations.append(text); self.canvas.draw_idle()

    def _pick_color(self):
        c=colorchooser.askcolor()[1]
        if c: self._brush_color=c

    def _clear_chart(self):
        for art in self._annotations:
            try: art.remove()
            except: pass
        self._annotations.clear(); self.draw(self._last_period)

    # ── Erase ────────────────────────────────────────────────

    def _activate_erase(self):
        if self._mode=="erase":
            self._disable_current_mode(); return
        self._disable_current_mode()
        self._mode="erase"
        size=int(float(self.size_slider.get()))
        self.canvas_widget.configure(cursor=f"circle {size}")
        self._er_press=self.canvas.mpl_connect("button_press_event",   self._erase_press)
        self._er_move =self.canvas.mpl_connect("motion_notify_event",  self._erase_move)
        self._er_rel  =self.canvas.mpl_connect("button_release_event",self._erase_release)

    def _erase_press(self,evt):
        if evt.inaxes!=self.ax or self._mode!="erase" or evt.xdata is None: return
        self._erase_start=(evt.xdata,evt.ydata)
        from matplotlib.patches import Rectangle
        self._erase_rect=Rectangle((evt.xdata,evt.ydata),0,0,
                                   linewidth=1,edgecolor="red",facecolor="none",linestyle="--")
        self.ax.add_patch(self._erase_rect); self.canvas.draw_idle()

    def _erase_move(self,evt):
        if (evt.inaxes!=self.ax or self._mode!="erase"
            or not hasattr(self,"_erase_rect") or evt.xdata is None): return
        x0,y0=self._erase_start; w=evt.xdata-x0; h=evt.ydata-y0
        self._erase_rect.set_width(w); self._erase_rect.set_height(h)
        if w<0: self._erase_rect.set_x(evt.xdata)
        if h<0: self._erase_rect.set_y(evt.ydata)
        self.canvas.draw_idle()

    def _erase_release(self,evt):
        if (evt.inaxes!=self.ax or self._mode!="erase"
            or not hasattr(self,"_erase_rect") or evt.xdata is None): return
        self._history.append(list(self._annotations))
        x0=self._erase_rect.get_x(); y0=self._erase_rect.get_y()
        w=self._erase_rect.get_width(); h=self._erase_rect.get_height()
        xmin,xmax=sorted([x0,x0+w]); ymin,ymax=sorted([y0,y0+h])
        survivors=[]
        for art in self._annotations:
            if isinstance(art,Line2D):
                xs,ys=art.get_data()
                if any(xmin<=x<=xmax and ymin<=y<=ymax for x,y in zip(xs,ys)):
                    art.remove(); continue
            else:
                x,y=art.get_position()
                if xmin<=x<=xmax and ymin<=y<=ymax:
                    art.remove(); continue
            survivors.append(art)
        self._annotations=survivors
        self._erase_rect.remove(); del self._erase_rect
        self._mode=None; self.canvas_widget.configure(cursor="")
        self.canvas.draw_idle()

    # ── Zoom/Pan ─────────────────────────────────────────────

    def _activate_zoom(self):
        if self._mode=="zoom":
            for cid in (self._zoom_cid,
                        getattr(self,"_pan_press_cid",None),
                        getattr(self,"_pan_move_cid",None),
                        getattr(self,"_pan_release_cid",None)):
                if cid: self.canvas.mpl_disconnect(cid)
            self._mode=None; self.canvas_widget.configure(cursor="")
            self.ax.set_xlim(self._zoom_orig_xlim); self.ax.set_ylim(self._zoom_orig_ylim)
            self.canvas.draw_idle(); return
        self._disable_current_mode(); self._mode="zoom"
        self._zoom_orig_xlim=self.ax.get_xlim(); self._zoom_orig_ylim=self.ax.get_ylim()
        self.canvas_widget.configure(cursor="tcross")
        self._zoom_cid       = self.canvas.mpl_connect("scroll_event",     self._on_zoom)
        self._pan_press_cid  = self.canvas.mpl_connect("button_press_event",self._pan_press)
        self._pan_move_cid   = self.canvas.mpl_connect("motion_notify_event",self._pan_move)
        self._pan_release_cid=self.canvas.mpl_connect("button_release_event",self._pan_release)

    def _pan_press(self,evt):
        if self._mode!="zoom" or evt.inaxes!=self.ax: return
        if evt.button==1:
            self._pan_start=(evt.xdata,evt.ydata)
            self._pan_xlim_start=self.ax.get_xlim()
            self._pan_ylim_start=self.ax.get_ylim()
        elif evt.button==3:
            self.ax.set_xlim(self._zoom_orig_xlim); self.ax.set_ylim(self._zoom_orig_ylim)
            self.canvas.draw_idle()

    def _pan_move(self,evt):
        if (self._mode!="zoom" or not hasattr(self,"_pan_start")
            or evt.button!=1 or evt.inaxes!=self.ax): return
        x0,y0=self._pan_start; dx=x0-evt.xdata; dy=y0-evt.ydata
        x0_lim,x1_lim=self._pan_xlim_start; y0_lim,y1_lim=self._pan_ylim_start
        self.ax.set_xlim(x0_lim+dx,x1_lim+dx); self.ax.set_ylim(y0_lim+dy,y1_lim+dy)
        self.canvas.draw_idle()

    def _pan_release(self,evt):
        if hasattr(self,"_pan_start"): del self._pan_start

    def _on_zoom(self,evt):
        if (self._mode!="zoom" or evt.inaxes!=self.ax or
            evt.xdata is None or evt.ydata is None): return
        factor = 0.9 if evt.button=="up" else 1.1
        x0,x1=self.ax.get_xlim(); y0,y1=self.ax.get_ylim()
        xd,yd=evt.xdata,evt.ydata
        nx0=xd-(xd-x0)*factor; nx1=xd+(x1-xd)*factor
        ny0=yd-(yd-y0)*factor; ny1=yd+(y1-yd)*factor
        self.ax.set_xlim(nx0,nx1); self.ax.set_ylim(ny0,ny1)
        self.canvas.draw_idle()

    # ── Save/Load ──────────────────────────────────────────────

    def _on_save(self):
        name=simpledialog.askstring("Save Chart","Name this view:")
        if not name or name in self._saved_charts: return
        self._saved_charts[name]={
            "ticker":self.ticker,"period":self._last_period,
            "type":self._chart_type,
            "annotations":[self._serialize_artist(a) for a in self._annotations]
        }
        self._save_to_file()
        messagebox.showinfo("Saved",f"Chart saved as “{name}”.")

    def _open_load_window(self):
        win=tk.Toplevel(self); win.title("Saved Charts"); win.transient(self)
        for name,meta in self._saved_charts.items():
            f=ttk.Frame(win,padding=4); f.pack(fill="x",padx=8,pady=2)
            ttk.Label(f,text=f"{name} [{meta['ticker']}]",width=25).pack(side="left")
            ttk.Button(f,text="Load",width=6,
                       command=lambda n=name,w=win:(self.load_saved(n),w.destroy())
                      ).pack(side="left",padx=4)
            ttk.Button(f,text="➖",width=3,
                       command=lambda n=name,fr=f:(
                           messagebox.askyesno("Delete",f"Remove “{n}”?"),
                           self._saved_charts.pop(n,None),
                           self._save_to_file(),
                           fr.destroy()
                       )
                      ).pack(side="left")

    def load_saved(self,name):
        meta=self._saved_charts.get(name)
        if not meta:
            messagebox.showerror("Not found",f"No saved chart “{name}”"); return
        # clear annotations
        for art in self._annotations:
            try: art.remove()
            except: pass
        self._annotations.clear()
        # restore settings
        self.ticker=meta["ticker"]
        self._last_period=meta["period"]
        self._chart_type=meta["type"]
        self.type_var.set(self._chart_type)
        self.draw(self._last_period)
        # reapply
        for art in meta["annotations"]:
            if art["kind"]=="line":
                ln,=self.ax.plot(art["xs"],art["ys"],color=art["color"],linewidth=art["lw"])
                self._annotations.append(ln); self._history.append(list(self._annotations))
            else:
                tx=self.ax.text(art["x"],art["y"],art["text"],color=art["color"],fontsize=art["size"])
                self._annotations.append(tx); self._history.append(list(self._annotations))
        self.canvas.draw_idle()
        if hasattr(self.master,"config"):
            self.master.config(text=f"{self.ticker} Chart")

    def _serialize_artist(self,artist):
        if isinstance(artist,Line2D):
            xs,ys=artist.get_data()
            return {"kind":"line","xs":list(xs),"ys":list(ys),
                    "color":artist.get_color(),"lw":artist.get_linewidth()}
        else:
            x,y=artist.get_position()
            return {"kind":"text","x":x,"y":y,
                    "text":artist.get_text(),
                    "color":artist.get_color(),
                    "size":artist.get_fontsize()}


class SettingsManager:
    """Tiny JSON persistence for user prefs across app restarts."""
    _FILE = pathlib.Path.home() / ".option_analyzer_settings.json"

    _DEFAULTS = {
        "user_name": "Trader",
        "theme": "light",
        "timezone": "America/Vancouver",
        "default_ticker": "SPY",            
        "watchlist": "SPY|^VIX"             
    }



    def __init__(self):
        self.data = self._DEFAULTS.copy()
        if self._FILE.exists():
            try:
                self.data.update(json.loads(self._FILE.read_text()))
            except Exception:
                pass  # Corrupt settings ➜ fallback to defaults

    def save(self):
        try:
            self._FILE.write_text(json.dumps(self.data))
        except Exception:
            print("⚠ Could not write settings file.")

    # convenient shortcuts
    def get(self, k, default=None):
        return self.data.get(k, default)

    def set(self, k, v):
        self.data[k] = v
        self.save()




class HomeDataManager:
    """Centralised, lightweight fetchers for the dashboard."""
    def __init__(self):
        from datetime import datetime
        self.now = datetime.now

    def get_latest_price(self, ticker: str) -> float | None:
        """
        Return the most-recent close for any ticker via yfinance (1d).
        """
        try:
            import yfinance as yf
            h = yf.Ticker(ticker).history(period="1d", auto_adjust=False)
            return float(h["Close"].iloc[-1])
        except Exception:
            return None

    def get_index_prices(self):
        """
        Return the latest SPY & VIX close prices as plain floats.
        Falls back to (None, None) if yfinance or the network is unavailable.
        """
        try:
            import yfinance as yf

            # Using Ticker().history keeps the columns simple (no MultiIndex)
            spy_price = yf.Ticker("SPY").history(period="1d")["Close"].iloc[-1]
            vix_price = yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]

            return float(spy_price), float(vix_price)
        except Exception:
            return None, None


    # ── News  ────────────────────────────────────────────────────────────
    def get_news_headlines(self, n: int = 20) -> tuple[list[tuple[str, float | None, str]], float | None]:
        """
        Return (headlines_list, overall_score)

        headlines_list : up to *n* entries of (headline, sentiment, url)
        overall_score  : average sentiment of the last 50 stories (or None)

        Sentiment scores are –1 … +1 (positive = bullish).
        """
        import datetime as dt, time, math, webbrowser

        # ── nested scorer (prefer your in-house analyser) ────────────────
        def _score(txt: str) -> float | None:
            try:
                from NewsSentimentAnalyzer import score_text
                return float(score_text(txt))
            except Exception:
                try:
                    from nltk.sentiment import SentimentIntensityAnalyzer
                    return SentimentIntensityAnalyzer().polarity_scores(txt)["compound"]
                except Exception:
                    return None

        cutoff_ts = dt.datetime.now().timestamp() - 86_400         # last 24 h
        rows: list[tuple[str, float | None, str]] = []             # table rows
        scores: list[float] = []                                   # for overall

        def _append(title: str, link: str):
            s = _score(title)
            rows.append((title, s, link))
            if s is not None:
                scores.append(s)

        # ── news feed via yfinance first ────────────────────────────────
        try:
            import yfinance as yf
            for item in (yf.Ticker("SPY").news or []):
                ts = item.get("providerPublishTime", 0)
                if ts >= cutoff_ts:
                    _append(item["title"], item.get("link", ""))
        except Exception:
            pass

        # ── fallback RSS if needed ──────────────────────────────────────
        if not rows:
            try:
                import feedparser
                rss = feedparser.parse(
                    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US"
                )
                for entry in rss.entries:
                    ts = time.mktime(getattr(entry, "published_parsed", time.gmtime(0)))
                    if ts >= cutoff_ts:
                        _append(entry.title, entry.link)
            except Exception:
                pass

                # newest first
        rows.sort(key=lambda x: x[0])     # already time-ordered
        if len(rows) < n:
            # ----- TOP-UP with older stories until we reach *n* --------------  NEW
            leftovers = []
            try:
                import yfinance as yf
                leftovers = yf.Ticker("SPY").news or []
            except Exception:
                pass
            try:
                import feedparser, time as _t
                rss2 = feedparser.parse(
                    "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US"
                ).entries
                leftovers += rss2
            except Exception:
                pass

            # iterate oldest→newest so we don't duplicate
            for item in sorted(leftovers, key=lambda d: d.get("providerPublishTime", 0)):
                title = item.get("title") or getattr(item, "title", "")
                link  = item.get("link")  or getattr(item, "link", "")
                if any(r[0] == title for r in rows):      # already added
                    continue
                rows.append((title, _score(title), link))
                if len(rows) >= n:
                    break
        # ---------------------------------------------------------------------

        top_rows = rows[:n]
        overall  = sum(scores) / len(scores) if scores else None
        return top_rows, overall



class HomeDashboard(ttk.Frame):
    """
    A professionally organized visual dashboard that provides a clear, at-a-glance
    view of market information and application actions.
    """
    def __init__(self, parent, controller):
        super().__init__(parent, padding="15 15 15 15")
        self.controller = controller
        self.data_mgr = controller.data_mgr
        # NYSE open hours in Eastern Time
        self._ny_open  = dt_time(hour=9,  minute=30)
        self._ny_close = dt_time(hour=16, minute=0)


        
        # Configure the main frame's grid layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1) # Main content area should expand

        self._build_ui()
        self._refresh()          # Initial data load
        self._auto_refresh()     # Start 30-second refresh loop

    # --- UI Construction ---

    def _build_ui(self):
        """Constructs the UI by building and placing modular components."""
        self._build_header()
        self._build_overview()
        self._build_main_panes()
        
        # Add a visual separator before the footer
        ttk.Separator(self).grid(row=3, column=0, pady=15, sticky="ew")
        
        self._build_footer()
        
    def _build_header(self):
        """Builds the top header bar with title, clock, and status icons."""
        header_frame = ttk.Frame(self)
        header_frame.grid(row=0, column=0, sticky="ew")
        header_frame.columnconfigure(1, weight=1) # Spacer column

        self.header_lbl = ttk.Label(header_frame, text="", style="Title.TLabel")
        self.header_lbl.grid(row=0, column=0, sticky="w")
        
        self.time_lbl = ttk.Label(header_frame, text="", style="Secondary.TLabel")
        self.time_lbl.grid(row=0, column=2, sticky="e", padx=10)

        # ── Live Market Status Indicator ───────────────────────────
        # Use our current theme’s background color; ttk styles don’t expose 'background' as a cget
        bg_color = self.controller.theme_settings()['bg']
        self.market_canvas = tk.Canvas(
            header_frame,
            width=12, height=12,
            highlightthickness=0,
            bg=bg_color
        )

        self.market_canvas.grid(row=0, column=3, sticky="e", padx=(5,0))
        self.market_circle = self.market_canvas.create_oval(2,2,10,10, fill="red", outline="")
        self.market_lbl    = ttk.Label(header_frame, text="Closed", style="Status.TLabel")
        self.market_lbl.grid(row=0, column=4, sticky="e", padx=(2,10))

        self._build_wifi_icon(header_frame)
        self.wifi_label.grid(row=0, column=5, sticky="e")
        self._start_clock()

        
    def _build_overview(self):
        """Builds the market overview section with stat cards."""
        overview_frame = ttk.Frame(self)
        overview_frame.grid(row=1, column=0, sticky="ew", pady=15)
        overview_frame.columnconfigure(0, weight=1)
        overview_frame.columnconfigure(1, weight=1)

        # Indices Card
        indices_card = ttk.LabelFrame(overview_frame, text="Market Indices")
        indices_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.index_lbl = ttk.Label(indices_card, text="Loading...", padding=10, style="Stat.TLabel")
        self.index_lbl.pack(expand=True, fill="both")
        
        # Watchlist Card
        watchlist_card = ttk.LabelFrame(overview_frame, text="Watchlist")
        watchlist_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        self.watchlist_lbl = ttk.Label(watchlist_card, text="Loading...", padding=10, style="Stat.TLabel", wraplength=400, justify="left")
        self.watchlist_lbl.pack(expand=True, fill="both")

    def _build_main_panes(self):
        """Builds the main split-pane view for news and charts."""
        main_panes = ttk.PanedWindow(self, orient="horizontal")
        main_panes.grid(row=2, column=0, sticky="nsew")

        # --- Left Pane: Market News ---
        news_box = ttk.LabelFrame(main_panes, text="Market News (Recent First)", padding=10)
        news_box.columnconfigure(0, weight=1)
        news_box.rowconfigure(1, weight=1) # Treeview row
        main_panes.add(news_box, weight=1)

        self.overall_news_lbl = ttk.Label(news_box, text="Overall sentiment: …")
        self.overall_news_lbl.grid(row=0, column=0, sticky="w", pady=(0, 5))

        cols = ("headline", "sentiment")
        self.news_tv = ttk.Treeview(news_box, columns=cols, show="headings", height=15)
        self.news_tv.heading("headline", text="Headline")
        self.news_tv.heading("sentiment", text="Score")
        self.news_tv.column("headline", width=400, stretch=True)
        self.news_tv.column("sentiment", width=80, anchor="e", stretch=False)
        self.news_tv.bind("<Double-1>", self._open_selected_article)
        
        vsb = ttk.Scrollbar(news_box, orient="vertical", command=self.news_tv.yview)
        self.news_tv.configure(yscrollcommand=vsb.set)

        self.news_tv.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")

        # --- Right Pane: Candlestick Chart ---
        self.chart_box = ttk.LabelFrame(main_panes, text="Chart", padding=5)
        self.chart_box.columnconfigure(0, weight=1)
        self.chart_box.rowconfigure(0, weight=1)
        main_panes.add(self.chart_box, weight=1)
        
        default_ticker = self.controller.settings.get('default_ticker', 'SPY')
        self.chart_box.config(text=f"{default_ticker} Chart")
        self.chart_pane = CandlestickChartPane(
            self.chart_box,
            theme=self.controller.current_theme,
            ticker=default_ticker
        )
        self.chart_pane.grid(row=0, column=0, sticky="nsew")

    def _build_footer(self):
        """Builds the bottom footer with quick actions and settings."""
        footer_frame = ttk.Frame(self)
        footer_frame.grid(row=4, column=0, sticky="ew")
        footer_frame.columnconfigure(1, weight=1) # Spacer column

        # Settings button on the left
        ttk.Button(footer_frame, text="⚙ Settings",
                   command=self.controller.open_settings_window, style="Pill.TButton")\
                   .grid(row=0, column=0, sticky="w")

        # Quick actions on the right
        actions_frame = ttk.Frame(footer_frame)
        actions_frame.grid(row=0, column=2, sticky="e")
        
        btn_map = {
            "📊 New Analysis": self.controller.open_input_window,
            "📰 Sentiment Analyzer": self.controller.launch_news_sentiment_analyzer,
            "📐 Strategy Builder": self.controller.launch_strategy_builder,
            "🧪 Strategy Tester": self.controller.launch_strategy_tester,
            "💬 Chatbot": self.controller.launch_chatbot,
        }

        for i, (text, cmd) in enumerate(btn_map.items()):
            ttk.Button(actions_frame, text=text, command=cmd).pack(side="left", padx=(5, 0))

    def _build_wifi_icon(self, parent_frame):
        """Initializes the Wi-Fi icon and its related resources."""
        fg_color = "#ffffff" if self.controller.current_theme == "dark" else "#000000"
        
        # Determine the background color reliably from the current theme
        bg_color = "#0f0f0f" if self.controller.current_theme == 'dark' else '#f0f0f0'

        self.wifi_icons = {
            key: load_icon(ICON_DIR / f"wifi_{key}.png", tint_color=fg_color)
            for key in ("disconnected", "weak", "medium", "strong", "secure")
        }

        self.wifi_label = tk.Label(parent_frame, bd=0)
        
       
        self.wifi_label.configure(bg=bg_color)

        # Only set the last status if icons were loaded successfully
        if self.wifi_icons.get("disconnected"):
            self._last_wifi_status = "disconnected"
            self._update_wifi_icon("disconnected")
        
        self._wifi_queue = queue.Queue()
        self._poll_wifi_queue()
        self.check_wifi()

    
    # --- Core Logic & Data Refresh ---

    def _start_clock(self):
        self._update_time()

    def _update_time(self):
        try:
            tz = ZoneInfo(self.controller.settings.get("timezone"))
            now = datetime.now(tz)
        except Exception:
            now = datetime.now()
        self.time_lbl.config(text=now.strftime("%b %d, %Y  %H:%M:%S"))
        # ← new: refresh the market‐open indicator
        self._update_market_status(now)
        self.after(1000, self._update_time)

    def _update_market_status(self, now_local):
        # convert to New York time
        ny = now_local.astimezone(ZoneInfo("America/New_York"))
        # default: closed
        status, color = "Closed", "red"
        if ny.weekday() < 5:  # Mon–Fri
            t = ny.time()
            if self._ny_open <= t <= self._ny_close:
                status, color = "Open", "green"
            else:
                status, color = "After-Hours", "orange"
        # apply it
        self.market_canvas.itemconfig(self.market_circle, fill=color)
        self.market_lbl.config(text=status, foreground=color)



    def check_wifi(self):
        def worker():
            import time, requests
            try:
                start = time.time()
                resp = requests.get("https://www.google.com", timeout=2.0)
                lat = (time.time() - start) * 1000
                if not resp.ok: status = "disconnected"
                elif resp.url.startswith("https://"): status = "secure"
                elif lat < 100: status = "strong"
                elif lat < 300: status = "medium"
                else: status = "weak"
            except Exception:
                status = "disconnected"
            self._wifi_queue.put(status)
        threading.Thread(target=worker, daemon=True).start()
        self.after(5000, self.check_wifi)

    def _poll_wifi_queue(self):
        try:
            while True:
                status = self._wifi_queue.get_nowait()
                self._update_wifi_icon(status)
        except queue.Empty:
            pass
        self.after(100, self._poll_wifi_queue)

    def _update_wifi_icon(self, status_key):
        if not hasattr(self, "wifi_label"): return
        self._last_wifi_status = status_key
        icon = self.wifi_icons.get(status_key)
        if icon:
            self.wifi_label.configure(image=icon)
            self.wifi_label.image = icon

    def apply_custom_theme(self):
        """
        Called when the application theme changes. Re-tints icons and updates
        the background of the tk.Label holding the icon.
        """
        fg = "#ffffff" if self.controller.current_theme == "dark" else "#000000"
        # Determine the background color reliably from the current theme
        bg = "#0f0f0f" if self.controller.current_theme == 'dark' else '#f0f0f0'

        # FIX: Explicitly update the label's background color during theme changes.
        if hasattr(self, "wifi_label"):
            self.wifi_label.configure(bg=bg)

        # Re-tint all icons
        for key in self.wifi_icons:
            path = ICON_DIR / f"wifi_{key}.png"
            self.wifi_icons[key] = load_icon(path, tint_color=fg)
            
        # Re-apply the current icon to the label
        if hasattr(self, "_last_wifi_status"):
            self._update_wifi_icon(self._last_wifi_status)


    def _open_selected_article(self, event=None):
        selected_item = self.news_tv.selection()
        if not selected_item: return
        # Assuming URL is the third value (hidden) in the Treeview row
        item_values = self.news_tv.item(selected_item[0], "values")
        if len(item_values) > 2:
            url = item_values[2]
            if url and url.startswith("http"):
                webbrowser.open(url)

    def _refresh(self):
        # Header
        self.header_lbl.config(text=f"Welcome, {self.controller.user_name}!")
        
        # Market Overview Cards
        spy, vix = self.data_mgr.get_index_prices()
        self.index_lbl.config(text=f"SPY {spy:,.2f}   |   VIX {vix:,.2f}" if spy is not None else "Indices: N/A")

        # Watchlist Card
        watchlist_tickers = [t.strip() for t in self.controller.settings.get("watchlist", "").split("|") if t.strip()]
        price_parts = []
        valid_tickers = []
        for ticker in watchlist_tickers:
            price = self.data_mgr.get_latest_price(ticker)
            if price is not None:
                price_parts.append(f"{ticker} {price:,.2f}")
                valid_tickers.append(ticker)
            # This version omits the disruptive messagebox on auto-refresh for a smoother UX
        if len(valid_tickers) != len(watchlist_tickers):
            self.controller.settings.set("watchlist", "|".join(valid_tickers))
        self.watchlist_lbl.config(text=" | ".join(price_parts) if price_parts else "No valid tickers in watchlist.")
        
        # News Panel
        rows, overall = self.data_mgr.get_news_headlines(20)
        if overall is None:
            txt, color = "Overall sentiment: N/A", "gray"
        elif overall > 0.25:
            txt, color = f"Overall sentiment: Bullish ({overall:+.2f})", "green"
        elif overall < -0.25:
            txt, color = f"Overall sentiment: Bearish ({overall:+.2f})", "red"
        else:
            txt, color = f"Overall sentiment: Neutral ({overall:+.2f})", "orange"
        self.overall_news_lbl.config(text=txt, foreground=color)

        self.news_tv.delete(*self.news_tv.get_children())
        for title, score, url in rows:
            tag = ""
            if score is not None:
                if score > 0.25: tag = "pos"
                elif score < -0.25: tag = "neg"
                else: tag = "neu"
            self.news_tv.insert("", "end", values=(title, f"{score:+.2f}" if score is not None else "N/A", url), tags=(tag,))
        self.news_tv.tag_configure("pos", foreground="green")
        self.news_tv.tag_configure("neg", foreground="red")
        self.news_tv.tag_configure("neu", foreground="orange")
        
    def _auto_refresh(self):
        self._refresh()
        self.after(30_000, self._auto_refresh)


# Import logic functions from the separate file
try:
    from MonteCarloSimulation import (
        fetch_ticker_data, calculate_drift_and_volatility,
        calculate_simulation_data, plot_simulation_paths,
        #binomial_tree_option_price,
        plot_distribution,
        generate_profit_heatmap_data, plot_profit_heatmap, 
        generate_option_surface_data, plot_option_surface_3d,
        calculate_trigger_stats_correctly as recalculate_trigger_price_correctly,
        set_max_paths, cached_binomial_price, 
        generate_volatility_surface_data,
        plot_volatility_surface_3d,   
        #cached_lsm_price

    )
except ImportError:
    messagebox.showerror("Import Error", "Could not find 'MonteCarloSimulation.py'. Make sure it's in the same directory as this script.")
    exit()

class OptionAnalyzerApp:
    def __init__(self, root):
        # -------------------------------------------------
        # 1️⃣  PERSISTENT SETTINGS (must come first!)
        self.settings      = SettingsManager()         # NEW → now exists
        self.current_theme = self.settings.get("theme", "light")
        # a BooleanVar so other code can read/update dark-mode setting
        self.is_dark_mode_var = tk.BooleanVar(value=(self.current_theme == "dark"))
        # -------------------------------------------------

        self.theme_callbacks = []  # Store callbacks for theme updates
        self.strategy_tester_instance = None
        self.root = root
        self.root.title("Option Analyzer")
        self.root.geometry("900x800")

        # handy access later
        self.data_mgr  = HomeDataManager()
        self.user_name = self.settings.get("user_name", "Trader")

        # Apply base ttk styles once at start-up
        configure_global_styles(self.current_theme)



        self.current_theme = self.settings.get("theme", "light") 
        self.theme_callbacks = []  # Store callbacks for theme updates
        self.strategy_tester_instance = None
        self.root = root
        self.root.title("Option Analyzer")
        self.root.geometry("900x800") # Give main window a bit more space
        self.llm = LLMHelper(model="deepseek-q4ks")

        self.settings    = SettingsManager()      # persistent prefs
        self.data_mgr    = HomeDataManager()      # live data fetcher
        self.user_name   = self.settings.get("user_name", "Trader")
        # --------------------------------


        # keep track of all child windows for theme propagation
        self.child_windows: list = []


        # --- Style Configuration ---
        style = ttk.Style()
        try:
            # Attempt to use a modern theme
            available_themes = style.theme_names()
            if 'clam' in available_themes: style.theme_use('clam')
            elif 'vista' in available_themes: style.theme_use('vista') # Good on Windows
            elif 'aqua' in available_themes: style.theme_use('aqua') # Good on Mac
            else: style.theme_use('default')
        except tk.TclError:
            print(" ttk themes not fully available, using default.")


        style.configure("TButton", padding=6, relief="flat", font=('Helvetica', 10))
        style.map("TButton", background=[('active', '#e0e0e0')]) # Subtle hover effect
        style.configure("TLabel", padding=3, font=('Helvetica', 10))
        style.configure("Title.TLabel", font=('Helvetica', 16, "bold")) # Specific style for title
        style.configure("Status.TLabel", font=('Helvetica', 10)) # Specific style for status
        style.configure("TEntry", padding=5, font=('Helvetica', 10))
        style.configure("TFrame", background=style.lookup('TLabel', 'background')) # Match frame bg

        

        # --- Main Layout (Dashboard) ---
        self.main_frame = ttk.Frame(root, padding="0 0 0 0", style="TFrame")
        self.main_frame.pack(expand=True, fill=tk.BOTH)

        self.dashboard = HomeDashboard(self.main_frame, self)
        self.dashboard.pack(expand=True, fill=tk.BOTH)

        # Status bar (must exist before animate_loading can update it)
        self.status_label = ttk.Label(self.root, text="Ready.", style="Status.TLabel", anchor="center")
        self.status_label.pack(fill="x", pady=4)


        # animation state
        self.is_loading     = False
        self.animation_chars = ["⣾","⣽","⣻","⢿","⡿","⣟","⣯","⣷"]
        self.animation_step = 0
        # ─────────────────────────────────────────────────────

        # --- other State Variables ---
        self.input_data = {} # To store results from analysis
        self.strategy_testers = [] # Keep track of StrategyTester windows



        
        # expose our theming helper on the root for children to call
        self.root.apply_theme_to_window = self.apply_theme_to_window

    def theme_settings(self):
        return {
            "light": {
                "bg": "#f0f0f0",
                "fg": "#000000",
                "entry_bg": "#ffffff"
            },
            "dark": {
                "bg": "#0f0f0f",
                "fg": "#ffffff",
                "entry_bg": "#3c3c3c"
            }
        }[self.current_theme]


    def apply_theme_to_window(self, window):
        """Central recursive theming for every widget in `window`."""
        try:
            if not window.winfo_exists():
                return
        except:
            return

        # derive our colors from the current_theme
        bg       = "#0f0f0f" if self.current_theme == 'dark' else "#f0f0f0"
        fg       = "#ffffff" if self.current_theme == 'dark' else "#000000"
        entry_bg = "#3c3c3c" if self.current_theme == 'dark' else "#ffffff"

        # theme this container
        try:
            window.configure(bg=bg)
        except:
            pass

        # walk all children
        for w in window.winfo_children():
            # ttk widgets respond to style → (we already set that globally)
            # raw tk widgets need explicit bg/fg
            if isinstance(w, (tk.Label, tk.Button, tk.Checkbutton, tk.Radiobutton)):
                try: w.configure(bg=bg, fg=fg)
                except: pass
            if isinstance(w, tk.Entry):
                try: w.configure(bg=entry_bg, fg=fg)
                except: pass
            if isinstance(w, tk.Text):
                try: w.configure(bg=entry_bg, fg=fg)
                except: pass

            # recurse into frames & toplevels
            if hasattr(w, 'winfo_children'):
                self.apply_theme_to_window(w)

        # Call apply_custom_theme if the window supports it
        try:
            if hasattr(window, 'apply_custom_theme'):
                window.apply_custom_theme()
        except:
            pass



    def set_status(self, text, color=None):
        """Updates the status label. Uses default label foreground if color is None."""
        try:
            if color:
                self.status_label.config(text=text, foreground=color)
            else:
                # Reset to default foreground color
                default_fg = ttk.Style().lookup('Status.TLabel', 'foreground')
                self.status_label.config(text=text, foreground=default_fg)
            self.root.update_idletasks() # Ensure GUI updates
        except tk.TclError:
             # Handle case where window might be destroyed during update
             print(f"Status update skipped (window closed?): {text}")


    def animate_loading(self):
        """Cycles through animation characters in the status label."""
        if not self.is_loading:
            return

        char = self.animation_chars[self.animation_step % len(self.animation_chars)]
        self.set_status(f"Running analysis {char}", "orange")
        self.animation_step += 1
        self.root.after(150, self.animate_loading)  # ~6fps



  # ---------------- SETTINGS (Refactored UI) ----------------
    def open_settings_window(self):
        """
        Opens a settings window with a professional and organized layout.
        Uses Labelframes to group related settings and provides clear spacing.
        """
        win = tk.Toplevel(self.root)
        win.title("Settings")
        win.geometry("750x650")  # Adjusted size for better spacing
        win.transient(self.root) # Keep window on top of main app
        win.grab_set() # Modal behavior
        self.apply_theme_to_window(win)

        # --- Main container frame ---
        main_frame = ttk.Frame(win, padding=(20, 10))
        main_frame.pack(expand=True, fill="both")

        # --- Section 1: User Preferences ---
        prefs_frame = ttk.Labelframe(main_frame, text="User Preferences", padding=15)
        prefs_frame.pack(fill="x", padx=10, pady=10)
        prefs_frame.columnconfigure(1, weight=1)

        # Display Name
        ttk.Label(prefs_frame, text="Display Name:").grid(row=0, column=0, sticky="w", pady=6, padx=5)
        name_var = tk.StringVar(value=self.user_name)
        ttk.Entry(prefs_frame, textvariable=name_var).grid(row=0, column=1, sticky="ew", pady=6)

        # Theme
        ttk.Label(prefs_frame, text="Theme:").grid(row=1, column=0, sticky="w", pady=6, padx=5)
        theme_var = tk.StringVar(value=self.current_theme)
        theme_buttons_frame = ttk.Frame(prefs_frame)
        theme_buttons_frame.grid(row=1, column=1, sticky="w")
        ttk.Radiobutton(theme_buttons_frame, text="Light", variable=theme_var, value="light").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(theme_buttons_frame, text="Dark", variable=theme_var, value="dark").pack(side="left")

        # --- Section 2: Application Defaults ---
        defaults_frame = ttk.Labelframe(main_frame, text="Application Defaults", padding=15)
        defaults_frame.pack(fill="x", padx=10, pady=5)
        defaults_frame.columnconfigure(1, weight=1)

        # Timezone
        ttk.Label(defaults_frame, text="Timezone:").grid(row=0, column=0, sticky="w", pady=6, padx=5)
        tz_list = [
            "America/Vancouver", "America/New_York", "Europe/London", "Asia/Tokyo",
            "Australia/Sydney", "Europe/Paris", "Europe/Berlin", "Asia/Kolkata",
            "Asia/Shanghai", "America/Sao_Paulo"
        ]
        tz_var = tk.StringVar(value=self.settings.get("timezone"))
        ttk.Combobox(defaults_frame, textvariable=tz_var, values=tz_list, state="readonly").grid(row=0, column=1, sticky="ew", pady=6)

        # Default Chart Ticker
        ttk.Label(defaults_frame, text="Default Chart Ticker:").grid(row=1, column=0, sticky="w", pady=6, padx=5)
        ticker_var = tk.StringVar(value=self.settings.get("default_ticker"))
        ttk.Entry(defaults_frame, textvariable=ticker_var).grid(row=1, column=1, sticky="ew", pady=6)

        # --- Section 3: Watchlist Editor ---
        watchlist_outer_frame = ttk.Labelframe(main_frame, text="Watchlist Tickers", padding=15)
        watchlist_outer_frame.pack(fill="x", expand=True, padx=10, pady=10)
        
        # This frame holds the chips and allows them to wrap if needed
        watchlist_frame = ttk.Frame(watchlist_outer_frame)
        watchlist_frame.pack(fill="x", pady=5)

        chips = []
        chip_frames = []
        drag_data = {"widget": None, "start_x": 0}

        add_btn = ttk.Button(watchlist_frame, text="＋", width=3)
        add_btn.pack(side="left", pady=(0, 5))

        def remove_chip(frame_to_remove, var_to_remove):
            idx = chips.index(var_to_remove)
            chips.pop(idx)
            chip_frames.pop(idx)
            frame_to_remove.destroy()

        def on_drag_start(event):
            widget = event.widget
            # Travel up to find the parent chip frame if a child was clicked
            while widget and not isinstance(widget, ttk.Frame) and widget.master != watchlist_frame:
                widget = widget.master
            
            if widget in chip_frames:
                drag_data["widget"] = widget
                drag_data["start_x"] = event.x_root - widget.winfo_rootx()
                x, y = widget.winfo_x(), widget.winfo_y()
                widget.pack_forget()
                widget.place(in_=watchlist_frame, x=x, y=y)
                widget.lift()

        def on_drag_motion(event):
            w = drag_data["widget"]
            if not w: return
            x = event.x_root - watchlist_frame.winfo_rootx() - drag_data["start_x"]
            x = max(0, min(x, watchlist_frame.winfo_width() - w.winfo_width()))
            w.place_configure(x=x)

        def on_drag_release(event):
            w = drag_data["widget"]
            if not w: return
            
            sorted_frames = sorted(chip_frames, key=lambda f: f.winfo_x())
            for f in chip_frames:
                f.place_forget()
            
            chip_frames[:] = sorted_frames
            chips[:] = [f.var for f in sorted_frames]
            
            for f in chip_frames:
                f.pack(side="left", padx=(0, 6), pady=(0, 5))
            
            add_btn.pack_forget()
            add_btn.pack(side="left", pady=(0, 5))
            drag_data["widget"] = None

        def add_watchlist_chip(ticker=""):
            var = tk.StringVar(value=ticker)
            
            # Style the chip frame
            style_name = 'Chip.TFrame'
            ttk.Style().configure(style_name, relief='solid', borderwidth=1, background=win.cget('bg'))
            frame_chip = ttk.Frame(watchlist_frame, style=style_name)
            frame_chip.var = var

            ent = ttk.Entry(frame_chip, textvariable=var, width=8)
            ent.pack(side="left", fill='x', expand=True, padx=(6, 4), pady=5)
            
            # Use a more subtle remove button
            btn_remove = ttk.Button(frame_chip, text="✕", width=2, style='Toolbutton',
                                    command=lambda f=frame_chip, v=var: remove_chip(f, v))
            btn_remove.pack(side="left", padx=(0, 6), pady=5)

            for w in (frame_chip, ent, btn_remove):
                w.bind("<ButtonPress-1>", on_drag_start)
                w.bind("<B1-Motion>", on_drag_motion)
                w.bind("<ButtonRelease-1>", on_drag_release)

            chip_frames.append(frame_chip)
            chips.append(var)
            
            add_btn.pack_forget()
            frame_chip.pack(side="left", padx=(0, 6), pady=(0, 5))
            add_btn.pack(side="left", pady=(0, 5))
            return var
        
        # Configure the add button command after add_watchlist_chip is defined
        add_btn.config(command=lambda: add_watchlist_chip())

        initial_watchlist = self.settings.get("watchlist", "").split("|")
        for t in filter(None, (x.strip() for x in initial_watchlist)):
            add_watchlist_chip(t)

        # --- Separator and Action Buttons ---
        ttk.Separator(main_frame).pack(fill='x', padx=10, pady=15)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill='x', padx=10, pady=(5, 10))
        button_frame.columnconfigure(0, weight=1) # Spacer

        ttk.Button(button_frame, text="⟳ Reset App", command=self.reset_app)\
            .grid(row=0, column=1, padx=5)
        ttk.Button(button_frame, text="Save Settings", command=lambda: save_and_close(), style="Accent.TButton")\
            .grid(row=0, column=2, padx=5)

        # --- Save Logic ---
        def save_and_close():
            self.user_name = name_var.get().strip() or "Trader"
            self.settings.set("user_name", self.user_name)

            if theme_var.get() != self.current_theme:
                self.is_dark_mode_var.set(theme_var.get() == "dark")
                self.toggle_theme()
            
            self.settings.set("timezone", tz_var.get())
            self.settings.set("default_ticker", ticker_var.get().strip().upper() or "SPY")

            valid_tickers = []
            for var in chips:
                ticker = var.get().strip().upper()
                if not ticker:
                    continue
                if self.data_mgr.get_latest_price(ticker) is None:
                    messagebox.showerror(
                        "Invalid Ticker",
                        f"The ticker '{ticker}' is invalid or could not be found and will not be saved.",
                        parent=win
                    )
                else:
                    valid_tickers.append(ticker)
            
            self.settings.set("watchlist", "|".join(valid_tickers) if valid_tickers else "SPY|^VIX")
            self.dashboard._refresh()
            win.destroy()

        win.bind("<Return>", lambda event: save_and_close())
        win.bind("<Escape>", lambda event: win.destroy())



    # ---------------- RESET ----------------
    def reset_app(self):
        ok = messagebox.askyesno("Reset App", "This will clear saved settings and restart the application.\nContinue?", parent=self.root)
        if not ok: return
        # 1. Clear settings file
        try:
            SettingsManager._FILE.unlink(missing_ok=True)
        except Exception:
            pass
        # 2. Relaunch self
        python = self._get_python_executable()
        os.execl(python, python, *sys.argv)

    def _toggle_fullscreen_input(self, window):
            is_full = window.attributes('-fullscreen')
            window.attributes('-fullscreen', not is_full)
            window.bind("<Escape>", lambda e: self._toggle_fullscreen_input(window))


    def launch_strategy_tester(self):
        """Launches the Strategy Tester window, ensuring only one instance is active."""
        if self.strategy_tester_instance and self.strategy_tester_instance.win.winfo_exists():
            self.strategy_tester_instance.win.lift()
            self.strategy_tester_instance.win.focus_force()
            return

        try:
            from strategy_tester import StrategyTesterWindow # Keep import local
        except ImportError:
            messagebox.showerror("Error", "strategy_tester.py not found.")
            return

        try:
            tester = StrategyTesterWindow(self.root, self)
            self.strategy_tester_instance = tester # Store the current instance
            self.strategy_testers.append(tester)   # Keep for theme updates
            self.apply_theme_to_window(tester.win)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open Strategy Tester:\n{e}")
            import traceback
            traceback.print_exc()

    def remove_strategy_tester(self, tester_instance):
        """Removes a closed tester window from the tracking list."""
        if tester_instance in self.strategy_testers:
            self.strategy_testers.remove(tester_instance)
        if self.strategy_tester_instance == tester_instance: 
            self.strategy_tester_instance = None

    def launch_news_sentiment_analyzer(self):
        window = NewsSentimentAnalyzerWindow(self.root, theme=self.current_theme)
        self.child_windows.append(window.win)
        self.apply_theme_to_window(window.win)


    def _get_python_executable(self):
        """
        Finds the correct Python executable, prioritizing the one used to run the app.
        This is important for when the app is bundled into an executable.
        """
        if getattr(sys, 'frozen', False):
            # The application is frozen
            return sys.executable
        return sys.executable # In a normal environment, this is python.exe or python

    def launch_chatbot(self):
        """
        Launches the Financial Chatbot in a separate, non-blocking process
        to prevent any GUI conflicts.
        """
        if ChatBot is None:
            messagebox.showerror("Unavailable", "Chatbot module not found.", parent=self.root)
            return

        try:
            # --- Robust Path Calculation ---
            # Get the directory where the current script (OptionsApp.py) is located.
            # os.path.abspath(__file__) gets the full path to this script.
            # os.path.dirname() gets the directory that contains the script.
            current_dir = os.path.dirname(os.path.abspath(__file__))
            
            # Join this directory with the name of the chatbot script.
            # os.path.join is the correct way to build paths that work on all operating systems.
            chatbot_script_path = os.path.join(current_dir, "Chatbot.py")
            # --------------------------------

            if not os.path.exists(chatbot_script_path):
                messagebox.showerror("File Not Found", f"Could not find the chatbot script at:\n{chatbot_script_path}", parent=self.root)
                return

            # Get the correct python executable
            python_executable = self._get_python_executable()
            
            # Pass the current theme as a command-line argument
            theme_arg = self.current_theme

            # Use Popen to launch the script in a new process.
            # This is non-blocking, so OptionsApp remains fully responsive.
            # We store the process object in case we want to manage it later.
            self._chatbot_proc = subprocess.Popen([python_executable, chatbot_script_path, theme_arg])

        except Exception as exc:
            messagebox.showerror("Chatbot Error", f"Could not start the Fin-Bot process:\n{exc}",
                                 parent=self.root)
            import traceback
            traceback.print_exc()
            
    def open_input_window(self):
        """Opens a Toplevel window for user inputs."""

        tooltips = {
            "Ticker": "The stock symbol (e.g., AAPL for Apple).",
            "Current Price (S0)": "The stock's price right now, in dollars.",
            "Barrier Price (H)": "Your target price or safety level to watch.",
            "Implied Volatility": "How much the market expects the stock to move.",
            "Risk-Free Rate": "A baseline interest rate, like from treasury bonds.",
            "Days to Expiry": "How many days left before the option expires.",
            "Strike Price (K)": "The price at which you can buy or sell the stock.",
            "Option Type": "'Call' if you're betting it goes up, 'Put' if down.",
            "Paths to Display": "How many simulated price paths to visualize (1–500)."
        }

        if self.is_loading:
            messagebox.showwarning("Busy", "Analysis is already in progress.", parent=self.root)
            return


        input_win = tk.Toplevel(self.root)
        input_win.title("Input Parameters")
        input_win.geometry("760x900")
        input_win.transient(self.root)

        self.apply_theme_to_window(input_win)

        # Create canvas + scrollbar wrapper
        canvas = tk.Canvas(input_win, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(input_win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Actual input frame inside the canvas
        input_frame = ttk.Frame(canvas)
        input_frame_id = canvas.create_window((0, 0), window=input_frame, anchor="nw")

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        input_frame.bind("<Configure>", on_frame_configure)

        # Resize canvas when window resized
        def on_canvas_resize(event):
            canvas.itemconfig(input_frame_id, width=event.width)

        canvas.bind("<Configure>", on_canvas_resize)

        # Enable mouse scrolling
        def _on_mousewheel(event):
            try:
                if event.num == 4 or event.delta > 0:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5 or event.delta < 0:
                    canvas.yview_scroll(1, "units")
            except tk.TclError:
                pass  # Ignore scroll after widget is destroyed

        canvas.bind_all("<MouseWheel>", _on_mousewheel)       # Windows & most trackpads
        canvas.bind_all("<Button-4>", _on_mousewheel)         # Linux scroll up
        canvas.bind_all("<Button-5>", _on_mousewheel)         # Linux scroll down


        # --- Top bar with fullscreen + close ---
        topbar = ttk.Frame(input_win, padding=(0, 5))
        topbar.place(relx=1.0, y=0, anchor="ne")

        fs_button = ttk.Button(topbar, text="⛶", width=3, command=lambda: self._toggle_fullscreen_input(input_win))
        fs_button.pack(side=tk.RIGHT)

        close_button = ttk.Button(topbar, text="✖", width=3, command=input_win.destroy)
        close_button.pack(side=tk.RIGHT, padx=(0, 5))

        self.educational_mode = tk.BooleanVar(value=False)
        edu_check = ttk.Checkbutton(
            input_frame,
            text="Educational Mode",
            variable=self.educational_mode,
            command=lambda: self._refresh_tooltips(self.tooltip_labels, tooltips)
        )
        edu_check.grid(row=0, column=0, columnspan=2, sticky='w', padx=5, pady=10)

        labels_hints_defaults = {
            "Ticker:": ("(e.g., AAPL)", "AAPL"),
            "Current Price (S0):": ("(e.g., 170.5)", "170.5"),
            "Barrier Price (H):": ("(Target/Floor, e.g., 180)", "180.0"),
            "Implied Volatility:": ("(Decimal, e.g., 0.25)", "0.25"),
            "Risk-Free Rate:": ("(Decimal, e.g., 0.04)", "0.04"),
            "Days to Expiry:": ("(e.g., 90)", "90"),
            "Strike Price (K):": ("(e.g., 175)", "175.0"),
            "Option Type:": ("(call or put)", "call"),
            "Paths to Display:": ("(1 to 500)", "30")
        }

        self.entries = {}
        self.tooltip_labels = {}

        for i, (label_text, (hint, default_val)) in enumerate(labels_hints_defaults.items(), start=1):
            clean_key = label_text.replace(":", "")
            label = ttk.Label(input_frame, text=f"{label_text} {hint}")
            label.grid(row=i, column=0, sticky='w', padx=5, pady=6)
            self.tooltip_labels[clean_key] = label

            entry = ttk.Entry(input_frame, width=18)
            entry.grid(row=i, column=1, sticky='ew', padx=5, pady=6)
            entry.insert(0, default_val)
            self.entries[clean_key] = entry

            if self.educational_mode.get() and clean_key in tooltips:
                Tooltip(label, tooltips[clean_key])

        self.greeks_mode = tk.StringVar(value="manual")
        mode_frame = ttk.Frame(input_frame)
        mode_frame.grid(row=i+1, column=0, columnspan=2, pady=(10, 5), sticky='w')
        ttk.Label(mode_frame, text="Greek Mode:").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="Manual", variable=self.greeks_mode, value="manual").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(mode_frame, text="Model (Binomial)", variable=self.greeks_mode, value="model").pack(side=tk.LEFT, padx=5)

        # --- Model choice section with config buttons ---
        self.model_choice = tk.StringVar(value="black_scholes")
        model_frame = ttk.LabelFrame(input_frame, text="Simulation Model", padding=(10,5))
        model_frame.grid(row=i+8, column=0, columnspan=2, sticky='ew', pady=(20,5))

        def ask_model_params(model_name, parent):
            win = tk.Toplevel(parent)
            win.title(f"{model_name.title()} Parameters")
            win.geometry("320x300")
            param_entries = {}

            def add_entry(label, default):
                row = ttk.Frame(win)
                row.pack(pady=3, fill='x')
                ttk.Label(row, text=label, width=18).pack(side='left')
                ent = ttk.Entry(row)
                ent.insert(0, str(default))
                ent.pack(side='left', fill='x', expand=True)
                param_entries[label] = ent

            if model_name == 'jump_diffusion':
                add_entry('λ (Jump Intensity)', 0.1)
                add_entry('μ (Jump Mean)', -0.1)
                add_entry('σ (Jump Volatility)', 0.2)
            elif model_name == 'heston':
                add_entry('κ (Mean Reversion)',    2.0)
                add_entry('θ (Long-run Var)',      0.04)
                add_entry('ξ (Vol of Vol)',        0.10)
                add_entry('v₀ (Initial Var)',      0.04)
                add_entry('ρ (Corr)',             -0.70)   
            elif model_name == 'rough_bergomi':
                add_entry('H (Hurst Exponent)',     0.10)
                add_entry('η (Vol of Vol)',         1.50)
                add_entry('ρ (Corr)',               0.00)   
            def save_and_close():
                self.input_data.setdefault("model_params", {})
                for key, entry in param_entries.items():
                    val = float(entry.get())
                    self.input_data["model_params"][key] = val

                win.destroy()

            ttk.Button(win, text="Save", command=save_and_close).pack(pady=10)
            win.bind("<Return>", lambda e: save_and_close())

        def add_model_row(text, value):
            row = ttk.Frame(model_frame)
            row.pack(anchor='w', fill='x', pady=2)
            ttk.Radiobutton(row, text=text, variable=self.model_choice, value=value).pack(side='left')
            if value != 'black_scholes':
                ttk.Button(row, text="⚙", width=2, command=lambda v=value: ask_model_params(v, input_win)).pack(side='left', padx=4)

        add_model_row("Black-Scholes", "black_scholes")
        add_model_row("Jump Diffusion", "jump_diffusion")
        add_model_row("Heston (Mean-Reverting Vol)", "heston")
        add_model_row("Rough Bergomi (Fractal Vol)", "rough_bergomi")

        # Greeks Input
        ttk.Label(input_frame, text="(Optional) Input Greeks:").grid(row=i+2, column=0, columnspan=2, pady=(20, 5))

        greek_defaults = {
            "Delta": "0.6",
            "Gamma": "0.05",
            "Vega": "-0.44",
            "Theta": "-0.18",
            "Rho": "0.2"
        }
        self.greeks_entries = {}
        for j, (greek, default) in enumerate(greek_defaults.items()):
            ttk.Label(input_frame, text=f"{greek}:").grid(row=i+3+j, column=0, sticky='w', padx=5)
            entry = ttk.Entry(input_frame, width=18)
            entry.grid(row=i+3+j, column=1, sticky='ew', padx=5, pady=3)
            entry.insert(0, default)
            self.greeks_entries[greek.lower()] = entry

        def update_greek_input_state():
            state = 'normal' if self.greeks_mode.get() == "manual" else 'disabled'
            for entry in self.greeks_entries.values():
                entry.config(state=state)

        self.greeks_mode.trace_add("write", lambda *args: update_greek_input_state())
        update_greek_input_state()

        # Submit
        submit_btn = ttk.Button(input_frame, text="Run Analysis",
                                command=lambda win=input_win: self.submit_inputs(win))
        submit_btn.grid(row=i+1, column=0, columnspan=2, pady=25)

        input_frame.columnconfigure(1, weight=1)

        if self.educational_mode.get():
            self._refresh_tooltips(self.tooltip_labels, tooltips)




    def submit_inputs(self, window):
        """Validates inputs and starts the analysis thread + animation."""
        if self.is_loading: return # Prevent multiple submissions

        try:
            # Retrieve and validate inputs
            input_values = {}
            input_values['ticker'] = self.entries["Ticker"].get().strip().upper()
            input_values['S0'] = float(self.entries["Current Price (S0)"].get())
            input_values['H'] = float(self.entries["Barrier Price (H)"].get())
            input_values['sigma'] = float(self.entries["Implied Volatility"].get())
            input_values['r'] = float(self.entries["Risk-Free Rate"].get())
            input_values['T_days'] = int(self.entries["Days to Expiry"].get())
            input_values['strike'] = float(self.entries["Strike Price (K)"].get())
            input_values['option_type'] = self.entries["Option Type"].get().strip().lower()
            input_values['paths_to_display'] = int(self.entries["Paths to Display"].get())
            #input_values['style'] = self.entries["Option Style"].get().strip().lower()
            input_values['educational_mode'] = self.educational_mode.get()
            # Collect Greeks if provided, else use 0
            greek_inputs = {}
            for greek in ['delta', 'gamma', 'vega', 'theta', 'rho']:
                try:
                    val = self.greeks_entries[greek].get()
                    greek_inputs[greek] = float(val) if val.strip() else 0.0
                except ValueError:
                    greek_inputs[greek] = 0.0  # Default fallback
            input_values['greek_inputs'] = greek_inputs
            input_values['greek_mode'] = self.greeks_mode.get()
            input_values['simulation_model'] = self.model_choice.get()
            input_values['model_params'] = self.input_data.get("model_params", {})




            # Basic Validation Checks
            if not input_values['ticker']: raise ValueError("Ticker symbol cannot be empty.")
            if input_values['S0'] <= 0: raise ValueError("Current Price must be positive.")
            if input_values['sigma'] < 0: raise ValueError("Implied Volatility cannot be negative.")
            # Allow r=0, but maybe warn if negative? For now, allow negative rates.
            if input_values['T_days'] <= 0: raise ValueError("Days to Expiry must be positive.")
            if input_values['strike'] <= 0: raise ValueError("Strike Price must be positive.")
            if input_values['option_type'] not in ['call', 'put']: raise ValueError("Option Type must be 'call' or 'put'.")
            if not (1 <= input_values['paths_to_display'] <= 500):
                raise ValueError("Paths to Display must be between 1 and 500.")
            #if input_values['style'] not in ['american', 'european']:
                #raise ValueError("Option Style must be 'american' or 'european'.")
            if input_values['greek_mode'] == "model":
                greeks = calculate_binomial_greeks(
                    input_values['S0'], input_values['strike'], input_values['T_days']/365,
                    input_values['r'], input_values['sigma'], option_type=input_values['option_type']
                )
                input_values['greek_inputs'] = greeks



            # If inputs are valid, close input window and start analysis
            window.destroy()

            # 3) Start the spinner *after* the window is gone
            self.is_loading = True
            self.animation_step = 0
            self.animate_loading()

            # 4) Spawn the analysis thread
            analysis_thread = threading.Thread(
                target=self.run_analysis_thread,
                args=(input_values,),
                daemon=True
            )
            analysis_thread.start()

        except ValueError as e:
            messagebox.showerror("Input Error", str(e), parent=self.root) # Show error on main window
            # Stop animation if it started (though likely didn't in case of validation error)
            self.is_loading = False
            self.set_status("Input validation failed", "red")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred during input: {e}", parent=self.root)
            self.is_loading = False
            self.set_status("An unexpected error occurred", "red")
            print(f"Input Submission Error Traceback:\n{traceback.format_exc()}")


    def run_analysis_thread(self, inputs):
        """The function executed in the background thread."""
        try:
            T = inputs['T_days'] / 365.0
            self.input_data = inputs.copy()
            sigma = inputs['sigma']
            self.input_data['T'] = T
            jump_params = None
            heston_params = None
            rough_params = None


            # 1. Fetch historical data
            prices = fetch_ticker_data(inputs['ticker'], inputs['T_days'] + 180)
            drift, realized_vol, stderr = calculate_drift_and_volatility(prices)
            self.input_data['drift'] = drift
            self.input_data['realized_vol'] = realized_vol
            self.input_data['vol_stderr'] = stderr

            set_max_paths(inputs['paths_to_display'])

            # 2. Detect simulation model
            model = inputs.get("simulation_model", "black_scholes")
            model_params = inputs.get("model_params", {})
            self.input_data["simulation_model"] = model  # For use in summary

            if model == "jump_diffusion":
                jump_params = {
                    'lambda': model_params.get('λ (Jump Intensity)', 0.1),
                    'mu': model_params.get('μ (Jump Mean)', -0.1),
                    'sigma': model_params.get('σ (Jump Volatility)', 0.2)
                }
                heston_params = rough_params = None

            if model == "heston":
                heston_params = {
                    'kappa': model_params.get('κ (Mean Reversion)',    2.0),
                    'theta': model_params.get('θ (Long-run Var)',      sigma**2),
                    'xi':    model_params.get('ξ (Vol of Vol)',        0.10),
                    'v0':    model_params.get('v₀ (Initial Var)',      sigma**2),
                    'rho':   model_params.get('ρ (Corr)',             -0.70)
                }
                jump_params = rough_params = None

            elif model == "rough_bergomi":
                rough_params = {
                    'H':   model_params.get('H (Hurst Exponent)',    0.10),
                    'eta': model_params.get('η (Vol of Vol)',        1.50),
                    'rho': model_params.get('ρ (Corr)',              0.00)
                }
                jump_params = heston_params = None

            # 3. Monte Carlo Simulation
            sim_results = calculate_simulation_data(
                inputs['S0'], inputs['H'], inputs['sigma'], drift, T, inputs['r'],
                n_simulations=10000, option_type=inputs['option_type'],
                model=model,
                jump_params=jump_params,
                heston_params=heston_params,
                rough_params=rough_params
            )
            (prob, avg_trig, std_trig, trig_prices, paths, days) = sim_results

            self.input_data['probability'] = prob
            self.input_data['avg_trigger'] = avg_trig
            self.input_data['std_trigger'] = std_trig
            self.input_data['trigger_prices'] = trig_prices
            self.input_data['sample_paths'] = paths
            self.input_data['sim_days'] = days

            # 4. Corrected trigger price calc
            correct_avg_trig, correct_std_trig, _ = recalculate_trigger_price_correctly(
                inputs['S0'], inputs['sigma'], T, inputs['r'],
                n_simulations=10000, option_type=inputs['option_type']
            )
            self.input_data['correct_avg_trigger'] = correct_avg_trig
            self.input_data['correct_std_trigger'] = correct_std_trig

            if model == "black_scholes":
                from MonteCarloSimulation import black_scholes_price
                bs_price = black_scholes_price(
                    inputs['S0'], inputs['strike'], T,
                    inputs['r'], inputs['sigma'], inputs['option_type']
                )
                self.input_data['bs_price'] = bs_price


            # 5. Binomial Fair Price
            fair_price = cached_binomial_price(
                inputs['S0'], inputs['strike'], T, inputs['r'], inputs['sigma'],
                N=500, option_type=inputs['option_type'], american=False
            )
            self.input_data['fair_price'] = fair_price
            self.input_data['educational_mode'] = inputs['educational_mode']

            # 6. Heatmap + Surface
            self.input_data['heatmap_data'] = generate_profit_heatmap_data(
                inputs['S0'], inputs['strike'], T, inputs['r'], inputs['sigma'],
                inputs['option_type'], initial_option_price=fair_price,
                low_pct_factor=0.5, high_pct_factor=2.0
            )

            # 7. Option Surface Data
            self.input_data['surface_data'] = generate_option_surface_data(
                inputs['S0'], inputs['strike'], T, inputs['r'], inputs['sigma'],
                inputs['option_type'], low_pct_factor=0.5, high_pct_factor=2.0
            )

            # 8. Volatility Surface Data
            self.input_data['vol_surface_data'] = generate_volatility_surface_data(
                 inputs['S0'], inputs['strike'], T, inputs['sigma']
            )

            # 7. Done → schedule UI update
            self.root.after(0, self.analysis_complete)

        except Exception as e:
            self.root.after(0, lambda err=e: self.analysis_failed(err))


    def analysis_complete(self):
        """Updates GUI after successful analysis."""
        self.is_loading = False # Stop animation flag
        time.sleep(0.1) # Small delay to ensure last animation frame clears
        self.set_status("Analysis complete. Launching results...", color="green")
        self.launch_analysis_results_window()    # NEW → pop up results window

    # ******** FIX: Moved analysis_failed inside the class ********
    def analysis_failed(self, error):
        """Handles errors occurring during the analysis thread."""
        self.is_loading = False
        # Short delay might prevent status update race condition if analysis fails instantly
        time.sleep(0.1)
        self.set_status("Analysis failed!", color="red")

        # Log the full traceback to the console for debugging
        traceback_str = traceback.format_exception(type(error), error, error.__traceback__)
        print("=== ANALYSIS THREAD ERROR TRACEBACK ===")
        print("".join(traceback_str))
        print("======================================")

        # Show a user-friendly error message
        tk.messagebox.showerror("Analysis Error",
                                f"Failed to complete analysis:\n{error}\n\n(Check console for detailed traceback)",
                                parent=self.root)
    # ******** END FIX ********

    def launch_analysis_results_window(self):
        """
        Pop up a Toplevel to house all the analysis-result buttons
        (summary, paths, heatmap, etc.), just like strat-tester does.
        """
        # 1. Create window
        win = tk.Toplevel(self.root)
        win.title("Analysis Results")
        win.geometry("600x400")
        win.transient(self.root)
        self.apply_theme_to_window(win)

        # 2. Container frame
        frm = ttk.Frame(win, padding=20)
        frm.pack(expand=True, fill=tk.BOTH)

        # 3. Button configs (same as create_results_buttons)
        buttons = [
            ("Show Summary Info",        self.show_summary_popup),
            ("Show Simulation Paths",    self.show_simulation_plot),
            ("Show Trigger Distribution",self.show_distribution_plot),
            ("Show Profit Heatmap ($)",  self.show_heatmap_plot),
            ("Show 3D Vol Surface",      self.show_3d_volatility_plot),
            ("📉 Analyze Greeks",        self.show_greek_analysis),
            ("📈 View Stock Chart",      self.show_stock_chart_window),
            ("Explain Position",         self.show_llm_explanation)
        ]

        # 4. Grid them in two columns
        for idx, (label, cmd) in enumerate(buttons):
            btn = ttk.Button(frm, text=label, command=cmd)
            btn.grid(row=idx // 2, column=idx % 2, padx=10, pady=8, sticky="ew")

        # 5. Close button
        close = ttk.Button(frm, text="✖ Close Results", command=win.destroy)
        close.grid(row=(len(buttons)+1)//2, column=0, columnspan=2, pady=(15,0))

        # 6. Make columns stretch
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=1)


    def display_results_summary_console(self):
         """Prints a simple text summary to the console (optional)."""
         if not self.input_data: return # Should not happen if called from analysis_complete


         fair_price_str = f"${self.input_data['fair_price']:.2f}" if not np.isnan(self.input_data['fair_price']) else "N/A (Calculation Error?)"
         prob_str = f"{self.input_data['probability']*100:.2f}%" if not np.isnan(self.input_data['probability']) else "N/A"
         avg_trig_str = f"${self.input_data['avg_trigger']:.2f}" if not np.isnan(self.input_data['avg_trigger']) else "N/A"
         real_vol_str = f"{self.input_data.get('realized_vol', np.nan)*100:.1f}%" # Use .get for safety
         stderr_str = f"{self.input_data.get('vol_stderr', np.nan)*100:.1f}%"

         summary = (
             f"\n--- Analysis Summary for {self.input_data['ticker']} ---\n"
             f"Option Type: {self.input_data['option_type'].capitalize()}, Strike: ${self.input_data['strike']:.2f}, Expiry: {self.input_data['T_days']} days\n"
             f"Current Price (S0): ${self.input_data['S0']:.2f}, Barrier (H): ${self.input_data['H']:.2f}\n"
             f"Input IV: {self.input_data['sigma']*100:.1f}%, Risk-Free Rate: {self.input_data['r']*100:.1f}%\n"
             f"Realized Volatility (hist.): {real_vol_str} (±{stderr_str})\n"
             f"--------------------------------------\n"
             f"{self.input_data['style'].capitalize()} Fair Value: {fair_price_str}\n"
             f"MC Probability of Hitting Barrier: {prob_str}\n"
             f"Avg. {'Max' if self.input_data['option_type']=='call' else 'Min'} Price in MC: {avg_trig_str}\n"
             f"--------------------------------------\n"
         )
         print(summary)


    def show_summary_popup(self):
        """Shows an enhanced summary window with key analysis metrics."""
        if not self.input_data:
            messagebox.showwarning("No Data", "Run an analysis first.", parent=self.root)
            return

        win = tk.Toplevel(self.root)
        win.title("Detailed Analysis Summary")
        win.geometry("920x960")
        win.transient(self.root)
        win.grab_set()

        self.apply_theme_to_window(win)
        win.grab_set()

        frame = ttk.Frame(win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        def fmt_val(val, fmt, default="N/A"):
            return fmt.format(val) if pd.notna(val) else default

        iv_val = self.input_data.get('sigma', 0)
        rv_val = self.input_data.get('realized_vol', 0)
        fair_price = fmt_val(self.input_data.get('fair_price'), "${:.4f}")
        prob = fmt_val(self.input_data.get('probability', 0) * 100, "{:.2f}%")
        avg_trig = fmt_val(self.input_data.get('avg_trigger'), "${:.2f}")
        vol = fmt_val(rv_val * 100, "{:.1f}%")
        stderr = fmt_val(self.input_data.get('vol_stderr', 0) * 100, "{:.1f}%")

        sim_count = 10000
        hits = int(self.input_data.get('probability', 0.0) * sim_count)
        trigger_type = "Maximum" if self.input_data.get('option_type') == 'call' else "Minimum"
        iv_pct = iv_val * 100

        # Volatility comparison
        if iv_val > rv_val + self.input_data.get('vol_stderr', 0):
            vol_status = f"Overpriced (IV = {iv_pct:.1f}%, Realized = {rv_val*100:.1f}%)"
        elif iv_val < rv_val - self.input_data.get('vol_stderr', 0):
            vol_status = f"Underpriced (IV = {iv_pct:.1f}%, Realized = {rv_val*100:.1f}%)"
        else:
            vol_status = f"Fairly Priced (IV = {iv_pct:.1f}%, Realized = {rv_val*100:.1f}%)"

        # Build Simulation Settings section with model-specific logic
        model = self.input_data.get('simulation_model', 'black_scholes')
        param_map = self.input_data.get("model_params", {})
        bs_price = self.input_data.get('bs_price', None)
        fair_price = self.input_data.get('fair_price', None)
        fair_price = fmt_val(fair_price, "${:.4f}")

        simulation_settings = [("Model Used", model.replace('_', ' ').title())]

        # Add model-generated price line
        if model == "black_scholes" and bs_price is not None:
            simulation_settings.append(("Black-Scholes Price", f"${bs_price:.4f}"))
        elif model != "black_scholes" and fair_price is not None:
            simulation_settings.append(("Model-Based Estimate", f"${fair_price:.4f}"))


        if model == "jump_diffusion":
            for key in ['λ (Jump Intensity)', 'μ (Jump Mean)', 'σ (Jump Volatility)']:
                if key in param_map:
                    simulation_settings.append((key, str(round(param_map[key], 6))))
        elif model == "heston":
            for key in ['κ (Mean Reversion)', 'θ (Long-run Var)', 'ξ (Vol of Vol)', 'v₀ (Initial Var)']:
                if key in param_map:
                    simulation_settings.append((key, str(round(param_map[key], 6))))
        elif model == "rough_bergomi":
            for key in ['H (Hurst Exponent)', 'η (Vol of Vol)']:
                if key in param_map:
                    simulation_settings.append((key, str(round(param_map[key], 6))))

        sections = [
            ("Underlying Info", [
                ("Ticker", self.input_data.get('ticker', 'N/A')),
                ("Option Type", self.input_data.get('option_type', '').capitalize()),
                ("Strike Price", f"${self.input_data.get('strike', 0):.2f}"),
                ("Barrier Price (H)", f"${self.input_data.get('H', 0):.2f}"),
                ("Current Price (S₀)", f"${self.input_data.get('S0', 0):.2f}"),
                ("Days to Expiry", str(self.input_data.get('T_days', 0)))
            ]),
            ("Inputs", [
                ("Implied Volatility", f"{iv_pct:.1f}%"),
                ("Risk-Free Rate", fmt_val(self.input_data.get('r', 0) * 100, "{:.2f}%"))
            ]),
            ("Monte Carlo Results", [
                ("Simulations Run", f"{sim_count:,}"),
                (f"Paths that hit barrier", f"{hits:,} ({prob})"),
                (f"Avg. {trigger_type} Price", avg_trig)
            ]),
            ("Simulation Settings", simulation_settings),
            ("Binomial Estimate", [
                ("Fair Option Value", fair_price),
                ("Realized Volatility", f"{vol} (±{stderr})"),
                ("Volatility Status", vol_status)
            ])
        ]

        for section_title, items in sections:
            title = ttk.Label(frame, text=section_title, font=("Helvetica", 11, "bold"))
            title.pack(anchor='w', pady=(10, 2))

            for label, val in items:
                row = ttk.Frame(frame)
                row.pack(fill=tk.X, pady=2)
                ttk.Label(row, text=f"{label}:", width=24).pack(side=tk.LEFT)
                ttk.Label(row, text=val).pack(side=tk.LEFT)

        ttk.Button(frame, text="Close", command=win.destroy).pack(pady=15)




    # --- Plotting Window Launchers ---

    def _launch_plot_window(self, plot_function, *args, **kwargs):
        """Launches a new window to display a plot."""
        try:
            popup = tk.Toplevel(self.root)
            # Use pop to get title but also remove it from kwargs if present
            # We use 'plot_title' to avoid potential conflicts with a 'title' kwarg
            # that the plot_function itself might need.
            popup.title(kwargs.pop('plot_title', "Plot Window"))
            popup.geometry("800x600")
            self.apply_theme_to_window(popup)

            plot_frame = ttk.Frame(popup, padding=10)
            plot_frame.pack(expand=True, fill=tk.BOTH)

            # Call the actual plotting function, passing the frame and all args/kwargs
            plot_function(plot_frame, *args, **kwargs)

        except Exception as e:
            traceback.print_exc()  # Log the full traceback
            messagebox.showerror("Plot Error", f"Failed to generate plot: {e}", parent=self.root)
        finally:
            self.set_status("")


    # Wrapper functions to call _launch_plot_window for each plot type
    def show_simulation_plot(self):
        if not self.input_data or 'sim_days' not in self.input_data or 'sample_paths' not in self.input_data:
            messagebox.showwarning("Missing Data", "Simulation path data is missing. Please run analysis.", parent=self.root)
            return
        self.set_status("Generating Simulation Path plot...")
        self._launch_plot_window(plot_simulation_paths,
            self.input_data['sim_days'],
            self.input_data['sample_paths'],
            self.input_data['S0'],
            self.input_data['H'],
            self.input_data['option_type'],
            self.input_data['sigma'],
            self.input_data['probability'],
            len(self.input_data['sample_paths']), # use the total number of simulations.
            self.input_data['paths_to_display'], # send the user inputed value.
            title=f"{self.input_data['ticker']} Simulation Paths",
            educational_mode=self.input_data.get('educational_mode', False),
            dark_mode=(self.current_theme == 'dark'))

        self.set_status("") # Clear status after plot launched (or failed)


    def show_distribution_plot(self):
        if not self.input_data or 'trigger_prices' not in self.input_data:
            messagebox.showwarning("Missing Data", "Trigger price data is missing. Please run analysis.", parent=self.root)
            return
        self.set_status("Generating Distribution plot...")
        self._launch_plot_window(plot_distribution,
                                 self.input_data['trigger_prices'],
                                 self.input_data['H'],
                                 self.input_data['probability'],
                                 self.input_data['option_type'],
                                 self.input_data['S0'],
                                 self.input_data['correct_avg_trigger'],
                                 self.input_data['correct_std_trigger'],
                                 dark_mode=(self.current_theme == 'dark'))
        self.set_status("")


    def show_heatmap_plot(self):
        if not self.input_data or 'heatmap_data' not in self.input_data or not self.input_data['heatmap_data']:
            messagebox.showwarning("Missing Data", "Heatmap data is not available. Please run analysis.", parent=self.root)
            return
        self.set_status("Generating Heatmap plot...")
        # Unpack heatmap data
        try:
            prices, times, profit_m, percent_m, day_lbls, price_lbls, premium = self.input_data['heatmap_data']
            self._launch_plot_window(plot_profit_heatmap,
                         prices, times, profit_m, percent_m, day_lbls, price_lbls, premium,
                         self.input_data['option_type'], self.input_data['strike'],
                         "Profit/Loss Heatmap",
                         self.input_data.get('probability'),
                          dark_mode=(self.current_theme == 'dark'))
        except Exception as e: # Catch potential errors during unpacking or plotting call
             messagebox.showerror("Plot Error", f"Failed to display heatmap:\n{e}", parent=self.root)
             print(f"Heatmap display error: {traceback.format_exc()}")
        finally:
            self.set_status("")


    def show_3d_volatility_plot(self):
        """
        Launch a 3D implied volatility surface plot.
        """
        if not self.input_data or 'vol_surface_data' not in self.input_data or not self.input_data['vol_surface_data']:
            messagebox.showwarning(
                "Missing Data",
                "Volatility surface data is not available. Please run analysis first.",
                parent=self.root
            )
            return

        self.set_status("Generating 3D Volatility Surface plot...")

        try:
            # Import the new plotting function here or ensure it's imported at the top
            from MonteCarloSimulation import plot_volatility_surface_3d

            p_grid, t_grid, iv_grid = self.input_data['vol_surface_data']
            self._launch_plot_window(
                plot_volatility_surface_3d, # <--- Use the NEW plot function
                p_grid,
                t_grid,
                iv_grid,
                plot_title="3D Implied Volatility Surface", # <-- Window Title
                title="3D Implied Volatility Surface",    # <-- Plot Title
                dark_mode=(self.current_theme == 'dark')
            )
        except Exception as e:
            messagebox.showerror(
                "Plot Error",
                f"Failed to display 3D volatility surface:\n{e}",
                parent=self.root
            )
            logging.error(f"3D Volatility Surface display error: {e}")
            traceback.print_exc() # Print detailed error
        finally:
            self.set_status("")


    def show_stock_chart_window(self):
            ticker = self.input_data.get("ticker", "")
            if not ticker:
                messagebox.showerror("Missing Ticker", "No stock ticker found.")
                return
            StockChartWindow(self.root, ticker, theme=self.current_theme)


    def toggle_theme(self):
        new_theme = 'dark' if self.is_dark_mode_var.get() else 'light'
        self.current_theme = new_theme

        import MonteCarloSimulation as sim
        sim.dark_mode = (new_theme == 'dark')

        configure_global_styles(new_theme)
        self.apply_theme_to_window(self.root)

        # Update any open Strategy Tester windows
        for tester in self.strategy_testers[:]: # Use slice copy for safe iteration
            if tester.win.winfo_exists():
                tester.update_theme(self.current_theme)
            else:
                # Clean up if window was closed unexpectedly
                self.remove_strategy_tester(tester)
        # ---------------------

        self.dashboard.chart_pane.set_theme(self.current_theme) # Update dashboard chart theme


        # rebuild child_windows list with only still-open windows
        live_children = []
        for win in self.child_windows:
            try:
                if win.winfo_exists():
                    self.apply_theme_to_window(win)
                    live_children.append(win)
            except:
                # if anything goes wrong, just drop this window
                continue
        self.child_windows = live_children
        self.settings.set("theme", self.current_theme)   # persist






    def launch_strategy_builder(self):
        # import here to avoid circular import
        from strategy_builder import StrategyBuilderWindow
        builder = StrategyBuilderWindow(self.root, self.current_theme)
        self.child_windows.append(builder)
        self.apply_theme_to_window(builder)
    
    def _toggle_fullscreen(self):
        is_full = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not is_full)
        self.root.bind("<Escape>", lambda e: self._toggle_fullscreen())

    def _close_window(self):
        try:
            self.root.destroy()
            # kill chatbot process if it is still alive
            if hasattr(self, "_chatbot_proc") and self._chatbot_proc.poll() is None:
                self._chatbot_proc.terminate()

        except Exception as e:
            print(f"Error closing window: {e}")

    def _refresh_tooltips(self, label_dict, tooltip_dict):
        # Add tooltips only if educational mode is ON
        if self.educational_mode.get():
            for key, label in label_dict.items():
                if key in tooltip_dict:
                    Tooltip(label, tooltip_dict[key])

    def show_greek_analysis(self):
        if not self.input_data or 'greek_inputs' not in self.input_data:
            messagebox.showwarning("No Greeks", "Please run an analysis first and input Greek values.", parent=self.root)
            return
        from Greeks import Greeks
        Greeks(self.root, self.input_data['greek_inputs'], self.input_data['S0'], self.input_data['T_days'], dark_mode=(self.current_theme == 'dark'))




    def show_llm_explanation(self):
        if not self.input_data:
            messagebox.showwarning("No Data", "Run an analysis first.", parent=self.root)
            return

        self.set_status("Extracting word salad from my ass...")

        try:
            explanation = self.llm.explain_option_strategy(
                        ticker=self.input_data['ticker'],
                        option_type=self.input_data['option_type'],
                        strike=self.input_data['strike'],
                        S0=self.input_data['S0'],
                        premium=self.input_data['fair_price'],
                        T_days=self.input_data['T_days'],
                        prob=self.input_data['probability'],
                        educational=self.input_data.get('educational_mode', False)
            )

        

            popup = tk.Toplevel(self.root)
            popup.title("📘 Strategy Explanation (LLM)")
            popup.geometry("700x500")
            self.apply_theme_to_window(popup)

            frame = ttk.Frame(popup, padding=20)
            frame.pack(expand=True, fill=tk.BOTH)

            text_box = tk.Text(frame, wrap=tk.WORD, height=25)
            text_box.insert(tk.END, explanation)
            text_box.config(state=tk.DISABLED)
            text_box.pack(expand=True, fill=tk.BOTH)

            ttk.Button(frame, text="Close", command=popup.destroy).pack(pady=10)
        except Exception as e:
            messagebox.showerror("LLM Error", f"Failed to get explanation: {e}", parent=self.root)
        finally:
            self.set_status("")


# --- Main Execution ---
if __name__ == "__main__":
    root = tk.Tk()
    app = OptionAnalyzerApp(root)
    # Optional: Set minimum window size
    root.minsize(400, 350)
    try:
        root.mainloop()
    except tk.TclError:
        print("GUI closed by user.")
        sys.exit()




