import tkinter as tk
from tkinter import ttk
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches
import time

class LoadingScreen(tk.Toplevel):
    """
    Refactored loading screen with a wider, "zoomed-out" view of the candlestick chart,
    featuring thinner candles and faster plotting for a high-density display.
    Core candle generation and animation logic remain identical to the original.
    """
    def __init__(self, parent, trader_name="Trader", theme="dark"):
        super().__init__(parent)
        self.overrideredirect(True)

        # --- Theme and Color Setup (Unchanged) ---
        dark_theme_colors = {
            "BG_COLOR": "#1c1e22", "TEXT_COLOR": "#f0f0f0", "ENTRY_LINE_COLOR": "#808080",
            "UP_CANDLE_COLOR": "#ffffff", "DOWN_CANDLE_COLOR": "#3498db",
            "TAKE_PROFIT_COLOR": "#00FFFF", "PROGRESS_BAR_COLOR": "#ffffff",
            "PROGRESS_TROUGH_COLOR": "#333b4f"
        }
        light_theme_colors = {
            "BG_COLOR": "#f0f0f0", "TEXT_COLOR": "#000000", "ENTRY_LINE_COLOR": "#808080",
            "UP_CANDLE_COLOR": "#26a69a", "DOWN_CANDLE_COLOR": "#ef5350",
            "TAKE_PROFIT_COLOR": "#00c853", "PROGRESS_BAR_COLOR": "#007bff",
            "PROGRESS_TROUGH_COLOR": "#d6d6d6"
        }
        self.colors = dark_theme_colors if theme == 'dark' else light_theme_colors

        # --- Window Geometry (Unchanged) ---
        self.config(bg=self.colors['BG_COLOR'])
        width, height = 1200, 800
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (screen_width / 2) - (width / 2), (screen_height / 2) - (height / 2)
        self.geometry(f'{width}x{height}+{int(x)}+{int(y)}')

        # --- Main UI Layout (Unchanged) ---
        main_frame = tk.Frame(self, bg=self.colors['BG_COLOR'])
        main_frame.pack(expand=True, fill=tk.BOTH, padx=40, pady=40)

        ttk.Label(
            main_frame, text=f"Welcome, {trader_name}", font=("Segoe UI Semibold", 28),
            background=self.colors['BG_COLOR'], foreground=self.colors['TEXT_COLOR']
        ).pack(pady=(40, 50))

        self.fig = Figure(figsize=(10, 6), dpi=100, facecolor=self.colors['BG_COLOR'])
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=main_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True)

        s = ttk.Style()
        s.theme_use('clam')
        s.configure("Loading.Horizontal.TProgressbar", troughcolor=self.colors['PROGRESS_TROUGH_COLOR'], background=self.colors['PROGRESS_BAR_COLOR'], thickness=5)
        self.progress_bar = ttk.Progressbar(main_frame, orient='horizontal', mode='determinate', length=400, style="Loading.Horizontal.TProgressbar")
        self.progress_bar.pack(pady=(30, 20))

        # --- State Variables (Unchanged) ---
        self.candles = []
        self.price_velocity = 0.0
        self.in_pre_climax_mode = False
        self.is_finale_triggered = False
        self._setup_chart()

    def _setup_chart(self, x_min=0, x_max=1):
        """Sets up the base chart elements like price levels and zones. (Unchanged)"""
        self.ax.clear()
        self.ax.set_facecolor(self.colors['BG_COLOR'])
        self.ax.tick_params(axis='both', colors='none', length=0)
        for spine in self.ax.spines.values():
            spine.set_edgecolor('none')

        self.entry_price = 100
        self.tp_level = 125
        self.sl_level = 75

        self.ax.axhline(y=self.entry_price, color=self.colors['ENTRY_LINE_COLOR'], linestyle='--', linewidth=1)

        tp_zone = patches.Rectangle((x_min, self.entry_price), x_max - x_min, self.tp_level - self.entry_price, facecolor=self.colors['UP_CANDLE_COLOR'], alpha=0.08)
        sl_zone = patches.Rectangle((x_min, self.sl_level), x_max - x_min, self.entry_price - self.sl_level, facecolor=self.colors['DOWN_CANDLE_COLOR'], alpha=0.08)
        self.ax.add_patch(tp_zone)
        self.ax.add_patch(sl_zone)

        self.ax.text(x_min + (x_max - x_min) * 0.01, self.entry_price + 1.5, 'Entry Price', color=self.colors['ENTRY_LINE_COLOR'], fontsize=9, va='bottom')
        self.ax.text(x_min + (x_max - x_min) * 0.01, self.tp_level - 1.5, 'Take Profit', color=self.colors['UP_CANDLE_COLOR'], fontsize=9, va='top', alpha=0.7)
        self.ax.text(x_min + (x_max - x_min) * 0.01, self.sl_level + 1.5, 'Stop Loss', color=self.colors['DOWN_CANDLE_COLOR'], fontsize=9, va='bottom')

        self.ax.set_xlim(x_min, x_max)
        self.ax.set_ylim(self.sl_level * 0.95, self.tp_level * 1.05)
        self.fig.tight_layout()

    def add_new_candle(self):
        """Generates a new candle with the exact same price logic. (Unchanged)"""
        if not self.candles:
            open_price = self.entry_price
        else:
            open_price = self.candles[-1]['close']

        is_near_top = open_price > self.tp_level - 15
        is_near_bottom = open_price < self.sl_level + 15

        if is_near_top:
            self.price_velocity = -abs(self.price_velocity * 0.7)
            random_shock = np.random.normal(-1.0, 1.5)
        elif is_near_bottom:
            self.price_velocity = abs(self.price_velocity * 0.7)
            random_shock = np.random.normal(1.0, 1.5)
        elif self.in_pre_climax_mode:
            random_shock = np.random.normal(-0.5, 1.5)
            self.price_velocity = self.price_velocity * 0.5 + random_shock * 0.4
        else:
            random_shock = np.random.normal(0.4, 2.2)
            self.price_velocity = self.price_velocity * 0.7 + random_shock * 0.5

        change = self.price_velocity + random_shock

        min_body_size = 0.2
        if abs(change) < min_body_size:
            change = min_body_size if change >= 0 else -min_body_size

        close_price = open_price + change
        close_price = np.clip(close_price, self.sl_level + 5, self.tp_level - 5)

        body_size = abs(close_price - open_price)
        high = min(max(open_price, close_price) + np.random.uniform(0.1, 0.4) * body_size + 0.5, self.tp_level - 1)
        low = max(min(open_price, close_price) - np.random.uniform(0.1, 0.4) * body_size - 0.5, self.sl_level + 1)

        self.candles.append({'open': open_price, 'close': close_price, 'high': high, 'low': low})
        self._draw_candles()

    def _draw_candles(self):
        """
        Draws candles with updated parameters for a "zoomed-out" view.
        - Smaller candle width and spacing.
        - Significantly more candles visible in the view.
        """
        # --- MODIFIED PARAMETERS for a zoomed-out view ---
        view_width_candles = 120  # Increased from 20 to show more candles
        total_x_range = 1.0       # Keep the total chart x-axis dimension consistent
        
        # Dynamically calculate width/spacing to fit the desired number of candles
        candle_spacing = total_x_range / view_width_candles
        candle_width = candle_spacing * 0.6 # Maintain a pleasant visual ratio
        # --- END OF MODIFICATIONS ---

        num_candles = len(self.candles)
        view_start_index = max(0, num_candles - view_width_candles)
        
        # The x-axis now represents candle indices * spacing, creating a scrolling effect
        x_min = view_start_index * candle_spacing
        x_max = (view_start_index + view_width_candles) * candle_spacing

        self._setup_chart(x_min, x_max)

        for i, candle in enumerate(self.candles[view_start_index:]):
            actual_index = view_start_index + i
            x_pos = (actual_index + 0.5) * candle_spacing
            
            is_final_candle = candle.get('is_finale', False)
            color = self.colors['TAKE_PROFIT_COLOR'] if is_final_candle else (self.colors['UP_CANDLE_COLOR'] if candle['close'] >= candle['open'] else self.colors['DOWN_CANDLE_COLOR'])

            # Draw candle wick
            self.ax.plot([x_pos, x_pos], [candle['low'], candle['high']], color=color, linewidth=0.8, zorder=5) # Thinner wick
            
            # Draw candle body
            body_height = candle['close'] - candle['open']
            body = patches.Rectangle(
                (x_pos - candle_width / 2, candle['open']),
                candle_width,
                body_height,
                facecolor=color,
                zorder=10
            )
            self.ax.add_patch(body)

        self.canvas.draw()

    def trigger_pre_climax_dip(self):
        """Triggers a temporary downward trend before the finale. (Unchanged)"""
        self.in_pre_climax_mode = True

    def animate_take_profit(self):
        """Animates the final candle hitting the take profit level. (Unchanged logic)"""
        self.is_finale_triggered = True # Set the flag to stop continuous candle generation
        if not self.candles: return

        open_price = self.candles[-1]['close']
        close_price = self.tp_level
        self.candles.append({
            'open': open_price, 'close': close_price, 'high': close_price,
            'low': open_price, 'is_finale': True
        })
        self._draw_candles()
        
        # Redraw the final marker after drawing candles
        candle_spacing = 1.0 / 120 # Use the same spacing as in _draw_candles
        x_pos = (len(self.candles) - 0.5) * candle_spacing
        
        self.ax.plot(x_pos, close_price, "o", markersize=8, markerfacecolor=self.colors['TAKE_PROFIT_COLOR'], markeredgecolor='white', alpha=0.9, zorder=12)
        self.canvas.draw()
        

    def update_progress_bar(self, percent):
        """Updates the loading progress bar. (Unchanged)"""
        self.progress_bar['value'] = percent * 100

    def fade_out_and_close(self):
        """Fades the window out and closes it. (Unchanged)"""
        alpha = self.attributes("-alpha")
        if alpha > 0.0:
            alpha -= 0.08
            self.attributes("-alpha", alpha)
            self.after(40, self.fade_out_and_close)
        else:
            self.destroy()

    def start_animation_loop(self, total_duration_ms: int = 5000, update_interval_ms: int = 5):
        """
        Starts the internal animation loop for this LoadingScreen instance.
        """
        self.total_duration_ms = total_duration_ms
        self.update_interval_ms = update_interval_ms
        self.start_time = time.time()
        self._animation_job = None # To store after ID for cancellation

        # Explicitly call _animation_step to kick off the loop
        self._animation_step_internal()

    def _animation_step_internal(self):
        """Internal step of the animation loop."""
        if self.is_finale_triggered:
            # Animation has finished its finale, stop regular candle drawing
            if self._animation_job:
                self.after_cancel(self._animation_job)
                self._animation_job = None
            return

        elapsed_time = (time.time() - self.start_time) * 1000
        progress_percent = min(elapsed_time / self.total_duration_ms, 1.0)
        
        self.update_progress_bar(progress_percent) # Update progress bar

        self.add_new_candle() # Draw a new candle

        # Trigger pre-climax dip if percentage is met
        if progress_percent >= 0.7 and not self.in_pre_climax_mode:
            self.trigger_pre_climax_dip()

        if progress_percent >= 1.0:
            if not self.is_finale_triggered:
                # This ensures animate_take_profit is called only once at the end
                self.animate_take_profit()
            # The fade_out_and_close is now handled by _hide_loading_overlay in IdeaSuiteView
            # so this internal loop just stops.
        else:
            self._animation_job = self.after(self.update_interval_ms, self._animation_step_internal)

