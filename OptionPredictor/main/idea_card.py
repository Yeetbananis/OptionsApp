# idea_card.py
from __future__ import annotations
import io
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, TYPE_CHECKING

import matplotlib.pyplot as plt
from PIL import Image, ImageTk

from idea_models import Idea
from llm_helper import LLMHelper

if TYPE_CHECKING:
    from OptionsApp import OptionAnalyzerApp


class IdeaCard(ttk.Frame):
    """A self-contained, interactive card displaying a single trading idea."""

    @staticmethod
    def _get_tag_color(tag: str) -> str:
        """Deterministically pick a color for a tag."""
        palette = [
            "#e6194b", "#3cb44b", "#ffe119", "#4363d8",
            "#f58231", "#911eb4", "#46f0f0", "#f032e6",
            "#bcf60c", "#fabebe"
        ]
        return palette[abs(hash(tag)) % len(palette)]


    CATEGORY_COLORS = {
        "📈 Volatility": "#f94144",
        "🗓 Earnings": "#f3722c",
        "🌊 Options Flow": "#f9c74f",
        "🚀 Momentum": "#90be6d",
        "🧑‍🌾 Theta Farms": "#43aa8b",
        "💬 Social": "#577590",
        "🎯 Setups": "#277da1",
        "🌎 Thematic": "#8e6e95",
        "🧪 Experimental": "#c3aed6"
    }
    RISK_COLORS = {"Low": "green", "Moderate": "orange", "High": "red"}


    def __init__(self, parent: tk.Misc, idea: Idea, app_controller: 'OptionAnalyzerApp', compact: bool = False):
        super().__init__(parent, padding=0, relief="solid", borderwidth=1)
        self.idea = idea
        self.app = app_controller
        self.compact = compact
        # keep track so we can revert when un-exploring
        self._initial_compact = compact


        # --- Theming ---
        is_dark = self.app.current_theme == 'dark'
        self.bg = '#2a2a2e' if is_dark else '#ffffff'
        self.fg = '#ffffff' if is_dark else '#000000'
        self.subtle_fg = '#bbbbbb' if is_dark else '#555555'
        self.configure(style='Card.TFrame')
        ttk.Style().configure('Card.TFrame', background=self.bg)

        # ── Compact styles for highlight-reel cards ─────────────────────
        style = ttk.Style()
        style.configure(
            "CompactCard.TButton",
            font=('Segoe UI', 6, 'bold'),
            padding=(4, 2)
        )
        style.configure(
            "CompactPill.TButton",
            font=('Segoe UI', 7),
            padding=(2, 1),
            borderwidth=0
        )


        # --- UI Build ---
        self._build_ui()

    def _build_ui(self):
        # Colored left bar for category
        bar_color = self.CATEGORY_COLORS.get(self.idea.category, "#888")
        tk.Frame(self, bg=bar_color, width=5).grid(row=0, column=0, rowspan=5, sticky="nsw")

        # Main content grid
        content_frame = ttk.Frame(self, style='Card.TFrame')
        self.content_frame = content_frame
        content_frame.grid(row=0, column=1, rowspan=5, sticky="nsew", padx=10, pady=8)
        content_frame.columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Row 0: Header (Ticker & Title)
        header_text = f"{self.idea.symbol} • {self.idea.title}"
        ttk.Label(content_frame, text=header_text, style="CardHeadline.TLabel", anchor="w").grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Style().configure("CardHeadline.TLabel", font=('Segoe UI', 11, "bold"), background=self.bg, foreground=self.fg)

        # Row 1: Description
        ttk.Label(content_frame, text=self.idea.description, wraplength=350, style="CardDesc.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 8))
        ttk.Style().configure("CardDesc.TLabel", font=('Segoe UI', 9), background=self.bg, foreground=self.fg)

        # Row 2: Sparkline Chart
        self.chart_label = ttk.Label(content_frame, background=self.bg)
        self.chart_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._generate_sparkline()

        # Row 3: Metrics & Strategy
        metrics_frame = ttk.Frame(content_frame, style='Card.TFrame')
        metrics_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=4)
        
        # Risk Level
        risk_color = self.RISK_COLORS.get(self.idea.risk, "grey")
        ttk.Label(metrics_frame, text=f"Risk: {self.idea.risk}", foreground=risk_color, font=('Segoe UI', 9, 'bold'), background=self.bg).pack(side="left")
        
        # Suggested Strategy
        strat_text = self.idea.suggested_strategy.get('type', '').replace('_', ' ').title()
        ttk.Label(metrics_frame, text=f"💡 {strat_text}", font=('Segoe UI', 9), background=self.bg, foreground=self.subtle_fg).pack(side="left", padx=15)
        
        # Row 4: Icon-only Action Buttons
        button_frame = ttk.Frame(content_frame, style='Card.TFrame')
        button_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8,0))

        # define both styles up front
        btn_style  = "CompactCard.TButton" if self.compact else "Card.TButton"
        pill_style = "CompactPill.TButton" if self.compact else "Pill.TButton"

        if self.compact:
            # Define each icon + callback
            icons = [
                ("▶",  self._on_view_strat),
                ("🤖", self._on_ask_llm),
                ("📝", self._on_notes),
                ("🌟" if self.idea.is_saved else "⭐",  self._toggle_save),
                ("✅" if self.idea.is_explored else "➕", self._toggle_explored),
            ]
            # One column per button, equal weight
            for idx, (sym, cmd) in enumerate(icons):
                btn = ttk.Button(
                    button_frame,
                    text=sym,
                    command=cmd,
                    style=btn_style
                )
                btn.grid(row=0, column=idx, sticky="nsew", padx=1)
                button_frame.columnconfigure(idx, weight=1)

            # keep references so _update_toggle_visuals can mutate them
            self.save_button     = button_frame.grid_slaves(row=0, column=3)[0]
            self.explored_button = button_frame.grid_slaves(row=0, column=4)[0]

        else:
            # full-text buttons
            ttk.Button(
                button_frame,
                text="View Strategy",
                command=self._on_view_strat,
                style=btn_style
            ).pack(side="left")
            ttk.Button(
                button_frame,
                text="Ask LLM",
                command=self._on_ask_llm,
                style=btn_style
            ).pack(side="left", padx=6)
            ttk.Button(
                button_frame,
                text="📝 Notes",
                command=self._on_notes,
                style=btn_style
            ).pack(side="left", padx=6)

            # right-aligned toggle pills
            toggle_frame = ttk.Frame(button_frame, style='Card.TFrame')
            toggle_frame.pack(side="right")
            self.save_button = ttk.Button(
                toggle_frame,
                text="🌟 Saved" if self.idea.is_saved else "⭐ Save",
                command=self._toggle_save,
                style=pill_style
            )
            self.save_button.pack(side="left", padx=4)
            self.explored_button = ttk.Button(
                toggle_frame,
                text="✅ Explored" if self.idea.is_explored else "➕ Explore",
                command=self._toggle_explored,
                style=pill_style
            )
            self.explored_button.pack(side="left")

        # ── If this idea has notes, show them ────────────────────────────
        if self.idea.notes:
            ttk.Label(
                content_frame,
                text=f"Notes: {self.idea.notes}",
                style="CardDesc.TLabel",
            ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8,2))

        # ── If this idea has tags, render colored pills ─────────────────
        if self.idea.tags:
            tags_frame = ttk.Frame(content_frame, style='Card.TFrame')
            tags_frame.grid(row=6, column=0, columnspan=2, sticky="w")
            for tag in self.idea.tags:
                color = self._get_tag_color(tag)
                tk.Label(
                    tags_frame,
                    text=tag,
                    bg=color,
                    fg=self.fg,
                    padx=4,
                    pady=2,
                ).pack(side="left", padx=(0,5), pady=(0,4))

        # ensure our save/explored icons/text update correctly
        self._update_toggle_visuals()


        # ── If this idea has notes, show them ────────────────────────────
        if self.idea.notes:
            ttk.Label(
                content_frame,
                text=f"Notes: {self.idea.notes}",
                style="CardDesc.TLabel",
            ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(8,2))

        # ── If this idea has tags, render colored pills ─────────────────
        if self.idea.tags:
            tags_frame = ttk.Frame(content_frame, style='Card.TFrame')
            tags_frame.grid(row=6, column=0, columnspan=2, sticky="w")
            for tag in self.idea.tags:
                color = self._get_tag_color(tag)
                tk.Label(
                    tags_frame,
                    text=tag,
                    bg=color,
                    fg=self.fg,
                    padx=4,
                    pady=2,
                ).pack(side="left", padx=(0,5), pady=(0,4))

        # ensure our save/explored icons/text update correctly
        self._update_toggle_visuals()


        # --- Button Styles ---
        ttk.Style().configure("Card.TButton", font=('Segoe UI', 8, 'bold'), padding=(8, 4))
        ttk.Style().configure("Pill.TButton", font=('Segoe UI', 9), padding=(6,3), borderwidth=0)

    def _rebuild_ui(self):
        """Clear & rebuild this card in-place."""
        for w in self.winfo_children():
            w.destroy()
        self._build_ui()



    def _generate_sparkline(self):
        if not self.idea.sparkline_data:
            self.chart_label.configure(text="Chart data not available.", foreground=self.subtle_fg, font=('Segoe UI', 8))
            return

        is_bullish = self.idea.sparkline_data[-1] > self.idea.sparkline_data[0]
        color = 'green' if is_bullish else 'red'
        
        fig = plt.figure(figsize=(3, 0.5), dpi=100)
        ax = fig.add_subplot(111)
        ax.plot(self.idea.sparkline_data, color=color, linewidth=1.5)
        
        # Styling
        plt.box(False)
        fig.patch.set_facecolor(self.bg)
        ax.set_facecolor(self.bg)
        ax.tick_params(axis='both', which='both', bottom=False, top=False, left=False, right=False, labelbottom=False, labelleft=False)
        ax.grid(False)
        plt.tight_layout(pad=0)

        # Render to Tkinter PhotoImage
        buf = io.BytesIO()
        fig.savefig(buf, format='png', transparent=False, facecolor=self.bg)
        plt.close(fig)
        buf.seek(0)
        
        img = Image.open(buf)
        self.sparkline_image = ImageTk.PhotoImage(img)
        self.chart_label.config(image=self.sparkline_image)

    # --- Callbacks to App Controller ---
    def _on_view_strat(self) -> None:
        """
        Open (or refocus) the Strategy-Builder window and preload the
        suggested legs that came with this Idea.

        Works with both legacy signature:
            launch_strategy_builder()
        and the newer one that accepts a dict:
            launch_strategy_builder(suggested_strategy)
        """
         # Package full idea data for prefill
        idea_data = {
            "symbol": self.idea.symbol,
            "metrics": {
                "spot_price": self.idea.metrics.get("spot_price", self.idea.metrics.get("spot", 0)),
                "dte":        self.idea.metrics.get("dte",        self.idea.metrics.get("DTE", 0)),
            },
            "suggested_strategy": self.idea.suggested_strategy or {}
        }
        # Launch builder with our prefill payload
        try:
            self.app.launch_strategy_builder(idea_data)
        except TypeError:
            # in case of older signature
            self.app.launch_strategy_builder()


    def _on_ask_llm(self):
         # 1) show & start the header indicator
        self.app.llm_status_label.pack(side="left", padx=(0,8))
        self.app.llm_progress.pack(side="left", padx=(0,8))
        self.app.llm_status_label.config(text="Fetching LLM…")
        self.app.llm_progress.start()



        # 2) do the work off the UI thread
        def worker():
            try:
                client = LLMHelper()
                # explain the suggested option strategy using your idea’s data
                resp = client.explain_option_strategy(
                    ticker=self.idea.symbol,
                    option_type=self.idea.suggested_strategy.get('type', ''),
                    strike=self.idea.suggested_strategy.get('strike', 0),
                    S0=self.idea.metrics.get('spot_price', self.idea.metrics.get('spot', 0)),
                    premium=self.idea.suggested_strategy.get('premium', 0),
                    T_days=self.idea.metrics.get('dte', 0),
                    prob=self.idea.metrics.get('barrier_hit_probability', 0),
                    metrics=self.idea.metrics
                )
                # back to UI
                self.after(0, lambda: self._on_llm_response(resp))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("LLM Error", str(e), parent=self))
            finally:
                # ensure spinner stops even on exception
                self.after(0, lambda: (
                    self.app.llm_progress.stop(),
                    self.app.llm_status_label.config(text="")
                ))

        threading.Thread(target=worker, daemon=True).start()

    def _on_llm_response(self, resp):
         # stop & hide the header spinner
        self.app.llm_progress.stop()
        self.app.llm_status_label.config(text="")
        self.app.llm_status_label.pack_forget()
        self.app.llm_progress.pack_forget()

        # open explanation in its own window
        win = tk.Toplevel(self)
        win.title(f"LLM Explanation — {self.idea.symbol}")
        win.transient(self); win.grab_set()

        txt = tk.Text(win, wrap="word", font=('Segoe UI', 10), padx=10, pady=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", resp)
        txt.config(state="disabled")

    def _show_llm_response(self, resp: str):
        """Render the LLM’s explanation text right below the tags/notes."""
        # destroy any old response
        if hasattr(self, "_llm_frame"):
            self._llm_frame.destroy()

        # container for the response
        self._llm_frame = ttk.Frame(self.content_frame, style='Card.TFrame')
        # place in its own row (after tags row)
        self._llm_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(8,2))

        # header label
        ttk.Label(
            self._llm_frame,
            text="🧠 Explanation:",
            style="CardDesc.TLabel"
        ).pack(anchor="w")

        # response text area
        resp_txt = tk.Text(
            self._llm_frame,
            wrap="word",
            height=4,
            bg=self.bg,
            fg=self.fg,
            relief="flat",
            borderwidth=0,
            font=('Segoe UI', 9)
        )
        resp_txt.insert("1.0", resp)
        resp_txt.config(state="disabled")
        resp_txt.pack(fill="both", expand=True, padx=(0,4), pady=(2,0))


  

    def _toggle_save(self):
        # flip saved state
        self.idea.is_saved = not self.idea.is_saved
        # update this card’s star icon/text
        self._update_toggle_visuals()
        # persist & live-refresh the Saved tab
        self.app.idea_suite_save(self.idea.uid, add=self.idea.is_saved)


    def _toggle_explored(self):
        # flip explored state
        self.idea.is_explored = not self.idea.is_explored
        # update this card’s button icon
        self._update_toggle_visuals()

        # on explore ➔ open detail window
        if self.idea.is_explored:
            # create & remember detail window
            win = tk.Toplevel(self)
            self._detail_win = win
            win.title(f"Idea Details — {self.idea.symbol}")
            win.transient(self)
            win.grab_set()
            # top: full-size card (compact=False)
            card_ct = ttk.Frame(win, padding=10)
            card_ct.pack(fill="x")
            IdeaCard(card_ct, self.idea, self.app, compact=False).pack(fill="x")
            # bottom: placeholder for future content
            extra_ct = ttk.Frame(win, padding=10, style='Card.TFrame')
            extra_ct.pack(fill="both", expand=True)
            # you can now add widgets into `extra_ct` for notes, charts, etc.

        # on un-explore ➔ destroy detail window
        else:
            if hasattr(self, "_detail_win"):
                try:
                    self._detail_win.destroy()
                except Exception:
                    pass
                del self._detail_win


    def _expand_view(self):
        """Open a modal with a full-size, non-compact card for detail."""
        win = tk.Toplevel(self)
        win.title(f"Idea Details — {self.idea.symbol}")
        win.transient(self)
        win.grab_set()

        # pack a full-size IdeaCard (compact=False) in a padded frame
        container = ttk.Frame(win, padding=20)
        container.pack(fill="both", expand=True)
        # instantiate a non-compact version of this card
        IdeaCard(container, self.idea, self.app, compact=False).pack(
            fill="both", expand=True
        )



    def _update_toggle_visuals(self):
        if self.compact:
            # icon-only
            self.save_button.config(text="🌟" if self.idea.is_saved else "⭐")
            self.explored_button.config(text="✅" if self.idea.is_explored else "➕")
        else:
            # full-text
            self.save_button.config(text="🌟 Saved"    if self.idea.is_saved   else "⭐ Save")
            self.explored_button.config(text="✅ Explored" if self.idea.is_explored else "➕ Explore")



    def _on_notes(self):
        win = tk.Toplevel(self)
        win.title("Notes & Tags")
        win.transient(self); win.grab_set()

        container = ttk.Frame(win, padding=10)
        container.pack(fill="both", expand=True)

        # — Notes text area —
        ttk.Label(container, text="Notes:").grid(row=0, column=0, sticky="w")
        notes_txt = tk.Text(container, height=5, wrap="word")
        notes_txt.grid(row=1, column=0, columnspan=2, sticky="ew", pady=5)
        notes_txt.insert("1.0", self.idea.notes or "")

        # — Tags editor —
        ttk.Label(container, text="Tags:").grid(row=2, column=0, sticky="w", pady=(10,0))
        tags_frame = ttk.Frame(container)
        tags_frame.grid(row=3, column=0, columnspan=2, sticky="w")

        def refresh_tags():
            for w in tags_frame.winfo_children():
                w.destroy()
            for t in self.idea.tags:
                frm = ttk.Frame(tags_frame)
                frm.pack(side="left", padx=2, pady=2)
                icon = tk.Label(frm, text=t, bg=self._get_tag_color(t),
                                fg=self.fg, padx=4, pady=2)
                icon.pack(side="left")
                btn = ttk.Button(frm, text="✕", width=2,
                                 command=lambda tag=t: remove_tag(tag))
                btn.pack(side="left", padx=(2,0))

        def remove_tag(tag):
            self.idea.tags.remove(tag)
            refresh_tags()

        new_tag_var = tk.StringVar()
        ttk.Entry(container, textvariable=new_tag_var).grid(
            row=4, column=0, sticky="w", pady=(5,0))
        ttk.Button(container, text="＋", width=2,
                   command=lambda: add_tag()
        ).grid(row=4, column=1, sticky="w", pady=(5,0))

        def add_tag():
            new = new_tag_var.get().strip()
            if new and new not in self.idea.tags:
                self.idea.tags.append(new)
                new_tag_var.set("")
                refresh_tags()

        refresh_tags()

        # — Save / Cancel —
        btns = ttk.Frame(container)
        btns.grid(row=5, column=0, columnspan=2, pady=(10,0))
        ttk.Button(
            btns,
            text="Save",
            command=lambda: self._save_notes(
                notes=notes_txt.get("1.0","end").strip(),
                tags=self.idea.tags,
                win=win
            )
        ).pack(side="right")
        ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right", padx=(0,5))

    def _save_notes(self, *, notes: str, tags: list[str], win):
        self.idea.notes = notes
        self.idea.tags  = tags
        # persist via controller
        self.app.idea_suite_save_notes(self.idea.uid, notes, tags)
        win.destroy()
