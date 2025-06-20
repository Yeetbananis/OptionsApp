from __future__ import annotations
import queue, threading, logging, webbrowser
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo
from pathlib import Path

import tkinter as tk
from tkinter import ttk


from ui.candlestick_pane import CandlestickChartPane
from core.engine.strategy_tester import load_icon, ICON_DIR

# ------------------------------------------------------------------
# Helper so every UI-updater can bail out quickly if the window is
# in the middle of shutting down.
# ------------------------------------------------------------------
def _widget_is_alive(widget) -> bool:
    return bool(widget and getattr(widget, "winfo_exists", lambda: False)())


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

    def update(self, text: str):
        self.text = text
        # if the tip is showing, refresh it
        if self.tipwindow:
            self.hide_tooltip()
            self.show_tooltip()

    def hide_tooltip(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None



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

        self._is_closing = False


       
        # Configure the main frame's grid layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1) # Main content area should expand

        self._build_ui()

        self._wl_after_id = None
        self._wl_animating = False
        self._marquee_position = 0.0
        self._pixels_per_frame = 1.

        # ── thread-safe hand-off queues ─────────────────────────────
        self._indices_q   = queue.Queue()
        self._watchlist_q = queue.Queue()

        # start background pollers (run on the Tk thread)
        self.after(100, self._poll_indices_q)
        self.after(100, self._poll_watchlist_q)

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
        """Top bar with title, mini Fear-&-Greed gauge, clock and status icons."""
        header_frame = ttk.Frame(self)
        header_frame.grid(row=0, column=0, sticky="ew")

        # ── column map ───────────────────────────────────────────────
        # 0  Welcome “title”         (left-aligned)
        # 1  Spacer (weight=1)       – pushes remaining widgets right
        # 2  Mini Fear & Greed gauge
        # 3  Clock
        # 4  Market-status dot
        # 5  Market-status label
        # 6  Wi-Fi icon
        header_frame.columnconfigure(1, weight=1)

        # 0 ─ Welcome
        self.header_lbl = ttk.Label(header_frame, text="", style="Title.TLabel")
        self.header_lbl.grid(row=0, column=0, sticky="w")

        # 2 ─ Mini Fear & Greed gauge
        # Increased size for better visuals and to fit text
        self.fng_canvas = tk.Canvas(header_frame,
                                    width=80, height=55,
                                    highlightthickness=0, bd=0)
        self.fng_canvas.grid(row=0, column=2, sticky="e", padx=(0, 10))

        # open CNN Fear & Greed page on right-click
        cnn_url = "https://www.cnn.com/markets/fear-and-greed"
        self.fng_canvas.bind(
            "<Button-3>",                      # Windows / Linux right-click
            lambda _e, url=cnn_url: webbrowser.open(url)
        )
        # macOS secondary click (Ctrl-click) – optional but nice
        self.fng_canvas.bind(
            "<Control-Button-1>",
            lambda _e, url=cnn_url: webbrowser.open(url)
        )

        self.fng_tooltip = Tooltip(self.fng_canvas, "Loading Fear & Greed…")
        
        # Make the canvas background match the theme
        bg_color = self.controller.theme_settings()['bg']
        self.fng_canvas.configure(bg=bg_color)

        # 3 ─ Clock
        self.time_lbl = ttk.Label(header_frame, text="", style="Secondary.TLabel")
        self.time_lbl.grid(row=0, column=3, sticky="e", padx=(0, 10))

        # 4–5 ─ Market-status indicator
        bg = self.controller.theme_settings()['bg']
        self.market_canvas = tk.Canvas(header_frame,
                                    width=12, height=12,
                                    highlightthickness=0, bg=bg)
        self.market_canvas.grid(row=0, column=4, sticky="e", padx=(5, 0))
        self.market_circle = self.market_canvas.create_oval(2, 2, 10, 10,
                                                            fill="red", outline="")
        self.market_lbl = ttk.Label(header_frame, text="Closed", style="Status.TLabel")
        self.market_lbl.grid(row=0, column=5, sticky="e", padx=(2, 10))

        # 6 ─ Wi-Fi icon
        self._build_wifi_icon(header_frame)
        self.wifi_label.grid(row=0, column=6, sticky="e")

        # start real-time clock
        self._start_clock()


        
    def _build_overview(self):
        """Builds the market overview section with stat cards."""
        overview_frame = ttk.Frame(self)
        overview_frame.grid(row=1, column=0, sticky="ew", pady=15)
        overview_frame.columnconfigure(0, weight=1)
        overview_frame.columnconfigure(1, weight=1)

        # Indices Card - now with a content frame
        indices_card = ttk.LabelFrame(overview_frame, text="Market Indices")
        indices_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.indices_content_frame = ttk.Frame(indices_card)
        self.indices_content_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # ───── Watch-list Card – infinite marquee of full-size boxes ─────
        watchlist_card = ttk.LabelFrame(overview_frame, text="Watchlist")
        watchlist_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        watchlist_card.config(height=90)

        # 1️⃣  Canvas with proper theme background
        bg_color = self.controller.theme_settings()['bg']
        self.wl_canvas = tk.Canvas(
            watchlist_card, height=90, highlightthickness=0, bd=0, bg=bg_color
        )
        self.wl_canvas.pack(fill="both", expand=True)

        # 2️⃣  Main strip
        self.wl_strip = ttk.Frame(self.wl_canvas)
        self.wl_window = self.wl_canvas.create_window(
            (0, 0), window=self.wl_strip, anchor="nw"
        )

        # 3️⃣  Alias for _refresh()
        self.watchlist_content_frame = self.wl_strip

        # 4️⃣  Clone strip
        self.wl_clone = ttk.Frame(self.wl_canvas)
        self.wl_clone_window = self.wl_canvas.create_window(
            (0, 0), window=self.wl_clone, anchor="nw"
        )

        # Bind the events to the class method (not nested function)
        self.wl_strip.bind("<Configure>", self._sync_wl_strip)
        self.wl_canvas.bind("<Configure>", self._sync_wl_strip)

        # ── Top Movers (greatest ±% change among watch-list) ─────────
        movers_card = ttk.LabelFrame(overview_frame, text="Top Movers")
        movers_card.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        self.movers_content_frame = ttk.Frame(movers_card)
        self.movers_content_frame.pack(fill="both", expand=True, padx=5, pady=5)



    def _sync_wl_strip(self, event=None):
        """
        Keep the canvas' scroll-region and the two ticker rows in sync.
        Called every time the inner strip changes size.
        """
        strip_w = self.wl_strip.winfo_reqwidth()
        if not strip_w: 
            return
        xview = self.wl_canvas.xview()          # ← remember position
        
       

        # 1️⃣  make BOTH windows exactly the same width
        self.wl_canvas.itemconfigure(self.wl_window, width=strip_w)
        self.wl_canvas.itemconfigure(self.wl_clone_window, width=strip_w)

        # 2️⃣  Set scroll region to accommodate both strips side by side
        self.wl_canvas.configure(scrollregion=(0, 0, strip_w * 2, 90))

        # 3️⃣  Position clone immediately after original (no gap)
        self.wl_canvas.coords(self.wl_clone_window, strip_w, 0)
        self.wl_canvas.xview_moveto(xview[0])   # ← restore position

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
            "💡 Idea Suite":          self.controller.launch_idea_suite, 
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
        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return
        try:
            tz = ZoneInfo(self.controller.settings.get("timezone"))
            now = datetime.now(tz)
        except Exception:
            now = datetime.now()
        self.time_lbl.config(text=now.strftime("%b %d, %Y  %H:%M:%S"))
        # ← new: refresh the market‐open indicator
        self._update_market_status(now)
        self._time_after_id = self.after(1000, self._update_time)

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
        self._wifi_check_after_id = self.after(5000, self.check_wifi)

    def _poll_wifi_queue(self):
        try:
            while True:
                status = self._wifi_queue.get_nowait()
                self._update_wifi_icon(status)
        except queue.Empty:
            pass
        self._wifi_poll_after_id = self.after(100, self._poll_wifi_queue)


    # ──────────────────────────────────────────────────────────────
    # Queue pollers (run on main/Tk thread)
    # ──────────────────────────────────────────────────────────────
    def _poll_indices_q(self):
        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return

        try:
            while True:                               # drain the queue
                data = self._indices_q.get_nowait()
                self._update_indices_ui(data)
        except queue.Empty:
            pass
        if self.winfo_exists():                       # keep polling
            self._indices_after_id = self.after(100, self._poll_indices_q)


    def _poll_watchlist_q(self):
        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return

        try:
            while True:
                data = self._watchlist_q.get_nowait()
                self._update_watchlist_ui(data)

                # derive movers (greatest |%| change) from same data
                if data:
                    movers = sorted(
                        data,
                        key=lambda d: abs(
                            (d["regularMarketPrice"] - d["previousClose"])
                            / d["previousClose"]),
                        reverse=True)[:3]
                else:
                    movers = []
                self._update_movers_ui(movers)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._watchlist_after_id = self.after(100, self._poll_watchlist_q)



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

        # Explicitly update the label's background color during theme changes.
        if hasattr(self, "wifi_label"):
            self.wifi_label.configure(bg=bg)

        # Re-tint all icons
        for key in self.wifi_icons:
            path = ICON_DIR / f"wifi_{key}.png"
            self.wifi_icons[key] = load_icon(path, tint_color=fg)
            
        # Re-apply the current icon to the label
        if hasattr(self, "_last_wifi_status"):
            self._update_wifi_icon(self._last_wifi_status)

        # Update the market canvas background to match the theme
        if hasattr(self, "wl_canvas"):
            canvas_bg = self.controller.theme_settings()['bg']
            self.wl_canvas.configure(bg=canvas_bg)


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
        # ADD THIS GUARD: Prevents running on a closed window
        if self._is_closing or not _widget_is_alive(self):
            return

        # greeting
        self.header_lbl.config(text=f"Welcome, {self.controller.user_name}!")

        # ─── Indices card ────────────────────────────────────────────────
        for w in self.indices_content_frame.winfo_children():
            w.destroy()
        ttk.Label(self.indices_content_frame, text="Loading indices…").pack()

        def fetch_indices():
            data = []
            for tkr in ("^SPX", "^VIX"):
                try:
                    d = self.data_mgr.get_ticker_details(tkr)
                    if d:
                        data.append(d)
                except Exception as e:
                    logging.exception("Index fetch failed: %s", e)
            self._indices_q.put(data)          #  ✅  queue hand-off

        threading.Thread(target=fetch_indices, daemon=True).start()


        # ─── Fear & Greed ────────────────────────────────────────────────
        def fetch_fng():
            score = self.data_mgr.get_fear_greed()
            try:
                self.after(0, self._update_fng_ui, score)
            except RuntimeError:
                pass
        threading.Thread(target=fetch_fng, daemon=True).start()


        # ─── Watch-list card + Top Movers ────────────────────────────────
        if not hasattr(self, "_wl_loader"):
            self._wl_loader = ttk.Label(self.watchlist_content_frame,
                                        text="Refreshing watchlist…")
            self._wl_loader.pack(expand=True)

        watchlist = [
            t.strip()
            for t in self.controller.settings.get("watchlist", "").split("|")
            if t.strip()
        ]

        def fetch_watchlist_and_movers():
            data = []
            for t in watchlist:
                try:
                    d = self.data_mgr.get_ticker_details(t)
                    if d:
                        data.append(d)
                except Exception as e:
                    logging.exception("Watch-list fetch failed: %s", e)
            self._watchlist_q.put(data)          # ✅ single hand-off

        threading.Thread(target=fetch_watchlist_and_movers, daemon=True).start()

        # ─── News panel ─────────────────────────────────────────────────
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
            if score is None:
                tag, val = "", "N/A"
            else:
                if score > 0.25:
                    tag = "pos"
                elif score < -0.25:
                    tag = "neg"
                else:
                    tag = "neu"
                val = f"{score:+.2f}"
            self.news_tv.insert("", "end", values=(title, val, url), tags=(tag,))
        self.news_tv.tag_configure("pos", foreground="green")
        self.news_tv.tag_configure("neg", foreground="red")
        self.news_tv.tag_configure("neu", foreground="orange")


    def _auto_refresh(self):
        #GUARD: Prevents running on a closed window
        if self._is_closing or not _widget_is_alive(self):
            return
        self._refresh()
        # SAVE THE ID: This allows shutdown() to cancel the task
        self._auto_refresh_id = self.after(30_000, self._auto_refresh)

    def _create_ticker_box(self, parent, data, context_ticker=None):
        """Creates and returns a styled frame for a single ticker."""
        price = data.get('regularMarketPrice', 0)
        prev_close = data.get('previousClose', 0)
        display_ticker = data.get('symbol', 'N/A')
        
        # If a specific ticker for context menus is not provided, use the display one.
        # This allows us to show "S&P 500" but have the right-click link to "^SPX".
        bind_ticker = context_ticker if context_ticker is not None else display_ticker

        change = price - prev_close
        pct_change = (change / prev_close) * 100 if prev_close != 0 else 0

        color = "green" if change >= 0 else "red"
        sign = "+" if change >= 0 else ""

        box = ttk.Frame(parent, borderwidth=1, relief="groove", padding=(8, 4))
        box.pack(side="left", padx=4, pady=4, fill="x")

        ticker_lbl = ttk.Label(box, text=display_ticker, font=("Segoe UI", 11, "bold"))
        ticker_lbl.grid(row=0, column=0, sticky="w")

        price_lbl = ttk.Label(box, text=f"{price:,.2f}", font=("Segoe UI", 11))
        price_lbl.grid(row=0, column=1, sticky="e", padx=(15, 0))

        change_text = f"{sign}{change:,.2f} ({sign}{pct_change:.2f}%)"
        change_lbl = ttk.Label(box, text=change_text, foreground=color, font=("Segoe UI", 9))
        change_lbl.grid(row=1, column=0, columnspan=2, sticky="w")

        # Bind the right-click event using the correct ticker for the web link
        for widget in [box, ticker_lbl, price_lbl, change_lbl]:
            widget.bind("<Button-3>", lambda event, t=bind_ticker: self._show_ticker_context_menu(event, t))
        
        #Ensure the created box is returned
        return box
    
    def _view_chart_for_ticker(self, ticker: str):
        """
        Switch the right-hand chart pane to *ticker* and update the header text.
        Also save it as the new default so the choice persists.
        """
        # redraw chart
        self.chart_pane.set_ticker(ticker)                    # uses CandlestickChartPane.set_ticker :contentReference[oaicite:3]{index=3}
        # update the frame’s title bar
        self.chart_box.config(text=f"{ticker} Chart")
        # remember for next launch
        try:
            self.controller.settings.set("default_ticker", ticker)
        except Exception:
            pass   # settings persistence is best-effort

        
    def _show_ticker_context_menu(self, event, ticker):
        """Right-click menu for a watch-list ticker."""
        m = tk.Menu(self, tearoff=0)
        m.add_command(
            label=f"View {ticker} on Google Finance",
            command=lambda t=ticker: self._open_google_finance(t)
        )
        m.add_command(                                  # ← NEW
            label="View chart",
            command=lambda t=ticker: self._view_chart_for_ticker(t)
        )
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _open_google_finance(self, ticker):
        """Opens a Google search for the ticker's stock info for reliability."""
        import webbrowser
        # Using a search query is more robust than guessing the exchange (e.g., NASDAQ, NYSE)
        webbrowser.open(f"https://www.google.com/search?q=stock%20price%20{ticker}")
    
    # ──────────────────────────────────────────────────────────────────
    def _update_watchlist_ui(self, data):
        """
        Rebuild the scrolling marquee using the regular full-size
        ticker boxes created by _create_ticker_box, then (re)start the
        infinite scroll animation.
        """

        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return
        
        #kill loading label
        if hasattr(self, "_wl_loader"):
            self._wl_loader.destroy()
            del self._wl_loader

        # Stop existing animation cleanly
        self._stop_watchlist_marquee()

        # Clear both the main strip and its clone
        for frame in (self.wl_strip, self.wl_clone):
            for w in frame.winfo_children():
                w.destroy()

        if not data:
            ttk.Label(self.wl_strip, text="Watch-list empty…").pack(padx=6)
            return

        # Populate original + clone strips with IDENTICAL boxes
        for d in data:
            # original row
            self._create_ticker_box(self.wl_strip, d)
            # clone row for seamless wrap-around
            self._create_ticker_box(self.wl_clone, d)

        # Ensure canvas size / scroll-region are up-to-date
        self.wl_strip.update_idletasks()
        # Trigger canvas configure to sync scroll region
        self.wl_canvas.event_generate("<Configure>")
        
        # Small delay to let UI settle before starting animation
        self.after(50, self._start_watchlist_marquee)

    def _update_indices_ui(self, all_data):
        """Callback function to build the indices UI on the main thread."""
        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return
        
        for widget in self.indices_content_frame.winfo_children():
            widget.destroy()

        if not all_data:
            ttk.Label(self.indices_content_frame, text="Could not load market data.").pack()
            return

        name_map = {
            '^SPX': 'S&P 500',
            '^VIX': 'VIX'
        }

        for data in all_data:
            original_ticker = data['symbol']
            data['symbol'] = name_map.get(original_ticker, original_ticker)
            
            # Create the box, passing the original ticker for the right-click context menu
            self._create_ticker_box(self.indices_content_frame, data, context_ticker=original_ticker)

    def _update_movers_ui(self, movers):
        """Populate Top Movers as one concise summary line."""
        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return
        
        for w in self.movers_content_frame.winfo_children():
            w.destroy()

        if not movers:
            ttk.Label(self.movers_content_frame,
                      text="No data (empty watch-list?)").pack()
            return

        parts = []
        for d in movers:
            sym   = d["symbol"]
            prc   = d["regularMarketPrice"]
            prev  = d["previousClose"]
            pct   = (prc - prev) / prev * 100 if prev else 0
            sign  = "+" if pct >= 0 else ""
            parts.append(f"{sym} {sign}{pct:.1f}%")

        summary = "   •   ".join(parts)
        ttk.Label(
            self.movers_content_frame,
            text=summary,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

    def _start_watchlist_marquee(self):
        """
        Robust continuous scrolling marquee with proper speed control and cleanup.
        """

        if self._is_closing or not _widget_is_alive(self):
            return
        # Stop any existing animation cleanly
        self._stop_watchlist_marquee()
        
        # Wait for UI to settle before starting
        self.wl_strip.update_idletasks()
        strip_width = self.wl_strip.winfo_reqwidth()
        
        if strip_width <= 0:
            return
        
        # Initialize marquee state
        self._wl_animating = True
        self._marquee_position = 0.0  # Absolute pixel position
        
        # Get speed setting (pixels per frame)
        speed_setting = float(self.controller.settings.get("marquee_speed", 1.5))
        # Convert speed setting to actual pixels per frame
        # Speed 1.0 = 1 pixel per frame, Speed 2.0 = 2 pixels per frame, etc.
        self._pixels_per_frame = max(0.1, speed_setting)
        
        # Animation timing
        self._frame_delay = 16  # ~60 FPS
        
        def _animate_step():
            """Single animation step with robust error handling."""
            if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
                return
            
            if not self._wl_animating:
                return
                
            try:
                # Check if canvas still exists
                if not self.wl_canvas.winfo_exists():
                    self._wl_animating = False
                    return
                
                # Update position
                self._marquee_position += self._pixels_per_frame
                
                # Reset position when we've scrolled one full strip width
                if self._marquee_position >= strip_width:
                    self._marquee_position = 0.0
                
                # Convert to fractional position for xview_moveto
                # Total scrollable area is strip_width * 2 (original + clone)
                fractional_pos = self._marquee_position / (strip_width * 2)
                
                # Apply scroll position
                self.wl_canvas.xview_moveto(fractional_pos)
                
                # Schedule next frame
                if self._wl_animating:
                    self._wl_after_id = self.wl_canvas.after(self._frame_delay, _animate_step)
                    
            except tk.TclError:
                # Widget destroyed during animation
                self._wl_animating = False
            except Exception as e:
                # Unexpected error - stop animation gracefully
                print(f"Marquee animation error: {e}")
                self._wl_animating = False
        
        # Start the animation
        _animate_step()

    def _stop_watchlist_marquee(self):
        """
        Cleanly stop the marquee animation.
        """
        self._wl_animating = False
        if hasattr(self, '_wl_after_id') and self._wl_after_id:
            try:
                # CRUCIAL FIX: The 'after' job was scheduled on the canvas.
                self.wl_canvas.after_cancel(self._wl_after_id)
            except Exception:
                pass
            self._wl_after_id = None

    def _update_marquee_speed(self):
        """
        Update marquee speed without restarting the entire animation.
        Call this when speed settings change.
        """
        if hasattr(self, '_wl_animating') and self._wl_animating:
            # Update speed on the fly
            speed_setting = float(self.controller.settings.get("marquee_speed", 1.5))
            self._pixels_per_frame = max(0.1, speed_setting)

    def _update_fng_ui(self, score: int | None):
        """
        Update the mini Fear & Greed gauge on the header.
        Draws a coloured arc, a centre value, and a needle.
        Also refreshes the tooltip with a plain-language interpretation.
        """
        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return
        
        c = self.fng_canvas
        c.delete("fng_gauge")                       # clear previous drawing

        # ── Static layout constants ─────────────────────────────────────
        cx, cy   = 35, 35          # centre
        radius   = 28
        arc_w    = 6

        # background semicircle (grey)
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        c.create_arc(*bbox, start=0, extent=180,
                    style="arc", width=arc_w,
                    outline="#555555", tags="fng_gauge")

        # ---------------- if data unavailable --------------------------
        if score is None:
            c.create_text(cx, cy - 5, text="N/A",
                        font=("Segoe UI", 12, "bold"),
                        fill="grey", tags="fng_gauge")
            self.fng_tooltip.update("Fear & Greed index unavailable")
            return

        # ── Colour & sentiment text by range ───────────────────────────
        if score < 25:
            clr, mood, note = "#D32F2F", "Extreme Fear", "Stocks may be undervalued"
        elif score < 50:
            clr, mood, note = "#F57C00", "Fear", "Bearish undertone"
        elif score < 75:
            clr, mood, note = "#9ACD32", "Greed", "Bullish sentiment"
        else:
            clr, mood, note = "#00B200", "Extreme Greed", "Markets may be overheated"

        # ── Dynamic coloured arc ---------------------------------------
        # score 0 → 180°, score 100 → 0°
        sweep_start = 180 - score * 1.8
        c.create_arc(*bbox, start=sweep_start, extent=180 - sweep_start,
                    style="arc", width=arc_w,
                    outline=clr, tags="fng_gauge")

        # ── Centre text -------------------------------------------------
        c.create_text(cx, cy - 8, text=str(score),
                    font=("Segoe UI", 14, "bold"),
                    fill=clr, tags="fng_gauge")
        c.create_text(cx, cy + 6, text="F&G Index",
                    font=("Segoe UI", 7),
                    fill="grey", tags="fng_gauge")

        # ── Tooltip -----------------------------------------------------
        self.fng_tooltip.update(f"{score} – {mood}\n{note}")

    def shutdown(self):
        """
        Called once, just before the root window is destroyed.
        It stops every repeating 'after' job, including the marquee animation,
        and marks the widget as closing so background threads exit early.
        """
        self._is_closing = True
        self._wl_animating = False # Stop marquee loop condition first

        # List of timers belonging to `self` (the HomeDashboard frame)
        frame_timers = [
            "_time_after_id", "_indices_after_id", "_watchlist_after_id",
            "_wifi_poll_after_id", "_wifi_check_after_id", "_auto_refresh_id",
        ]
        for attr in frame_timers:
            after_id = getattr(self, attr, None)
            if after_id:
                try:
                    self.after_cancel(after_id)
                except Exception:
                    pass

        # The marquee timer belongs to the CANVAS, not the frame.
        # This was the source of the freeze.
        marquee_timer_id = getattr(self, "_wl_after_id", None)
        if marquee_timer_id:
            try:
                # Crucial fix: cancel the timer on the widget that created it.
                self.wl_canvas.after_cancel(marquee_timer_id)
            except Exception:
                pass


