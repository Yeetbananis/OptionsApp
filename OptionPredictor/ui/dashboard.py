from __future__ import annotations
import queue, threading, logging, webbrowser, time
from datetime import datetime, time as dt_time, timedelta
from zoneinfo import ZoneInfo
import json
from pathlib import Path
import json, matplotlib
matplotlib.use("Agg")                   # keep backend head-less friendly
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import tkinter as tk
from tkinter import ttk


from ui.candlestick_pane import CandlestickChartPane
from ui.bounceoverlay import BounceOverlay
from ui.events_calendar import EventsCalendar
from core.engine.strategy_tester import load_icon, ICON_DIR


_SENT_HISTORY_FILE = Path.home() / ".option_analyzer_sentiment.json"


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


# --------------------------------------------------------------------------
# SideMenu - A sliding navigation panel
# --------------------------------------------------------------------------
class SideMenu(ttk.Frame):
    """A sliding side menu for navigation, which appears over the main content."""
    def __init__(self, parent, controller, style):
        super().__init__(parent, style=style)
        self.parent = parent
        self.controller = controller
        self.is_open = False
        self._animation_job = None

        # --- Configuration ---
        self.menu_width_rel = 0.20  # 20% of parent width
        self.animation_speed = 15   # ms per frame
        self.animation_easing = 0.2 # Fraction of distance to move each frame

        # Initial placement (off-screen to the left)
        self.place(relx=-self.menu_width_rel, rely=0, relwidth=self.menu_width_rel, relheight=1)

        self._build_content()

        # Bind a click-away-to-close event to the parent
        self.parent.bind("<Button-1>", self._check_close, add="+")


    def _build_content(self):
        """Creates the buttons and widgets inside the menu."""
        container = ttk.Frame(self, padding=15)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)

        # --- Header with Title and Close Button ---
        header_frame = ttk.Frame(container)
        header_frame.pack(fill="x", pady=(0, 20), anchor="n")
        header_frame.columnconfigure(0, weight=1)

        title = ttk.Label(header_frame, text="Navigation", style="Title.TLabel")
        title.grid(row=0, column=0, sticky="w")

        style = "Toolbutton" if "Toolbutton" in ttk.Style().theme_names() else "TButton"
        close_btn = ttk.Button(header_frame, text="«", command=self.hide, style=style, width=3)
        close_btn.grid(row=0, column=1, sticky="e")
        Tooltip(close_btn, "Close Menu")

        #  Frame to hold New and Load buttons side-by-side
        analysis_actions_frame = ttk.Frame(container)
        analysis_actions_frame.pack(fill="x", pady=4)
        analysis_actions_frame.columnconfigure((0, 1), weight=1) # Make columns share space

        new_btn = ttk.Button(analysis_actions_frame, text="✨ New Analysis", command=self.controller.open_input_window, style="Accent.TButton")
        new_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        Tooltip(new_btn, "Run a new Monte Carlo simulation.")

        load_btn = ttk.Button(analysis_actions_frame, text="📂 Load Analysis", command=self.controller._launch_load_window, style="Pill.TButton")
        load_btn.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        Tooltip(load_btn, "Load a previously saved analysis.")


        # --- Other Action Buttons (New Analysis is no longer here) ---
        btn_map = {
            "💡 Idea Suite": self.controller.launch_idea_suite,
            "📰 Sentiment Analyzer": self.controller.launch_news_sentiment_analyzer,
            "📐 Strategy Builder": self.controller.launch_strategy_builder,
            "🧪 Strategy Tester": self.controller.launch_strategy_tester,
            "💬 Chatbot": self.controller.launch_chatbot,
        }
        for text, cmd in btn_map.items():
            btn = ttk.Button(container, text=text, command=cmd, style="Pill.TButton")
            btn.pack(fill="x", pady=4)

        ttk.Separator(container, orient="horizontal").pack(fill="x", pady=20)

        # --- Settings & Layout ---
        settings_btn = ttk.Button(container, text="⚙ Settings", command=self.controller.open_settings_window, style="Pill.TButton")
        settings_btn.pack(fill="x", pady=4)

        customize_btn = ttk.Button(container, text="🎨 Customize Layout", command=self._toggle_customize_and_close, style="Pill.TButton")
        customize_btn.pack(fill="x", pady=4)

    def _toggle_customize_and_close(self):
        """Wrapper to enter customize mode AND close the menu."""
        self.parent._toggle_customize_mode(True)
        self.hide()

    def toggle(self):
        """Opens or closes the menu with a sliding animation."""
        if self.is_open:
            self.hide()
        else:
            self.show()

    def show(self):
        """Animates the menu into view."""
        if self.is_open:
            return
        if self._animation_job:
            self.after_cancel(self._animation_job)

        self.is_open = True
        self.lift()  # Bring to the front
        self._animate(target_relx=0)

    def hide(self):
        """Animates the menu out of view."""
        if not self.is_open:
            return
        if self._animation_job:
            self.after_cancel(self._animation_job)

        self.is_open = False
        self._animate(target_relx=-self.menu_width_rel)

    def _animate(self, target_relx):
        """The animation engine for sliding the menu."""
        current_relx = float(self.place_info()['relx'])
        distance = target_relx - current_relx

        # Stop when very close to the target
        if abs(distance) < 0.001:
            self.place(relx=target_relx)
            self._animation_job = None
            if not self.is_open:
                self.lower()  # Hide behind main content after closing
            return

        # Move a fraction of the remaining distance for a smooth ease-out effect
        new_relx = current_relx + distance * self.animation_easing
        self.place(relx=new_relx)

        self._animation_job = self.after(self.animation_speed, lambda: self._animate(target_relx))

    def _check_close(self, event):
        """Closes the menu if the user clicks anywhere outside of it."""
        if not self.is_open:
            return

        # Do nothing if the click was on the menu button itself (it handles its own toggle)
        menu_button = getattr(self.parent, 'menu_btn', None)
        if event.widget == menu_button:
            return

        # Check if the click was inside the side menu or one of its children
        try:
            if self.winfo_containing(event.x_root, event.y_root) is not None:
                return  # Click was inside the menu, so do nothing.
        except (KeyError, tk.TclError):
            return # Widget might be getting destroyed, just exit.

        # If we reach here, the click was outside.
        self.hide()

    def shutdown(self):
        """Clean up resources like running animations and event bindings."""
        if self._animation_job:
            self.after_cancel(self._animation_job)
        try:
            self.parent.unbind("<Button-1>")
        except tk.TclError:
            pass # Ignore errors if parent is already destroyed.


