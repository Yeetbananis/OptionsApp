# idea_suite_view.py
from __future__ import annotations
import queue, time, random, datetime as dt, threading, traceback
from typing import List, Dict, Tuple, TYPE_CHECKING
import tkinter as tk
from tkinter import ttk, messagebox

if TYPE_CHECKING:
    from app.OptionsApp import OptionAnalyzerApp
    from core.engine.idea_suite_controller import IdeaSuiteController

from ui.LoadingScreen import LoadingScreen, IdeaSuiteLoadingOverlay

from ui.idea_card import IdeaCard
from core.engine.idea_engine import CATEGORY_LABELS
from core.models.idea_models import Idea
from ui.ideatooltip import IdeaTooltip
from core.engine.strategy_recommender import StrategyRecommender
from app.llm_helper import LLMHelper
from core.storage.saved_storage import load_saved_ids, save_ids, load_saved_notes, save_notes

DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "GOOG", "TSLA",
    "META", "BRK-B", "UNH", "JNJ", "V", "JPM", "WMT",
    "PG", "BAC", "MA", "HD", "DIS", "PFE"
]

class IdeaSuiteView(ttk.Frame):
    """
    A robust view for displaying and interacting with trading ideas,
    with a reliable initial data loading mechanism.
    """
    POLL_MS = 200

    def __init__(self, parent: ttk.Notebook, app: 'OptionAnalyzerApp'):
        super().__init__(parent)
        parent.add(self, text="💡 Idea Suite")

        self.app = app
        self.is_dark = app.current_theme == 'dark'
        
        # --- State Management ---
        self.controller: IdeaSuiteController | None = None
        self.queue: queue.Queue[List[Idea]] = queue.Queue()
        self._progress_queue: queue.Queue[Tuple[int, int]] = queue.Queue()
        self._all_ideas: List[Idea] = []
        self._saved_ids = set(load_saved_ids())
        self._saved_notes = load_saved_notes()
        self.universe = self.app.settings.get("idea_universe", DEFAULT_UNIVERSE)
        
        # Expose save helpers to the main app so IdeaCard can call them
        self.app.idea_suite_save = self._persist_uid
        self.app.idea_suite_save_notes = self._persist_notes
        self.app.idea_suite_view_expand = self._highlight_expand
        self.app.idea_suite_view_refresh = self._render_saved_tab

        self._category_tabs: Dict[str, ttk.Frame] = {}
        self._build_ui()

        # NEW: Create a dedicated loading screen instance for Idea Suite refreshes
        # It's now a ttk.Frame directly within this IdeaSuiteView
        self._idea_suite_loader = IdeaSuiteLoadingOverlay(self, self.app.user_name, theme=self.app.current_theme)
        # It is placed to cover the entire view, but starts hidden
        self._idea_suite_loader.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._idea_suite_loader.place_forget() # Initially hidden
        
        # Start polling the queue for results from the background thread
        self.after(100, self._poll_queue)

    def set_controller(self, controller: "IdeaSuiteController"):
        """Gives the view a reference to its controller to request refreshes."""
        self.controller = controller

    def refresh_ideas(self):
        """Public method to trigger a data refresh for the view."""
        if self.controller:
            self._show_loading_overlay()
            self.universe = self.app.settings.get("idea_universe", DEFAULT_UNIVERSE)
            self.controller.refresh(self.universe, self._progress_queue) 

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1) # Main content area

        self._build_header_controls()
        self._build_highlight_reel()

        # --- Main Notebook for Content ---
        self.content_nb = ttk.Notebook(self)
        self.content_nb.grid(row=2, column=0, sticky="nsew", padx=6, pady=6)
        
        self.ideas_tab = ttk.Frame(self.content_nb)
        self.content_nb.add(self.ideas_tab, text="Curated Ideas")
        self.ideas_tab.columnconfigure(0, weight=1)
        self.ideas_tab.rowconfigure(0, weight=1)

        self.category_nb = ttk.Notebook(self.ideas_tab)
        self.category_nb.grid(row=0, column=0, sticky="nsew")

        self._build_wizard_tab()
        self._build_copilot_tab()
        
        # --- Saved-Ideas tab -------------------------------------------------
        self.saved_tab = ScrollableFrame(self.content_nb, self.is_dark)
        self.content_nb.add(self.saved_tab, text="⭐ Saved Ideas")

        # --- Timeline at the bottom ---
        self.timeline = Timeline(self, self.is_dark)
        self.timeline.grid(row=3, column=0, sticky="ew", padx=6, pady=(10, 6))

    def _build_header_controls(self):
        top_bar = ttk.Frame(self, padding=(8, 8, 8, 0))
        top_bar.grid(row=0, column=0, sticky="ew")

        filter_frame = ttk.Frame(top_bar)
        filter_frame.pack(side="left")
        ttk.Label(filter_frame, text="🔍 Filter by:").pack(side="left")
        self.filter_category  = self._create_filter_combobox(filter_frame, "Category",  ["All"] + list(CATEGORY_LABELS.values()))
        self.filter_risk      = self._create_filter_combobox(filter_frame, "Risk",      ["All", "Low", "Moderate", "High"])
        self.filter_timeframe = self._create_filter_combobox(filter_frame, "Timeframe", ["All", "Day", "Swing", "Long-Term"])

        self.llm_status_label = ttk.Label(top_bar, text="", style="Status.TLabel")
        self.llm_progress     = ttk.Progressbar(top_bar, mode="indeterminate", length=80)
        self.app.llm_status_label = self.llm_status_label
        self.app.llm_progress     = self.llm_progress

        self.action_frame = ttk.Frame(top_bar)
        self.action_frame.pack(side="right")
        top_bar.columnconfigure(1, weight=1)

        self.last_updated_label = ttk.Label(self.action_frame, text="Last updated: Never")
        self.last_updated_label.pack(side="left", padx=(0, 8))

        self.refresh_button = ttk.Button(self.action_frame, text="🔄 Refresh Ideas", command=self._start_refresh)
        self.refresh_button.pack(side="left")

        self.settings_button = ttk.Button(self.action_frame, text="⚙️", width=3, command=self._open_universe_settings)
        self.settings_button.pack(side="left", padx=(6,0))

    def _create_filter_combobox(self, parent, label, values):
        ttk.Label(parent, text=f"{label}:").pack(side="left", padx=(10, 2))
        combo = ttk.Combobox(parent, values=values, state="readonly", width=15)
        combo.set("All")
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", self._apply_filters)
        return combo

    def _build_highlight_reel(self):
        self.highlight_fr = ttk.LabelFrame(self, text="🔥 Today’s Highlight Reel", padding=10)
        self.highlight_fr.grid(row=1, column=0, sticky="ew", padx=6, pady=10)
        self.highlight_fr.columnconfigure([0,1,2,3,4], weight=1)
        ttk.Label(self.highlight_fr, text="Refreshing ideas...").grid(row=0, column=0)

    def _build_wizard_tab(self):
        wizard_tab = ttk.Frame(self.content_nb, padding=20)
        self.content_nb.add(wizard_tab, text="🧙‍♂️ Build Your Own Idea")
        wizard_tab.columnconfigure(1, weight=1)

        ttk.Label(wizard_tab, text="Build-Your-Own-Idea Wizard", font=('Segoe UI', 14, 'bold')).grid(row=0, column=0, columnspan=2, pady=(0,20), sticky='w')
        
        # Form fields with variables
        self.wizard_vars = {
            'ticker': tk.StringVar(value='SPY'),
            'spot_price': tk.DoubleVar(value=500.0),
            'direction': tk.StringVar(value='Neutral/Mod Bullish'),
            'vol_view': tk.StringVar(value='Decrease/Flat'),
            'time_horizon': tk.StringVar(value='< 30 Days'),
            'risk_tolerance': tk.StringVar(value='Medium'),
            'iv_percent': tk.DoubleVar(value=50.0)
        }
        
        ttk.Label(wizard_tab, text="Ticker:").grid(row=1, column=0, sticky='w', pady=5)
        ttk.Entry(wizard_tab, textvariable=self.wizard_vars['ticker']).grid(row=1, column=1, sticky='ew')
        
        ttk.Label(wizard_tab, text="Current Price:").grid(row=2, column=0, sticky='w', pady=5)
        ttk.Entry(wizard_tab, textvariable=self.wizard_vars['spot_price']).grid(row=2, column=1, sticky='ew')

        ttk.Label(wizard_tab, text="Directional View:").grid(row=3, column=0, sticky='w', pady=5)
        ttk.Combobox(wizard_tab, textvariable=self.wizard_vars['direction'], values=["Bullish", "Bearish", "Neutral/Mod Bullish", "Neutral/Range-Bound"]).grid(row=3, column=1, sticky='ew')
        
        ttk.Label(wizard_tab, text="Volatility View:").grid(row=4, column=0, sticky='w', pady=5)
        ttk.Combobox(wizard_tab, textvariable=self.wizard_vars['vol_view'], values=["Increase", "Decrease/Flat", "Collapse"]).grid(row=4, column=1, sticky='ew')
        
        ttk.Label(wizard_tab, text="Risk Tolerance:").grid(row=5, column=0, sticky='w', pady=5)
        ttk.Combobox(wizard_tab, textvariable=self.wizard_vars['risk_tolerance'], values=["Low", "Medium", "High"]).grid(row=5, column=1, sticky='ew')

        ttk.Button(wizard_tab, text="🤖 Suggest Strategies", command=self._run_idea_wizard).grid(row=6, column=1, sticky='e', pady=20)
        

    # ──────────────────────────────────────────────────────────────
    # Wizard: collect inputs → call recommender → show results
    def _run_idea_wizard(self):
        try:
            raw = {k: v.get() for k, v in self.wizard_vars.items()}

            # ---------- build the rich inputs dict ----------
            inputs = {
                "ticker": raw["ticker"].upper(),
                "current_price": raw["spot_price"],
                "spot_price": raw["spot_price"],
                "direction": "Neutral" if raw["direction"].startswith("Neutral") else raw["direction"].split()[0],
                "iv_percent": raw["iv_percent"],
                "iv": raw["iv_percent"] / 100.0,
                "vol_view": raw["vol_view"],
                # map horizon to DTE
                "dte": 25 if "<" in raw["time_horizon"] else 45 if "30" in raw["time_horizon"] else 90,
                "risk_tolerance": raw["risk_tolerance"],
                "prefer_defined_risk": raw["risk_tolerance"] in ("Low", "Medium"),
                "confidence": 70,  # simple default
            }
            inputs["T_years"] = inputs["dte"] / 365.0

            # predicted IV: +10 % if “Increase”, –10 % if “Collapse”, else flat
            if raw["vol_view"] == "Increase":
                inputs["predicted_iv"] = inputs["iv"] * 1.10
            elif raw["vol_view"] == "Collapse":
                inputs["predicted_iv"] = inputs["iv"] * 0.90
            else:
                inputs["predicted_iv"] = inputs["iv"]

            # target price & move %
            spot = inputs["current_price"]
            if inputs["direction"] == "Bullish":
                inputs["target_price"] = spot * 1.05
            elif inputs["direction"] == "Bearish":
                inputs["target_price"] = spot * 0.95
            else:
                inputs["target_price"] = spot
            inputs["move_percent"] = abs(inputs["target_price"] - spot) / spot * 100

            # ---------- call recommender ----------
            recommender = StrategyRecommender(inputs=inputs)
            top = recommender.recommend_top_strategies(n=5)

            # normalise for display
            recommendations = [
                {
                    "strategy_name": s_name,
                    "score": score,
                    "description": desc,
                    "justification": notes.split(),
                }
                for score, s_name, notes, desc in top
            ]

            self._show_wizard_results(recommendations)

        except Exception as e:
            messagebox.showerror(
                "Wizard Error",
                f"Could not generate recommendations:\n{traceback.format_exc()}",
                parent=self,
            )


    def _show_wizard_results(self, recommendations):
        win = tk.Toplevel(self)
        win.title("Strategy Recommendations")
        win.geometry("600x400")
        win.transient(self)
        win.grab_set()

        text = tk.Text(win, wrap='word', font=('Segoe UI', 10), relief='flat', padx=10, pady=10)
        text.pack(expand=True, fill='both')
        
        if not recommendations:
            text.insert('1.0', "No suitable strategies found for the given criteria.")
        else:
            header = "Top Strategy Recommendations:\n\n"
            text.insert('1.0', header)
            
            for rec in recommendations:
                res_str = (f"▶ {rec['strategy_name']} (Score: {rec['score']:.1f})\n"
                           f"  - {rec['description']}\n"
                           f"  - Justification: {' '.join(rec['justification'])}\n\n")
                text.insert('end', res_str)
        
        text.config(state='disabled')

    def _render_saved_tab(self):
        frame = self.saved_tab.scrollable_frame
        # clear out old cards
        for w in frame.winfo_children():
            w.destroy()

        # show every idea that’s currently starred
        for idea in self._all_ideas:
            if idea.uid in self._saved_ids:
                # pull in any notes/tags
                data = self._saved_notes.get(idea.uid, {})
                idea.notes = data.get("notes", "")
                idea.tags  = data.get("tags", [])
                card = IdeaCard(frame, idea, self.app)
                card.grid(sticky="ew", padx=10, pady=5)


    def _persist_uid(self, uid: str, *, add: bool):
        if add:
            self._saved_ids.add(uid)
        else:
            self._saved_ids.discard(uid)
        save_ids(sorted(self._saved_ids))
        self._render_saved_tab()   # live update tab
    
    def _persist_notes(self, uid: str, notes: str, tags: list[str]):
        self._saved_notes[uid] = {"notes": notes, "tags": tags}
        save_notes(self._saved_notes)
        # if you want to immediately refresh the “Saved Ideas” tab:
        self._render_saved_tab()

    def _open_universe_settings(self):
        win = tk.Toplevel(self)
        win.title("Universe Settings")
        win.transient(self)
        win.grab_set()
        win.columnconfigure(0, weight=1)

        # frame to hold all ticker rows
        container = ttk.Frame(win, padding=10)
        container.grid(row=0, column=0, sticky="nsew")

        # list of StringVars for each ticker
        ticker_vars: list[tk.StringVar] = [tk.StringVar(value=t) for t in self.universe]

        def redraw():
            # clear existing rows
            for w in container.winfo_children():
                w.destroy()
            # re-create a row for each ticker
            for idx, var in enumerate(ticker_vars):
                row = ttk.Frame(container)
                row.grid(row=idx, column=0, sticky="ew", pady=2)
                row.columnconfigure(0, weight=1)
                entry = ttk.Entry(row, textvariable=var)
                entry.grid(row=0, column=0, sticky="ew")
                btn = ttk.Button(
                    row,
                    text="✕",
                    width=2,
                    command=lambda v=var: remove_ticker(v)
                )
                btn.grid(row=0, column=1, padx=(5,0))

        def remove_ticker(var: tk.StringVar):
            ticker_vars.remove(var)
            redraw()

        def add_ticker():
            ticker_vars.append(tk.StringVar())
            redraw()

        # “＋” button
        add_btn = ttk.Button(win, text="＋ Add Ticker", command=add_ticker)
        add_btn.grid(row=1, column=0, pady=(0,10))

        # action buttons
        btn_frame = ttk.Frame(win)
        btn_frame.grid(row=2, column=0, pady=(0,10))

        def on_save():
            # collect non-empty, uppercase tickers
            new_univ = [
                v.get().strip().upper()
                for v in ticker_vars
                if v.get().strip()
            ]
            self.universe = new_univ
            self.app.settings.set("idea_universe", self.universe)
            self.app.save_settings()
            win.destroy()
            self._start_refresh()

        ttk.Button(btn_frame, text="Save",   command=on_save).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(side="left")
        
        # initial draw
        redraw()




    def _build_copilot_tab(self):
        copilot_tab = ttk.Frame(self.content_nb, padding=20)
        self.content_nb.add(copilot_tab, text="🧠 AI Co-Pilot")
        copilot_tab.rowconfigure(1, weight=1)
        copilot_tab.columnconfigure(0, weight=1)

        ttk.Label(copilot_tab, text="AI Co-Pilot for Idea Generation", font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(copilot_tab, text="Use natural language to find trading ideas from the app's data models.", wraplength=600).pack(anchor='w', pady=(5, 15))

        self.copilot_response_text = tk.Text(copilot_tab, height=10, wrap="word", relief="solid", borderwidth=1)
        self.copilot_response_text.pack(fill="both", expand=True, pady=5)
        self.copilot_response_text.insert("1.0", "Ask a question about the current ideas below...")
        self.copilot_response_text.config(state="disabled")

        prompt_frame = ttk.Frame(copilot_tab)
        prompt_frame.pack(fill="x", pady=(10, 0))
        prompt_frame.columnconfigure(0, weight=1)

        self.copilot_prompt_entry = ttk.Entry(prompt_frame, font=('Segoe UI', 10))
        self.copilot_prompt_entry.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        self.copilot_prompt_entry.insert(0, "Which of these earnings plays has the highest expected move?")
        
        ttk.Button(prompt_frame, text="Generate", command=self._ask_copilot).grid(row=0, column=1)

    def _ask_copilot(self):
        prompt = self.copilot_prompt_entry.get()
        if not prompt: return

       # reveal & start the loading indicator just left of the action buttons
        self.llm_status_label.pack(side="left",  before=self.action_frame, padx=(0,8))
        self.llm_progress    .pack(side="left",  before=self.action_frame, padx=(0,8))
        self.llm_status_label.config(text="Fetching AI…")
        self.llm_progress.start()

        def llm_worker():
            try:
                llm = LLMHelper()
                # assemble a simple context string for the AI
                context_str = "\n".join(f"{i.symbol}: {i.title}" for i in self._all_ideas)
                answer = llm.answer_query_with_context(prompt, context_str)
                self.after(0, lambda: self._display_copilot(answer))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("LLM Error", str(e), parent=self))
            finally:
                self.after(0, lambda: (
                        self.llm_progress.stop(),
                        self.llm_status_label.config(text=""),
                        self.llm_progress.pack_forget(),
                        self.llm_status_label.pack_forget()
                ))

        threading.Thread(target=llm_worker, daemon=True).start()

    def _display_copilot(self, text: str):
        # insert LLM answer into the copilot text box
        self.copilot_response_text.config(state="normal")
        self.copilot_response_text.delete("1.0", "end")
        self.copilot_response_text.insert("1.0", text)
        self.copilot_response_text.config(state="disabled")



    def _start_refresh(self):
            """Internal method called by the refresh button."""
            self.refresh_button.config(state="disabled")
            self.last_updated_label.config(text="Updating...")
            self.refresh_ideas()

    def _poll_queue(self):
        """Check for new ideas AND progress updates from the background thread."""
        try:
            # Process completed ideas (this branch means the full list of ideas has arrived)
            new_ideas = self.queue.get_nowait()

            # Full data received, trigger finale on loader
            if self._idea_suite_loader and self._idea_suite_loader.winfo_exists():
                self._idea_suite_loader.trigger_climax_and_take_profit() # NEW: Trigger finale here
                # Schedule hiding AFTER the climax animation completes
                self._idea_suite_loader.after(1500, lambda: self._idea_suite_loader.place_forget()) # Hide after 1.5s

            self.app.set_status("Idea generation complete.", color="green")
            if self.app and hasattr(self.app, '_cancel_loading_animation'):
                self.app._cancel_loading_animation() # Stop main app's spinner if it was active

            for i in new_ideas:
                i.is_saved = i.uid in self._saved_ids

            self._all_ideas = new_ideas
            self._apply_filters()

            self.last_updated_label.config(text=f"Last updated: {time.strftime('%I:%M:%S %p')}")
            self.refresh_button.config(state="normal")
        except queue.Empty:
            pass # No new idea data

        try:
            # Process progress updates
            processed_count, total_count = self._progress_queue.get_nowait()
            if total_count > 0:
                progress_pct = processed_count / total_count
                if self._idea_suite_loader and self._idea_suite_loader.winfo_exists():
                    self._idea_suite_loader.update_progress_bar(progress_pct)
                self.app.set_status(f"Generating ideas... {processed_count}/{total_count} symbols processed.", color="blue")
        except queue.Empty:
            pass # No new progress data

        finally:
            self.after(self.POLL_MS, self._poll_queue)

    def _show_loading_overlay(self):
        """Displays the Idea Suite's dedicated animated loading screen as an overlay."""
        if self._idea_suite_loader and self._idea_suite_loader.winfo_exists():
            # Ensure the loader is placed to cover the entire view
            self._idea_suite_loader.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._idea_suite_loader.lift() # Bring to front
            self._idea_suite_loader.focus_force() # Ensure it captures focus

            # Reset the loader's internal state
            self._idea_suite_loader._setup_chart() # Reset chart
            self._idea_suite_loader.candles = [] # Clear old candles
            self._idea_suite_loader.is_finale_triggered = False # Reset finale state
            self._idea_suite_loader.in_pre_climax_mode = False # Reset mode
            self._idea_suite_loader.price_velocity = 0.0 # Reset velocity
            self._idea_suite_loader.progress_bar['value'] = 0 # Reset progress bar

            self.app.set_status("Generating ideas...", color="blue")

            # Start the animation loop directly on the _idea_suite_loader instance
            self._idea_suite_loader.start_animation_loop(total_duration_ms=10000, update_interval_ms=5) # Start its own animation


    def _hide_loading_overlay(self):
        """Hides the Idea Suite's dedicated loading screen and restores content."""
        if self._idea_suite_loader and self._idea_suite_loader.winfo_exists():
            # Trigger finale sequence on the dedicated loader
            self._idea_suite_loader.update_progress_bar(1.0)
            self._idea_suite_loader.trigger_pre_climax_dip()
            self._idea_suite_loader.animate_take_profit()

            # Schedule the animation finale and then hide the loader frame
            # The animation has its own internal timer, so we schedule the hiding after it completes.
            self._idea_suite_loader.after(1500, lambda: self._idea_suite_loader.place_forget()) # Hide the frame after animation

        # Stop main app's general loading animation/status if it was linked
        if self.app and hasattr(self.app, '_cancel_loading_animation'):
            self.app._cancel_loading_animation()
            self.app.set_status("Idea generation complete.", color="green")



    def _apply_filters(self, event=None):
        cat_filter = self.filter_category.get()
        risk_filter = self.filter_risk.get()
        
        filtered_ideas = self._all_ideas
        
        if cat_filter != "All":
            filtered_ideas = [i for i in filtered_ideas if CATEGORY_LABELS.get(i.category) == cat_filter]
        if risk_filter != "All":
            filtered_ideas = [i for i in filtered_ideas if i.risk == risk_filter]
            
        self._render(filtered_ideas)

    def _render(self, ideas: List[Idea]):
        self._render_highlight_reel(ideas)
        self._render_category_tabs(ideas)
        self._render_timeline(ideas)
        self._render_saved_tab()

    def _render_highlight_reel(self, ideas: List[Idea]):
        for w in self.highlight_fr.winfo_children(): w.destroy()
        
        def blended_score(idea: Idea):
            score = idea.score
            if idea.category == "💬 Social": score *= 1.2
            if "UnusualActivity" in idea.metrics: score *= 1.5
            if hasattr(self.app, 'settings') and idea.symbol in self.app.settings.get("watchlist", ""): score *= 1.3
            return score

        top5 = sorted(ideas, key=blended_score, reverse=True)[:5]
        if not top5:
            ttk.Label(self.highlight_fr, text="No ideas generated. Check console for data errors.").grid()
            return

        for idx, idea in enumerate(top5):
            IdeaCard(
                self.highlight_fr, idea, self.app,
                compact=True
            ).grid(row=0, column=idx, padx=5, pady=5, sticky="nsew")

    def _highlight_expand(self, uid: str, expand: bool):
        collapsed_w =  80
        expanded_w  = collapsed_w * 3

        for col_idx, child in enumerate(self.highlight_fr.winfo_children()):
            if not isinstance(child, IdeaCard):
                continue

            # always compact‐mode buttons
            child.compact = True

            if child.idea.uid == uid and expand:
                self.highlight_fr.columnconfigure(col_idx, weight=1, minsize=expanded_w)
            else:
                self.highlight_fr.columnconfigure(col_idx, weight=1, minsize=collapsed_w)

            child._rebuild_ui()





    def _render_category_tabs(self, ideas: List[Idea]):
        buckets: Dict[str, list[Idea]] = {label: [] for label in CATEGORY_LABELS.values()}
        for idea in ideas:
            label = CATEGORY_LABELS.get(idea.category)
            if label and label in buckets:
                 buckets[label].append(idea)

        # Clear all existing widgets from tabs before re-rendering
        for label in self._category_tabs:
            scroll_frame = self._category_tabs[label]
            for w in scroll_frame.scrollable_frame.winfo_children():
                w.destroy()

        # Hide all tabs initially
        for tab in self.category_nb.tabs():
            self.category_nb.hide(tab)

        for label, items in buckets.items():
            if not items: continue
            
            # Create tab if it doesn't exist
            if label not in self._category_tabs:
                scroll_frame = ScrollableFrame(self.category_nb, self.is_dark)
                self._category_tabs[label] = scroll_frame
                self.category_nb.add(scroll_frame, text=label)
            else:
                # If tab exists, make sure it's visible
                try:
                    self.category_nb.add(self._category_tabs[label], text=label)
                except tk.TclError: # Already managed
                    pass
            
            container = self._category_tabs[label].scrollable_frame
            for idx, idea in enumerate(sorted(items, key=lambda i: -i.score)):
                IdeaCard(container, idea, self.app).grid(row=idx, column=0, sticky="ew", padx=10, pady=5)


    def _render_timeline(self, ideas: List[Idea]):
        events = [(i.event_ts, i.symbol, i.title) for i in ideas if i.event_ts]
        self.timeline.set_events(events)

