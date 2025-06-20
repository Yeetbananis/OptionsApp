# recommendation_dialog.py (or wherever you placed it)
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import re # Import re for potential advanced validation

# Default values (can be adjusted)
DEFAULT_REC_VOL = 20.0  # Default IV % for recommendation input
DEFAULT_REC_DTE = 30    # Default DTE for recommendation input
DEFAULT_REC_BUDGET = 1000.0 # Default Risk Budget $
TARGET_ADJUST_FACTOR = 1.05 # Factor to auto-adjust target if inconsistent (e.g., 5%)

class RecommendationInputDialog(simpledialog.Dialog):
    """
    A custom dialog window to gather user inputs for strategy recommendation.
    Includes input validation and normalization.
    """
    def __init__(self, parent, title, initial_price=100.0):
        self.initial_price = initial_price
        # Store input variables (use specific types)
        self.ticker_var = tk.StringVar()
        self.current_price_var = tk.DoubleVar(value=initial_price)
        self.iv_var = tk.DoubleVar(value=DEFAULT_REC_VOL) # Use % input
        self.predicted_iv_var = tk.DoubleVar(value=DEFAULT_REC_VOL)
        self.target_price_var = tk.DoubleVar(value=initial_price) # Default to current
        self.direction_var = tk.StringVar(value="Neutral")
        self.confidence_var = tk.IntVar(value=75) # Default confidence %
        self.dte_var = tk.IntVar(value=DEFAULT_REC_DTE)
        self.risk_budget_var = tk.DoubleVar(value=DEFAULT_REC_BUDGET)
        self.prefer_defined_risk_var = tk.StringVar(value="Yes") # Default Yes
        self.result = None # To store results if OK is pressed
        super().__init__(parent, title)

    def body(self, master):
        """Creates the dialog body layout."""
        master.pack_configure(padx=15, pady=10) # Add padding

        # Use grid layout for better alignment
        frame = ttk.Frame(master)
        frame.pack(fill=tk.BOTH, expand=True)
        col_count = 4 # Use 4 columns for label/entry pairs

        # --- Row 0 ---
        ttk.Label(frame, text="Ticker:").grid(row=0, column=0, padx=5, pady=4, sticky='w')
        ticker_entry = ttk.Entry(frame, textvariable=self.ticker_var, width=12)
        ticker_entry.grid(row=0, column=1, padx=5, pady=4, sticky='ew')
        ticker_entry.focus_set() # Start cursor here

        ttk.Label(frame, text="Current Price:").grid(row=0, column=2, padx=5, pady=4, sticky='w')
        price_entry = ttk.Entry(frame, textvariable=self.current_price_var, width=12)
        price_entry.grid(row=0, column=3, padx=5, pady=4, sticky='ew')

         # --- Row 1 ---
        ttk.Label(frame, text="Implied Vol (%):").grid(row=1, column=0, padx=5, pady=4, sticky='w')
        iv_entry = ttk.Entry(frame, textvariable=self.iv_var, width=12)
        iv_entry.grid(row=1, column=1, padx=5, pady=4, sticky='ew')

        ttk.Label(frame, text="Predicted Vol (%):").grid(row=1, column=2, padx=5, pady=4, sticky='w') # Next column
        pred_iv_entry = ttk.Entry(frame, textvariable=self.predicted_iv_var, width=12)
        pred_iv_entry.grid(row=1, column=3, padx=5, pady=4, sticky='ew') # Column after label

        # --- Row 2 --- 
        ttk.Label(frame, text="Direction View:").grid(row=2, column=0, padx=5, pady=4, sticky='w') # Moved to row 2, col 0
        direction_combo = ttk.Combobox(frame, textvariable=self.direction_var,
                                    values=["Bullish", "Bearish", "Neutral"],
                                    state="readonly", width=10)
        direction_combo.grid(row=2, column=1, padx=5, pady=4, sticky='ew') # Moved to row 2, col 1

        # Target Price and Confidence now shift to Row 3, etc. Adjust all subsequent row numbers accordingly.

        # Example:
        # --- Row 3 --- 
        ttk.Label(frame, text="Target Price:").grid(row=3, column=0, padx=5, pady=4, sticky='w')
        target_entry = ttk.Entry(frame, textvariable=self.target_price_var, width=12)
        target_entry.grid(row=3, column=1, padx=5, pady=4, sticky='ew')

        ttk.Label(frame, text="Confidence (%):").grid(row=3, column=2, padx=5, pady=4, sticky='w')
        conf_entry = ttk.Entry(frame, textvariable=self.confidence_var, width=12)
        conf_entry.grid(row=3, column=3, padx=5, pady=4, sticky='ew')

        # --- Row 4 --- 
        # DTE and Risk Budget...
        ttk.Label(frame, text="Days to Expiry (DTE):").grid(row=4, column=0, padx=5, pady=4, sticky='w')
        dte_entry = ttk.Entry(frame, textvariable=self.dte_var, width=12)
        dte_entry.grid(row=4, column=1, padx=5, pady=4, sticky='ew')

        ttk.Label(frame, text="Risk Budget ($):").grid(row=4, column=2, padx=5, pady=4, sticky='w')
        budget_entry = ttk.Entry(frame, textvariable=self.risk_budget_var, width=12)
        budget_entry.grid(row=4, column=3, padx=5, pady=4, sticky='ew')


        # --- Row 5 --- 
        # Prefer Defined Risk...
        ttk.Label(frame, text="Prefer Defined Risk:").grid(row=5, column=0, padx=5, pady=4, sticky='w')
        defined_combo = ttk.Combobox(frame, textvariable=self.prefer_defined_risk_var,
                                    values=["Yes", "No"], state="readonly", width=10)
        defined_combo.grid(row=5, column=1, padx=5, pady=4, sticky='ew')

        # Make columns expandable
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        return ticker_entry # initial focus

    def validate(self):
        """Validates the user inputs."""
        try:
            # Retrieve values first
            cp = self.current_price_var.get()
            tp = self.target_price_var.get()
            direction = self.direction_var.get()
            ticker_raw = self.ticker_var.get()

            # Basic Validation
            if cp <= 0: raise ValueError("Current Price must be positive.")

            iv = self.iv_var.get()
            if iv <= 0: raise ValueError("Implied Volatility must be positive.")

            pred_iv = self.predicted_iv_var.get()
            if pred_iv <= 0: raise ValueError("Predicted Volatility must be positive.")

            conf = self.confidence_var.get()
            if not (0 <= conf <= 100): raise ValueError("Confidence must be between 0 and 100.")

            dte = self.dte_var.get()
            if dte <= 0: raise ValueError("DTE must be positive.")

            budget = self.risk_budget_var.get()
            if budget <= 0: raise ValueError("Risk budget must be positive.")

            ticker = ticker_raw.strip().upper() # Fix #7: Normalize ticker
            if not ticker: raise ValueError("Ticker cannot be empty.")
            # Optional: Add more robust ticker validation using regex if needed
            # if not re.match("^[A-Z0-9.^]{1,5}$", ticker): # Example for US stock tickers
            #     raise ValueError("Ticker format appears invalid.")
            self.ticker_var.set(ticker) # Update the entry with normalized value

            # Fix #1: Handle Inconsistent Target Price
            target_adjusted = False
            if direction == "Bullish" and tp <= cp:
                 original_tp = tp
                 tp = cp * TARGET_ADJUST_FACTOR
                 self.target_price_var.set(round(tp, 2)) # Update the entry field
                 target_adjusted = True
                 warning_msg = f"Target Price ({original_tp:.2f}) was below Current Price ({cp:.2f}) for Bullish view. Auto-adjusted to {tp:.2f}."
            elif direction == "Bearish" and tp >= cp:
                 original_tp = tp
                 tp = cp / TARGET_ADJUST_FACTOR # Adjust downwards
                 self.target_price_var.set(round(tp, 2)) # Update the entry field
                 target_adjusted = True
                 warning_msg = f"Target Price ({original_tp:.2f}) was above Current Price ({cp:.2f}) for Bearish view. Auto-adjusted to {tp:.2f}."
            elif direction == "Neutral" and tp != cp:
                # If neutral, maybe target should ideally be current price? Optional.
                # self.target_price_var.set(round(cp, 2))
                pass # Allow neutral target to differ for now

            if target_adjusted:
                messagebox.showwarning("Input Adjusted", warning_msg, parent=self)
                # We adjusted, so validation passes for this check, but let user know.

            return True # Validation successful (potentially after adjustment)

        except (tk.TclError, ValueError) as e:
            messagebox.showerror("Input Error", f"Invalid input: {e}", parent=self)
            return False # Keep dialog open

    def apply(self):
        """Processes validated inputs and stores them in self.result."""
        # Values should be valid now due to validate()
        current_price = self.current_price_var.get()
        target_price = self.target_price_var.get() # Use potentially adjusted value
        move_percent = ((target_price - current_price) / current_price * 100) if current_price != 0 else 0

        self.result = {
            "ticker": self.ticker_var.get(), # Already normalized
            "current_price": current_price,
            "iv_percent": self.iv_var.get(),
            "predicted_iv_percent": self.predicted_iv_var.get(),
            "target_price": target_price,
            "direction": self.direction_var.get(),
            "confidence": self.confidence_var.get(),
            "dte": self.dte_var.get(),
            "risk_budget": self.risk_budget_var.get(),
            "prefer_defined_risk": self.prefer_defined_risk_var.get() == "Yes",
            # --- Calculated fields ---
            "move_percent": move_percent,
            "iv": self.iv_var.get() / 100.0, # Convert IV to decimal for calculations
            "predicted_iv": self.predicted_iv_var.get() / 100.0 # Convert to decimal
        }

