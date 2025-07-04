import tkinter as tk
from tkinter import ttk
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.patches as patches

class LoadingScreen(tk.Toplevel):
    """
    Final polished version of the loading screen with robust boundary detection
    and guaranteed candle body visibility.
    """
    def __init__(self, parent, trader_name="Trader", theme="dark"):
        super().__init__(parent)
        self.overrideredirect(True)

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
        
        self.config(bg=self.colors['BG_COLOR'])
        width, height = 1200, 800
        screen_width, screen_height = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = (screen_width / 2) - (width / 2), (screen_height / 2) - (height / 2)
        self.geometry(f'{width}x{height}+{int(x)}+{int(y)}')
        
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

        self.candles = []
        self.price_velocity = 0.0
        self.in_pre_climax_mode = False
        self.is_finale_triggered = False
        self._setup_chart()

    def _setup_chart(self, x_min=0, x_max=1):
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
        
        self.ax.text(x_min + 0.02, self.entry_price + 1.5, 'Entry Price', color=self.colors['ENTRY_LINE_COLOR'], fontsize=10, va='bottom')
        self.ax.text(x_min + 0.02, self.tp_level - 1.5, 'Take Profit', color=self.colors['UP_CANDLE_COLOR'], fontsize=10, va='top', alpha=0.7)
        self.ax.text(x_min + 0.02, self.sl_level + 1.5, 'Stop Loss', color=self.colors['DOWN_CANDLE_COLOR'], fontsize=10, va='bottom')

        self.ax.set_xlim(x_min, x_max)
        self.ax.set_ylim(self.sl_level * 0.95, self.tp_level * 1.05)
        self.fig.tight_layout()

    def add_new_candle(self):
        """Draws one new candle with natural, boundary-aware momentum."""
        if not self.candles:
            open_price = self.entry_price
        else:
            open_price = self.candles[-1]['close']

        # **FIX**: Increased distance for boundary detection to trigger reversals sooner.
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
        
        # **FIX**: Enforce a minimum change to prevent flat "line" candles.
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
        candle_width = 0.03
        candle_spacing = 0.045
        view_width_candles = 20
        num_candles = len(self.candles)
        view_start_index = max(0, num_candles - view_width_candles)
        x_min = view_start_index * candle_spacing
        x_max = (view_start_index + view_width_candles) * candle_spacing
        
        self._setup_chart(x_min, x_max)

        for i, candle in enumerate(self.candles):
            x_pos = (i + 1) * candle_spacing
            if x_pos < x_min - candle_spacing: continue
            
            is_final_candle = candle.get('is_finale', False)
            color = self.colors['TAKE_PROFIT_COLOR'] if is_final_candle else (self.colors['UP_CANDLE_COLOR'] if candle['close'] >= candle['open'] else self.colors['DOWN_CANDLE_COLOR'])
            
            self.ax.plot([x_pos, x_pos], [candle['low'], candle['high']], color=color, linewidth=1.5, zorder=5)
            body = patches.Rectangle((x_pos - candle_width/2, candle['open']), candle_width, candle['close'] - candle['open'], facecolor=color, zorder=10)
            self.ax.add_patch(body)

        self.canvas.draw()
        
    def trigger_pre_climax_dip(self):
        self.in_pre_climax_mode = True

    def animate_take_profit(self):
        self.is_finale_triggered = True
        if not self.candles: return
        
        open_price = self.candles[-1]['close']
        close_price = self.tp_level
        self.candles.append({
            'open': open_price, 'close': close_price, 'high': close_price,
            'low': open_price, 'is_finale': True
        })
        self._draw_candles()
        
        candle_spacing = 0.045
        x_pos = len(self.candles) * candle_spacing
        self.ax.plot(x_pos, close_price, "o", markersize=15, markerfacecolor=self.colors['TAKE_PROFIT_COLOR'], markeredgecolor='white', alpha=0.7)
        self.canvas.draw()

    def update_progress_bar(self, percent):
        self.progress_bar['value'] = percent * 100

    def fade_out_and_close(self):
        alpha = self.attributes("-alpha")
        if alpha > 0.0:
            alpha -= 0.08
            self.attributes("-alpha", alpha)
            self.after(40, self.fade_out_and_close)
        else:
            self.destroy()