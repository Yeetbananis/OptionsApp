# ===========================
# Standard Library Imports
# ===========================
import re
import traceback

# ===========================
# GUI Framework Imports
# ===========================
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

# ===========================
# Scientific & Visualization Imports
# ===========================
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from scipy.stats import norm

# ===========================
# Local Module Imports
# ===========================
from ui.recommendation_dialog import RecommendationInputDialog, RecommendationResultsDialog
from core.engine.strategy_recommender import StrategyRecommender

# Constants for plot clarity
PLOT_PRICE_RANGE_FACTOR = 0.3 # Plot S0 +/- 30% initially
PLOT_POINTS = 500           # Number of points for the P/L curve
MC_DEFAULT_PATHS = 5000     # Default paths for MC sim
MC_DEFAULT_VOL = 0.20       # Default simulation vol
MC_DEFAULT_RATE = 0.05      # Default simulation rate
MC_DEFAULT_DAYS = 30        # Default simulation expiry

class StrategyBuilderWindow(tk.Toplevel):
     # --- DEFINITIVE FIX: ADD THIS LINE ---
    # Define the class variable that acts as the global lock.
    # It must be here, outside of any method.
    _is_open = False
    # --- END FIX ---
    def __init__(self, parent, app_controller, idea_data: dict | None = None):
        print("DEBUG: 1. Attempting to create StrategyBuilderWindow...")

        print("DEBUG: 1. Attempting to create StrategyBuilderWindow...")

        # This check will now work because the variable exists.
        if StrategyBuilderWindow._is_open:
            print("DEBUG: ERROR! An instance is already open. Aborting creation.")
            messagebox.showerror("Window Already Open",
                                 "The Strategy Builder is already open or closing.\n"
                                 "Please close the existing window and try again.",
                                 parent=parent)
            self.after(0, self.destroy)
            return # Stop initialization

        # If the lock is free, acquire it and proceed.
        StrategyBuilderWindow._is_open = True
        print("DEBUG: 2. Lock acquired. Initializing new StrategyBuilderWindow.")

        super().__init__(parent)
        self.parent = parent
        self.app_controller = app_controller # Store the main app instance
        self.current_theme = self.app_controller.current_theme

        self.title("Multi-Option Strategy Builder")
        self.geometry("1100x850") # Wider and taller for more features
        self.transient(parent)
        self.grab_set()


 
         # apply the central theme via the parent
        if hasattr(parent, 'apply_theme_to_window'):
            parent.apply_theme_to_window(self)

        # --- Data Structures ---
        self.legs = [] # List to store leg dictionaries
        self.underlying_price = tk.DoubleVar(value=100.0)
        self.mc_sim_volatility = tk.DoubleVar(value=MC_DEFAULT_VOL)
        self.mc_sim_rate = tk.DoubleVar(value=MC_DEFAULT_RATE)
        self.mc_sim_days = tk.IntVar(value=MC_DEFAULT_DAYS)
        self.mc_sim_paths = tk.IntVar(value=MC_DEFAULT_PATHS)

        self.strategy_results = {
            'net_premium': 0.0,
            'max_profit': None,
            'max_loss': None,
            'break_evens': [],
            'pop': None, # Probability of Profit
            'mc_pnl_results': None # Store MC P&L outcomes
        }
        self.plot_view_mode = tk.StringVar(value="pnl") # 'pnl' or 'mc'

        self.what_if_scenarios = {
                'S_shift': 0.0,
                'vol_shift': 0.0,
                'rate_shift': 0.0,
                'days_passed': 0
            }


        # --- Matplotlib Setup ---
        self._setup_plot_area() # Creates fig, ax, canvas but doesn't plot yet

        # --- UI Setup ---
        self._setup_ui()

        self.bind("<Configure>", self._enforce_fixed_heights)

        # --- Plotting Elements ---
        self.pnl_line = None # Handle for the P&L line object

        # --- Initial Plot ---
        self._update_plot() # Draw initial empty/default plot

        # --- Connect Events ---
        self.fig.canvas.mpl_connect("motion_notify_event", self._on_hover)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if idea_data:
            self._prefill_from_idea(idea_data)

    def _setup_plot_area(self):
        """Initializes the Matplotlib figure and canvas area."""
        # Determine plot colors based on theme
        bg_color = ttk.Style().lookup('TFrame', 'background')
        fg_color = ttk.Style().lookup('TLabel', 'foreground')
        self.plot_colors = {'bg': bg_color, 'fg': fg_color, 'line': fg_color,
                            'profit': 'green', 'loss': 'red', 'zero_line': ':',
                            'annotation_bg': 'white', 'annotation_fg': 'black',
                            'mc_hist': 'skyblue'}

        self.fig, self.ax = plt.subplots(constrained_layout=True, facecolor=self.plot_colors['bg'])
        self.ax.set_facecolor(self.plot_colors['bg'])
        self.ax.tick_params(axis='x', colors=self.plot_colors['fg'])
        self.ax.tick_params(axis='y', colors=self.plot_colors['fg'])
        self.ax.spines['bottom'].set_color(self.plot_colors['fg'])
        self.ax.spines['top'].set_color(self.plot_colors['fg'])
        self.ax.spines['left'].set_color(self.plot_colors['fg'])
        self.ax.spines['right'].set_color(self.plot_colors['fg'])
        self.ax.yaxis.label.set_color(self.plot_colors['fg'])
        self.ax.xaxis.label.set_color(self.plot_colors['fg'])
        self.ax.title.set_color(self.plot_colors['fg'])

        self.hover_annotation = self._setup_hover_annotation()


    def _setup_hover_annotation(self):
        """Creates the hover annotation object, initially hidden."""
        annot = self.ax.annotate("", xy=(0,0), xytext=(10,10), textcoords="offset points",
                                 bbox=dict(boxstyle="round,pad=0.4", fc=self.plot_colors['annotation_bg'], alpha=0.8),
                                 arrowprops=dict(arrowstyle="->", connectionstyle="arc3,rad=0.1"),
                                 fontsize=9, color=self.plot_colors['annotation_fg'])
        annot.set_visible(False)
        return annot
    
    def _enforce_fixed_heights(self, event=None):
        try:
            if hasattr(self, 'canvas_widget') and self.canvas_widget.winfo_exists():
                desired_height = int(self.winfo_height() * 0.6)
                self.canvas_widget.configure(height=desired_height)
                self.canvas.draw_idle()
        except:
            pass

    # In strategy_builder.py

    def _prefill_from_idea(self, idea_data: dict):
        """
        Takes data from an Idea object and populates the strategy builder's fields.
        """
        self._set_status("Loaded from Idea Suite.", "blue")

        # Extract data from the idea dictionary
        symbol = idea_data.get('symbol')
        strategy_info = idea_data.get('suggested_strategy', {})
        strategy_type = strategy_info.get('type', 'Custom').replace('_', ' ').title()

        # ⚠️ We no longer pre-fill S₀ or DTE—user will enter those manually.

        # --- REPLACEMENT START ---
        # The previous logic was too complex and failed on simple names like "Long Call".
        # This new logic directly formats the strategy name into the expected method name format.
        # e.g., "Long Call" -> "_apply_long_call_template"
        # e.g., "Iron Condor" -> "_apply_iron_condor_template"
        method_name_base = strategy_type.lower().replace(' ', '_')
        method_name = f"_apply_{method_name_base}_template"
        # --- REPLACEMENT END ---
        
        tgt = getattr(self, method_name, None)
        if callable(tgt):
            # Invoke the template's default settings
            tgt()

            # --- DEFINITIVE FIX, PART 1 ---
            # Do NOT show a blocking messagebox here. Instead, schedule it to
            # appear after the window is fully initialized and drawn.
            # This prevents the application from freezing.
            def show_delayed_popup():
                msg = (
                    f"Template “{strategy_type}” applied with default strikes/premiums.\n\n"
                    "Please now enter the idea’s specific:\n"
                    f" • Current Price (S₀): {idea_data.get('metrics', {}).get('spot_price', '…')}\n"
                    f" • Days to Expiration (DTE): {idea_data.get('metrics', {}).get('dte', '…')}\n\n"
                    "Then adjust strikes & premiums as needed."
                )
                messagebox.showinfo("Enter Idea Parameters", msg, parent=self)

            self.after(100, show_delayed_popup)
            # --- END FIX ---
        else:
            messagebox.showwarning(
                "Template Not Found",
                f"No builder-template for “{strategy_type}”.\n"
                "Select one manually from the Templates tab.",
                parent=self
            )


    def _on_close(self):
        """
        Handles the window close event (title bar 'X').
        Instead of destroying the window, it now just hides it to be reused later.
        """
        # Release the grab so other windows can be used
        self.grab_release()
        # Hide the window
        self.withdraw()
        
    def _setup_ui(self):
        """Creates the main UI layout."""
        # Main Frame splits Left (Controls) and Right (Plot)
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.columnconfigure(0, weight=2) # Controls area slightly narrower
        main_frame.columnconfigure(1, weight=3) # Plot area wider
        main_frame.rowconfigure(0, weight=1)

        topbar = ttk.Frame(self, padding=(0, 5))
        topbar.place(relx=1.0, y=5, anchor="ne")  # Position inside UI

        # Fullscreen toggle button with ⛶
        fullscreen_btn = ttk.Button(topbar, text="⛶", width=3, command=self._toggle_fullscreen)
        fullscreen_btn.pack(side=tk.RIGHT)

        # Close window button with ✖ (to the left of fullscreen)
        close_btn = ttk.Button(topbar, text="✖", width=3, command=self._close_window)
        close_btn.pack(side=tk.RIGHT, padx=(0, 5))


        # --- Left Panel (Controls) ---
        left_panel = ttk.Frame(main_frame, padding="5")
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        left_panel.rowconfigure(0, weight=1) # Allow notebook to expand
        left_panel.columnconfigure(0, weight=1)

        # Notebook for Inputs/Templates
        controls_notebook = ttk.Notebook(left_panel)
        controls_notebook.grid(row=0, column=0, sticky="nsew", pady=(0, 10))

        # --- Tab 1: Build Strategy ---
        build_tab = ttk.Frame(controls_notebook, padding="10")
        controls_notebook.add(build_tab, text="Build Strategy")
        build_tab.columnconfigure(0, weight=1)
        build_tab.rowconfigure(2, weight=1) # Treeview expands

        # Underlying Input Frame
        underlying_frame = ttk.LabelFrame(build_tab, text="Underlying Asset", padding="10")
        underlying_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        underlying_frame.columnconfigure(1, weight=1)
        ttk.Label(underlying_frame, text="Current Price (S0):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.s0_entry = ttk.Entry(underlying_frame, textvariable=self.underlying_price, width=10)
        self.s0_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')

        # Add Leg Frame
        leg_input_frame = self._create_leg_input_frame(build_tab) # Use helper
        leg_input_frame.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        # Legs List Frame
        legs_list_frame = self._create_legs_list_frame(build_tab) # Use helper
        legs_list_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))

        # Update Button (for Expiration P&L plot)
        update_button = ttk.Button(build_tab, text="Update Expiration P&L Plot", command=self._update_strategy_and_pnl_plot)
        update_button.grid(row=3, column=0, pady=(10, 0), sticky='ew')

        # --- Tab 2: Strategy Templates ---
        templates_tab = ttk.Frame(controls_notebook, padding="10")
        controls_notebook.add(templates_tab, text="Templates")
        templates_tab.columnconfigure(0, weight=1)
        # Add template buttons
        self._create_template_buttons(templates_tab)

        # --- Right Panel (Plot & Results/Simulation) ---
        right_panel = ttk.Frame(main_frame, padding="5")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_panel.rowconfigure(1, weight=1) # Plot area expands
        right_panel.columnconfigure(0, weight=1)

        # Plot View Toggle Frame
        plot_toggle_frame = ttk.Frame(right_panel)
        plot_toggle_frame.grid(row=0, column=0, sticky="ew", pady=(0,5))
        ttk.Label(plot_toggle_frame, text="Plot View:").pack(side=tk.LEFT, padx=(0, 5))
        pnl_radio = ttk.Radiobutton(plot_toggle_frame, text="Expiration P&L", variable=self.plot_view_mode, value="pnl", command=self._update_plot)
        pnl_radio.pack(side=tk.LEFT, padx=5)
        mc_radio = ttk.Radiobutton(plot_toggle_frame, text="MC Simulation", variable=self.plot_view_mode, value="mc", command=self._update_plot)
        mc_radio.pack(side=tk.LEFT, padx=5)
        risk_radio = ttk.Radiobutton(plot_toggle_frame, text="Risk Curves", variable=self.plot_view_mode, value="risk", command=self._update_plot)
        risk_radio.pack(side=tk.LEFT, padx=5)



        plot_frame = ttk.Frame(right_panel)
        plot_frame.grid(row=1, column=0, sticky="nsew")

        # Ensure canvas takes 60% of window height
        self.update_idletasks()
        desired_height = int(self.winfo_height() * 0.6)

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")
        self.canvas_widget.configure(height=desired_height)

        plot_frame.rowconfigure(0, weight=1)
        plot_frame.columnconfigure(0, weight=1)

        # Add Matplotlib toolbar
        toolbar_frame = ttk.Frame(plot_frame)
        toolbar_frame.grid(row=1, column=0, sticky="ew")
        toolbar = NavigationToolbar2Tk(self.canvas, toolbar_frame)
        toolbar.update()


        # Notebook for Results/Simulation Controls
        results_notebook = ttk.Notebook(right_panel)
        results_notebook.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        # --- Results Tab ---
        results_tab = ttk.Frame(results_notebook, padding="10")
        results_notebook.add(results_tab, text="Strategy Summary")
        self._create_results_display(results_tab)

        # --- Simulation Tab ---
        simulation_tab = ttk.Frame(results_notebook, padding="10")
        results_notebook.add(simulation_tab, text="Monte Carlo Simulation")
        self._create_simulation_controls(simulation_tab)

        # Status Label
        self.status_label = ttk.Label(self, text="Ready. Add legs or use templates.", padding=5, anchor='w')
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

        # --- What-If Scenarios Tab ---
        whatif_tab = ttk.Frame(results_notebook, padding="10")
        results_notebook.add(whatif_tab, text="📚 What-If Scenarios")
        self._create_whatif_controls(whatif_tab)

        # --- Risk Curves Tab ---
        self.risk_curve_tab = ttk.Frame(results_notebook)
        results_notebook.add(self.risk_curve_tab, text="Risk Curves (Greeks)")


        input_frame = ttk.Frame(self.risk_curve_tab)
        input_frame.pack(fill='x', padx=10, pady=10)

        # Inside _setup_ui, replace the OptionMenu line in the Risk Curves tab setup
        self.curve_variable = tk.StringVar(value="Underlying Price")
        ttk.Label(input_frame, text="X-Axis:").grid(row=0, column=0, padx=5, sticky='w')
        ttk.OptionMenu(input_frame, self.curve_variable, "Underlying Price", "Underlying Price", "Implied Volatility", "Days Passed").grid(row=0, column=1, padx=5)

        ttk.Label(input_frame, text="Lower Bound (% or Days):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.lower_bound_entry = ttk.Entry(input_frame, width=10)
        self.lower_bound_entry.insert(0, "-50")
        self.lower_bound_entry.grid(row=1, column=1)

        ttk.Label(input_frame, text="Upper Bound (% or Days):").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.upper_bound_entry = ttk.Entry(input_frame, width=10)
        self.upper_bound_entry.insert(0, "100")
        self.upper_bound_entry.grid(row=2, column=1)

        self.show_percent_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(input_frame, text="Show % Return", variable=self.show_percent_var).grid(row=3, column=0, columnspan=2, sticky='w', pady=5)

        ttk.Button(input_frame, text="Generate Graph", command=self._generate_greek_risk_curve).grid(row=4, column=0, columnspan=2, pady=10)

        # Optional: Export Buttons
        export_frame = ttk.Frame(self.risk_curve_tab)
        export_frame.pack(pady=5)
        ttk.Button(export_frame, text="Save as Image", command=lambda: self._export_risk_curve("png")).pack(side='left', padx=5)
        ttk.Button(export_frame, text="Export PDF", command=lambda: self._export_risk_curve("pdf")).pack(side='left', padx=5)

        # Persistent click-based insight box
        self.greek_click_label = ttk.Label(self.risk_curve_tab, text="Click the graph to inspect ΔV at any point.",
                                        wraplength=400, justify="left", padding=5)
        self.greek_click_label.pack(fill='x', padx=10, pady=(0, 10))





    # --- Helper methods for creating UI sections ---

    def _create_leg_input_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Add Option Leg", padding="10")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)


        ttk.Label(frame, text="Action:").grid(row=0, column=0, padx=5, pady=3, sticky='w')
        self.leg_action_var = tk.StringVar(value='Buy')
        action_combo = ttk.Combobox(frame, textvariable=self.leg_action_var,
                                    values=['Buy', 'Sell'], state="readonly", width=6)
        action_combo.grid(row=0, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Type:").grid(row=0, column=2, padx=5, pady=3, sticky='w')
        self.leg_type_var = tk.StringVar(value='Call')
        type_combo = ttk.Combobox(frame, textvariable=self.leg_type_var,
                                values=['Call', 'Put'], state="readonly", width=6)
        type_combo.grid(row=0, column=3, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Strike:").grid(row=1, column=0, padx=5, pady=3, sticky='w')
        self.leg_strike_var = tk.DoubleVar(value=100.0)
        strike_entry = ttk.Entry(frame, textvariable=self.leg_strike_var, width=8)
        strike_entry.grid(row=1, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Premium:").grid(row=1, column=2, padx=5, pady=3, sticky='w')
        self.leg_premium_var = tk.DoubleVar(value=1.50)
        premium_entry = ttk.Entry(frame, textvariable=self.leg_premium_var, width=8)
        premium_entry.grid(row=1, column=3, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Contracts (100 shares each):").grid(row=2, column=0, padx=5, pady=3, sticky='w')
        self.leg_quantity_var = tk.IntVar(value=1)
        quantity_entry = ttk.Entry(frame, textvariable=self.leg_quantity_var, width=8)
        quantity_entry.grid(row=2, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Capital ($):").grid(row=2, column=2, padx=5, pady=3, sticky='w')
        self.leg_capital_var = tk.DoubleVar(value=0.0)
        capital_entry = ttk.Entry(frame, textvariable=self.leg_capital_var, width=8)  
        capital_entry.grid(row=2, column=3, padx=5, pady=3, sticky='ew')          

        ttk.Label(frame, text="Delta:").grid(row=3, column=0, padx=5, pady=3, sticky='w')
        self.leg_delta_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.leg_delta_var, width=8).grid(row=3, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Gamma:").grid(row=3, column=2, padx=5, pady=3, sticky='w')
        self.leg_gamma_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.leg_gamma_var, width=8).grid(row=3, column=3, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Theta:").grid(row=4, column=0, padx=5, pady=3, sticky='w')
        self.leg_theta_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.leg_theta_var, width=8).grid(row=4, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Vega:").grid(row=4, column=2, padx=5, pady=3, sticky='w')
        self.leg_vega_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.leg_vega_var, width=8).grid(row=4, column=3, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Rho:").grid(row=5, column=0, padx=5, pady=3, sticky='w')
        self.leg_rho_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.leg_rho_var, width=8).grid(row=5, column=1, padx=5, pady=3, sticky='ew')

        # Move Add Button down
        add_leg_button = ttk.Button(frame, text="Add Leg", command=self._add_leg)
        add_leg_button.grid(row=6, column=3, padx=(40, 5), pady=10, sticky='e')

        return frame

    def _create_legs_list_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="Current Strategy Legs", padding="10")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.legs_tree = ttk.Treeview(frame, columns=("Action", "Qty", "Type", "Strike", "Premium", "Cost/Credit",
                                              "Delta", "Gamma", "Theta", "Vega", "Rho"),
                              show="headings", height=6)

        columns = [
            ("Action", 60), ("Qty", 50), ("Type", 60), ("Strike", 70), ("Premium", 70), ("Cost/Credit", 100),
            ("Delta", 60), ("Gamma", 60), ("Theta", 60), ("Vega", 60), ("Rho", 60)
        ]
        for name, width in columns:
            self.legs_tree.heading(name, text=name)
            self.legs_tree.column(name, width=width, anchor='center')

        self.legs_tree.grid(row=0, column=0, sticky="nsew")
        frame.grid_propagate(False)  # Prevent the frame from resizing based on content
        frame.config(height=200)     # Set a fixed height (adjust if needed)


        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.legs_tree.yview)
        self.legs_tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns')

        x_scrollbar = ttk.Scrollbar(frame, orient="horizontal", command=self.legs_tree.xview)
        self.legs_tree.configure(xscrollcommand=x_scrollbar.set)
        x_scrollbar.grid(row=1, column=0, sticky='ew', columnspan=2)

        # Set grid sticky correctly to let x-scrollbar work with treeview sizing
        self.legs_tree.grid(row=0, column=0, columnspan=2, sticky="nsew")

        edit_leg_button = ttk.Button(frame, text="Edit Selected Leg", command=self._edit_leg)
        edit_leg_button.grid(row=1, column=0, columnspan=2, pady=(5, 0), sticky='ew')

        remove_leg_button = ttk.Button(frame, text="Remove Selected Leg", command=self._remove_leg)
        remove_leg_button.grid(row=2, column=0, columnspan=2, pady=(5, 0), sticky='ew')

        clear_all_button = ttk.Button(frame, text="Clear All Legs", command=self._clear_all_legs)
        clear_all_button.grid(row=3, column=0, columnspan=2, pady=(5, 0), sticky='ew')

        
        return frame
    
    def _create_whatif_controls(self, parent):
        # --- SCROLLABLE CONTAINER SETUP ---
        container = ttk.Frame(parent)
        container.pack(fill='both', expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # FIX HEIGHT TO 50% OF WINDOW
        self.after(100, lambda: canvas.configure(height=self.winfo_height() // 2))

        # --- Actual What-If Controls ---
        frame = ttk.LabelFrame(scrollable_frame, text="Manual Market Shift Entry", padding=10)
        frame.pack(fill='both', expand=True)

        ttk.Label(frame, text="Underlying % Change:").pack(anchor="w")
        s_entry = ttk.Entry(frame)
        s_entry.insert(0, "0.0")
        s_entry.pack(fill="x", pady=2)

        ttk.Label(frame, text="IV Change (%):").pack(anchor="w")
        v_entry = ttk.Entry(frame)
        v_entry.insert(0, "0.0")
        v_entry.pack(fill="x", pady=2)

        ttk.Label(frame, text="Interest Rate Change (%):").pack(anchor="w")
        r_entry = ttk.Entry(frame)
        r_entry.insert(0, "0.0")
        r_entry.pack(fill="x", pady=2)

        ttk.Label(frame, text="Days Passed:").pack(anchor="w")
        d_entry = ttk.Entry(frame)
        d_entry.insert(0, "0")
        d_entry.pack(fill="x", pady=2)

        # --- Apply Shift Logic ---
        def apply_shift(s_shift=0.0, v_shift=0.0, r_shift=0.0, days=0):
            self.what_if_scenarios['S_shift'] = s_shift
            self.what_if_scenarios['vol_shift'] = v_shift
            self.what_if_scenarios['rate_shift'] = r_shift
            self.what_if_scenarios['days_passed'] = days

        def manual_scenario():
            try:
                s_shift = float(s_entry.get()) / 100.0
                v_shift = float(v_entry.get()) / 100.0
                r_shift = float(r_entry.get()) / 100.0
                days = int(d_entry.get())
                label = "Manual Scenario"

                self._apply_scenario(label, lambda: apply_shift(s_shift, v_shift, r_shift, days))
            except ValueError:
                messagebox.showerror("Input Error", "Please enter valid numeric values.", parent=self)

        ttk.Button(frame, text="Apply Manual Scenario", command=manual_scenario).pack(fill="x", pady=(10, 4))
        ttk.Button(frame, text="♻️ Reset All", command=lambda: self._apply_scenario("Reset to base case", lambda: apply_shift(0, 0, 0, 0))).pack(fill='x', pady=(4, 0))

        self.scenario_summary_label = ttk.Label(frame, text="", justify="left", wraplength=360)
        self.scenario_summary_label.pack(fill='x', pady=(10, 0))

    def _generate_greek_risk_curve(self):
        variable = self.curve_variable.get()
        try:
            lower = float(self.lower_bound_entry.get())
            upper = float(self.upper_bound_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "Bounds must be valid numbers.", parent=self)
            return

        if variable == "Days Passed":
            if lower < 0 or upper < 0:
                messagebox.showerror("Input Error", "Days passed must be non-negative.", parent=self)
                return
            if lower >= upper:
                messagebox.showerror("Input Error", "Lower bound must be less than upper bound.", parent=self)
                return
            upper = min(upper, self.mc_sim_days.get())
        else:
            if lower <= -100 or upper >= 500:
                messagebox.showerror("Input Error", "Price/IV bounds too extreme (suggest -100% to +200%).", parent=self)
                return
            if lower >= upper:
                messagebox.showerror("Input Error", "Lower bound must be less than upper bound.", parent=self)
                return

        self._plot_greek_risk_curve(variable, lower, upper)
        # Navigate to Risk Curve tab
        results_notebook = self.risk_curve_tab.master
        results_notebook.select(self.risk_curve_tab)


    def _calculate_second_order_greeks(self, S, K, T, r, sigma, option_type='call'):
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        nd1 = norm.pdf(d1)
        vomma = nd1 * np.sqrt(T) * d1 * d2 / sigma
        color = -nd1 * (2 * r * T - d2 * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T))
        return vomma, color
    
    def _get_atm_strike(self):
        if not self.legs:
            return round(self.underlying_price.get() / 5) * 5
        strikes = [leg['strike'] for leg in self.legs]
        return np.median(strikes)

    
    def _plot_greek_risk_curve(self, variable, lower, upper):
        S0 = self.underlying_price.get()
        T0 = self.mc_sim_days.get() / 365  # Initial time to expiry in years
        sigma0 = self.mc_sim_volatility.get()
        r = self.mc_sim_rate.get()
        K = self._get_atm_strike()

        contracts = sum(leg['quantity'] for leg in self.legs)
        if contracts <= 0:
            self._set_status("Cannot calculate: No option contracts in strategy.", "red")
            return

        # Use total Greeks from the strategy
        delta = self.total_greek_values.get("delta", 0)  # Unscaled, per contract
        gamma = self.total_greek_values.get("gamma", 0)  # Unscaled, per contract
        theta = self.total_greek_values.get("theta", 0)  # Per day, per contract
        vega = self.total_greek_values.get("vega", 0)    # Per contract

        if variable == "Underlying Price":
            x = np.linspace(S0 * (1 + lower / 100), S0 * (1 + upper / 100), 100)
            dx = x - S0
            # P&L change using delta and gamma (first-order sufficient for small changes)
            y = delta * dx  # Delta in $ per $ per contract, dx in $, y in $
            xlabel = "Underlying Price ($)"
            if abs(lower) > 50 or abs(upper) > 100:
                self._set_status("⚠️ Greek ΔV estimate only accurate near current price. Try -25% to +25%.", "orange")

        elif variable == "Implied Volatility":
            x = np.linspace(sigma0 * (1 + lower / 100), sigma0 * (1 + upper / 100), 100)
            dv = x - sigma0  # Change in volatility
            y = vega * dv    # Vega in $ per 1% IV, dv in decimal, y in $
            xlabel = "Implied Volatility"

        elif variable == "Days Passed":  # Renamed from "Time to Expiry"
            x = np.linspace(lower, upper, 100)  # x in days passed
            x = np.clip(x, 0, self.mc_sim_days.get())  # Prevent exceeding expiry
            y = theta * x  # Theta in $ per day, x in days, y in $
            xlabel = "Days Passed"

        else:
            return

        if self.show_percent_var.get():
            cost_basis = self.get_position_cost()
            if cost_basis != 0:
                y = (y / abs(cost_basis)) * 100

        self._draw_greek_risk_curve(x, y, xlabel)

    def _draw_greek_risk_curve(self, x, y, xlabel):
            self.plot_view_mode.set("risk")
            self.ax.clear()
            self.hover_annotation.set_visible(False)

            self.ax.plot(x, y, label="Estimated ΔV", color='blue')
            self.ax.axhline(0, color='gray', linestyle='--')
            self.ax.axvline(x[len(x)//2], color='black', linestyle=':')

            self.ax.fill_between(x, y, 0, where=(y > 0), color='green', alpha=0.2)
            self.ax.fill_between(x, y, 0, where=(y < 0), color='red', alpha=0.2)

            self.ax.set_xlabel(xlabel, color=self.plot_colors['fg'])
            self.ax.set_ylabel("P&L Change (% if checked)" if self.show_percent_var.get() else "P&L Change ($)", color=self.plot_colors['fg'])
            self.ax.set_title("Greek Risk Curve", color=self.plot_colors['fg'])
            self.ax.legend()

            # Update persistent label with max gain/loss
            max_gain = np.max(y)
            max_loss = np.min(y)
            summary = f"Max Gain: {max_gain:.2f}     Max Loss: {max_loss:.2f}"
            if hasattr(self, "greek_click_label"):
                existing = self.greek_click_label.cget("text")
                lines = existing.split("\n")
                if lines and "Max Gain" in lines[-1]:
                    lines[-1] = summary
                else:
                    lines.append(summary)
                self.greek_click_label.config(text="\n".join(lines))


            self.canvas.draw_idle()

            # -- Update persistent value label on click (no popups) --
            def on_click(event):
                if event.inaxes != self.ax:
                    return
                clicked_x = event.xdata
                if clicked_x is None:
                    return
                nearest_idx = (np.abs(x - clicked_x)).argmin()
                value = y[nearest_idx]
                msg = f"At {xlabel} = {x[nearest_idx]:.4f}\nEstimated ΔV = {value:.2f}"
                if hasattr(self, "greek_click_label"):
                    self.greek_click_label.config(text=msg)

            self.fig.canvas.mpl_connect('button_press_event', on_click)


    def _export_risk_curve(self, filetype):
        try:
            if not self.fig or not self.ax.has_data():
                messagebox.showwarning("Nothing to Save", "Generate a risk curve first before exporting.", parent=self)
                return

            filetypes = [(f"{filetype.upper()} files", f"*.{filetype}"), ("All files", "*.*")]
            filename = filedialog.asksaveasfilename(
                title=f"Export Risk Curve as {filetype.upper()}",
                defaultextension=f".{filetype}",
                filetypes=filetypes,
                parent=self
            )

            if not filename:
                return  # User cancelled

            self.fig.savefig(filename, bbox_inches='tight')
            messagebox.showinfo("Export Successful", f"Risk curve successfully saved as {filetype.upper()}:\n{filename}", parent=self)

        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export risk curve:\n{e}", parent=self)



    def _create_template_buttons(self, parent):
        frame = ttk.LabelFrame(parent, text="Apply Template (clears existing legs)", padding="10")
        frame.grid(row=0, column=0, sticky="new")

        templates = {
            "Long Call": self._apply_long_call_template,
            "Long Put": self._apply_long_put_template,
            "Covered Call": self._apply_covered_call_template,
            "Protective Put": self._apply_protective_put_template,
            "Bull Call": self._apply_bull_call_template,
            "Bear Put": self._apply_bear_put_template,
            "Iron Condor": self._apply_iron_condor_template,
            "Straddle": self._apply_straddle_template,
            "Strangle": self._apply_strangle_template,
            "Butterfly": self._apply_butterfly_template,
            "Calendar": self._apply_calendar_template,
             "Diagonal Spread": self._apply_diagonal_spread_template,
            "Ratio Spread": self._apply_ratio_spread_template,
            "Backspread": self._apply_backspread_template,
            "Jade Lizard": self._apply_jade_lizard_template,
            "Iron Butterfly": self._apply_iron_butterfly_template,
            "Broken Butterfly": self._apply_broken_butterfly_template,
            "📡 LLM Strat": self._prompt_llm_for_strategy,
            "💡 Recommend Strat": self._open_recommendation_dialog
        }

        row, col = 0, 0
        max_cols = 2  # You can adjust this based on desired layout
        for name, command in templates.items():
            btn = ttk.Button(frame, text=name, command=command, width=20)
            btn.grid(row=row, column=col, padx=5, pady=5, sticky='ew')
            col += 1
            if col >= max_cols:
                col = 0
                row += 1

        parent.columnconfigure(0, weight=1)
        return frame
    
    def _toggle_fullscreen(self):
            is_full = self.attributes('-fullscreen')
            self.attributes('-fullscreen', not is_full)
            self.bind("<Escape>", lambda e: self._toggle_fullscreen()) # Bind Escape to exit fullscreen
            


    def _clear_all_legs(self):
        if messagebox.askyesno("Confirm", "Clear all legs from the strategy?", parent=self):
            self.legs.clear()
            self._update_legs_display()
            self._update_plot()
            self._set_status("All legs cleared.", "orange")

    def _close_window(self):
        """Handles the custom '✖' close button click."""
        self._on_close() # Call the same hide logic
    
    def _recursive_theme(self, widget, bg, fg):
        try:
            widget.configure(bg=bg)
        except:
            pass
        try:
            widget.configure(fg=fg)
        except:
            pass
        try:
            widget.configure(highlightbackground=bg)
        except:
            pass

        if isinstance(widget, (tk.Frame, ttk.Frame, tk.Toplevel)):
            for child in widget.winfo_children():
                self._recursive_theme(child, bg, fg)




    def _create_results_display(self, parent):
        frame = parent # Use the passed tab frame directly
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text="Net Premium:").grid(row=0, column=0, padx=5, pady=3, sticky='w')
        self.net_premium_label = ttk.Label(frame, text="N/A", width=18, anchor='e', style="Result.TLabel")
        self.net_premium_label.grid(row=0, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Max Profit:").grid(row=0, column=2, padx=5, pady=3, sticky='w')
        self.max_profit_label = ttk.Label(frame, text="N/A", width=18, anchor='e', style="Result.TLabel")
        self.max_profit_label.grid(row=0, column=3, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Max Loss:").grid(row=1, column=0, padx=5, pady=3, sticky='w')
        self.max_loss_label = ttk.Label(frame, text="N/A", width=18, anchor='e', style="Result.TLabel")
        self.max_loss_label.grid(row=1, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Break-evens:").grid(row=1, column=2, padx=5, pady=3, sticky='w')
        self.break_evens_label = ttk.Label(frame, text="N/A", width=18, anchor='w', wraplength=160, style="Result.TLabel")
        self.break_evens_label.grid(row=1, column=3, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Prob. of Profit (MC):").grid(row=2, column=0, padx=5, pady=3, sticky='w')
        self.pop_label = ttk.Label(frame, text="N/A", width=18, anchor='e', style="Result.TLabel")
        self.pop_label.grid(row=2, column=1, padx=5, pady=3, sticky='ew')

        ttk.Label(frame, text="Option Value Change:").grid(row=2, column=2, padx=5, pady=3, sticky='w')
        self.value_change_label = ttk.Label(frame, text="N/A", width=18, anchor='e', style="Result.TLabel")
        self.value_change_label.grid(row=2, column=3, padx=5, pady=3, sticky='ew')

        separator = ttk.Separator(frame, orient="horizontal")
        separator.grid(row=3, column=0, columnspan=4, pady=(10, 5), sticky='ew')

        greeks = ['Delta', 'Gamma', 'Theta', 'Vega', 'Rho']
        self.total_greek_labels = {}

        for i, greek in enumerate(greeks):
            ttk.Label(frame, text=f"Total {greek}:").grid(row=4+i//2, column=(i%2)*2, padx=5, pady=3, sticky='w')
            label = ttk.Label(frame, text="N/A", width=18, anchor='e', style="Result.TLabel")
            label.grid(row=4+i//2, column=(i%2)*2 + 1, padx=5, pady=3, sticky='ew')
            self.total_greek_labels[greek.lower()] = label

        separator = ttk.Separator(frame, orient="horizontal")
        separator.grid(row=9, column=0, columnspan=4, pady=(10, 5), sticky='ew')

        # Greek Risk Table header (now starts below)
        header_row = 10
        ttk.Label(frame, text="Greek").grid(row=header_row, column=0, padx=5, pady=(10, 2), sticky='w')
        ttk.Label(frame, text="Net Exposure").grid(row=header_row, column=1, padx=5, pady=(10, 2), sticky='w')
        ttk.Label(frame, text="Risk Level").grid(row=header_row, column=2, padx=5, pady=(10, 2), sticky='w')

        self.greek_risk_rows = {}  # store labels for live update

        for i, greek in enumerate(greeks):
            greek_key = greek.lower()
            row = header_row + i + 1

            name_label = ttk.Label(frame, text=greek.capitalize())
            exposure_label = ttk.Label(frame, text="N/A", width=12)
            risk_label = ttk.Label(frame, text="N/A", width=18)

            name_label.grid(row=row, column=0, sticky='w', padx=5)
            exposure_label.grid(row=row, column=1, sticky='w', padx=5)
            risk_label.grid(row=row, column=2, sticky='w', padx=5)

            self.greek_risk_rows[greek_key] = {
                "exposure": exposure_label,
                "risk": risk_label
            }



        # Style for result labels (optional, for emphasis)
        style = ttk.Style()
        style.configure("Result.TLabel", font=('Helvetica', 10, 'bold')) # Make results bold
        
        return frame

    def _create_simulation_controls(self, parent):
        frame = parent # Use the passed tab frame directly
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text="Sim Volatility (%):").grid(row=0, column=0, padx=5, pady=4, sticky='w')
        vol_entry = ttk.Entry(frame, textvariable=tk.DoubleVar(value=self.mc_sim_volatility.get()*100), width=8) # Show as %
        vol_entry.grid(row=0, column=1, padx=5, pady=4, sticky='ew')
        vol_entry.bind("<FocusOut>", lambda e: self.mc_sim_volatility.set(float(vol_entry.get()) / 100.0 if float(vol_entry.get()) else MC_DEFAULT_VOL))
        vol_entry.bind("<Return>", lambda e: self.mc_sim_volatility.set(float(vol_entry.get()) / 100.0 if float(vol_entry.get()) else MC_DEFAULT_VOL))


        ttk.Label(frame, text="Risk-Free Rate (%):").grid(row=0, column=2, padx=5, pady=4, sticky='w')
        rate_entry = ttk.Entry(frame, textvariable=tk.DoubleVar(value=self.mc_sim_rate.get()*100), width=8) # Show as %
        rate_entry.grid(row=0, column=3, padx=5, pady=4, sticky='ew')
        rate_entry.bind("<FocusOut>", lambda e: self.mc_sim_rate.set(float(rate_entry.get()) / 100.0 if rate_entry.get() else MC_DEFAULT_RATE))
        rate_entry.bind("<Return>", lambda e: self.mc_sim_rate.set(float(rate_entry.get()) / 100.0 if rate_entry.get() else MC_DEFAULT_RATE))

        ttk.Label(frame, text="Strategy Expiry (Days):").grid(row=1, column=0, padx=5, pady=4, sticky='w')
        days_entry = ttk.Entry(frame, textvariable=self.mc_sim_days, width=8)
        days_entry.grid(row=1, column=1, padx=5, pady=4, sticky='ew')

        ttk.Label(frame, text="Simulation Paths:").grid(row=1, column=2, padx=5, pady=4, sticky='w')
        paths_entry = ttk.Entry(frame, textvariable=self.mc_sim_paths, width=8)
        paths_entry.grid(row=1, column=3, padx=5, pady=4, sticky='ew')
        

        run_sim_button = ttk.Button(frame, text="Run Monte Carlo Simulation", command=self._run_strategy_monte_carlo)
        run_sim_button.grid(row=2, column=0, columnspan=4, pady=(15, 5), sticky='ew')
        return frame

    # --- Core Logic Methods ---

    def _set_status(self, text, color=None):
        # Same as before
        style_name = "Status.TLabel"
        if color:
            style_name = f"{color.capitalize()}.Status.TLabel"
            ttk.Style().configure(style_name, foreground=color, anchor='w') # Anchor left
        try:
            self.status_label.config(text=text, style=style_name)
            self.update_idletasks()
        except tk.TclError:
             print(f"Status update skipped (window closed?): {text}")

    def _validate_leg_inputs(self):
        try:
            strike = self.leg_strike_var.get()
            premium = self.leg_premium_var.get()
            capital = self.leg_capital_var.get()
            quantity = self.leg_quantity_var.get()

            if strike <= 0:
                raise ValueError("Strike must be positive.")
            if premium < 0:
                raise ValueError("Premium cannot be negative.")

            if quantity <= 0 and capital <= 0:
                raise ValueError("Enter contracts or capital.")

            return True
        except (tk.TclError, ValueError) as e:
            messagebox.showerror("Input Error", str(e), parent=self)
            return False


    def _add_leg(self):
        if not self._validate_leg_inputs():
            return

        premium = self.leg_premium_var.get()
        quantity = self.leg_quantity_var.get()
        capital = self.leg_capital_var.get()
        final_quantity = quantity
        if quantity <= 0 and capital > 0:
            contract_cost = 100 * premium
            final_quantity = int(capital // contract_cost)
            if final_quantity <= 0:
                messagebox.showwarning("Insufficient Capital", f"Capital too low for contracts at ${premium:.2f}/contract", parent=self)
                return

        # Parse Greeks
        def parse_greek(val):
            try: return float(val)
            except: return None

        leg = {
            'action': self.leg_action_var.get(),
            'type': self.leg_type_var.get(),
            'strike': self.leg_strike_var.get(),
            'premium': premium,
            'quantity': final_quantity,
            'delta': parse_greek(self.leg_delta_var.get()),
            'gamma': parse_greek(self.leg_gamma_var.get()),
            'theta': parse_greek(self.leg_theta_var.get()),
            'vega': parse_greek(self.leg_vega_var.get()),
            'rho': parse_greek(self.leg_rho_var.get())
        }

        self.legs.append(leg)
        self._update_legs_display()
        self._set_status(f"Added {final_quantity} {leg['action']} {leg['type']}(K={leg['strike']}). Update plot.", "blue")

    def _remove_leg(self):
        # Same as before, triggers plot update
        selected_items = self.legs_tree.selection()
        if not selected_items: return
        indices_to_remove = sorted([self.legs_tree.index(item) for item in selected_items], reverse=True)
        removed_count = 0
        for index in indices_to_remove:
            if 0 <= index < len(self.legs):
                del self.legs[index]; removed_count += 1
        if removed_count > 0:
            self._update_legs_display()
            self._set_status(f"Removed {removed_count} leg(s). Update plot.", "blue")
            # self._update_strategy_and_pnl_plot() # Uncomment for auto-update

    def _edit_leg(self):
        selected = self.legs_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Select a leg to edit.", parent=self)
            return

        index = int(selected[0])
        if index >= len(self.legs):
            messagebox.showerror("Invalid Selection", "Invalid leg index.", parent=self)
            return

        leg = self.legs[index]

        try:
            action = simpledialog.askstring("Edit Action", "Buy or Sell?", initialvalue=leg['action'], parent=self)
            type_ = simpledialog.askstring("Edit Type", "Call or Put?", initialvalue=leg['type'], parent=self)
            strike = float(simpledialog.askstring("Edit Strike", "Strike Price:", initialvalue=str(leg['strike']), parent=self))
            premium = float(simpledialog.askstring("Edit Premium", "Premium:", initialvalue=str(leg['premium']), parent=self))
            quantity = int(simpledialog.askstring("Edit Quantity", "Contracts:", initialvalue=str(leg['quantity']), parent=self))

            def try_parse(val):
                try: return float(val)
                except: return None

            delta = try_parse(simpledialog.askstring("Edit Delta", "Delta (optional):", initialvalue=str(leg.get('delta', '')), parent=self))
            gamma = try_parse(simpledialog.askstring("Edit Gamma", "Gamma (optional):", initialvalue=str(leg.get('gamma', '')), parent=self))
            theta = try_parse(simpledialog.askstring("Edit Theta", "Theta (optional):", initialvalue=str(leg.get('theta', '')), parent=self))
            vega = try_parse(simpledialog.askstring("Edit Vega", "Vega (optional):", initialvalue=str(leg.get('vega', '')), parent=self))
            rho = try_parse(simpledialog.askstring("Edit Rho", "Rho (optional):", initialvalue=str(leg.get('rho', '')), parent=self))

        except (ValueError, TypeError):
            messagebox.showerror("Invalid Input", "One or more fields have invalid input.", parent=self)
            return

        leg.update({
            'action': action,
            'type': type_,
            'strike': strike,
            'premium': premium,
            'quantity': quantity,
            'delta': delta,
            'gamma': gamma,
            'theta': theta,
            'vega': vega,
            'rho': rho
        })

        self._update_legs_display()
        self._set_status(f"Updated leg {index}.", "blue")

    def _classify_greek_risk(self, value, greek):
        thresholds = {
            'delta': [10, 50, 100, 200],
            'gamma': [5, 20, 50, 100],
            'theta': [10, 50, 100, 200],
            'vega':  [20, 50, 100, 200],
            'rho':   [5, 10, 20, 50]
        }

        labels = ["✅ Minimal", "🟢 Low", "🟡 Moderate", "🟠 High", "🔴 Extreme"]

        abs_val = abs(value)
        greek = greek.lower()
        if greek not in thresholds:
            return "N/A"

        for i, limit in enumerate(thresholds[greek]):
            if abs_val < limit:
                return labels[i]
        return labels[-1]



    def _update_legs_display(self):
        self.legs_tree.delete(*self.legs_tree.get_children())  # Clear existing rows
        for i, leg in enumerate(self.legs):
            cost_credit = leg['premium'] * 100 * leg['quantity'] * (-1 if leg['action'] == 'Buy' else 1)
            values = (
                leg['action'], leg['quantity'], leg['type'], f"{leg['strike']:.2f}",
                f"{leg['premium']:.2f}", f"{cost_credit:+.2f}",
                f"{leg.get('delta', 'N/A') if leg.get('delta') is not None else 'N/A'}",
                f"{leg.get('gamma', 'N/A') if leg.get('gamma') is not None else 'N/A'}",
                f"{leg.get('theta', 'N/A') if leg.get('theta') is not None else 'N/A'}",
                f"{leg.get('vega', 'N/A') if leg.get('vega') is not None else 'N/A'}",
                f"{leg.get('rho', 'N/A') if leg.get('rho') is not None else 'N/A'}"
            )
            self.legs_tree.insert("", tk.END, iid=i, values=values)


    # --- Template Methods ---
    def _apply_template(self, template_legs):
        """Clears current legs and adds legs from the template."""
        self.legs.clear()
        self.legs.extend(template_legs)
        self._update_legs_display()
        self._update_strategy_and_pnl_plot() # Update plot immediately
        self._set_status("Applied template. Review premiums and update.", "green")

    def _apply_bull_call_template(self):
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5 # ATM strike (approx)
        k2 = k1 + 5          # OTM strike
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': k1, 'premium': 2.00, 'quantity': 1}, # Placeholder premium
            {'action': 'Sell','type': 'Call', 'strike': k2, 'premium': 0.50, 'quantity': 1}  # Placeholder premium
        ]
        self._apply_template(legs)

    def _apply_bear_put_template(self):
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5 # ATM strike (approx)
        k2 = k1 - 5          # OTM strike
        legs = [
            {'action': 'Buy', 'type': 'Put', 'strike': k1, 'premium': 2.00, 'quantity': 1},
            {'action': 'Sell','type': 'Put', 'strike': k2, 'premium': 0.50, 'quantity': 1}
        ]
        self._apply_template(legs)

    def _apply_straddle_template(self):
        s0 = self.underlying_price.get()
        k = round(s0 / 5) * 5 # ATM strike (approx)
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': k, 'premium': 2.50, 'quantity': 1},
            {'action': 'Buy', 'type': 'Put', 'strike': k, 'premium': 2.00, 'quantity': 1}
        ]
        self._apply_template(legs)

    def _apply_iron_condor_template(self):
        s0 = self.underlying_price.get()
        atm = round(s0 / 5) * 5
        spread = 5 # Typical spread width
        # Sell Put Spread (OTM)
        sell_put_k = atm - spread
        buy_put_k = sell_put_k - spread
        # Sell Call Spread (OTM)
        sell_call_k = atm + spread
        buy_call_k = sell_call_k + spread
        legs = [
             # Sell OTM Put Spread
            {'action': 'Sell', 'type': 'Put', 'strike': sell_put_k, 'premium': 0.70, 'quantity': 1},
            {'action': 'Buy', 'type': 'Put', 'strike': buy_put_k, 'premium': 0.20, 'quantity': 1},
             # Sell OTM Call Spread
            {'action': 'Sell', 'type': 'Call', 'strike': sell_call_k, 'premium': 0.60, 'quantity': 1},
            {'action': 'Buy', 'type': 'Call', 'strike': buy_call_k, 'premium': 0.15, 'quantity': 1}
        ]
        self._apply_template(legs)

    def _apply_long_call_template(self):
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5 # ATM strike (approx)
        # Placeholder premiums - User MUST adjust these
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': k1, 'premium': 3.00, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Applied Long Call template. Adjust strike/premium.", "blue")
        # messagebox.showwarning("Placeholder", "Apply Long Call template logic needs implementation (strikes, premiums).", parent=self)

    def _apply_long_put_template(self):
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5 # ATM strike (approx)
        legs = [
            {'action': 'Buy', 'type': 'Put', 'strike': k1, 'premium': 2.50, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Applied Long Put template. Adjust strike/premium.", "blue")

    def _apply_covered_call_template(self):
        # NOTE: This strategy technically requires owning 100 shares per contract sold.
        # The builder doesn't track share ownership, so this is purely setting up the option leg.
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5 + 5 # Slightly OTM strike (approx)
        legs = [
             # Implicit: Assumes user OWNS 100 shares of underlying
            {'action': 'Sell', 'type': 'Call', 'strike': k1, 'premium': 1.00, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Applied Covered Call template (Sell Call leg). Assumes stock ownership. Adjust strike/premium.", "blue")
        messagebox.showinfo("Important Note", "Covered Call strategy assumes you own 100 shares of the underlying per contract sold. This tool only added the 'Sell Call' leg.", parent=self)

    def _apply_protective_put_template(self):
        # NOTE: Assumes owning 100 shares. Adds the 'Buy Put' leg.
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5 - 5 # Slightly OTM put strike (approx)
        legs = [
             # Implicit: Assumes user OWNS 100 shares of underlying
            {'action': 'Buy', 'type': 'Put', 'strike': k1, 'premium': 1.20, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Applied Protective Put template (Buy Put leg). Assumes stock ownership. Adjust strike/premium.", "blue")
        messagebox.showinfo("Important Note", "Protective Put strategy assumes you own 100 shares of the underlying per contract bought. This tool only added the 'Buy Put' leg.", parent=self)

    def _apply_strangle_template(self):
        s0 = self.underlying_price.get()
        atm = round(s0 / 5) * 5
        spread = 5 # Distance from ATM
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': atm + spread, 'premium': 1.50, 'quantity': 1}, # OTM Call
            {'action': 'Buy', 'type': 'Put', 'strike': atm - spread, 'premium': 1.30, 'quantity': 1}   # OTM Put
        ]
        self._apply_template(legs)
        self._set_status("Applied Strangle template. Adjust strikes/premiums.", "blue")

    def _apply_butterfly_template(self):
        # Example: Long Call Butterfly (Buy 1 ITM, Sell 2 ATM, Buy 1 OTM)
        s0 = self.underlying_price.get()
        atm = round(s0 / 5) * 5
        spread = 5 # Wing width
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': atm - spread, 'premium': 4.00, 'quantity': 1},
            {'action': 'Sell', 'type': 'Call', 'strike': atm, 'premium': 2.00, 'quantity': 2},
            {'action': 'Buy', 'type': 'Call', 'strike': atm + spread, 'premium': 0.80, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Applied Call Butterfly template. Adjust strikes/premiums.", "blue")

    def _apply_calendar_template(self):
        # Example: Long Calendar Call (Sell Near-Term, Buy Far-Term - SAME STRIKE)
        # NOTE: This tool doesn't handle multiple expiries! This template is conceptual.
        # We will just add one leg representing the long-term buy for visual payoff shape.
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5 # ATM strike (approx)
        # Premiums are very context-dependent here.
        legs = [
             # We can only represent one expiration in this simple model's P/L chart.
             # We'll add the LONG option leg as it dominates the far-term payoff shape.
             # User must understand this doesn't capture the time decay aspect accurately.
            {'action': 'Buy', 'type': 'Call', 'strike': k1, 'premium': 3.50, 'quantity': 1}, # Represents the LONG dated option
            # {'action': 'Sell', 'type': 'Call', 'strike': k1, 'premium': 1.50, 'quantity': 1}, # SHORT dated (Can't plot accurately together)
        ]
        self._apply_template(legs)
        self._set_status("Applied conceptual Calendar template (Long Leg only). Adjust strike/premium.", "orange")
        messagebox.showwarning("Limitation", "Calendar Spreads involve different expiries. This tool plots based on a single expiry.\nThe template added the long leg only for a basic shape. Actual P/L depends heavily on time decay (theta) and volatility changes.", parent=self)

    def _apply_diagonal_spread_template(self):
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5
        k2 = k1 + 5
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': k1, 'premium': 4.00, 'quantity': 1},
            {'action': 'Sell', 'type': 'Call', 'strike': k2, 'premium': 1.00, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Diagonal Spread template applied.", "blue")

    def _apply_ratio_spread_template(self):
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5
        k2 = k1 + 5
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': k1, 'premium': 3.00, 'quantity': 1},
            {'action': 'Sell', 'type': 'Call', 'strike': k2, 'premium': 1.20, 'quantity': 2},
        ]
        self._apply_template(legs)
        self._set_status("Ratio Spread template applied.", "blue")

    def _apply_backspread_template(self):
        s0 = self.underlying_price.get()
        k1 = round(s0 / 5) * 5
        k2 = k1 + 5
        legs = [
            {'action': 'Sell', 'type': 'Call', 'strike': k1, 'premium': 2.50, 'quantity': 1},
            {'action': 'Buy', 'type': 'Call', 'strike': k2, 'premium': 1.50, 'quantity': 2},
        ]
        self._apply_template(legs)
        self._set_status("Backspread template applied.", "blue")

    def _apply_jade_lizard_template(self):
        s0 = self.underlying_price.get()
        k_put = round(s0 / 5) * 5 - 5
        k_call1 = round(s0 / 5) * 5 + 5
        k_call2 = k_call1 + 5
        legs = [
            {'action': 'Sell', 'type': 'Put', 'strike': k_put, 'premium': 1.50, 'quantity': 1},
            {'action': 'Sell', 'type': 'Call', 'strike': k_call1, 'premium': 1.00, 'quantity': 1},
            {'action': 'Buy', 'type': 'Call', 'strike': k_call2, 'premium': 0.30, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Jade Lizard template applied.", "blue")

    def _apply_iron_butterfly_template(self):
        s0 = self.underlying_price.get()
        atm = round(s0 / 5) * 5
        spread = 5
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': atm + spread, 'premium': 1.20, 'quantity': 1},
            {'action': 'Sell', 'type': 'Call', 'strike': atm, 'premium': 2.50, 'quantity': 1},
            {'action': 'Sell', 'type': 'Put', 'strike': atm, 'premium': 2.30, 'quantity': 1},
            {'action': 'Buy', 'type': 'Put', 'strike': atm - spread, 'premium': 1.00, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Iron Butterfly template applied.", "blue")

    def _apply_broken_butterfly_template(self):
        s0 = self.underlying_price.get()
        atm = round(s0 / 5) * 5
        wings = 5
        broken_wing = 10
        legs = [
            {'action': 'Buy', 'type': 'Call', 'strike': atm - wings, 'premium': 3.00, 'quantity': 1},
            {'action': 'Sell', 'type': 'Call', 'strike': atm, 'premium': 2.00, 'quantity': 2},
            {'action': 'Buy', 'type': 'Call', 'strike': atm + broken_wing, 'premium': 0.50, 'quantity': 1},
        ]
        self._apply_template(legs)
        self._set_status("Broken Wing Butterfly template applied.", "blue")

    # --- Recommendation Feature ---

    def _open_recommendation_dialog(self):
        """Opens the input dialog, gets recommendations, and shows results."""
        try:
            current_price = self.underlying_price.get()
        except tk.TclError:
             messagebox.showerror("Error", "Please enter a valid current underlying price first.", parent=self)
             return

        # 1. Get Inputs
        input_dialog = RecommendationInputDialog(self, "Recommend Options Strategy", initial_price=current_price)
        if not input_dialog.result: # User cancelled input dialog
            return

        inputs = input_dialog.result
        self._set_status("Analyzing inputs for recommendations...", "blue")
        self.update_idletasks() # Show status update

        # 2. Get Recommendations
        try:
            recommender = StrategyRecommender(inputs)
            # Get top 3 recommendations
            top_recommendations = recommender.recommend_top_strategies(n=3)
        except Exception as e:
             messagebox.showerror("Recommendation Error", f"Failed to get recommendations:\n{e}", parent=self)
             print(traceback.format_exc()) # Log detailed error
             self._set_status("Recommendation failed.", "red")
             return

        self._set_status("Displaying recommendations...", "blue")
        self.update_idletasks()

        # 3. Display Ranked List and Get Selection
        if not top_recommendations or top_recommendations[0][1] == "No Suitable Strategy":
             messagebox.showinfo("No Matches",
                                 top_recommendations[0][2] if top_recommendations else "Could not find any suitable strategies.",
                                 parent=self)
             self._set_status("No suitable strategies found.", "orange")
             return

        results_dialog = RecommendationResultsDialog(self, "Top Strategy Recommendations", top_recommendations)
        # results_dialog.selected_strategy will be None if cancelled, or the chosen name if OK

        if results_dialog.selected_strategy:
            selected_strategy_name = results_dialog.selected_strategy
            self._set_status(f"Selected '{selected_strategy_name}'. Asking to apply template...", "blue")

            # 4. Ask to Apply Template for the SELECTED strategy
            template_methods = {
                "Long Call": self._apply_long_call_template,
                "Long Put": self._apply_long_put_template,
                "Covered Call": self._apply_covered_call_template,
                "Protective Put": self._apply_protective_put_template,
                "Bull Call Spread": self._apply_bull_call_template,
                "Bear Put Spread": self._apply_bear_put_template,
                "Iron Condor": self._apply_iron_condor_template,
                "Straddle": self._apply_straddle_template,
                "Strangle": self._apply_strangle_template,
                "Butterfly Spread": self._apply_butterfly_template,
                "Iron Butterfly": self._apply_iron_butterfly_template,
                "Calendar Spread": self._apply_calendar_template,
                "Diagonal Spread": self._apply_diagonal_spread_template,
                "Ratio Spread": self._apply_ratio_spread_template,
                "Backspread": self._apply_backspread_template,
                "Jade Lizard": self._apply_jade_lizard_template,
                "Broken Wing Butterfly": self._apply_broken_butterfly_template,
            }


            apply_func = template_methods.get(selected_strategy_name)

            if apply_func:
                 if messagebox.askyesno("Apply Template?",
                                       f"Do you want to apply the '{selected_strategy_name}' template?\n(This will clear existing legs)",
                                       parent=self):
                      try:
                          apply_func() # Call the corresponding template function
                          self._set_status(f"Applied '{selected_strategy_name}' template from recommendation.", "green")
                      except Exception as e:
                          messagebox.showerror("Template Error", f"Could not apply template for {selected_strategy_name}:\n{e}", parent=self)
                          print(traceback.format_exc()) # Log detailed error
                          self._set_status(f"Error applying {selected_strategy_name} template.", "red")
            else:
                 messagebox.showwarning("Not Implemented", f"Template function for '{selected_strategy_name}' is not yet available in the builder.", parent=self)
                 self._set_status(f"Template for '{selected_strategy_name}' not implemented.", "orange")
        else:
            # User cancelled the results selection dialog
            self._set_status("Recommendation viewing cancelled.", "orange")

        

    # --- Calculation Methods ---

    def _calculate_strategy_payoff_at_price(self, S_price, net_premium):
        """Calculates strategy payoff for a single final price S_price."""
        total_intrinsic_payoff = 0.0
        for leg in self.legs:
            K = leg['strike']
            Q = leg['quantity'] * 100 # Convert to shares
            action_mult = 1 if leg['action'] == 'Buy' else -1

            if leg['type'] == 'Call':
                intrinsic_value = np.maximum(0, S_price - K)
            else: # Put
                intrinsic_value = np.maximum(0, K - S_price)

            total_intrinsic_payoff += action_mult * intrinsic_value * Q

        # Total P/L = Intrinsic Value Payoff + Net Premium Received/Paid
        return total_intrinsic_payoff + net_premium
    
    def get_position_cost(self):
        """Estimate total capital outlay for the strategy."""
        total_cost = 0.0
        for leg in self.legs:
            quantity = leg.get('quantity', 1)
            premium = leg.get('premium', 0.0)
            multiplier = -1 if leg['action'] == 'Buy' else 1
            total_cost += multiplier * premium * 100 * quantity
        return total_cost


    def _calculate_strategy_payoff_range(self, S_values):
        """Vectorized strategy P/L over a range of final prices."""
        total_payoff_vector = np.zeros_like(S_values, dtype=float)
        net_premium = 0.0

        for leg in self.legs:
            P = leg['premium']
            Q = leg['quantity'] * 100 # Convert to shares
            action_mult = 1 if leg['action'] == 'Buy' else -1
            net_premium += (-action_mult * P * Q)  # Debit = negative

            K = leg['strike']
            if leg['type'] == 'Call':
                intrinsic_value = np.maximum(0, S_values - K)
            else:  # Put
                intrinsic_value = np.maximum(0, K - S_values)

            total_payoff_vector += action_mult * intrinsic_value * Q

        total_payoff_vector += net_premium
        return total_payoff_vector, net_premium



    def _find_break_evens(self, S_values, payoff_values):
        # Same as before
        break_evens = []
        sign_changes = np.where(np.diff(np.sign(payoff_values)))[0]
        for idx in sign_changes:
            S1, S2 = S_values[idx], S_values[idx+1]
            P1, P2 = payoff_values[idx], payoff_values[idx+1]
            if abs(P2 - P1) > 1e-9:
                be = S1 - P1 * (S2 - S1) / (P2 - P1)
                if min(S1, S2) <= be <= max(S1, S2): break_evens.append(be)
            elif abs(P1) < 1e-6 : break_evens.append(S1)
        if break_evens: break_evens = sorted(list(set(np.round(break_evens, 2))))
        return break_evens

    def _calculate_metrics(self, S_values, payoff_values, net_premium):
        # Calculate initial max profit/loss from the payoff curve
        max_profit = np.max(payoff_values)
        max_loss = np.min(payoff_values)

        # **FIX**: Correctly define max loss for debit-only strategies
        # A strategy of only long options has a max loss equal to the debit paid.
        is_debit_only_strategy = bool(self.legs) and all(leg.get('action') == 'Buy' for leg in self.legs)
        if is_debit_only_strategy:
            # The net_premium for a debit is negative, which is the correct max_loss value.
            max_loss = net_premium

        # Now, check for infinite risk which overrides any finite calculation
        if self.legs:
            net_short_calls = sum(l['quantity'] for l in self.legs if l['action']=='Sell' and l['type']=='Call')
            net_long_calls = sum(l['quantity'] for l in self.legs if l['action']=='Buy' and l['type']=='Call')
            net_short_puts = sum(l['quantity'] for l in self.legs if l['action']=='Sell' and l['type']=='Put')
            net_long_puts = sum(l['quantity'] for l in self.legs if l['action']=='Buy' and l['type']=='Put')

            if net_short_calls > net_long_calls: max_loss = -np.inf
            if net_short_puts > net_long_puts: max_loss = -np.inf
            if net_long_calls > net_short_calls: max_profit = np.inf

        # Store the final, corrected metrics
        self.strategy_results['net_premium'] = net_premium
        self.strategy_results['max_profit'] = max_profit
        self.strategy_results['max_loss'] = max_loss
        
        # Find break-evens using the calculated payoff curve
        self.strategy_results['break_evens'] = self._find_break_evens(S_values, payoff_values)

        self._update_results_display()

        
    def _update_results_display(self):
        res = self.strategy_results
        prem_text = f"{res['net_premium']:+.2f}"
        prem_type = " (Debit)" if res['net_premium'] < 0 else " (Credit)" if res['net_premium'] > 0 else ""
        self.net_premium_label.config(text=prem_text + prem_type)

        if res['max_profit'] == np.inf:
            profit_text = "Unlimited"
        elif res['max_profit'] is not None:
            profit_text = f"{res['max_profit']:,.2f}"
        else:
            profit_text = "N/A"
        self.max_profit_label.config(text=profit_text)

        if res['max_loss'] == -np.inf:
            loss_text = "Unlimited"
        elif res['max_loss'] is not None:
            loss_text = f"{res['max_loss']:,.2f}"
        else:
            loss_text = "N/A"
        self.max_loss_label.config(text=loss_text)

        if res['break_evens']:
            be_text = ", ".join([f"{be:.2f}" for be in res['break_evens']])
        else:
            be_text = "None" if res['net_premium'] is not None else "N/A"
        self.break_evens_label.config(text=be_text)

        if res['pop'] is not None:
            pop_text = f"{res['pop'] * 100:.1f}%"
        else:
            pop_text = "N/A (Run Sim)"
        self.pop_label.config(text=pop_text)

        if 'value_change' in res and res['value_change'] is not None:
            delta = res['value_change']
            sign = '+' if delta >= 0 else ''
            self.value_change_label.config(text=f"{sign}{delta:.2f}")
        else:
            self.value_change_label.config(text="N/A")

        # Calculate total Greeks
        totals = {'delta': 0.0, 'gamma': 0.0, 'theta': 0.0, 'vega': 0.0, 'rho': 0.0}
        has_values = {key: False for key in totals}

        for leg in self.legs:
            for greek in totals:
                if greek in leg and isinstance(leg[greek], (int, float)):
                    totals[greek] += leg[greek] * leg['quantity']  # Total per position
                    has_values[greek] = True

        # Display total Greeks
        for greek in totals:
            if has_values[greek]:
                display_value = totals[greek]
                self.total_greek_labels[greek].config(text=f"{display_value:+.2f}")
            else:
                self.total_greek_labels[greek].config(text="N/A")

        # Store totals for use in risk curves
        self.total_greek_values = totals

        # Update Greek Risk Classification Table
        for greek in totals:
            val = totals[greek] if has_values[greek] else None
            if val is not None:
                self.greek_risk_rows[greek]["exposure"].config(text=f"{val:+.2f}")
                self.greek_risk_rows[greek]["risk"].config(text=self._classify_greek_risk(val, greek))
            else:
                self.greek_risk_rows[greek]["exposure"].config(text="N/A")
                self.greek_risk_rows[greek]["risk"].config(text="N/A")

        if has_values['delta'] and abs(totals['delta']) < 0.01:
            self.total_greek_labels['delta'].config(text=f"{totals['delta']:+.2f} (Δ-neutral)")

    # --- Monte Carlo Simulation ---
    def _run_strategy_monte_carlo(self):
        """Runs MC sim for the strategy and updates results/plot."""
        self._set_status("Running Monte Carlo simulation...", "orange")
        self.update_idletasks() # Ensure status shows

        # Validate inputs
        try:
            S0 = self.underlying_price.get() * (1 + self.what_if_scenarios['S_shift'])
            sigma = self.mc_sim_volatility.get() + self.what_if_scenarios['vol_shift']
            r = self.mc_sim_rate.get() + self.what_if_scenarios['rate_shift']
            days = self.mc_sim_days.get() - self.what_if_scenarios['days_passed']
            days = max(days, 1)  # Ensure days stays positive
            n_sim = self.mc_sim_paths.get()
            T = days / 365.0

            if S0 <= 0: raise ValueError("Underlying Price must be positive.")
            if sigma < 0: raise ValueError("Sim Volatility cannot be negative.")
            if T <= 0: raise ValueError("Strategy Expiry must be positive.")
            if n_sim <= 0: raise ValueError("Number of Paths must be positive.")
            if not self.legs: raise ValueError("Add legs to the strategy first.")

        except (tk.TclError, ValueError) as e:
             messagebox.showerror("Input Error", f"Invalid simulation parameter: {e}", parent=self)
             self._set_status("Simulation input error.", "red")
             return

        # Calculate net premium once (assuming it's fixed at entry)
        net_premium = sum(leg['premium'] * leg['quantity'] * (-1 if leg['action'] == 'Buy' else 1) for leg in self.legs)

        # Simulate final underlying prices (S_T) - Risk Neutral for pricing consistency
        drift = (r - 0.5 * sigma**2) * T
        vol_term = sigma * np.sqrt(T)
        np.random.seed(42) # Reproducibility
        Z = np.random.standard_normal(n_sim)
        final_log_S = np.log(S0) + drift + vol_term * Z
        final_S = np.exp(final_log_S)

        # Calculate P&L for each simulated final price
        final_pnl = np.zeros(n_sim)
        for i in range(n_sim):
            final_pnl[i] = self._calculate_strategy_payoff_at_price(final_S[i], net_premium)

        # Calculate Probability of Profit (POP)
        pop = np.mean(final_pnl > 0) # P&L > 0 means profit

        # Store results
        self.strategy_results['pop'] = pop
        self.strategy_results['mc_pnl_results'] = final_pnl

        self._update_results_display() # Update labels including POP
        self.plot_view_mode.set("mc") # Switch plot view to MC results
        self._update_plot() # Update the plot to show histogram
        self._set_status(f"Monte Carlo simulation complete (POP: {pop*100:.1f}%).", "green")


    # --- Plotting ---
    def _update_strategy_and_pnl_plot(self):
        """Convenience method to update results and switch view to P&L plot."""
        self.plot_view_mode.set("pnl") # Ensure plot mode is P&L
        self._update_plot()           # Update the plot
        self._set_status("Expiration P&L plot updated.", "green")


    def _update_plot(self):
        """Clears and redraws the plot based on the selected view mode."""
        self.ax.clear() # Clear previous plot
        self.pnl_line = None # Reset P&L line handle
        self.hover_annotation.set_visible(False) # Hide annotation

        mode = self.plot_view_mode.get()

        # --- Apply common styling ---
        self.ax.set_facecolor(self.plot_colors['bg'])
        self.ax.tick_params(axis='x', colors=self.plot_colors['fg'])
        self.ax.tick_params(axis='y', colors=self.plot_colors['fg'])
        # ... (set all spines, labels, title colors as in _setup_plot_area)
        self.ax.yaxis.label.set_color(self.plot_colors['fg'])
        self.ax.xaxis.label.set_color(self.plot_colors['fg'])
        self.ax.title.set_color(self.plot_colors['fg'])
        self.ax.grid(True, linestyle=self.plot_colors['zero_line'], alpha=0.5)


        # --- Plot based on mode ---
        if mode == "pnl":
            self._plot_expiration_pnl()
        elif mode == "mc":
            self._plot_mc_distribution()
        elif mode == "risk":
            self._generate_greek_risk_curve()
        else: # Default or error case
             self.ax.text(0.5, 0.5, "Select plot view", ha='center', va='center', transform=self.ax.transAxes, color=self.plot_colors['fg'])

        self.canvas_widget.configure(height=int(self.winfo_height() * 0.6))
        self.canvas.draw_idle() # Use draw_idle for potentially better responsiveness
        



    def _update_scenario_summary(self, label, old_price, old_vol, old_rate, old_days, old_pop, old_premium):
        new_price = self.underlying_price.get() * (1 + self.what_if_scenarios['S_shift'])
        new_vol = self.mc_sim_volatility.get()
        new_rate = self.mc_sim_rate.get()
        new_days = self.mc_sim_days.get()
        new_pop = self.strategy_results.get("pop")
        new_premium = self.strategy_results.get("net_premium")

        delta_pop = (new_pop - old_pop) if old_pop is not None and new_pop is not None else None
        delta_premium = new_premium - old_premium if new_premium is not None and old_premium is not None else None

        msg = f"📊 Scenario Applied: {label}\n"
        msg += f"• Underlying: ${old_price:.2f} ➝ ${new_price:.2f}\n"
        msg += f"• IV: {old_vol*100:.1f}% ➝ {new_vol*100:.1f}%\n"
        msg += f"• Rate: {old_rate*100:.2f}% ➝ {new_rate*100:.2f}%\n"
        msg += f"• Days to Expiry: {old_days} ➝ {new_days}\n"

        if delta_premium:
            msg += f"• Position Value: {old_premium:+.2f} ➝ {new_premium:+.2f} ({delta_premium:+.2f})\n"
        if delta_pop:
            msg += f"• POP: {old_pop*100:.1f}% ➝ {new_pop*100:.1f}% ({delta_pop*100:+.1f}%)\n"

        insight = ""
        if delta_premium and abs(delta_premium) > 0.01:
            if delta_premium > 0:
                insight += "📈 Strategy looks more favorable under this scenario."
            else:
                insight += "📉 Strategy loses value in this scenario."

        if delta_pop and abs(delta_pop) > 0.01:
            if delta_pop > 0:
                insight += " ✅ Higher chance of profit!"
            else:
                insight += " ⚠️ Lower chance of profit."

        self.scenario_summary_label.config(text=msg + "\n" + insight)

    def _apply_scenario(self, label, change_func):
            # Capture base values before applying shift
            base_S = self.underlying_price.get()
            base_vol = self.mc_sim_volatility.get()
            base_rate = self.mc_sim_rate.get()
            base_days = self.mc_sim_days.get()
            old_pop = self.strategy_results.get("pop")

            # Simulate expected value *before* shift for accurate delta
            self._run_strategy_monte_carlo()
            old_ev = np.mean(self.strategy_results['mc_pnl_results']) if self.strategy_results['mc_pnl_results'] is not None else None

            # Apply shift to what-if scenarios
            change_func()

            # Simulate *after* shift
            self._run_strategy_monte_carlo()
            new_ev = np.mean(self.strategy_results['mc_pnl_results']) if self.strategy_results['mc_pnl_results'] is not None else None

            # Calculate shifted values
            new_S = base_S * (1 + self.what_if_scenarios['S_shift'])
            new_vol = base_vol + self.what_if_scenarios['vol_shift']
            new_rate = base_rate + self.what_if_scenarios['rate_shift']
            new_days = max(base_days - self.what_if_scenarios['days_passed'], 1)

            # Set value change for display
            if old_ev is not None and new_ev is not None:
                self.strategy_results['value_change'] = new_ev - old_ev
            else:
                self.strategy_results['value_change'] = None

            # Compose scenario summary
            msg = f"📊 Scenario Applied: {label}\n"
            msg += f"• Underlying: ${base_S:.2f} ➝ ${new_S:.2f}\n"
            msg += f"• IV: {base_vol*100:.1f}% ➝ {new_vol*100:.1f}%\n"
            msg += f"• Rate: {base_rate*100:.2f}% ➝ {new_rate*100:.2f}%\n"
            msg += f"• Days to Expiry: {base_days} ➝ {new_days}\n"

            if old_ev is not None and new_ev is not None:
                delta_ev = new_ev - old_ev
                msg += f"• Expected Value: {old_ev:+.2f} ➝ {new_ev:+.2f} ({delta_ev:+.2f})\n"

            if old_pop is not None and self.strategy_results['pop'] is not None:
                delta_pop = self.strategy_results['pop'] - old_pop
                msg += f"• POP: {old_pop*100:.1f}% ➝ {self.strategy_results['pop']*100:.1f}% ({delta_pop*100:+.1f}%)\n"

            # Add commentary
            insight = ""
            if old_ev is not None and new_ev is not None and abs(delta_ev) > 0.01:
                insight += "📈 Strategy looks more favorable." if delta_ev > 0 else "📉 Strategy loses value."

            if old_pop is not None and self.strategy_results['pop'] is not None and abs(delta_pop) > 0.01:
                insight += " ✅ Higher chance of profit!" if delta_pop > 0 else " ⚠️ Lower chance of profit."

            self.scenario_summary_label.config(text=msg + "\n" + insight)

    def _plot_expiration_pnl(self):
        """Plots the static expiration P&L curve."""
        self.ax.set_xlabel("Underlying Price at Expiration ($)", color=self.plot_colors['fg'])
        self.ax.set_ylabel("Profit / Loss ($)", color=self.plot_colors['fg'])
        self.ax.set_title("Strategy Payoff Diagram (at Expiration)", color=self.plot_colors['fg'])
        self.ax.axhline(0, color=self.plot_colors['fg'], linewidth=1.0, linestyle='-')

        if not self.legs:
            self.ax.text(0.5, 0.5, "No legs added to strategy", ha='center', va='center',
                        transform=self.ax.transAxes, color=self.plot_colors['fg'])
            self._update_results_display()
            return

        try:
            S0 = self.underlying_price.get()
            assert S0 > 0
        except:
            S0 = 100.0

         # Dynamic X range around current price (±PLOT_PRICE_RANGE_FACTOR)
        range_factor = PLOT_PRICE_RANGE_FACTOR  # e.g. 0.3 for ±30%
        low  = max(S0 * (1 - range_factor), 0.0)  # don’t go below zero
        high = S0 * (1 + range_factor)
        self.S_values = np.linspace(low, high, PLOT_POINTS)
        self.ax.set_xlim(low, high)
        try:
            self.payoff_values, net_premium = self._calculate_strategy_payoff_range(self.S_values)
        except Exception as e:
            messagebox.showerror("Calculation Error", f"Failed to calculate payoff: {e}", parent=self)
            print(traceback.format_exc())
            return

        self.pnl_line, = self.ax.plot(self.S_values, self.payoff_values, color=self.plot_colors['line'],
                                    linewidth=2, label="Strategy P/L")

        self.ax.fill_between(self.S_values, self.payoff_values, 0, where=self.payoff_values >= 0,
                            facecolor=self.plot_colors['profit'], alpha=0.3, interpolate=True)
        self.ax.fill_between(self.S_values, self.payoff_values, 0, where=self.payoff_values < 0,
                            facecolor=self.plot_colors['loss'], alpha=0.3, interpolate=True)

        break_evens = self._find_break_evens(self.S_values, self.payoff_values)
        self.strategy_results['break_evens'] = break_evens
        for i, be in enumerate(break_evens):
            label = f'Break-even ({be:.2f})' if i == 0 else None
            self.ax.plot(be, 0, 'o', color='gold', markersize=6, label=label)
            self.ax.vlines(be, 0, self.payoff_values[np.argmin(np.abs(self.S_values - be))],
                        color='gold', linestyle=':', linewidth=1)

        self._calculate_metrics(self.S_values, self.payoff_values, net_premium)

        self.ax.axvline(S0, color='cyan', linestyle='--', linewidth=1, label=f'Current Price (S0={S0:.2f})')

        max_p = self.strategy_results['max_profit']
        max_l = self.strategy_results['max_loss']
        if max_p != np.inf and max_p is not None:
            max_p_idx = np.argmax(self.payoff_values)
            self.ax.plot(self.S_values[max_p_idx], max_p, '^', color=self.plot_colors['profit'],
                        markersize=7, label=f'Max Profit ({max_p:,.2f})')
        if max_l != -np.inf and max_l is not None:
            max_l_idx = np.argmin(self.payoff_values)
            self.ax.plot(self.S_values[max_l_idx], max_l, 'v', color=self.plot_colors['loss'],
                        markersize=7, label=f'Max Loss ({max_l:,.2f})')

        # Fixed Y range
        buffer_factor = 0.10
        if max_l != -np.inf and max_p != np.inf:
            plot_range = max_p - max_l if max_p != max_l else abs(net_premium)*2 if net_premium else 10
            y_min_limit = max_l - plot_range * buffer_factor if max_l is not None else self.ax.get_ylim()[0]
            y_max_limit = max_p + plot_range * buffer_factor if max_p is not None else self.ax.get_ylim()[1]
            self.ax.set_ylim(y_min_limit, y_max_limit)

        # X-axis: widen to 40% margin around strikes
        plot_min = min(self.S_values) - (max(self.S_values) - min(self.S_values)) * 0.1
        plot_max = max(self.S_values) + (max(self.S_values) - min(self.S_values)) * 0.1
        self.ax.set_xlim(plot_min, plot_max)

        handles, labels = self.ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        legend = self.ax.legend(by_label.values(), by_label.keys(), fontsize='small')
        for text in legend.get_texts():
            text.set_color(self.plot_colors['fg'])



    def _plot_mc_distribution(self):
        """Plots the histogram of simulated P&L results."""
        self.ax.set_title("Monte Carlo: Strategy P&L Distribution at Expiry", color=self.plot_colors['fg'])
        self.ax.set_xlabel("Final Profit / Loss ($)", color=self.plot_colors['fg'])
        self.ax.set_ylabel("Frequency (%)", color=self.plot_colors['fg'])

        pnl_results = self.strategy_results.get('mc_pnl_results')
        pop = self.strategy_results.get('pop')

        if pnl_results is None:
            self.ax.text(0.5, 0.5, "Run Monte Carlo simulation first", ha='center', va='center', transform=self.ax.transAxes, color=self.plot_colors['fg'])
            return

        # Plot histogram using numpy and matplotlib directly for better style control
        # If all values are nearly identical, reduce bins or skip plot
        if np.ptp(pnl_results) < 1e-6 or len(np.unique(pnl_results)) < 2:
            self.ax.text(0.5, 0.5, "Simulation results have too little variation to show histogram.",
                        ha='center', va='center', transform=self.ax.transAxes, color=self.plot_colors['fg'])
            return

        # Safe bin count based on data spread
        bin_count = min(50, max(1, len(np.unique(pnl_results)) // 2))
        counts, bins = np.histogram(pnl_results, bins=bin_count)

        bin_centers = 0.5 * (bins[:-1] + bins[1:])
        total_paths = len(pnl_results)
        percentages = (counts / total_paths) * 100

        self.ax.bar(bin_centers, percentages, width=np.diff(bins)[0], color=self.plot_colors['mc_hist'], edgecolor=self.plot_colors['fg'], alpha=0.75)

        # Add vertical line at P&L = 0
        self.ax.axvline(0, color='gold', linestyle='--', linewidth=1.5, label='Break-even (P&L=0)')

        # Add mean P&L line
        mean_pnl = np.mean(pnl_results)
        self.ax.axvline(mean_pnl, color='magenta', linestyle=':', linewidth=1.5, label=f'Mean P&L (${mean_pnl:.2f})')

        # Add text for POP
        if pop is not None:
            y_lim = self.ax.get_ylim()
            self.ax.text(0.05, 0.95, f"Prob. Profit: {pop*100:.1f}%", transform=self.ax.transAxes,
                         ha='left', va='top', fontsize=10, color=self.plot_colors['profit'], weight='bold')

        self.ax.legend(fontsize='small')


    # --- Hover Interaction ---
    def _on_hover(self, event):
        """Handles mouse hover events over the plot canvas."""
        # Check if plot mode is P&L and line exists
        if self.plot_view_mode.get() != "pnl" or self.pnl_line is None:
            if self.hover_annotation.get_visible():
                self.hover_annotation.set_visible(False)
                self.canvas.draw_idle()
            return

        visible = self.hover_annotation.get_visible()
        # Check if event is within the axes
        if event.inaxes == self.ax:
            # Check if mouse is near the P&L line
            cont, ind = self.pnl_line.contains(event)
            if cont:
                # Get the index of the closest data point on the line
                x_mouse = event.xdata
                try:
                    # Find index in S_values closest to mouse x-position
                    idx = np.argmin(np.abs(self.S_values - x_mouse))
                    x_point, y_point = self.S_values[idx], self.payoff_values[idx]

                    # Update annotation text and position
                    self.hover_annotation.set_text(f" S: ${x_point:.2f}\nP&L: ${y_point:,.2f}")
                    self.hover_annotation.set_position((x_point, y_point))
                    # Adjust text offset based on quadrant relative to point (basic)
                    x_offset = 10 if x_mouse < (self.S_values[-1] + self.S_values[0])/2 else -60
                    y_offset = 10
                    self.hover_annotation.xytext = (x_offset, y_offset)

                    self.hover_annotation.set_visible(True)
                    self.canvas.draw_idle()
                except (IndexError, TypeError, AttributeError):
                     # Handle cases where S_values/payoff_values might be empty or invalid
                     if visible:
                         self.hover_annotation.set_visible(False)
                         self.canvas.draw_idle()
            else: # Mouse not near the line
                if visible:
                    self.hover_annotation.set_visible(False)
                    self.canvas.draw_idle()
        else: # Mouse not in axes
            if visible:
                self.hover_annotation.set_visible(False)
                self.canvas.draw_idle()

    def _apply_llm_strategy(self, strategy_data):
        """Applies the strategy received from the LLM to the builder."""
        if not isinstance(strategy_data, dict) or 'legs' not in strategy_data:
            raise ValueError("Invalid strategy format from LLM.")

        self.legs.clear()
        for leg in strategy_data['legs']:
            # **FIX**: Create a fully validated leg, now including the premium
            # provided by the LLM, with fallbacks for safety.
            validated_leg = {
                'action': leg.get('action'),
                'type': leg.get('type'),
                'strike': float(leg.get('strike', 0)),
                'premium': float(leg.get('premium', 0.0)), # Use the premium from the LLM
                'quantity': int(leg.get('quantity', 1))
            }
            # Add all greeks as None initially
            for greek in ['delta', 'gamma', 'theta', 'vega', 'rho']:
                validated_leg[greek] = None
            
            self.legs.append(validated_leg)

        # Update the UI to show the new legs and recalculate the P&L plot
        self._update_legs_display()
        self._update_strategy_and_pnl_plot()

    def _show_llm_note_popup(self, title, note_text):
        """Displays the LLM's note in a dedicated, scrollable window."""
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("550x350")
        win.transient(self)
        win.grab_set()
        
        if hasattr(self, 'app_controller'):
            self.app_controller.apply_theme_to_window(win)

        main_frame = ttk.Frame(win, padding=15)
        main_frame.pack(expand=True, fill=tk.BOTH)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        text_frame = ttk.LabelFrame(main_frame, text="AI Rationale")
        text_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        text_box = tk.Text(text_frame, wrap=tk.WORD, relief="flat", padx=10, pady=5, font=("Segoe UI", 10))
        text_box.grid(row=0, column=0, sticky="nsew")
        text_box.insert(tk.END, note_text)
        text_box.config(state=tk.DISABLED)

        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=text_box.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        text_box.configure(yscrollcommand=vsb.set)
        
        if hasattr(self, 'app_controller'):
            theme_settings = self.app_controller.theme_settings()
            text_box.config(background=theme_settings['entry_bg'], foreground=theme_settings['fg'])

        ttk.Button(main_frame, text="Close", command=win.destroy).grid(row=1, column=0, sticky="e")

    def _prompt_llm_for_strategy(self):
        def labeled_row_grid(container, row, label, widget):
            ttk.Label(container, text=label).grid(row=row, column=0, sticky='w', padx=10, pady=5)
            widget.grid(row=row, column=1, sticky='ew', padx=10, pady=5)

        window = tk.Toplevel(self)
        window.title("📡 LLM Strategy Builder")
        window.geometry("400x400")
        window.transient(self)
        window.grab_set()

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(1, weight=1)

        vars = {
            "ticker": tk.StringVar(value="AAPL"),
            "price": tk.DoubleVar(value=self.underlying_price.get()),
            "direction": tk.StringVar(value="Bearish"),
            "target": tk.DoubleVar(value=self.underlying_price.get() * 0.9),
            "dte": tk.IntVar(value=self.mc_sim_days.get()),
            "iv": tk.DoubleVar(value=self.mc_sim_volatility.get() * 100),
            "risk": tk.StringVar(value="Moderate"),
            "defined": tk.BooleanVar(value=True)
        }

        labeled_row_grid(frame, 0, "Ticker:", ttk.Entry(frame, textvariable=vars["ticker"]))
        labeled_row_grid(frame, 1, "Current Price:", ttk.Entry(frame, textvariable=vars["price"]))
        labeled_row_grid(frame, 2, "Market View:", ttk.Combobox(frame, textvariable=vars["direction"], values=["Bullish", "Bearish", "Neutral"], state="readonly"))
        labeled_row_grid(frame, 3, "Target Price:", ttk.Entry(frame, textvariable=vars["target"]))
        labeled_row_grid(frame, 4, "Days to Expiry:", ttk.Entry(frame, textvariable=vars["dte"]))
        labeled_row_grid(frame, 5, "Implied Volatility (%):", ttk.Entry(frame, textvariable=vars["iv"]))
        labeled_row_grid(frame, 6, "Risk Tolerance:", ttk.Combobox(frame, textvariable=vars["risk"], values=["Low", "Moderate", "High"], state="readonly"))
        ttk.Label(frame, text="Prefer Defined Risk:").grid(row=7, column=0, sticky='w', padx=10, pady=5)
        ttk.Checkbutton(frame, variable=vars["defined"]).grid(row=7, column=1, sticky='w', padx=10, pady=5)

        ttk.Button(frame, text="📡 Generate Strategy", command=lambda: run_llm()).grid(row=8, column=0, columnspan=2, pady=20)

        def run_llm():
            try:
                # Use the shared LLM helper from the main app
                llm = self.app_controller.llm
                self._set_status("Asking LLM for strategy...", "orange")
                
                # The llm helper method now handles token checking internally
                strategy = llm.recommend_strategy_structured(
                    ticker=vars["ticker"].get(),
                    spot=vars["price"].get(),
                    direction=vars["direction"].get(),
                    target=vars["target"].get(),
                    dte=vars["dte"].get(),
                    iv=vars["iv"].get(),
                    risk=vars["risk"].get(),
                    preference="Growth"
                )
                self._apply_llm_strategy(strategy)
                self._set_status("✅ LLM strategy applied.", "green")

                if "note" in strategy and strategy["note"]:
                    self._show_llm_note_popup("LLM Rationale", strategy["note"])

                window.destroy()

            except (ConnectionError, PermissionError) as e:
                messagebox.showerror("AI Error", str(e), parent=self)
                self._set_status("❌ LLM strategy failed.", "red")
            except Exception as e:
                # Use the app's copyable error for detailed tracebacks
                self.app_controller.show_copyable_error("LLM Error", f"An unexpected error occurred:\n{traceback.format_exc()}")
                self._set_status("❌ LLM strategy failed.", "red")