class RecommendationResultsDialog(simpledialog.Dialog):
    """Displays a ranked list of recommended strategies and allows selection."""

    def __init__(self, parent, title, recommendations):
        """
        Args:
            recommendations (list): List of tuples:
                (score, name, justification_notes, description)
        """
        self.recommendations = recommendations
        self.selected_strategy = None # Store the name of the selected strategy
        super().__init__(parent, title)

    def body(self, master):
        master.pack_configure(padx=10, pady=10)
        master.config(width=600, height=400) # Give it some size

        ttk.Label(master, text="Top Recommended Strategies:", font=('Helvetica', 12, 'bold')).pack(pady=(0, 10))

        # --- Use a Treeview for structured display ---
        columns = ("Score", "Strategy", "Notes")
        self.tree = ttk.Treeview(master, columns=columns, show="headings", height=5) # Show 5 rows initially

        self.tree.heading("Score", text="Score")
        self.tree.column("Score", width=60, anchor='center')
        self.tree.heading("Strategy", text="Strategy")
        self.tree.column("Strategy", width=150, anchor='w')
        self.tree.heading("Notes", text="Key Considerations / Justification")
        self.tree.column("Notes", width=350, anchor='w') # Wider for notes

        # Add data to Treeview
        for i, (score, name, notes, desc) in enumerate(self.recommendations):
            # Truncate long notes for display in tree if needed
            display_notes = (notes[:100] + '...') if len(notes) > 100 else notes
            self.tree.insert("", tk.END, iid=i, values=(f"{score:.0f}", name, display_notes))

        self.tree.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # --- Description Area ---
        self.desc_label = ttk.Label(master, text="Select a strategy above to see details.", wraplength=580, justify=tk.LEFT)
        self.desc_label.pack(fill=tk.X, pady=5)

        # Bind selection event to update description
        self.tree.bind("<<TreeviewSelect>>", self.on_strategy_select)

        return self.tree # Initial focus

    def on_strategy_select(self, event=None):
        """Updates the description label when a strategy is selected."""
        selected_item = self.tree.selection()
        if not selected_item:
            self.desc_label.config(text="Select a strategy above to see details.")
            return

        item_index = self.tree.index(selected_item[0])
        if 0 <= item_index < len(self.recommendations):
            score, name, notes, description = self.recommendations[item_index]
            self.desc_label.config(text=f"Details for {name}:\n\n{description}\n\nNotes: {notes}")
        else:
             self.desc_label.config(text="Error displaying details.")


    def buttonbox(self):
        """Creates custom Apply and Cancel buttons."""
        box = ttk.Frame(self)

        apply_button = ttk.Button(box, text="Apply Selected Strategy", width=20, command=self.ok, default=tk.ACTIVE)
        apply_button.pack(side=tk.LEFT, padx=15, pady=10)
        cancel_button = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        cancel_button.pack(side=tk.LEFT, padx=5, pady=10)

        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)

        box.pack()

    def validate(self):
        """Checks if a strategy was selected before applying."""
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("No Selection", "Please select a strategy from the list to apply.", parent=self)
            return False
        return True

    def apply(self):
        """Stores the selected strategy name."""
        selected_item = self.tree.selection()
        # Assuming validate() ensures selection exists
        item_index = self.tree.index(selected_item[0])
        self.selected_strategy = self.recommendations[item_index][1] # Get the name (index 1)