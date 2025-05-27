# app.py
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import numpy as np # Import numpy if needed for default values or checks
import time # For small delay in animation
import traceback # Import traceback for detailed error logging
import pandas as pd
import sys
import time # Make sure time is imported 
from matplotlib.lines import Line2D # Needed for Line2D used in educational mode
from llm_helper import LLMHelper
from StockChartWindow import StockChartWindow

def configure_global_styles(theme: str):
    """
    Apply *every* ttk style rule for light vs dark.
    Must be called *before* you re-skin each window.
    """
    style = ttk.Style()
    style.theme_use('clam')

    if theme == 'dark':
        bg, fg           = "#0f0f0f", '#ffffff'
        entry_bg         = '#3c3c3c'
        button_bg        = '#555555'
        header_bg        = '#444444'
        combobox_bg      = entry_bg
        notebook_sel_bg  = '#333333'
        tree_bg, field_bg= entry_bg, entry_bg
    else:
        bg, fg           = '#f0f0f0', '#000000'
        entry_bg         = '#ffffff'
        button_bg        = '#e0e0e0'
        header_bg        = '#d9d9d9'
        combobox_bg      = entry_bg
        notebook_sel_bg  = '#ffffff'
        tree_bg, field_bg= entry_bg, entry_bg

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
        #cached_lsm_price

    )
except ImportError:
    messagebox.showerror("Import Error", "Could not find 'MonteCarloSimulation.py'. Make sure it's in the same directory as this script.")
    exit()

