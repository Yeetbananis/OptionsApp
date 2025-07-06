from __future__ import annotations
import json, io, zipfile, requests
from pathlib import Path

import tkinter as tk
from tkinter import ttk, colorchooser, simpledialog, messagebox

import pandas as pd
import mplfinance as mpf
import yfinance as yf
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.lines import Line2D


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
        # Create a dedicated, writable directory in the user's home folder
        data_dir = Path.home() / ".option_analyzer_data"
        data_dir.mkdir(exist_ok=True) # This ensures the directory exists
        self._saved_file = data_dir / "saved_charts.json"
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

    def refresh_data(self):
        """Public method to allow external components to trigger a data reload."""
        print(f"Refreshing chart data for {self.ticker}...")
        self.draw(self._last_period)

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

    def set_theme(self, theme):
        """
        Sets the new theme and triggers a full redraw of the chart.
        The drawing logic in the 'draw' method will apply the correct colors.
        """
        self.theme = theme
        self.refresh_data()
        
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
