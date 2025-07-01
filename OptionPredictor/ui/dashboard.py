from __future__ import annotations
import queue, threading, logging, webbrowser
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
import json

import tkinter as tk
from tkinter import ttk


from ui.candlestick_pane import CandlestickChartPane
from core.engine.strategy_tester import load_icon, ICON_DIR

REFRESH_INTERVAL = 30 # seconds between data refreshes

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


# ────────────────────────────────────────────────────────────────
# LayoutDragManager  ✦  drag-swap + delete-tile (no resize)
# ────────────────────────────────────────────────────────────────
class LayoutDragManager:
    OUTLINE_COLOR = "#3498db"
    OUTLINE_WIDTH = 2
    GRID_COLS     = 2          # tiles per row when re-flowing deleted layout

    def __init__(self, container: tk.Widget, components: dict[str, ttk.Widget]):
        self.container   = container
        self.components  = components          # {name: widget}
        self._dragging   = None
        self._indicator  = None
        self._close_btns = {}                  # widget → ✕ label
        self._edit_mode  = False

    # ── public toggles ───────────────────────────────────────────
    def enable_edit_mode(self, flag: bool = True):
        if flag and not self._edit_mode:
            self._bind_all()
            self._add_close_badges()
        elif not flag and self._edit_mode:
            self._unbind_all()
            self._remove_badges()
            self._hide_indicator()
        self._edit_mode = flag

    def save_layout(self):               # just an alias for external call-sites
        self.enable_edit_mode(False)

    # ── drag mechanics ───────────────────────────────────────────
    def _bind_all(self):
        for w in self.components.values():
            w.bind("<ButtonPress-1>",  self._on_press,   add="+")
            w.bind("<B1-Motion>",      self._on_motion,  add="+")
            w.bind("<ButtonRelease-1>",self._on_release, add="+")
            w.configure(cursor="hand2")

    def _unbind_all(self):
        for w in self.components.values():
            w.unbind("<ButtonPress-1>")
            w.unbind("<B1-Motion>")
            w.unbind("<ButtonRelease-1>")
            w.configure(cursor="")
        self.container.configure(cursor="")

    def _on_press(self, event):
        widget = self._top_parent(event.widget)
        if widget in self.components.values():
            self._dragging = widget
            widget.lift()
            self._show_indicator(widget)

    def _on_motion(self, event):
        if not self._dragging:
            return
        target = self._widget_under_pointer(event.x_root, event.y_root)
        if target and target is not self._dragging:
            self._show_indicator(target)

    def _on_release(self, event):
        if not self._dragging:
            return
        target = self._widget_under_pointer(event.x_root, event.y_root)
        if target and target is not self._dragging:
            self._swap_positions(self._dragging, target)
        self._hide_indicator()
        self._dragging = None

    # ── swapping + helper ────────────────────────────────────────
    def _swap_positions(self, w1, w2):
        i1, i2 = w1.grid_info(), w2.grid_info()
        w1.grid(row=i2["row"], column=i2["column"],
                sticky="nsew", padx=5, pady=5)
        w2.grid(row=i1["row"], column=i1["column"],
                sticky="nsew", padx=5, pady=5)

    def _widget_under_pointer(self, x_root, y_root):
        for w in self.components.values():
            if w is self._dragging or not _widget_is_alive(w):
                continue
            x, y = w.winfo_rootx(), w.winfo_rooty()
            if x <= x_root <= x + w.winfo_width() and y <= y_root <= y + w.winfo_height():
                return w
        return None

    # ── visual outline ───────────────────────────────────────────
    def _show_indicator(self, widget):
        if self._indicator is None:
            self._indicator = tk.Frame(self.container, bg="",
                                       highlightthickness=self.OUTLINE_WIDTH,
                                       highlightbackground=self.OUTLINE_COLOR)
        self._indicator.place(x=widget.winfo_x(), y=widget.winfo_y(),
                              width=widget.winfo_width(), height=widget.winfo_height())

    def _hide_indicator(self):
        if self._indicator:
            self._indicator.place_forget()

    # ── ✕ delete badges ─────────────────────────────────────────
    def _add_close_badges(self):
        for tile in self.components.values():
            btn = tk.Label(tile, text="✕", font=("Segoe UI", 9, "bold"),
                           fg="#ffffff", bg="#cc0000", cursor="hand2")
            btn.place(relx=1.0, x=-12, y=2, anchor="ne")
            btn.bind("<Button-1>", lambda _e, t=tile: self._delete_tile(t))
            self._close_btns[tile] = btn

    def _remove_badges(self):
        for b in self._close_btns.values():
            b.destroy()
        self._close_btns.clear()

    # ────────────────────────────────────────────────────────────────
    def _reflow_visible_tiles(self):
        """
        Lay out **only** the tiles that are currently mapped
        in a clean 2-column grid.  If the last row has a single tile
        it spans both columns for a balanced look.
        """
        visible = [w for w in self.components.values() if w.winfo_manager()]
        total   = len(visible)

        for idx, w in enumerate(visible):
            row = idx // self.GRID_COLS
            col = idx % self.GRID_COLS

            # full-width if it’s the last tile AND an odd count
            colspan = 2 if (idx == total - 1 and total % self.GRID_COLS == 1) else 1

            w.grid(row=row, column=col,
                rowspan=1, columnspan=colspan,
                sticky="nsew", padx=5, pady=5)


    def _delete_tile(self, tile):
        """
        Hide the tile, then call _reflow_visible_tiles()
        so the remaining widgets fill the space gracefully.
        """
        # 1) remove from the grid
        tile.grid_forget()

        # 2) remove its ✕ badge if present
        if badge := self._close_btns.pop(tile, None):
            badge.destroy()

        # 3) tidy up the rest
        self._reflow_visible_tiles()

    # ── misc helpers ─────────────────────────────────────────────
    @staticmethod
    def _top_parent(widget):
        while widget.master and not isinstance(widget, ttk.LabelFrame):
            widget = widget.master
        return widget

    def cleanup(self):
        self.enable_edit_mode(False)


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

        # ─── auto-refresh bookkeeping ─────────────────────────────────────
        self._last_update_ts   = None     # datetime of last successful _refresh()
        self._countdown_after  = None     # after() id for 1-second countdown ticks
        self._countdown_secs   = REFRESH_INTERVAL

        # --- Layout Customization State ---
        self._in_customize_mode = False
        self._drag_manager = None
        self._components = {}
        self._component_builders = {}
        self._main_content_frame = None


       
        # Configure the main frame's grid layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1) 

        self._build_ui()

        # ─── persistent drag-and-resize manager (starts disabled) ───
        self.drag_mgr = LayoutDragManager(self._main_content_frame,
                                          self._components)

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
        self._start_refresh_countdown()   # immediate first load + countdown

    # --- UI Construction ---

    def _build_ui(self):
        """Constructs the UI by building and placing modular components."""
        self._build_header()

        self._main_content_frame = ttk.Frame(self)
        self._main_content_frame.grid(row=1, column=0, sticky="nsew", pady=15)
        self._main_content_frame.columnconfigure((0, 1), weight=1)
        # CRITICAL FIX: Make the row with news/chart expandable
        self._main_content_frame.rowconfigure(2, weight=1)

        self._register_component_builders()
        self._apply_layout()

        ttk.Separator(self).grid(row=2, column=0, pady=15, sticky="ew")
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


    def _register_component_builders(self):
        """Maps component names to their creation methods for dynamic layout."""
        self._component_builders = {
            "indices": self._create_indices_card,
            "watchlist": self._create_watchlist_card,
            "movers": self._create_movers_card,
            "news": self._create_news_pane,
            "chart": self._create_chart_pane
        }

    def _apply_layout(self):
        """Loads layout from settings and grids components accordingly."""
        try:
            layout_json = self.controller.settings.get('dashboard_layout')
            saved_layout = json.loads(layout_json) if layout_json else self._get_default_layout()
        except (json.JSONDecodeError, TypeError):
            saved_layout = self._get_default_layout()

        for comp_info in saved_layout:
            name = comp_info["name"]
            if name not in self._components:
                builder = self._component_builders.get(name)
                if builder:
                    self._components[name] = builder(self._main_content_frame)

            widget = self._components.get(name)
            if widget:
                widget.grid(row=comp_info["row"], column=comp_info["column"],
                            rowspan=comp_info["rowspan"], columnspan=comp_info["columnspan"],
                            sticky="nsew", padx=5, pady=5)

    def _get_default_layout(self):
        """Returns the factory-default layout configuration."""
        return [
            {"name": "indices",   "row": 0, "column": 0, "rowspan": 1, "columnspan": 1},
            {"name": "watchlist", "row": 0, "column": 1, "rowspan": 1, "columnspan": 1},
            {"name": "movers",    "row": 1, "column": 0, "rowspan": 1, "columnspan": 2},
            {"name": "news",      "row": 2, "column": 0, "rowspan": 1, "columnspan": 1},
            {"name": "chart",     "row": 2, "column": 1, "rowspan": 1, "columnspan": 1}
        ]

    # These are the refactored builder methods. Add all five.
    def _create_indices_card(self, parent):
        indices_card = ttk.LabelFrame(parent, text="Market Indices")
        self.indices_content_frame = ttk.Frame(indices_card)
        self.indices_content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        return indices_card

    def _create_watchlist_card(self, parent):
        watchlist_card = ttk.LabelFrame(parent, text="Watchlist")
        watchlist_card.config(height=90)
        bg_color = self.controller.theme_settings()['bg']
        self.wl_canvas = tk.Canvas(watchlist_card, height=90, highlightthickness=0, bd=0, bg=bg_color)
        self.wl_canvas.pack(fill="both", expand=True)
        self.wl_strip = ttk.Frame(self.wl_canvas)
        self.wl_window = self.wl_canvas.create_window((0, 0), window=self.wl_strip, anchor="nw")
        self.watchlist_content_frame = self.wl_strip
        self.wl_clone = ttk.Frame(self.wl_canvas)
        self.wl_clone_window = self.wl_canvas.create_window((0, 0), window=self.wl_clone, anchor="nw")
        self.wl_strip.bind("<Configure>", self._sync_wl_strip)
        self.wl_canvas.bind("<Configure>", self._sync_wl_strip)
        return watchlist_card

    def _create_movers_card(self, parent):
        movers_card = ttk.LabelFrame(parent, text="Top Movers")
        self.movers_content_frame = ttk.Frame(movers_card)
        self.movers_content_frame.pack(fill="both", expand=True, padx=5, pady=5)
        return movers_card

    def _create_news_pane(self, parent):
        news_box = ttk.LabelFrame(parent, text="Market News (Recent First)", padding=10)
        news_box.columnconfigure(0, weight=1)
        news_box.rowconfigure(1, weight=1)
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
        return news_box

    def _create_chart_pane(self, parent):
        default_ticker = self.controller.settings.get('default_ticker', 'SPY')
        chart_box = ttk.LabelFrame(parent, text=f"{default_ticker} Chart", padding=5)
        chart_box.columnconfigure(0, weight=1)
        chart_box.rowconfigure(0, weight=1)
        self.chart_box = chart_box
        self.chart_pane = CandlestickChartPane(chart_box, theme=self.controller.current_theme, ticker=default_ticker)
        self.chart_pane.grid(row=0, column=0, sticky="nsew")
        return chart_box

    def _build_footer(self):
        """Builds the bottom footer with quick actions and settings."""
        footer_frame = ttk.Frame(self)
        footer_frame.grid(row=4, column=0, sticky="ew") # Use row 4 in your original file if needed
        footer_frame.columnconfigure(2, weight=1) # Spacer column

        # Customization Buttons
        self.customize_btn = ttk.Button(footer_frame, text="🎨 Customize Layout", command=lambda: self._toggle_customize_mode(True), style="Pill.TButton")
        self.customize_btn.grid(row=0, column=0, sticky="w", padx=(0,5))
        # brand-new reset button (hidden by default)
        self.reset_layout_btn = ttk.Button(
            footer_frame, text="🔄 Reset Layout",
            command=self._reset_to_default, style="Pill.TButton")
        self.reset_layout_btn.grid_remove()
        self.save_layout_btn = ttk.Button(footer_frame, text="✅ Save Layout", command=self._save_layout, style="Pill.TButton")
        self.cancel_layout_btn = ttk.Button(footer_frame, text="❌ Cancel", command=self._cancel_layout, style="Pill.TButton")
        self.save_layout_btn.grid_remove()
        self.cancel_layout_btn.grid_remove()

        # Settings button
        ttk.Button(footer_frame, text="⚙ Settings", command=self.controller.open_settings_window, style="Pill.TButton").grid(row=0, column=1, sticky="w")
        
        self.refresh_lbl = ttk.Label(footer_frame, text="Updated: —   Next: —", font=("Segoe UI", 9))
        self.refresh_lbl.grid(row=0, column=2, sticky="e")
        
        actions_frame = ttk.Frame(footer_frame)
        actions_frame.grid(row=0, column=3, sticky="e")
        
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

    
    def _toggle_customize_mode(self, enable: bool):
        """
        Turns layout edit mode on/off.
        While enabled you can drag-swap or resize tiles;
        disabling locks the layout again.
        """
        self._in_customize_mode = enable

        if enable:
            # swap button set
            self.customize_btn.grid_remove()
            self.save_layout_btn.grid(row=0, column=0, sticky="w", padx=(0, 5))
            self.cancel_layout_btn.grid(row=0, column=1, sticky="w", padx=(0, 5))
            
            self.reset_layout_btn.grid(row=0, column=2, sticky="w", padx=(0, 5))
            # activate manager
            self.drag_mgr.enable_edit_mode(True)

        else:
            # restore original buttons
            self.save_layout_btn.grid_remove()
            self.cancel_layout_btn.grid_remove()
            self.customize_btn.grid()

            self.reset_layout_btn.grid_remove()
            # deactivate manager
            self.drag_mgr.enable_edit_mode(False)

    def _get_or_create_tile(self, name: str):
        """
        Return (and if needed build) the tile called *name*.

        Uses the same builders that _register_component_builders()
        stored in self._component_builders, so the names in
        _get_default_layout always line up.
        """
        # Already present → just return it
        if name in self._components:
            return self._components[name]

        # Otherwise build it with the registry we set up earlier
        builder = self._component_builders.get(name)
        if builder is None:
            raise ValueError(f"Unknown dashboard tile: {name!r}")

        widget = builder(self._main_content_frame)   # create the card
        self._components[name] = widget
        return widget

    def _reset_to_default(self):
        """
        Restore factory layout no matter which tiles were deleted.
        """
        # forget every tile that is currently visible
        for w in self._components.values():
            w.grid_forget()

        # default grid spec
        default = self._get_default_layout()      # ← your existing helper

        for info in default:
            tile = self._get_or_create_tile(info["name"])   # ensure exists
            tile.grid(
                row=info["row"], column=info["column"],
                rowspan=info["rowspan"], columnspan=info["columnspan"],
                sticky="nsew", padx=5, pady=5
            )

        # save & exit customise mode
        self.controller.settings.set(
            "dashboard_layout", json.dumps(default)
        )
        self._toggle_customize_mode(False)



    def _save_layout(self):
        self.drag_mgr.save_layout()          # ← locks drag & resize
        new_layout = []
        for name, widget in self._components.items():
            if not _widget_is_alive(widget) or not widget.grid_info(): continue
            info = widget.grid_info()
            new_layout.append({
                "name": name, "row": info["row"], "column": info["column"],
                "rowspan": info.get("rowspan", 1), "columnspan": info.get("columnspan", 1),
            })
        self.controller.settings.set('dashboard_layout', json.dumps(new_layout))
        self._toggle_customize_mode(enable=False)

    def _cancel_layout(self):
        self._toggle_customize_mode(enable=False)
        self._apply_layout() # Revert to last saved layout

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

    # ────────────────────────────────────────────────────────────────
    # Market-status indicator with live countdown
    # ────────────────────────────────────────────────────────────────
    def _update_market_status(self, now_local):
        """
        Replaces the old Open/Closed text with:
            Open  – closes in 03:12:44
            Pre-Market – opens in 00:27:33
            After-Hours – opens in 14:58:12
            Closed – opens in 43h 22m     (weekend)
        The coloured dot stays the same (green / orange / red).
        """
        from math import floor
        ny = now_local.astimezone(ZoneInfo("America/New_York"))

        open_dt   = ny.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_dt  = ny.replace(hour=16, minute=0, second=0, microsecond=0)
        ny_time   = ny.time()

        # default values
        status, color, msg = "Closed", "red", ""

        if ny.weekday() < 5:                               # Mon-Fri
            if self._ny_open <= ny_time <= self._ny_close:  # regular session
                status, color = "Open", "green"
                rem = close_dt - ny
                h, m, s = rem.seconds // 3600, (rem.seconds // 60) % 60, rem.seconds % 60
                msg = f" – closes in {h:02d}:{m:02d}:{s:02d}"
            elif ny_time < self._ny_open:                   # pre-market
                status, color = "Pre-Market", "orange"
                rem = open_dt - ny
                h, m, s = rem.seconds // 3600, (rem.seconds // 60) % 60, rem.seconds % 60
                msg = f" – opens in {h:02d}:{m:02d}:{s:02d}"
            else:                                           # after-hours
                status, color = "After-Hours", "orange"
                # next trading day (tomorrow or Monday)
                days = 1 if ny.weekday() < 4 else (7 - ny.weekday())
                next_open = open_dt + timedelta(days=days)
                rem = next_open - ny
                h, m, s = rem.seconds // 3600 + rem.days * 24, (rem.seconds // 60) % 60, rem.seconds % 60
                msg = f" – opens in {h:02d}:{m:02d}:{s:02d}"
        else:                                               # weekend
            days = (7 - ny.weekday()) % 7 or 1             # until next Monday
            next_open = open_dt + timedelta(days=days)
            rem = next_open - ny
            h_tot = rem.days * 24 + floor(rem.seconds / 3600)
            m = (rem.seconds // 60) % 60
            status, color = "Closed", "red"
            msg = f" – opens in {h_tot}h {m}m"

        # apply colours + text
        self.market_canvas.itemconfig(self.market_circle, fill=color)
        self.market_lbl.config(text=f"{status}{msg}", foreground=color)


    # ────────────────────────────────────────────────────────────────
    # Auto-refresh scheduler & per-second countdown
    # ────────────────────────────────────────────────────────────────
    def _start_refresh_countdown(self):
        """Trigger an immediate data load, then start the second-by-second clock."""
        self._refresh()                      # ← existing full refresh
        self._countdown_secs = REFRESH_INTERVAL
        self._tick_refresh_countdown()       # first tick

    def _tick_refresh_countdown(self):
        if self._is_closing or not _widget_is_alive(self):
            return

        # label text
        up_txt  = self._last_update_ts.strftime("%H:%M:%S") if self._last_update_ts else "—"
        nxt_txt = f"0:{self._countdown_secs:02d}"
        self.refresh_lbl.config(text=f"Updated: {up_txt}   Next: {nxt_txt}")

        # reached zero? → fetch & reset
        if self._countdown_secs == 0:
            self._refresh()
            self._countdown_secs = REFRESH_INTERVAL
        else:
            self._countdown_secs -= 1

        # schedule next one-second tick
        self._countdown_after = self.after(1000, self._tick_refresh_countdown)


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


    # ------------------------------------------------------------------
    # FULLY ROBUST _refresh : works no-matter which tiles were removed
    # ------------------------------------------------------------------
    def _refresh(self):
        # 1️⃣  Bail out if the window is going away
        if self._is_closing or not _widget_is_alive(self):
            return

        # 2️⃣  Clear whatever panels are still mapped
        for name in (
            "indices_content_frame",
            "movers_content_frame",
            "watchlist_content_frame",
            "news_tv"
        ):
            if not hasattr(self, name):
                continue
            widget = getattr(self, name)
            if not widget.winfo_manager():          # hidden via ✕
                continue

            # Treeview vs Frame
            if callable(getattr(widget, "delete", None)):
                widget.delete(*widget.get_children())
            else:
                for child in widget.winfo_children():
                    child.destroy()

        # 3️⃣  Greeting
        self.header_lbl.config(text=f"Welcome, {self.controller.user_name}!")

        # 4️⃣  Indices  ────────────────────────────────────────────────
        if hasattr(self, "indices_content_frame") and self.indices_content_frame.winfo_manager():
            ttk.Label(self.indices_content_frame,
                      text="Loading indices…").pack()
            def fetch_indices():
                data = []
                for tkr in ("^SPX", "^VIX"):
                    try:
                        d = self.data_mgr.get_ticker_details(tkr)
                        if d:
                            data.append(d)
                    except Exception as e:
                        logging.exception("Index fetch failed: %s", e)
                self._indices_q.put(data)
            threading.Thread(target=fetch_indices, daemon=True).start()

        # 5️⃣  Fear & Greed (always present)  ────────────────────────
        threading.Thread(
            target=lambda: self.after(
                0, self._update_fng_ui,
                self.data_mgr.get_fear_greed()
            ),
            daemon=True
        ).start()

        # 6️⃣  Watch-list + Movers  ──────────────────────────────────
        if hasattr(self, "watchlist_content_frame") and self.watchlist_content_frame.winfo_manager():
            if not hasattr(self, "_wl_loader"):
                self._wl_loader = ttk.Label(self.watchlist_content_frame,
                                            text="Refreshing watchlist…")
                self._wl_loader.pack(expand=True)

            watchlist = [
                t.strip() for t in
                self.controller.settings.get("watchlist", "").split("|")
                if t.strip()
            ]

            def fetch_watchlist():
                data = []
                for t in watchlist:
                    try:
                        d = self.data_mgr.get_ticker_details(t)
                        if d:
                            data.append(d)
                    except Exception as e:
                        logging.exception("Watch-list fetch failed: %s", e)
                self._watchlist_q.put(data)
            threading.Thread(target=fetch_watchlist, daemon=True).start()

        # 7️⃣  News pane  ────────────────────────────────────────────
        if hasattr(self, "news_tv") and self.news_tv.winfo_manager():
            rows, overall = self.data_mgr.get_news_headlines(20)
            if overall is None:
                txt, col = "Overall sentiment: N/A", "gray"
            elif overall > 0.25:
                txt, col = f"Overall sentiment: Bullish ({overall:+.2f})", "green"
            elif overall < -0.25:
                txt, col = f"Overall sentiment: Bearish ({overall:+.2f})", "red"
            else:
                txt, col = f"Overall sentiment: Neutral ({overall:+.2f})", "orange"
            self.overall_news_lbl.config(text=txt, foreground=col)

            for title, score, url in rows:
                if score is None:
                    tag, val = "", "N/A"
                else:
                    tag = "pos" if score > 0.25 else "neg" if score < -0.25 else "neu"
                    val = f"{score:+.2f}"
                self.news_tv.insert("", "end", values=(title, val, url), tags=(tag,))
            self.news_tv.tag_configure("pos", foreground="green")
            self.news_tv.tag_configure("neg", foreground="red")
            self.news_tv.tag_configure("neu", foreground="orange")

        # 8️⃣  Timestamp for the countdown strip
        self._last_update_ts = datetime.now()



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

    # ────────────────────────────────────────────────────────────────
    # Top-Movers card  —  horizontal layout
    # ────────────────────────────────────────────────────────────────
    def _update_movers_ui(self, movers):
        """
        Show movers on one row, coloured green (up) or red (down):
            TSLA: 231.15 ↑ 245.80 (+6.37%)   NVDA: 120.4 ↓ 114.1 (-5.23%) …
        """
        import tkinter as tk       # already present elsewhere, but here for clarity

        # block updates if window is closing
        if getattr(self, "_is_closing", False) or not _widget_is_alive(self):
            return

        # clear previous widgets
        for w in self.movers_content_frame.winfo_children():
            w.destroy()

        if not movers:
            ttk.Label(self.movers_content_frame,
                    text="No data (empty watch-list?)").pack()
            return

        # one label per mover, packed side-by-side
        for d in movers:
            sym   = d["symbol"]
            price = d["regularMarketPrice"]
            prev  = d["previousClose"] or 0.0
            pct   = (price - prev) / prev * 100 if prev else 0.0

            up     = price >= prev
            colour = "green" if up else "red"
            arrow  = "↑" if up else "↓"

            text = f"{sym}: {prev:,.2f} {arrow} {price:,.2f} ({pct:+.2f}%)"

            ttk.Label(
                self.movers_content_frame,
                text=text,
                foreground=colour,
                font=("Segoe UI", 10, "bold")
            ).pack(side=tk.LEFT, padx=10)   # ← horizontal layout

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
            "_wifi_poll_after_id", "_wifi_check_after_id", "_auto_refresh_id", "_countdown_after",
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

        if hasattr(self, '_drag_manager') and self._drag_manager:
            self._drag_manager.cleanup()