class ScrollableFrame(ttk.Frame):
    """A scrollable frame for holding content like idea cards."""
    def __init__(self, parent, is_dark: bool):
        super().__init__(parent)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        bg = '#1e1e1e' if is_dark else '#f0f0f0'
        canvas = tk.Canvas(self, highlightthickness=0, bg=bg)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        
        self.scrollable_frame = ttk.Frame(canvas)
        self.scrollable_frame.columnconfigure(0, weight=1)
        
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        
        canvas_frame = canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        # ── mouse wheel scroll everywhere ───────────────────────────────
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        # bind while pointer is over this widget
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))


        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_frame, width=event.width)

        self.scrollable_frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)

class Timeline(ttk.Frame):
    """Horizontal timeline with hover tooltips."""
    def __init__(self, parent: tk.Misc, is_dark: bool):
        super().__init__(parent)
        bg = '#2a2a2e' if is_dark else '#ffffff'
        self._canvas = tk.Canvas(self, height=45, highlightthickness=0, bg=bg)
        self._canvas.pack(fill="x", expand=True)
        self.canvas = self._canvas        # ← add this alias line
        self._events: list = []
        self._tooltips: list = []
        self._canvas.bind("<Configure>", lambda e: self._redraw())


    def set_events(self, events: list):
        self._events = sorted(events, key=lambda x: x[0])
        self._redraw()

    def _redraw(self):
        self._canvas.delete("all")
        self._tooltips.clear()
        if not self._events: return

        now = int(time.time())
        future_events = [e for e in self._events if e[0] > now]
        if not future_events: return

        max_ts = max(ts for ts, _, _ in future_events)
        min_ts = min(ts for ts, _, _ in future_events)
        
        time_span = max_ts - min_ts if max_ts > min_ts else 1
        w = self._canvas.winfo_width()
        
        for ts, symbol, title in future_events:
            x = int(((ts - min_ts) / time_span) * (w - 60)) + 30 # Add padding
            if not (20 < x < w - 20): continue
            
            line = self._canvas.create_line(x, 10, x, 30, fill="#888")
            date_str = dt.datetime.fromtimestamp(ts).strftime('%a, %b %d')
            text = self.canvas.create_text(x, 35, text=f"{symbol}\n{date_str}", anchor="n", font=("Segoe UI", 7), fill="#aaa")
            
            hover_target = self._canvas.create_rectangle(x-10, 10, x+10, 45, fill="", outline="")
            
            tooltip_text = f"{symbol}: {title}\nDate: {dt.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')}"
            # Store the tooltip object to prevent it from being garbage collected
            self._tooltips.append(IdeaTooltip(self._canvas, tooltip_text, hover_target))