# --- Main Application Logic to run and demonstrate the chart ---
if __name__ == '__main__':
    root = tk.Tk()
    root.withdraw() # Hide the main root window

    loading_screen = LoadingScreen(root, trader_name="Gemini")

    total_duration_ms = 5000  # Total duration of the loading animation
    update_interval_ms = 5   # How often to add a new candle (faster plotting)
    
    start_time = time.time()
    
    def animation_loop():
        elapsed_time = (time.time() - start_time) * 1000
        progress_percent = min(elapsed_time / total_duration_ms, 1.0)
        
        loading_screen.update_progress_bar(progress_percent)
        
        if not loading_screen.is_finale_triggered:
            loading_screen.add_new_candle()

        # Trigger pre-climax dip at 70% progress
        if progress_percent >= 0.7 and not loading_screen.in_pre_climax_mode:
            loading_screen.trigger_pre_climax_dip()

        if progress_percent >= 1.0:
            if not loading_screen.is_finale_triggered:
                loading_screen.animate_take_profit()
            
            # Wait a moment before closing
            root.after(1200, loading_screen.fade_out_and_close)
            root.after(2000, root.quit) # Ensure the main loop exits
        else:
            root.after(update_interval_ms, animation_loop)

    # Start the animation
    root.after(100, animation_loop)
    
    root.mainloop()


 # ui/idea_suite_loading_overlay.py