class OptionAnalyzerApp:
    def __init__(self, root):

        self.current_theme = 'light'  # or 'dark'
        self.root = root
        self.root.title("Option Analyzer")
        self.root.geometry("900x800") # Give main window a bit more space
        self.llm = LLMHelper(model="deepseek-q4ks")

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

        

        # --- Main Layout ---
        self.main_frame = ttk.Frame(root, padding="20 20 20 20", style="TFrame")
        self.main_frame.pack(expand=True, fill=tk.BOTH)
        # Configure row/column weights for resizing behavior
        self.main_frame.rowconfigure(0, weight=0) # Title row
        self.main_frame.rowconfigure(1, weight=0) # Button row
        self.main_frame.rowconfigure(2, weight=1) # Results buttons frame (allow expansion)
        self.main_frame.rowconfigure(3, weight=0) # Status label row
        self.main_frame.columnconfigure(0, weight=1)


        self.title_label = ttk.Label(self.main_frame, text="Option Analysis Tool", style="Title.TLabel", anchor="center")
        self.title_label.grid(row=0, column=0, pady=(10, 30), sticky="ew")

        topbar = ttk.Frame(self.root, padding=(0, 5))
        topbar.place(relx=1.0, y=5, anchor="ne")  # Top right corner

        fullscreen_btn = ttk.Button(topbar, text="⛶", width=3, command=self._toggle_fullscreen)
        fullscreen_btn.pack(side=tk.RIGHT)

        close_btn = ttk.Button(topbar, text="✖", width=3, command=self._close_window)
        close_btn.pack(side=tk.RIGHT, padx=(0, 5))


        # Create a neat button row with grid layout
        button_frame = ttk.Frame(self.main_frame)
        button_frame.grid(row=1, column=0, pady=10)

        # --- Button row -----------------------------------------------------------
        # Start Analysis
        self.start_button = ttk.Button(button_frame, text="📊 Start New Analysis",
                                    command=self.open_input_window, width=25)
        self.start_button.grid(row=0, column=0, padx=10, pady=5)

        # Strategy Builder
        self.strategy_builder_button = ttk.Button(button_frame, text="📐 Strategy Builder",
                                                command=self.launch_strategy_builder, width=25)
        self.strategy_builder_button.grid(row=0, column=1, padx=10, pady=5)

        # ── Strategy Tester *before* dark‑mode toggle
        self.strategy_tester_button = ttk.Button(button_frame, text="🧪 Strategy Tester",
                                                command=self.launch_strategy_tester, width=25)
        self.strategy_tester_button.grid(row=0, column=2, padx=10, pady=5)

        # 🌙 Dark‑mode toggle --------------------------------------------------
        self.is_dark_mode_var = tk.BooleanVar(value=(self.current_theme == 'dark'))
        self.toggle_theme_button = ttk.Checkbutton(
            button_frame,
            text="🌙 Dark Mode",
            command=self.toggle_theme,
            variable=self.is_dark_mode_var,
            style="Theme.TCheckbutton"
        )
        self.toggle_theme_button.grid(row=0, column=3, padx=10, pady=5)




        # Frame to hold buttons for displaying results
        self.results_buttons_frame = ttk.Frame(self.main_frame, style="TFrame")
        self.results_buttons_frame.grid(row=2, column=0, pady=10, sticky="nsew")
        # Configure grid inside results frame
        self.results_buttons_frame.columnconfigure(0, weight=1)
        self.results_buttons_frame.columnconfigure(1, weight=1)

        self.status_label = ttk.Label(self.main_frame, text="Ready.", style="Status.TLabel", anchor="center")
        self.status_label.grid(row=3, column=0, pady=10, sticky="ew")

        # --- State Variables ---
        self.input_data = {} # To store results from analysis
        self.is_loading = False # Flag for loading animation
        self.animation_chars = ['|', '/', '-', '\\'] # Animation characters
        self.animation_step = 0

        
        # expose our theming helper on the root for children to call
        self.root.apply_theme_to_window = self.apply_theme_to_window

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
        if not self.is_loading: # Stop animation if flag is false
            return

        char = self.animation_chars[self.animation_step % len(self.animation_chars)]
        self.set_status(f"Running analysis {char}", "orange")
        self.animation_step += 1
        # Schedule the next animation frame
        self.root.after(150, self.animate_loading) # Update ~6 times per second


    def clear_results_buttons(self):
        """Removes old result buttons."""
        for widget in self.results_buttons_frame.winfo_children():
            widget.destroy()

    def _toggle_fullscreen_input(self, window):
            is_full = window.attributes('-fullscreen')
            window.attributes('-fullscreen', not is_full)
            window.bind("<Escape>", lambda e: self._toggle_fullscreen_input(window))


    def launch_strategy_tester(self):
        # import here to avoid circular import
        from strategy_tester import StrategyTesterWindow
        tester = StrategyTesterWindow(self.root, self.current_theme)
        self.child_windows.append(tester.win)
        self.apply_theme_to_window(tester.win)





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

        self.clear_results_buttons()
        self.set_status("")

        input_win = tk.Toplevel(self.root)
        input_win.title("Input Parameters")
        input_win.geometry("760x900")
        input_win.transient(self.root)
        input_win.grab_set()

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

            # --- Start Loading Animation ---
            self.is_loading = True
            self.animation_step = 0
            self.animate_loading()
            # --- ----------------------- ---

            # Start analysis in a separate thread
            analysis_thread = threading.Thread(target=self.run_analysis_thread, args=(input_values,), daemon=True)
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
            self.input_data['surface_data'] = generate_option_surface_data(
                inputs['S0'], inputs['strike'], T, inputs['r'], inputs['sigma'],
                inputs['option_type'], low_pct_factor=0.5, high_pct_factor=2.0
            )

            # 7. Done → schedule UI update
            self.root.after(0, self.analysis_complete)

        except Exception as e:
            self.root.after(0, lambda err=e: self.analysis_failed(err))


    def analysis_complete(self):
        """Updates GUI after successful analysis."""
        self.is_loading = False # Stop animation flag
        time.sleep(0.1) # Small delay to ensure last animation frame clears
        self.set_status("Analysis complete. View results below.", color="green")
        # self.display_results_summary_console() # Optionally print summary to console
        self.create_results_buttons()

    # ******** FIX: Moved analysis_failed inside the class ********
    def analysis_failed(self, error):
        """Handles errors occurring during the analysis thread."""
        self.is_loading = False
        # Short delay might prevent status update race condition if analysis fails instantly
        time.sleep(0.1)
        self.set_status("Analysis failed!", color="red")
        self.clear_results_buttons()

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


    def create_results_buttons(self):
        """Creates buttons to display plots and results."""
        self.clear_results_buttons() # Ensure frame is empty

        # Button configurations: (Text, command)
        buttons_config = [
            ("Show Summary Info", self.show_summary_popup),
            ("Show Simulation Paths", self.show_simulation_plot),
            ("Show Trigger Distribution", self.show_distribution_plot),
            ("Show Profit Heatmap ($/%)", self.show_heatmap_plot),
            ("Show 3D Value Surface", self.show_3d_surface_plot),
            ("📉 Analyze Greeks", self.show_greek_analysis),
            ("📈 View Stock Chart", self.show_stock_chart_window),
            ("Explain my position", self.show_llm_explanation)
        ]

        # Arrange buttons in a grid within the results frame
        num_cols = 2
        for i, (text, command) in enumerate(buttons_config):
            button = ttk.Button(self.results_buttons_frame, text=text, command=command)
            button.grid(row=i // num_cols, column=i % num_cols, padx=5, pady=5, sticky="ew")

        # Return to Main Menu button
        return_btn = ttk.Button(self.results_buttons_frame, text="⬅ Return to Main Menu", command=self.clear_results_buttons)
        return_btn.grid(row=(len(buttons_config) // 2) + 1, column=0, columnspan=2, pady=(15, 0), sticky="ew")

        # Add a return to main menu button
        return_btn = ttk.Button(self.results_buttons_frame, text="⬅ Return to Main Menu", command=self.clear_results_buttons)
        return_btn.grid(row=(len(buttons_config) // 2) + 1, column=0, columnspan=2, pady=(15, 0), sticky="ew")



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

    def _launch_plot_window(self, plot_function, *args, title="Plot", **kwargs):
        """Helper to create a Toplevel window and run a plotting function safely."""
        if not self.input_data:
             messagebox.showwarning("No Data", "Run an analysis first.", parent=self.root)
             return
        if self.is_loading:
             messagebox.showwarning("Busy", "Analysis is in progress. Cannot show plot yet.", parent=self.root)
             return

        plot_win = None # Initialize plot_win to None
        try:
            plot_win = tk.Toplevel(self.root)
            plot_win.title(title)
            plot_win.geometry("850x650") # Default size for plot windows
            plot_win.transient(self.root) # Keep on top

        
            self.apply_theme_to_window(plot_win) # Apply theme to the new window
            plot_win.grab_set()

            # Add a frame for the plot content
            plot_frame = ttk.Frame(plot_win, padding="5 5 5 5")
            plot_frame.pack(expand=True, fill=tk.BOTH)

            # Add a close button to the plot window
            close_button = ttk.Button(plot_frame, text="Close Plot", command=plot_win.destroy)
            close_button.pack(side=tk.BOTTOM, pady=(5,0)) # Pack at bottom

            # Run the plot function, passing the frame as the parent
            # Plotting should happen in the main thread as it interacts with Tkinter canvas
            plot_function(plot_frame, *args, **kwargs)


        except Exception as e:
            print(f"Plotting Error Traceback ({title}):\n{traceback.format_exc()}")
            # Ensure window is closed if plotting fails mid-way
            try:
                if plot_win and plot_win.winfo_exists():
                    plot_win.destroy()
            except tk.TclError: pass # Ignore errors during cleanup if window already gone

            messagebox.showerror("Plotting Error", f"Could not generate plot '{title}':\n{e}", parent=self.root)
            self.set_status(f"Error plotting {title}", "red")


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
                                 title="Trigger Price Distribution",
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


    def show_3d_surface_plot(self):
        if not self.input_data or 'surface_data' not in self.input_data or not self.input_data['surface_data']:
             messagebox.showwarning("Missing Data", "Surface data is not available. Please run analysis.", parent=self.root)
             return
        self.set_status("Generating 3D Surface plot...")
        # Unpack surface data
        try:
            p_grid, t_grid, v_grid = self.input_data['surface_data']
            self._launch_plot_window(plot_option_surface_3d,
                                    p_grid, t_grid, v_grid,
                                    self.input_data['option_type'], self.input_data['strike'],
                                    title="3D Option Value Surface", 
                                    educational_mode=self.input_data.get('educational_mode', False),
                                     dark_mode=(self.current_theme == 'dark'))
        except Exception as e: # Catch potential errors during unpacking or plotting call
             messagebox.showerror("Plot Error", f"Failed to display 3D surface:\n{e}", parent=self.root)
             print(f"3D Surface display error: {traceback.format_exc()}")
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