class HomeDashboard(ttk.Frame):
    """
    A professionally organized visual dashboard that provides a clear, at-a-glance
    view of market information and application actions.
    """
    def __init__(self, parent, controller):
        super().__init__(parent, padding="15 15 15 15")
        self.controller = controller
        self.data_mgr = controller.data_mgr
        self.refresh_interval = self.controller.settings.get("refresh_interval", 30)
        # NYSE open hours in Eastern Time
        self._ny_open  = dt_time(hour=9,  minute=30)
        self._ny_close = dt_time(hour=16, minute=0)
        self._last_known_wifi_status = "unknown"

        self._is_closing = False

        # ─── auto-refresh bookkeeping ─────────────────────────────────────
        self._last_update_ts   = None     # datetime of last successful _refresh()
        self._countdown_after  = None     # after() id for 1-second countdown ticks
        self._countdown_secs   = self.refresh_interval

        # --- Layout Customization State ---
        self._in_customize_mode = False
        self._drag_manager = None
        self._components = {}
        self._component_builders = {}
        self._main_content_frame = None
        self.side_menu = None #  Will hold the side menu instance

        # Create the overlay but do not show it yet.
        # It will be placed on screen only when explicitly enabled.
        self.bounce_overlay = BounceOverlay(self)

        # Configure the main frame's grid layout
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── HISTORICAL MARKET SENTIMENT ───────────────────────────────────
        try:
            self.sentiment_hist = json.loads(_SENT_HISTORY_FILE.read_text())
            # convert ISO strings back to datetime objects
            self.sentiment_hist = [
                (datetime.fromisoformat(ts), val) for ts, val in self.sentiment_hist
            ]
        except Exception:
            self.sentiment_hist = []          # first run or corrupt file
        # ───────────────────────────────────────────────────────────


        self._build_ui()

        # ─── persistent drag-and-resize manager (starts disabled) ───
        self.drag_mgr = LayoutDragManager(self._main_content_frame,
                                          self._components)

        self._wl_after_id = None
        self._wl_animating = False
        self._marquee_position = 0.0
        self._pixels_per_frame = 1.
        self._initial_loads_signaled = set()

        # ── thread-safe hand-off queues ─────────────────────────────
        self._indices_q   = queue.Queue()
        self._watchlist_q = queue.Queue()
        self._news_q = queue.Queue() 

        self._fund_cache = {}

        # start background pollers (run on the Tk thread)
        self.after(100, self._poll_indices_q)
        self.after(100, self._poll_watchlist_q)
        self.after(100, self._poll_news_q)

        self.update_earnings_events()

        self._start_refresh_countdown()   # immediate first load + countdown

    # --- UI Construction ---

    def _build_ui(self):
        """Constructs the UI by building and placing modular components."""
        self._build_header()

        self._main_content_frame = ttk.Frame(self)
        self.grid_rowconfigure(1, weight=1) # Make the content area expand
        self._main_content_frame.grid(row=1, column=0, sticky="nsew", pady=15)
        self._main_content_frame.columnconfigure(0, weight=1, uniform="dashboard")
        self._main_content_frame.columnconfigure(1, weight=1, uniform="dashboard")
        self._main_content_frame.rowconfigure(2, weight=1)

        self._register_component_builders()
        self._apply_layout()

        ttk.Separator(self).grid(row=2, column=0, pady=15, sticky="ew")
        self._build_footer()
        self._build_side_menu()

        self.toggle_bounce_overlay() # Set initial state

    def _build_header(self):
        """Top bar with menu, title, gauges, clock and status icons."""
        header_frame = ttk.Frame(self)
        header_frame.grid(row=0, column=0, sticky="ew")

        # --- Column layout for the header ---
        # 0: Menu, 1: Title, 2: Spacer, 3: F&G, 4: Clock, 5: Dot, 6: Status, 7: Events, 8: WiFi
        header_frame.columnconfigure(2, weight=1)  # Spacer column

        # 0 ─ Menu Button (NEW)
        style = "Toolbutton" if "Toolbutton" in ttk.Style().theme_names() else "TButton"
        self.menu_btn = ttk.Button(header_frame, text="☰", command=self._toggle_side_menu, style=style)
        self.menu_btn.grid(row=0, column=0, sticky="w", padx=(0, 10))
        Tooltip(self.menu_btn, "Open Navigation Menu")

        # 1 ─ Welcome Title
        self.header_lbl = ttk.Label(header_frame, text="", style="Title.TLabel")
        self.header_lbl.grid(row=0, column=1, sticky="w")

        # 3 ─ Mini Fear & Greed gauge
        self.fng_canvas = tk.Canvas(header_frame, width=80, height=55, highlightthickness=0, bd=0)
        self.fng_canvas.grid(row=0, column=3, sticky="e", padx=(0, 10))
        cnn_url = "https://www.cnn.com/markets/fear-and-greed"
        self.fng_canvas.bind("<Button-3>", lambda _e, url=cnn_url: webbrowser.open(url))
        self.fng_canvas.bind("<Control-Button-1>", lambda _e, url=cnn_url: webbrowser.open(url))
        self.fng_tooltip = Tooltip(self.fng_canvas, "Loading Fear & Greed…")
        bg_color = self.controller.theme_settings()['bg']
        self.fng_canvas.configure(bg=bg_color)

        # 4 ─ Clock
        self.time_lbl = ttk.Label(header_frame, text="", style="Secondary.TLabel")
        self.time_lbl.grid(row=0, column=4, sticky="e", padx=(0, 10))

        # 5-6 ─ Market-status indicator
        self.market_canvas = tk.Canvas(header_frame, width=12, height=12, highlightthickness=0, bg=bg_color)
        self.market_canvas.grid(row=0, column=5, sticky="e", padx=(5, 0))
        self.market_circle = self.market_canvas.create_oval(2, 2, 10, 10, fill="red", outline="")
        self.market_lbl = ttk.Label(header_frame, text="Closed", style="Status.TLabel")
        self.market_lbl.grid(row=0, column=6, sticky="e", padx=(2, 10))

        # 7 ─ Events Calendar button
        self.events_btn = ttk.Button(header_frame, text="🗓  Events", command=lambda: EventsCalendar(self), style="Pill.TButton")
        self.events_btn.grid(row=0, column=7, sticky="e", padx=(0, 10))

        # 8 ─ Wi-Fi icon
        self._build_wifi_icon(header_frame)
        self.wifi_label.grid(row=0, column=8, sticky="e")

        self._start_clock()


    def _build_side_menu(self):
        """Initializes the sliding side navigation menu."""
        style = "Card.TFrame" if "Card.TFrame" in ttk.Style().theme_names() else "TFrame"
        self.side_menu = SideMenu(self, self.controller, style=style)

    def _toggle_side_menu(self):
        """Shows or hides the side menu."""
        if self.side_menu:
            self.side_menu.toggle()

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
        news_box.grid_propagate(False)
        news_box.columnconfigure(0, weight=1)
        news_box.rowconfigure(1, weight=1)
        news_box.rowconfigure(2, weight=0)
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
        hist_btn = ttk.Button(
            news_box, text="📈  Historical Sentiment",
            command=self._open_sentiment_history, style="Pill.TButton"
        )
        hist_btn.grid(row=2, column=0, columnspan=2, sticky="e", pady=(8, 0))
        return news_box

    def _create_chart_pane(self, parent):
        default_ticker = self.controller.settings.get('default_ticker', 'SPY')
        chart_box = ttk.LabelFrame(parent, text=f"{default_ticker} Chart", padding=5)
        chart_box.columnconfigure(0, weight=1)
        chart_box.rowconfigure(0, weight=1)
        self.chart_box = chart_box
        self.chart_pane = CandlestickChartPane(chart_box, theme=self.controller.current_theme, ticker=default_ticker)
        chart_box.grid_propagate(False)
        self.chart_pane.grid(row=0, column=0, sticky="nsew")
        return chart_box

    def _build_footer(self):
        """Builds the bottom footer with layout controls, action buttons, and refresh status."""
        footer_frame = ttk.Frame(self)
        footer_frame.grid(row=4, column=0, sticky="ew", pady=(15, 0))
        # Create a spacer column in the middle to push content to the sides
        footer_frame.columnconfigure(1, weight=1)

        # --- Left side: Layout Customization Buttons (hidden by default) ---
        layout_controls_frame = ttk.Frame(footer_frame)
        layout_controls_frame.grid(row=0, column=0, sticky="w")
        
        self.save_layout_btn = ttk.Button(layout_controls_frame, text="✅ Save Layout", command=self._save_layout, style="Pill.TButton")
        self.cancel_layout_btn = ttk.Button(layout_controls_frame, text="❌ Cancel", command=self._cancel_layout, style="Pill.TButton")
        self.reset_layout_btn = ttk.Button(layout_controls_frame, text="🔄 Reset Layout", command=self._reset_to_default, style="Pill.TButton")
        
        self.save_layout_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.cancel_layout_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.reset_layout_btn.pack(side=tk.LEFT)
        
        # Hide the entire frame initially and save a reference to it
        layout_controls_frame.grid_remove()
        self.layout_controls_frame = layout_controls_frame

        # --- Right side: Action Buttons and Refresh Label ---
        actions_frame = ttk.Frame(footer_frame)
        actions_frame.grid(row=0, column=2, sticky="e")
        
        self.refresh_lbl = ttk.Label(actions_frame, text="Updated: —   Next: —", font=("Segoe UI", 9))
        self.refresh_lbl.pack(side=tk.RIGHT, padx=(10, 0))



    def _sync_wl_strip(self, event=None):
        """
        Keep the canvas' scroll-region and the two ticker rows in sync.
        Called every time the inner strip changes size.
        """
        strip_w = self.wl_strip.winfo_reqwidth()
        if not strip_w:
            return
        xview = self.wl_canvas.xview()

        self.wl_canvas.itemconfigure(self.wl_window, width=strip_w)
        self.wl_canvas.itemconfigure(self.wl_clone_window, width=strip_w)
        self.wl_canvas.configure(scrollregion=(0, 0, strip_w * 2, 90))
        self.wl_canvas.coords(self.wl_clone_window, strip_w, 0)
        self.wl_canvas.xview_moveto(xview[0])

    def _build_wifi_icon(self, parent_frame):
        """Initializes the Wi-Fi icon and its related resources."""
        fg_color = "#ffffff" if self.controller.current_theme == "dark" else "#000000"
        bg_color = "#0f0f0f" if self.controller.current_theme == 'dark' else '#f0f0f0'

        self.wifi_icons = {
            key: load_icon(ICON_DIR / f"wifi_{key}.png", tint_color=fg_color)
            for key in ("disconnected", "weak", "medium", "strong", "secure")
        }

        self.wifi_label = tk.Label(parent_frame, bd=0)
        self.wifi_label.configure(bg=bg_color)

        if self.wifi_icons.get("disconnected"):
            self._last_wifi_status = "disconnected"
            self._update_wifi_icon("disconnected")

        self._wifi_queue = queue.Queue()
        self._poll_wifi_queue()
        self.check_wifi()


    def _toggle_customize_mode(self, enable: bool):
        """
        Turns layout edit mode on/off. Shows/hides the Save/Cancel/Reset buttons in the footer.
        """
        self._in_customize_mode = enable

        if enable:
            # Show the layout editing buttons frame
            self.layout_controls_frame.grid()
            self.drag_mgr.enable_edit_mode(True)
        else:
            # Hide the layout editing buttons frame
            self.layout_controls_frame.grid_remove()
            self.drag_mgr.enable_edit_mode(False)

    def _get_or_create_tile(self, name: str):
        """
        Return (and if needed build) the tile called *name*.
        """
        if name in self._components:
            return self._components[name]

        builder = self._component_builders.get(name)
        if builder is None:
            raise ValueError(f"Unknown dashboard tile: {name!r}")

        widget = builder(self._main_content_frame)
        self._components[name] = widget
        return widget

    def _reset_to_default(self):
        """
        Restore factory layout no matter which tiles were deleted.
        """
        for w in self._components.values():
            w.grid_forget()

        default = self._get_default_layout()

        for info in default:
            tile = self._get_or_create_tile(info["name"])
            tile.grid(
                row=info["row"], column=info["column"],
                rowspan=info["rowspan"], columnspan=info["columnspan"],
                sticky="nsew", padx=5, pady=5
            )

        self.controller.settings.set(
            "dashboard_layout", json.dumps(default)
        )
        self._toggle_customize_mode(False)

    def _save_layout(self):
        self.drag_mgr.save_layout()
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

    def toggle_bounce_overlay(self):
        """
        Checks settings and correctly starts or stops the bounce overlay by
        calling its own start/stop methods.
        """
        try:
            # Get the current setting (which defaults to False)
            is_enabled = self.controller.settings.get('enable_bounce_overlay', False)

            if is_enabled:
                # The start() method handles creating and showing the overlay
                self.bounce_overlay.start()
            else:
                # The stop() method handles destroying the overlay
                self.bounce_overlay.stop()
        except Exception as e:
            logging.error(f"Failed to toggle bounce overlay: {e}")


    def _poll_news_q(self):
        """Polls for news data from the background thread."""
        if self._is_closing or not _widget_is_alive(self): return
        try:
            while True:
                # Data is a tuple: (rows, overall_sentiment)
                data = self._news_q.get_nowait()
                self._update_news_ui(data)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._news_after_id = self.after(100, self._poll_news_q)

    def _update_news_ui(self, data):
        """Updates the news UI elements from the main thread."""
        rows, overall = data
        if overall is None:
            txt, col = "Overall sentiment: N/A", "gray"
        elif overall > 0.25:
            txt, col = f"Overall sentiment: Bullish ({overall:+.2f})", "green"
        elif overall < -0.25:
            txt, col = f"Overall sentiment: Bearish ({overall:+.2f})", "red"
        else:
            txt, col = f"Overall sentiment: Neutral ({overall:+.2f})", "orange"
        
        self.overall_news_lbl.config(text=txt, foreground=col)
        
        # Writing to disk is also a blocking operation, but it's much faster.
        # We do it here on the main thread for simplicity.
        if overall is not None:
            self._record_sentiment_point(overall)

        self.news_tv.delete(*self.news_tv.get_children())
        for title, score, url in rows:
            if score is None: tag, val = "", "N/A"
            else:
                tag = "pos" if score > 0.25 else "neg" if score < -0.25 else "neu"
                val = f"{score:+.2f}"
            self.news_tv.insert("", "end", values=(title, val, url), tags=(tag,))
        
        self.news_tv.tag_configure("pos", foreground="green")
        self.news_tv.tag_configure("neg", foreground="red")
        self.news_tv.tag_configure("neu", foreground="orange")

        if 'news' not in self._initial_loads_signaled:
            self.controller.on_initial_load_complete('news')
            self._initial_loads_signaled.add('news')

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
        self._update_market_status(now)
        self._time_after_id = self.after(1000, self._update_time)

    def _update_market_status(self, now_local):
        """
        Updates the market status indicator with a live countdown.
        """
        from math import floor
        ny = now_local.astimezone(ZoneInfo("America/New_York"))
        open_dt   = ny.replace(hour=9,  minute=30, second=0, microsecond=0)
        close_dt  = ny.replace(hour=16, minute=0, second=0, microsecond=0)
        ny_time   = ny.time()
        status, color, msg = "Closed", "red", ""

        if ny.weekday() < 5:
            if self._ny_open <= ny_time <= self._ny_close:
                status, color = "Open", "green"
                rem = close_dt - ny
                h, m, s = rem.seconds // 3600, (rem.seconds // 60) % 60, rem.seconds % 60
                msg = f" – closes in {h:02d}:{m:02d}:{s:02d}"
            elif ny_time < self._ny_open:
                status, color = "Pre-Market", "orange"
                rem = open_dt - ny
                h, m, s = rem.seconds // 3600, (rem.seconds // 60) % 60, rem.seconds % 60
                msg = f" – opens in {h:02d}:{m:02d}:{s:02d}"
            else:
                status, color = "After-Hours", "orange"
                days = 1 if ny.weekday() < 4 else (7 - ny.weekday())
                next_open = open_dt + timedelta(days=days)
                rem = next_open - ny
                h, m, s = rem.seconds // 3600 + rem.days * 24, (rem.seconds // 60) % 60, rem.seconds % 60
                msg = f" – opens in {h:02d}:{m:02d}:{s:02d}"
        else:
            days = (7 - ny.weekday()) % 7 or 1
            next_open = open_dt + timedelta(days=days)
            rem = next_open - ny
            h_tot = rem.days * 24 + floor(rem.seconds / 3600)
            m = (rem.seconds // 60) % 60
            status, color = "Closed", "red"
            msg = f" – opens in {h_tot}h {m}m"

        self.market_canvas.itemconfig(self.market_circle, fill=color)
        self.market_lbl.config(text=f"{status}{msg}", foreground=color)

    def _start_refresh_countdown(self):
        """Trigger an immediate data load, then start the second-by-second clock."""
        self._refresh()
        self._countdown_secs = self.refresh_interval
        self._tick_refresh_countdown()

    def _tick_refresh_countdown(self):
        if self._is_closing or not _widget_is_alive(self):
            return

        up_txt  = self._last_update_ts.strftime("%H:%M:%S") if self._last_update_ts else "—"
        nxt_txt = f"0:{self._countdown_secs:02d}"
        self.refresh_lbl.config(text=f"Updated: {up_txt}   Next: {nxt_txt}")

        if self._countdown_secs == 0:
            self._refresh()
            self._countdown_secs = self.refresh_interval
        else:
            self._countdown_secs -= 1

        self._countdown_after = self.after(1000, self._tick_refresh_countdown)

    def update_refresh_interval(self, new_interval_seconds: int):
        """
        Called from the main app when the user saves a new refresh interval.
        """
        self.refresh_interval = new_interval_seconds
        # To make the change feel responsive, if the user lowers the interval,
        # we adjust the current countdown.
        self._countdown_secs = min(self._countdown_secs, self.refresh_interval)

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
        if _widget_is_alive(self):
            self._wifi_poll_after_id = self.after(100, self._poll_wifi_queue)

    def _poll_indices_q(self):
        if self._is_closing or not _widget_is_alive(self): return
        try:
            while True:
                data = self._indices_q.get_nowait()
                # **FIX**: Pass the data to the UI update function
                self._update_indices_ui(data)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._indices_after_id = self.after(100, self._poll_indices_q)

    def _poll_watchlist_q(self):
        if self._is_closing or not _widget_is_alive(self): return
        try:
            while True:
                data = self._watchlist_q.get_nowait()
                self._update_watchlist_ui(data)
                
                # **FIX**: Filter out None values before sorting to prevent crashes
                valid_data = [d for d in data if d and d.get("regularMarketPrice") and d.get("previousClose")]
                
                if valid_data:
                    movers = sorted(
                        valid_data,
                        key=lambda d: abs((d["regularMarketPrice"] - d["previousClose"]) / d["previousClose"]),
                        reverse=True)[:3]
                else:
                    movers = []
                self._update_movers_ui(movers)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self._watchlist_after_id = self.after(100, self._poll_watchlist_q)

    def _update_wifi_icon(self, new_status_key):
        if not hasattr(self, "wifi_label"): return

        # **FIX**: Check if the status has changed from disconnected to connected
        if self._last_known_wifi_status == 'disconnected' and new_status_key != 'disconnected':
            print("Internet connection restored. Triggering a full data refresh.")
            self.controller.set_status("Internet connection restored. Refreshing data...", "green")
            self._refresh()

        self._last_known_wifi_status = new_status_key
        icon = self.wifi_icons.get(new_status_key)
        if icon:
            self.wifi_label.configure(image=icon)
            self.wifi_label.image = icon

    def apply_custom_theme(self):
        """
        Called when the application theme changes. Re-tints icons and updates backgrounds.
        """
        fg = "#ffffff" if self.controller.current_theme == "dark" else "#000000"
        bg = "#0f0f0f" if self.controller.current_theme == 'dark' else '#f0f0f0'

        if hasattr(self, "wifi_label"):
            self.wifi_label.configure(bg=bg)

        for key in self.wifi_icons:
            path = ICON_DIR / f"wifi_{key}.png"
            self.wifi_icons[key] = load_icon(path, tint_color=fg)

        if hasattr(self, "_last_wifi_status"):
            self._update_wifi_icon(self._last_wifi_status)

        if hasattr(self, "wl_canvas"):
            canvas_bg = self.controller.theme_settings()['bg']
            self.wl_canvas.configure(bg=canvas_bg)

    def _record_sentiment_point(self, value: float):
        """Append (timestamp, value) and persist to disk."""
        if self.sentiment_hist and abs(self.sentiment_hist[-1][1] - value) < 1e-6:
            return
        self.sentiment_hist.append((datetime.now(), value))
        self.sentiment_hist = [
            (ts, v) for ts, v in self.sentiment_hist
            if (datetime.now() - ts).days < 365*5
        ]
        try:
            _SENT_HISTORY_FILE.write_text(
                json.dumps([(ts.isoformat(), v) for ts, v in self.sentiment_hist])
            )
        except Exception as e:
            logging.exception("Could not save sentiment history: %s", e)

    def _open_sentiment_history(self):
        """Pop-up a chart that tracks VADER news-sentiment."""
        if not self.sentiment_hist:
            tk.messagebox.showinfo("Sentiment unavailable", "No sentiment data recorded yet.")
            return

        theme = getattr(self.controller, "current_theme", "light")
        palette = {
            "dark": {"bg": "#0f0f0f", "fg": "#ffffff", "line": "#42a5f5", "grid": "#444444"},
            "light": {"bg": "#ffffff", "fg": "#000000", "line": "#0B84A5", "grid": "#d0d0d0"}
        }[theme]

        win = tk.Toplevel(self)
        win.title("News Sentiment Trend")
        win.geometry("760x480")
        self.controller.apply_theme_to_window(win)
        win.configure(background=palette['bg'])

        title_lbl = ttk.Label(win, text="News Sentiment Trend", font=("Segoe UI Semibold", 14), anchor="w", padding=(10, 6, 0, 4))
        title_lbl.pack(fill="x")

        fig  = Figure(figsize=(7.0, 3.8), dpi=100, facecolor=palette['bg'])
        ax   = fig.add_subplot(111, facecolor=palette['bg'])
        dates, scores = zip(*self.sentiment_hist)
        ax.plot(dates, scores, linewidth=2.2, color=palette['line'])
        ax.scatter(dates[-1], scores[-1], s=80, zorder=3, facecolor=palette['bg'], edgecolor=palette['line'], linewidths=2)

        import matplotlib.dates as mdates
        locator   = mdates.AutoDateLocator()
        formatter = mdates.ConciseDateFormatter(locator)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(formatter)
        fig.autofmt_xdate()
        ax.set_xlim(dates[0], datetime.now())
        ax.set_ylabel("VADER score", color=palette['fg'])
        ax.set_title("Market news-sentiment trend", color=palette['fg'], pad=12, fontsize=12)
        ax.grid(True, linestyle="--", linewidth=0.6, color=palette['grid'], alpha=0.8)
        ax.tick_params(axis="both", colors=palette['fg'])
        for spine in ax.spines.values():
            spine.set_color(palette['grid'])
        fig.tight_layout(pad=2.0)

        canvas = FigureCanvasTkAgg(fig, master=win)
        canvas.draw()
        canvas_widget = canvas.get_tk_widget()
        canvas_widget.pack(fill="both", expand=True, padx=10, pady=8)
        canvas_widget.configure(background=palette['bg'])

    def _open_selected_article(self, event=None):
        selected_item = self.news_tv.selection()
        if not selected_item: return
        item_values = self.news_tv.item(selected_item[0], "values")
        if len(item_values) > 2:
            url = item_values[2]
            if url and url.startswith("http"):
                webbrowser.open(url)

    def _refresh(self):
        """
        Fetches all dashboard data and explicitly refreshes the chart pane,
        ensuring components can handle fetch failures.
        """
        if self._is_closing or not _widget_is_alive(self): return

        self.header_lbl.config(text=f"Welcome, {self.controller.user_name}!")
        
        # Explicitly tell the chart to refresh its data
        if hasattr(self, 'chart_pane') and self.chart_pane:
            self.chart_pane.refresh_data()

        def run_with_timeout(target_func, timeout=10):
            result = None
            def worker():
                nonlocal result
                try: result = target_func()
                except Exception as e: logging.warning(f"Data fetch failed for {target_func.__name__}: {e}")
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()
            thread.join(timeout)
            if thread.is_alive(): logging.info(f"Data fetch for {target_func.__name__} timed out (likely offline). Skipping.")
            return result

        def fetch_all():
            # **FIX**: Each task now gracefully handles None on failure
            fng_score = run_with_timeout(self.data_mgr.get_fear_greed)
            if not self._is_closing: self.after(0, lambda: self._update_fng_ui(fng_score))
            
            indices_data = run_with_timeout(lambda: [self.data_mgr.get_ticker_details(t) for t in ("^SPX", "^VIX")])
            if not self._is_closing: self._indices_q.put(indices_data or [])

            watchlist_data = run_with_timeout(lambda: [self.data_mgr.get_ticker_details(t) for t in self._get_watchlist_symbols()])
            if not self._is_closing: self._watchlist_q.put(watchlist_data or [])

            news_data = run_with_timeout(lambda: self.data_mgr.get_news_headlines(20))
            if not self._is_closing: self._news_q.put(news_data or ([], None))

        threading.Thread(target=fetch_all, daemon=True).start()
        self._last_update_ts = datetime.now()
        self.update_earnings_events()

    def _get_watchlist_symbols(self):
        raw = self.controller.settings.get("watchlist", "")
        return [t.strip().upper() for t in raw.split("|") if t.strip()]

    def _auto_refresh(self):
        if self._is_closing or not _widget_is_alive(self): return
        self._refresh()
        self._auto_refresh_id = self.after(30_000, self._auto_refresh)

    def _create_ticker_box(self, parent, data, context_ticker=None):
        """
        Watch-list chip with a *taller* invisible hit-area so the tooltip
        fires as soon as the pointer is anywhere above the tile.  Visual
        footprint (width, border, fonts, inter-chip gap) stays identical.
        """
        # ── maths ───────────────────────────────────────────────────
        price        = data.get("regularMarketPrice", 0)
        prev_close   = data.get("previousClose", 0)
        display_tkr  = data.get("symbol", "N/A")
        bind_ticker  = context_ticker if context_ticker else display_tkr

        change       = price - prev_close
        pct_change   = (change / prev_close * 100) if prev_close else 0
        sign         = "+" if change >= 0 else ""
        colour       = "green" if change >= 0 else "red"

        # ── INVISIBLE hit-area (adds *vertical* padding only) ───────
        # 6 px extra top & bottom = far easier to hover while scrolling
        hitbox = ttk.Frame(parent, style="Hitbox.TFrame", padding=(0, 6))
        hitbox.pack(side="left", padx=4)        # same horiz gap as before

        # ── visual chip (unchanged look) ────────────────────────────
        box = ttk.Frame(hitbox, borderwidth=1, relief="groove", padding=(8, 4))
        box.pack()                              # centred inside hitbox

        ticker_lbl = ttk.Label(box, text=display_tkr,
                               font=("Segoe UI", 11, "bold"))
        ticker_lbl.grid(row=0, column=0, sticky="w")

        price_lbl = ttk.Label(box, text=f"{price:,.2f}",
                              font=("Segoe UI", 11))
        price_lbl.grid(row=0, column=1, sticky="e", padx=(15, 0))

        change_lbl = ttk.Label(
            box,
            text=f"{sign}{change:,.2f} ({sign}{pct_change:.2f}%)",
            foreground=colour,
            font=("Segoe UI", 9)
        )
        change_lbl.grid(row=1, column=0, columnspan=2, sticky="w")

        # ── bind tooltip & menu to every sub-widget for reliability ─
        for tgt in (hitbox, box, ticker_lbl, price_lbl, change_lbl):
                    # ── bindings ────────────────────────────────────────────────
                # 1️⃣ Tooltip + context-menu on the HITBOX only
                hitbox.bind(
                    "<Button-3>",
                    lambda e, t=bind_ticker: self._show_ticker_context_menu(e, t),
                    add="+",
                )
                self._attach_ticker_tooltip(hitbox, bind_ticker)

                # 2️⃣ Child widgets:
                #    • get their own right-click menu
                #    • prepend the hitbox’s bind-tag so they inherit its tooltip –
                #      this prevents duplicate tooltips.
                for tgt in (box, ticker_lbl, price_lbl, change_lbl):
                    tgt.bind(
                        "<Button-3>",
                        lambda e, t=bind_ticker: self._show_ticker_context_menu(e, t),
                        add="+",
                    )
                    # Inherit the hitbox’s bindings (tooltip) without re-binding it
                    tgt.bindtags((hitbox,) + tgt.bindtags())


        return hitbox

    def _view_chart_for_ticker(self, ticker: str):
        self.chart_pane.set_ticker(ticker)
        self.chart_box.config(text=f"{ticker} Chart")
        try:
            self.controller.settings.set("default_ticker", ticker)
        except Exception:
            pass

    def _show_ticker_context_menu(self, event, ticker):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label=f"View {ticker} on Google Finance", command=lambda t=ticker: self._open_google_finance(t))
        m.add_command(label="View chart", command=lambda t=ticker: self._view_chart_for_ticker(t))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _open_google_finance(self, ticker):
        # Schedule the webbrowser call to run safely on the main Tkinter event loop.
        self.after(0, lambda: webbrowser.open(f"https://www.google.com/search?q=stock%20price%20{ticker}"))

    # ──────────────────────────────────────────────────────────────
    #   Fundamentals fetch  (15-minute memoisation)
    # ──────────────────────────────────────────────────────────────
    _TOOLTIP_TTL = 900   # seconds

    def _get_fundamentals(self, ticker: str) -> dict | None:
        """Return a small dict of fundamentals, or None on failure."""
        now   = time.time()
        entry = self._fund_cache.get(ticker)
        if entry and now - entry["ts"] < self._TOOLTIP_TTL:
            return entry["data"]

        try:
            raw = self.data_mgr.get_ticker_details(ticker)   # you already use this
            if not raw:
                return None
            snap = {
                "name"      : raw.get("shortName") or "",
                "price"     : raw.get("regularMarketPrice"),
                "prev"      : raw.get("previousClose"),
                "high"      : raw.get("regularMarketDayHigh"),
                "low"       : raw.get("regularMarketDayLow"),
                "cap"       : raw.get("marketCap"),
                "pe"        : raw.get("trailingPE"),
            }
            snap["chg_pct"] = (
                ((snap["price"] - snap["prev"]) / snap["prev"]) * 100
                if snap["prev"] else None
            )
            self._fund_cache[ticker] = {"data": snap, "ts": now}
            return snap
        except Exception as exc:
            logging.exception("fundamentals fetch failed for %s", ticker)
            return None

    def _attach_ticker_tooltip(self, widget: tk.Widget, ticker: str):
        """
        Instant, follow-mouse tooltip that works with your project’s
        Tooltip class (show_tooltip / hide_tooltip / update).
        """
        tip = Tooltip(widget, "Loading…")        # your Tooltip auto-binds <Enter>/<Leave>

        # helper to build the card
        def _refresh_card():
            f = self._get_fundamentals(ticker)
            if not f:
                tip.update("Data unavailable")
                return
            arrow  = "▲" if f["chg_pct"] and f["chg_pct"] > 0 else "▼"
            change = f"{f['chg_pct']:+.2f}%" if f["chg_pct"] is not None else "—"
            tip.update(
                f"{ticker} — {f['name']}\n"
                f"Price: {f['price']:,} {arrow} {change}\n"
                f"Market Cap: {f['cap']/1e9:.1f} B\n" if f['cap'] else "Market Cap: N/A\n"
                f"P/E Ratio:  {f['pe'] or '—'}\n"
                f"Day Range:  {f['low']:,} – {f['high']:,}"
            )

        # ── bindings ──────────────────────────────────────────────
        # 1️⃣  On hover: update the card *then* show the tooltip once.
        widget.bind(
            "<Enter>",
            lambda e: (_refresh_card(), tip.show_tooltip()),
            add="+"
        )

        # 2️⃣  On leave: hide it.
        widget.bind("<Leave>", lambda e: tip.hide_tooltip(), add="+")



    def _update_watchlist_ui(self, data):
        if self._is_closing or not _widget_is_alive(self): return

        if hasattr(self, "_wl_loader"):
            self._wl_loader.destroy()
            del self._wl_loader

        self._stop_watchlist_marquee()
        for frame in (self.wl_strip, self.wl_clone):
            for w in frame.winfo_children():
                w.destroy()

        # **FIX**: Check if data is not None and is a list before proceeding
        if not isinstance(data, list):
            ttk.Label(self.wl_strip, text="Watchlist data unavailable...").pack(padx=6)
            return

        for d in data:
            if d is not None:
                self._create_ticker_box(self.wl_strip, d)
                self._create_ticker_box(self.wl_clone, d)

        if 'watchlist' not in self._initial_loads_signaled:
            self.controller.on_initial_load_complete('watchlist')
            self._initial_loads_signaled.add('watchlist')

        self.wl_strip.update_idletasks()
        self.wl_canvas.event_generate("<Configure>")
        self.after(50, self._start_watchlist_marquee)

    def _update_indices_ui(self, all_data):
        if self._is_closing or not _widget_is_alive(self): return
        for widget in self.indices_content_frame.winfo_children():
            widget.destroy()
        if not all_data:
            ttk.Label(self.indices_content_frame, text="Could not load market data.").pack()
            return
        
        name_map = {'^SPX': 'S&P 500', '^VIX': 'VIX'}
        for data in all_data:
            # **FIX**: Add a check to skip None values from failed fetches
            if data is None:
                continue
            original_ticker = data['symbol']
            data['symbol'] = name_map.get(original_ticker, original_ticker)
            self._create_ticker_box(self.indices_content_frame, data, context_ticker=original_ticker)

        if 'indices' not in self._initial_loads_signaled:
            self.controller.on_initial_load_complete('indices')
            self._initial_loads_signaled.add('indices')

    def _update_movers_ui(self, movers):
        if self._is_closing or not _widget_is_alive(self): return
        for w in self.movers_content_frame.winfo_children():
            w.destroy()
        if not movers:
            ttk.Label(self.movers_content_frame, text="No data (empty watch-list?)").pack()
            return
        for d in movers:
            sym, price, prev = d["symbol"], d["regularMarketPrice"], d["previousClose"] or 0.0
            pct = (price - prev) / prev * 100 if prev else 0.0
            up = price >= prev
            colour, arrow = ("green", "↑") if up else ("red", "↓")
            text = f"{sym}: {prev:,.2f} {arrow} {price:,.2f} ({pct:+.2f}%)"
            ttk.Label(self.movers_content_frame, text=text, foreground=colour, font=("Segoe UI", 10, "bold")).pack(side=tk.LEFT, padx=10)

    def _start_watchlist_marquee(self):
        if self._is_closing or not _widget_is_alive(self): return
        self._stop_watchlist_marquee()
        self.wl_strip.update_idletasks()
        strip_width = self.wl_strip.winfo_reqwidth()
        if strip_width <= 0: return

        self._wl_animating = True
        self._marquee_position = 0.0
        speed_setting = float(self.controller.settings.get("marquee_speed", 1.5))
        self._pixels_per_frame = max(0.1, speed_setting)
        self._frame_delay = 16  # ~60 FPS

        def _animate_step():
            if not self._wl_animating or not _widget_is_alive(self): return
            try:
                self._marquee_position += self._pixels_per_frame
                if self._marquee_position >= strip_width: self._marquee_position = 0.0
                fractional_pos = self._marquee_position / (strip_width * 2)
                self.wl_canvas.xview_moveto(fractional_pos)
                self._wl_after_id = self.wl_canvas.after(self._frame_delay, _animate_step)
            except tk.TclError:
                self._wl_animating = False
            except Exception as e:
                print(f"Marquee animation error: {e}")
                self._wl_animating = False
        _animate_step()

    def _stop_watchlist_marquee(self):
        self._wl_animating = False
        if hasattr(self, '_wl_after_id') and self._wl_after_id:
            try:
                self.wl_canvas.after_cancel(self._wl_after_id)
            except Exception:
                pass
            self._wl_after_id = None

    def _update_marquee_speed(self):
        if hasattr(self, '_wl_animating') and self._wl_animating:
            speed_setting = float(self.controller.settings.get("marquee_speed", 1.5))
            self._pixels_per_frame = max(0.1, speed_setting)

    def _update_fng_ui(self, score: int | None):
        """
        Updates the Fear & Greed gauge and signals that the initial F&G data load is complete.
        """
        if self._is_closing or not _widget_is_alive(self): return
        
        # --- This is the same drawing logic as before ---
        c = self.fng_canvas
        c.delete("fng_gauge")
        cx, cy, radius, arc_w = 40, 40, 32, 7
        bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
        c.create_arc(*bbox, start=0, extent=180, style="arc", width=arc_w, outline="#555555", tags="fng_gauge")

        if score is None:
            c.create_text(cx, cy - 5, text="N/A", font=("Segoe UI", 14, "bold"), fill="grey", tags="fng_gauge")
            self.fng_tooltip.update("Fear & Greed index unavailable")
        else:
            if score < 25: clr, mood = "#D32F2F", "Extreme Fear"
            elif score < 45: clr, mood = "#F57C00", "Fear"
            elif score < 55: clr, mood = "grey", "Neutral"
            elif score < 75: clr, mood = "#9ACD32", "Greed"
            else: clr, mood = "#00B200", "Extreme Greed"

            sweep_start = 180 - score * 1.8
            c.create_arc(*bbox, start=sweep_start, extent=180 - sweep_start, style="arc", width=arc_w, outline=clr, tags="fng_gauge")
            c.create_text(cx, cy - 10, text=str(score), font=("Segoe UI", 16, "bold"), fill=clr, tags="fng_gauge")
            c.create_text(cx, cy + 10, text="F&G Index", font=("Segoe UI", 8), fill="grey", tags="fng_gauge")
            self.fng_tooltip.update(f"{score} – {mood}")

        # **FIX**: Signal that the initial load for this task is complete
        if 'fng' not in self._initial_loads_signaled:
            self.controller.on_initial_load_complete('fng')
            self._initial_loads_signaled.add('fng')

    #  Method to update earnings events in the calendar
    def update_earnings_events(self):
        """
        Provides earnings data to the EventsCalendar instance when it's opened.
        This method is called by OptionsApp whenever earnings data is updated.
        """
        # Retrieve earnings data from settings, which is managed by OptionsApp
        earnings_data_dict = self.controller.settings.get("earnings_data", {})

        earnings_events = []
        for symbol, data in earnings_data_dict.items():
            if data and data.get("next_earnings_date"):
                # Use a unique tag for earnings events
                earnings_events.append(
                    (data["next_earnings_date"], f"Earnings: {symbol}", "earnings_watchlist", "—",
                     f"https://finance.yahoo.com/calendar/earnings?symbol={symbol}",
                     f"EPS Est: {data.get('estimated_eps', 'N/A'):.2f}, Actual: {data.get('reported_eps', 'N/A'):.2f} (Surprise: {data.get('surprise_percentage', 'N/A'):+.1f}%)" if data.get('reported_eps') is not None else "")
                )

        # When opening the calendar, it will get the latest events
        # We don't directly manipulate the calendar here, but ensure the data is ready for it.
        # Signal that earnings data has been processed for initial load
        if 'earnings' not in self._initial_loads_signaled:
            self.controller.on_initial_load_complete('earnings')
            self._initial_loads_signaled.add('earnings')


    def shutdown(self):
        """
        Stops all repeating tasks and cleans up resources before the window closes.
        """
        self._is_closing = True
        self._stop_watchlist_marquee() # More robust way to stop animation

        # Clean up the side menu first
        if hasattr(self, 'side_menu') and self.side_menu:
            self.side_menu.shutdown()

        frame_timers = [
            "_time_after_id", "_indices_after_id", "_watchlist_after_id",
            "_wifi_poll_after_id", "_wifi_check_after_id", "_auto_refresh_id", "_countdown_after",
        ]
        for attr in frame_timers:
            after_id = getattr(self, attr, None)
            if after_id:
                try: self.after_cancel(after_id)
                except Exception: pass

        if hasattr(self, 'bounce_overlay'):
            self.bounce_overlay.stop()

        if hasattr(self, '_drag_manager') and self._drag_manager:
            self._drag_manager.cleanup()