import tkinter as tk
from tkinter import ttk
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches
import time

class IdeaSuiteLoadingOverlay(ttk.Frame): # Inherit from ttk.Frame
    """
    An embedded loading screen component (ttk.Frame) for the Idea Suite,
    featuring a candlestick chart animation and progress bar.
    It is designed to be placed as an overlay within another widget.
    """
    def __init__(self, parent, trader_name="Trader", theme="dark"):
        super().__init__(parent) # Call ttk.Frame init
        
        # --- Theme and Color Setup ---
        dark_theme_colors = {
            "BG_COLOR": "#1c1e22", "TEXT_COLOR": "#f0f0f0", "ENTRY_LINE_COLOR": "#808080",
            "UP_CANDLE_COLOR": "#ffffff", "DOWN_CANDLE_COLOR": "#3498db",
            "TAKE_PROFIT_COLOR": "#00FFFF", "PROGRESS_BAR_COLOR": "#ffffff",
            "PROGRESS_TROUGH_COLOR": "#333b4f"
        }
        light_theme_colors = {
            "BG_COLOR": "#f0f0f0", "TEXT_COLOR": "#000000", "ENTRY_LINE_COLOR": "#808080",
            "UP_CANDLE_COLOR": "#26a69a", "DOWN_CANDLE_COLOR": "#ef5350",
            "TAKE_PROFIT_COLOR": "#00c853", "PROGRESS_BAR_COLOR": "#007bff",
            "PROGRESS_TROUGH_COLOR": "#d6d6d6"
        }
        self.colors = dark_theme_colors if theme == 'dark' else light_theme_colors

        # --- Frame Configuration ---
        self.config(style="IdeaSuiteLoadingOverlay.TFrame") # Apply a style
        s = ttk.Style()
        s.configure("IdeaSuiteLoadingOverlay.TFrame", background=self.colors['BG_COLOR'])

        # --- Main UI Layout (Inside this Frame) ---
        main_frame = ttk.Frame(self, style="IdeaSuiteLoadingOverlay.TFrame")
        main_frame.pack(expand=True, fill=tk.BOTH, padx=40, pady=40)

        ttk.Label(
            main_frame, text=f"Generating ideas for {trader_name}", font=("Segoe UI Semibold", 28),
            background=self.colors['BG_COLOR'], foreground=self.colors['TEXT_COLOR']
        ).pack(pady=(40, 50))

        self.fig = Figure(figsize=(10, 6), dpi=100, facecolor=self.colors['BG_COLOR'])
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=main_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.pack(fill=tk.BOTH, expand=True)

        s.configure("Loading.Horizontal.TProgressbar", troughcolor=self.colors['PROGRESS_TROUGH_COLOR'], background=self.colors['PROGRESS_BAR_COLOR'], thickness=5)
        self.progress_bar = ttk.Progressbar(main_frame, orient='horizontal', mode='determinate', length=400, style="Loading.Horizontal.TProgressbar")
        self.progress_bar.pack(pady=(30, 20))

        # --- State Variables ---
        self.candles = []
        self.price_velocity = 0.0
        self.in_pre_climax_mode = False
        self.is_finale_triggered = False
        self._animation_job = None # To store after ID for cancellation
        self._setup_chart()

    def _setup_chart(self, x_min=0, x_max=1):
        """Sets up the base chart elements like price levels and zones."""
        self.ax.clear()
        self.ax.set_facecolor(self.colors['BG_COLOR'])
        self.ax.tick_params(axis='both', colors='none', length=0)
        for spine in self.ax.spines.values():
            spine.set_edgecolor('none')

        self.entry_price = 100
        self.tp_level = 125
        self.sl_level = 75

        self.ax.axhline(y=self.entry_price, color=self.colors['ENTRY_LINE_COLOR'], linestyle='--', linewidth=1)

        tp_zone = patches.Rectangle((x_min, self.entry_price), x_max - x_min, self.tp_level - self.entry_price, facecolor=self.colors['UP_CANDLE_COLOR'], alpha=0.08)
        sl_zone = patches.Rectangle((x_min, self.sl_level), x_max - x_min, self.entry_price - self.sl_level, facecolor=self.colors['DOWN_CANDLE_COLOR'], alpha=0.08)
        self.ax.add_patch(tp_zone)
        self.ax.add_patch(sl_zone)

        self.ax.text(x_min + (x_max - x_min) * 0.01, self.entry_price + 1.5, 'Entry Price', color=self.colors['ENTRY_LINE_COLOR'], fontsize=9, va='bottom')
        self.ax.text(x_min + (x_max - x_min) * 0.01, self.tp_level - 1.5, 'Take Profit', color=self.colors['UP_CANDLE_COLOR'], fontsize=9, va='top', alpha=0.7)
        self.ax.text(x_min + (x_max - x_min) * 0.01, self.sl_level + 1.5, 'Stop Loss', color=self.colors['DOWN_CANDLE_COLOR'], fontsize=9, va='bottom')

        self.ax.set_xlim(x_min, x_max)
        self.ax.set_ylim(self.sl_level * 0.95, self.tp_level * 1.05)
        self.fig.tight_layout()

    def add_new_candle(self):
        """Generates a new candle with the exact same price logic."""
        if not self.candles:
            open_price = self.entry_price
        else:
            open_price = self.candles[-1]['close']

        is_near_top = open_price > self.tp_level - 15
        is_near_bottom = open_price < self.sl_level + 15

        if is_near_top:
            self.price_velocity = -abs(self.price_velocity * 0.7)
            random_shock = np.random.normal(-1.0, 1.5)
        elif is_near_bottom:
            self.price_velocity = abs(self.price_velocity * 0.7)
            random_shock = np.random.normal(1.0, 1.5)
        elif self.in_pre_climax_mode:
            random_shock = np.random.normal(-0.5, 1.5)
            self.price_velocity = self.price_velocity * 0.5 + random_shock * 0.4
        else:
            random_shock = np.random.normal(0.4, 2.2)
            self.price_velocity = self.price_velocity * 0.7 + random_shock * 0.5

        change = self.price_velocity + random_shock

        min_body_size = 0.2
        if abs(change) < min_body_size:
            change = min_body_size if change >= 0 else -min_body_size

        close_price = open_price + change
        close_price = np.clip(close_price, self.sl_level + 5, self.tp_level - 5)

        body_size = abs(close_price - open_price)
        high = min(max(open_price, close_price) + np.random.uniform(0.1, 0.4) * body_size + 0.5, self.tp_level - 1)
        low = max(min(open_price, close_price) - np.random.uniform(0.1, 0.4) * body_size - 0.5, self.sl_level + 1)

        self.candles.append({'open': open_price, 'close': close_price, 'high': high, 'low': low})
        self._draw_candles()

    def _draw_candles(self):
        """Draws candles with updated parameters for a "zoomed-out" view."""
        view_width_candles = 120
        total_x_range = 1.0       
        candle_spacing = total_x_range / view_width_candles
        candle_width = candle_spacing * 0.6 

        num_candles = len(self.candles)
        view_start_index = max(0, num_candles - view_width_candles)
        
        x_min = view_start_index * candle_spacing
        x_max = (view_start_index + view_width_candles) * candle_spacing

        self._setup_chart(x_min, x_max)

        for i, candle in enumerate(self.candles[view_start_index:]):
            actual_index = view_start_index + i
            x_pos = (actual_index + 0.5) * candle_spacing
            
            is_final_candle = candle.get('is_finale', False)
            color = self.colors['TAKE_PROFIT_COLOR'] if is_final_candle else (self.colors['UP_CANDLE_COLOR'] if candle['close'] >= candle['open'] else self.colors['DOWN_CANDLE_COLOR'])

            self.ax.plot([x_pos, x_pos], [candle['low'], candle['high']], color=color, linewidth=0.8, zorder=5)
            
            body_height = candle['close'] - candle['open']
            body = patches.Rectangle(
                (x_pos - candle_width / 2, candle['open']),
                candle_width,
                body_height,
                facecolor=color,
                zorder=10
            )
            self.ax.add_patch(body)

        self.canvas.draw()

    def trigger_pre_climax_dip(self):
        """Triggers a temporary downward trend before the finale."""
        self.in_pre_climax_mode = True

    def animate_take_profit(self):
        """Animates the final candle hitting the take profit level."""
        self.is_finale_triggered = True
        if not self.candles: return

        open_price = self.candles[-1]['close']
        close_price = self.tp_level
        self.candles.append({
            'open': open_price, 'close': close_price, 'high': close_price,
            'low': open_price, 'is_finale': True
        })
        self._draw_candles()
        
        # Redraw the final marker after drawing candles
        candle_spacing = 1.0 / 120
        x_pos = (len(self.candles) - 0.5) * candle_spacing
        
        self.ax.plot(x_pos, close_price, "o", markersize=8, markerfacecolor=self.colors['TAKE_PROFIT_COLOR'], markeredgecolor='white', alpha=0.9, zorder=12)
        self.canvas.draw()
        

    def update_progress_bar(self, percent):
        """Updates the loading progress bar."""
        self.progress_bar['value'] = percent * 100
        

    def start_animation_loop(self, total_duration_ms: int = 5000, update_interval_ms: int = 5):
        """Starts the internal animation loop for this instance."""
        self.total_duration_ms = total_duration_ms
        self.update_interval_ms = update_interval_ms
        self.start_time = time.time()
        self._animation_job = None

        self._animation_step_internal()

    def _animation_step_internal(self):
        """Internal step of the animation loop."""
        if self.is_finale_triggered:
            if self._animation_job:
                self.after_cancel(self._animation_job)
                self._animation_job = None
            return

        # No longer using elapsed_time for progress_percent
        # progress_percent is now updated externally via update_progress_bar

        self.update_progress_bar(self.progress_bar['value'] / 100) # Use actual progress bar value for internal logic
        self.add_new_candle()

        # Trigger pre-climax dip if percentage is met (still use external progress bar value)
        if (self.progress_bar['value'] / 100) >= 0.7 and not self.in_pre_climax_mode:
            self.trigger_pre_climax_dip()

        # This loop continues indefinitely until is_finale_triggered is set externally
        self._animation_job = self.after(self.update_interval_ms, self._animation_step_internal)

    def trigger_climax_and_take_profit(self):
        """
        Externally triggered method to initiate the final dip and take-profit animation.
        This is called when all data processing is truly complete.
        """
        if not self.is_finale_triggered: # Only trigger once
            self.update_progress_bar(1.0) # Ensure bar is at 100%
            self.trigger_pre_climax_dip()
            self.animate_take_profit()