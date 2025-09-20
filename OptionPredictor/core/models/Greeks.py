import tkinter as tk
from tkinter import ttk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import numpy as np
from scipy.stats import norm

class Greeks:
    def __init__(self, root, greek_inputs, S0, T_days, dark_mode=False):
        self.root = root
        self.greek_inputs = greek_inputs
        self.S0 = S0
        self.T = T_days / 365
        self.dark_mode = dark_mode
        self.K = self.S0  # or actual strike input
        self.r = 0.04
        self.sigma = 0.25
        self._canvases = []



        self.second_order = {
            'vomma': 0.2,
            'vanna': 0.1,
            'charm': -0.05,
            'zomma': 0.03,
            'color': -0.02,
            'speed': 0.12,
            'ultima': 0.07,
            'epsilon': 0.05,
            'lambda': 1.5
        }


        self.setup_ui()
        

    def setup_ui(self):
        self.win = tk.Toplevel(self.root)
        self.win.title("Greek Sensitivity Analysis")
        self.win.geometry("1100x800")

        self.bg_color = "#000000" if self.dark_mode else "#f0f0f0"
        self.fg_color = "#f0f0f0" if self.dark_mode else "#000000"

        self.win.configure(bg=self.bg_color)

        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(expand=True, fill=tk.BOTH)

        self.create_risk_tab()
        self.create_greek_charts()
        self.create_multi_greek_plot()
        self.create_second_order_tab()
        self.create_second_order_explainer()

    def style_widget(self, widget):
        try:
            widget.configure(background=self.bg_color, foreground=self.fg_color)
        except:
            pass



    def create_second_order_explainer(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📚 2nd Order Breakdown")

        # Match colors to theme
        bg = self.bg_color
        fg = self.fg_color

        # Scrollable canvas setup
        canvas = tk.Canvas(frame, bg=bg, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)

        scroll_frame = ttk.Frame(canvas, style="TFrame")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Force scroll_frame width to match canvas width
            canvas.itemconfig(window_id, width=canvas.winfo_width())

        window_id = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        # Force an initial update so content renders immediately
        frame.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))
        canvas.itemconfig(window_id, width=canvas.winfo_width())

        scroll_frame.bind("<Configure>", _on_frame_configure)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # === Two-column layout ===
        left_col = ttk.Frame(scroll_frame, style="TFrame")
        right_col = ttk.Frame(scroll_frame, style="TFrame")

        left_col.pack(side="left", fill="both", expand=True, padx=20, pady=10)
        right_col.pack(side="left", fill="both", expand=True, padx=20, pady=10)

        # All your sections
        sections = {
            "Charm (Delta Decay)": (
                "Charm measures how Delta (your sensitivity to stock price) changes as time passes. It's especially relevant near expiry when Delta changes more rapidly.",
                "Example: If Charm is -0.05, your Delta drops by 0.05 each day. If Delta was 0.60 today, it might be 0.55 tomorrow. This means you'll profit less from price moves as time passes.",
                "Example Use Case: A trader long gamma sees strong P&L from price moves early in the week. As the week closes, even with big price moves, gamma is gone — less opportunity to profit. Important when timing gamma scalps.",
                "Who uses it: Short-dated options traders. Risk desks modeling theta/gamma interaction. Firms selling weekly or zero-day options.",
                "📈 Analogy:\nDelta = speed\nCharm = brake pedal\nEach day that passes, your speed (Delta) reduces — so you earn less per $1 move, like slowly coasting to a stop."
            ),
            "Vanna (Delta-Vega Link)": (
                "Vanna captures how Delta changes when volatility changes, or how Vega changes with price. It's critical for understanding how volatility skew shifts your risk.",
                "Example: A Vanna of +0.08 means if implied volatility increases 1%, your Delta increases by 0.08. Useful for traders who gamma scalp and adjust deltas constantly.",
                "Example Use Case: Useful for gamma scalpers adjusting deltas as volatility spikes or drops. Helps manage hedges more responsively.",
                "Who uses it: Skew traders, market makers, dispersion desks.",
                "📈 Analogy:\nDelta = your steering\nVanna = wind on the road\nWhen volatility changes, it’s like a gust of wind nudging your car — you need to constantly correct your steering to stay on course."
            ),
            "Vomma (Volga)": (
                "Vomma is the rate of change of Vega with respect to volatility. In simpler terms, it tells you how your Vega exposure itself changes when vol moves.",
                "Example: Vomma of +0.3 means if vol rises 1%, Vega increases by 0.3. If Vega was 0.5, it becomes 0.8. This means your option becomes more reactive to vol changes.",
                "Example Use Case: Important for traders long Vega via straddles or strangles, especially when expecting vol breakouts.",
                "Who uses it: Volatility arbitrage desks, earnings traders, long vol hedge funds.",
                "📈 Analogy:\nVega = speed\nVomma = acceleration\nSlope of Vomma = how violently your acceleration is changing → like your car jerking forward/backward. High Vomma slope = ultra-sensitive option."
            ),
            "Zomma (Gamma Sensitivity to Volatility)": (
                "Zomma tracks how Gamma changes as volatility changes. This affects the curvature of Delta exposure — crucial when trying to hold hedges over large moves.",
                "Example: If Zomma is -0.1, rising vol reduces Gamma. So if you're long Gamma expecting sharp moves, rising vol may actually reduce your edge.",
                "Example Use Case: Important for hedging big swings in low-vol vs high-vol environments.",
                "Who uses it: Risk managers, convexity traders, exotic derivatives desks.",
                "📈 Analogy:\nGamma = how sharply you can turn\nZomma = road condition\nAs vol rises, the road might get slicker — you can’t turn (adjust Delta) as easily. Hedging becomes harder."
            ),
            "Color (Gamma Decay Over Time)": (
                "Color shows how Gamma decays over time. Gamma tells you how fast Delta changes — Color shows how fast that sensitivity fades.",
                "Example: Color = -0.02 means Gamma drops 0.02 each day. If Gamma was 0.10 today, it might be 0.08 tomorrow. This means less curvature = flatter P&L over time.",
                "Example Use Case: A gamma-heavy position that generates large P&L from price moves will flatten out and make less as time decays Gamma away.",
                "Who uses it: Short gamma desks, hedging teams, options desks writing short-dated contracts.",
                "📈 Analogy:\nGamma = steering sharpness\nColor = rust over time\nEach passing day rusts your steering wheel a little — it becomes harder to steer effectively (adjust to price moves)."
            ),
            "Speed (Gamma Acceleration)": (
                "Speed measures how Gamma changes with stock price. It's the second derivative of Delta w.r.t. price — showing convexity acceleration.",
                "Example: If Speed = 0.1, and stock rises $1, your Gamma increases by 0.1. More Gamma = stronger Delta sensitivity ahead.",
                "Example Use Case: Traders hedging large directional positions with convexity risk.",
                "Who uses it: Exotic options desks, institutional gamma scalpers.",
                "📈 Analogy:\nGamma = steering curve\nSpeed = how fast that curve steepens — more curve means more whip as you turn!"
            ),
            "Ultima (Vol-of-Vol Sensitivity)": (
                "Ultima measures how Vomma (vega acceleration) changes with volatility. It’s the third derivative of option price w.r.t. vol.",
                "Example: Ultima = 0.07 → when vol explodes, Vega gets turbo-charged. For long-vol traders, this signals massive convexity.",
                "Example Use Case: Earnings plays with sudden vol pops, tail risk hedging.",
                "Who uses it: Long vol hedge funds, tail risk desks, exotic vol traders.",
                "📈 Analogy:\nVomma = pedal to accelerate Vega\nUltima = turbo boost button. Push it and Vega surges even faster."
            ),
            "Epsilon (Dividend Sensitivity)": (
                "Epsilon shows how option price reacts to dividend changes. A $1 dividend increase reduces call value by Epsilon.",
                "Example: If Epsilon = 0.05 and SPY increases its dividend $1, your call drops $0.05.",
                "Example Use Case: Relevant when trading options near ex-div dates or on dividend-heavy names like SPY, AAPL.",
                "Who uses it: Dividend arbitrageurs, structured product desks.",
                "📈 Analogy:\nDividend = gravity\nEpsilon = how much that gravity pulls your option down when dividend increases."
            ),
            "Lambda (Leverage Ratio)": (
                "Lambda is the ratio of % change in option price to % change in stock. It quantifies option leverage — how much bang for your buck.",
                "Example: Lambda = 2.0 → if stock rises 1%, your option rises 2%.",
                "Example Use Case: Used when comparing option returns to stock. Helpful when structuring leveraged trades.",
                "Who uses it: Retail directional traders, leverage funds, options screeners.",
                "📈 Analogy:\nLambda = turbo boost\nIf stock rises, your option rises faster — like putting your trade on steroids."
            )
        }

        # Alternate sections left/right
        for i, (title, (desc, example, use_case, who_uses, analogy)) in enumerate(sections.items()):
            target_col = left_col if i % 2 == 0 else right_col
            ttk.Label(target_col, text=title, font=("Helvetica", 14, "bold"), foreground="#004488").pack(anchor='w', pady=(20, 5))
            ttk.Label(target_col, text=desc, wraplength=450, justify="left").pack(anchor='w', padx=10)
            ttk.Label(target_col, text=example, wraplength=450, justify="left", foreground="gray").pack(anchor='w', padx=10, pady=(3, 5))
            ttk.Label(target_col, text=use_case, wraplength=450, justify="left", foreground="gray").pack(anchor='w', padx=10, pady=(0, 3))
            ttk.Label(target_col, text=who_uses, wraplength=450, justify="left", foreground="gray").pack(anchor='w', padx=10, pady=(0, 5))
            ttk.Label(target_col, text=analogy, wraplength=450, justify="left", foreground="#336699", font=("Helvetica", 9, "italic")).pack(anchor='w', padx=10, pady=(0, 15))
            
                # --- Force redraw when this tab is selected ---
        def _on_tab_changed(event, frame=frame, canvas=canvas, window_id=window_id):
            current = event.widget.nametowidget(event.widget.select())
            if current is frame:
                try:
                    w = frame.winfo_width() or frame.winfo_reqwidth()
                    h = frame.winfo_height() or frame.winfo_reqheight()
                    canvas.itemconfig(window_id, width=w)
                    canvas.configure(scrollregion=canvas.bbox("all"))
                    canvas.update_idletasks()
                except Exception:
                    pass

        # bind only once for this notebook
        if not hasattr(self, "_second_order_tab_bound"):
            self.notebook.bind("<<NotebookTabChanged>>", _on_tab_changed)
            self._second_order_tab_bound = True



    def create_risk_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="⚠️ Risk")

        headers = ["Parameter", "Change", "Impact", "Greek"]
        first_order = [
            ("📂 Stock Price", "+$1", f"+${self.greek_inputs.get('delta', 0):.2f}", "Delta"),
            ("🌀 Gamma Effect", "+$1 again", f"+${self.greek_inputs.get('gamma', 0):.2f}", "Gamma"),
            ("⏳ 1 day passes", "-1 day", f"{self.greek_inputs.get('theta', 0):+.2f}", "Theta"),
            ("📉 Volatility +1%", "+1%", f"{self.greek_inputs.get('vega', 0):+.2f}", "Vega"),
            ("🏦 Rate +0.25%", "+0.25%", f"{self.greek_inputs.get('rho', 0) * 0.25:.2f}", "Rho")
        ]

        second_order = [
            ("⌛ Delta Decay", "1 day passes", f"{self.second_order.get('charm', 0):+.2f}", "Charm"),
            ("🎯 Delta-Vega Link", "Volatility -1%", f"{self.second_order.get('vanna', 0):+.2f}", "Vanna"),
            ("📈 Vega Sensitivity", "Volatility +1%", f"{self.second_order.get('vomma', 0):+.2f}", "Vomma"),
            ("📊 Gamma Sensitivity", "Volatility +1%", f"{self.second_order.get('zomma', 0):+.2f}", "Zomma"),
            ("🩸 Gamma Decay", "1 day passes", f"{self.second_order.get('color', 0):+.2f}", "Color"),
            ("🚀 Gamma Acceleration", "+$1 again", f"{self.second_order.get('speed', 0):+.2f}", "Speed"),
            ("🧨 Vol-of-Vol Sensitivity", "Volatility +1%", f"{self.second_order.get('ultima', 0):+.2f}", "Ultima"),
            ("💸 Dividend Impact", "Div ↑ by $1", f"{self.second_order.get('epsilon', 0):+.2f}", "Epsilon"),
            ("📊 Option Leverage", "+1% Underlying", f"{self.second_order.get('lambda', 0):+.2f}", "Lambda")
        ]


        all_rows = first_order + second_order

        for col, header in enumerate(headers):
            ttk.Label(frame, text=header, font=("Helvetica", 10, "bold")).grid(row=0, column=col, padx=10, pady=8)

        explanations = {
            "Delta": "Delta tells you how much your option price will change for a $1 move in the stock. If Delta is +0.6, a $1 increase in the stock raises your option value by ~$0.60.",
            "Gamma": "Gamma shows how much your Delta changes as the stock price moves. A positive Gamma means Delta rises faster as the stock moves, increasing your gain potential per $1.",
            "Theta": "Theta shows how much your option price changes each day. A Theta of -0.10 means your option loses $0.10 in value every day from time decay.",
            "Vega": "Vega measures how much your option price changes for a 1% change in implied volatility. A Vega of +0.20 means the option price increases by ~$0.20 if volatility rises 1%.",
            "Rho": "Rho tells you how much your option price changes if interest rates rise 1%. A Rho of +0.5 means a 1% rate hike raises the option price by ~$0.50.",

            "Charm": "Charm shows how your Delta changes over time. For example, if Charm is -0.05, your Delta drops by 0.05 each day, meaning your sensitivity to stock moves declines daily.",
            "Vanna": "Vanna measures how Delta changes when volatility changes or how Vega shifts when stock price moves. A Vanna of -0.03 means Delta drops by 0.03 for every 1% drop in volatility.",
            "Vomma": "Vomma shows how Vega changes with volatility. If Vomma is +0.10, your Vega increases by 0.10 if volatility rises 1%, meaning your option becomes more sensitive to further vol shifts.",
            "Zomma": "Zomma explains how Gamma reacts to volatility changes. For example, if Zomma is +0.02, your Gamma increases by that much if vol rises, affecting Delta's curvature.",
            "Color": "Color shows how Gamma changes with time. If Color is -0.01, your Gamma drops by 0.01 every day, slowly reducing your ability to benefit from acceleration in price movement."
        }

        total = 0
        for row, (param, change, impact, greek) in enumerate(all_rows, start=1):
            val = self.greek_inputs.get(greek.lower(), 0) if greek.lower() in self.greek_inputs else self.second_order.get(greek.lower(), 0)
            if greek.lower() == 'rho':
                val *= 0.25
            total += val
            for col, val_txt in enumerate((param, change, impact, greek)):
                ttk.Label(frame, text=val_txt).grid(row=row, column=col, padx=10, pady=5)
            ttk.Label(frame, text=explanations.get(greek, ""), font=("Helvetica", 8, "italic"), foreground="gray").grid(row=row, column=4, padx=10, pady=5, sticky="w")

        ttk.Label(frame, text="TOTAL", font=("Helvetica", 10, "bold")).grid(row=len(all_rows)+1, column=2, padx=10, pady=10)
        ttk.Label(frame, text=f"${total:+.2f}", font=("Helvetica", 10, "bold")).grid(row=len(all_rows)+1, column=3, padx=10, pady=10)

        dashboard = ttk.Frame(frame)
        dashboard.grid(row=1, column=5, rowspan=len(all_rows)+1, padx=20, pady=10, sticky="ns")

        for greek in ['delta', 'gamma', 'vega', 'theta', 'rho',
              'charm', 'vanna', 'vomma', 'zomma', 'color',
              'speed', 'ultima', 'epsilon', 'lambda']:
            val = abs(self.greek_inputs.get(greek, 0)) if greek in self.greek_inputs else abs(self.second_order.get(greek, 0))
            color = "green"
            if val > 0.75:
                color = "red"
            elif val > 0.3:
                color = "orange"
            lbl = tk.Label(dashboard, text=f"{greek.capitalize()}: {val:+.2f}", bg=color, fg="white", width=22)
            lbl.pack(pady=2)

    


  


    # Replace your create_greek_charts with this implementation:
    def create_greek_charts(self):
        from matplotlib.figure import Figure

        # local colors based on theme (explicit, avoids global rc changes)
        bg = "#1e1e1e" if self.dark_mode else "#ffffff"
        fg = "#f0f0f0" if self.dark_mode else "#000000"

        # helper to style each Axes so theme is always correct
        def _style_axes(ax):
            ax.set_facecolor(bg)
            ax.title.set_color(fg)
            ax.xaxis.label.set_color(fg)
            ax.yaxis.label.set_color(fg)
            ax.tick_params(colors=fg)
            for spine in ax.spines.values():
                spine.set_color(fg)

        # Greek list
        greeks = ['delta', 'gamma', 'vega', 'theta', 'rho']

        for greek in greeks:
            # Create a Figure object (not pyplot) — isolate from global state
            fig = Figure(figsize=(10, 4), dpi=100, facecolor=bg)
            axs = fig.subplots(1, 2)

            # prepare data
            x_price = np.linspace(self.S0 * 0.8, self.S0 * 1.2, 100)
            x_time = np.linspace(1, max(1, int(self.T * 365)), 100)
            base_val = self.greek_inputs.get(greek, 0)

            if greek == 'delta':
                y_price = base_val * (1 / (1 + np.exp(-0.2 * (x_price - self.S0))))
            elif greek == 'gamma':
                y_price = base_val * np.exp(-((x_price - self.S0) ** 2) / (2 * (self.S0 * 0.05) ** 2))
            elif greek == 'vega':
                y_price = base_val * np.exp(-((x_price - self.S0) ** 2) / (2 * (self.S0 * 0.1) ** 2))
            else:
                y_price = np.full_like(x_price, base_val)

            if greek == 'theta':
                y_time = base_val * np.exp(-x_time / 60)
            elif greek == 'vega':
                y_time = base_val * np.exp(-x_time / 100)
            elif greek == 'gamma':
                decay_constant = 50
                y_time = base_val * np.exp(-x_time / decay_constant)
            else:
                y_time = np.full_like(x_time, base_val)

            # draw
            axs[0].plot(x_price, y_price)
            axs[0].set_title(f"{greek.capitalize()} vs Price")
            axs[0].set_xlabel("Stock Price")
            axs[0].set_ylabel(greek.capitalize())
            axs[0].grid(True)

            axs[1].plot(x_time, y_time)
            axs[1].set_title(f"{greek.capitalize()} vs Time")
            axs[1].set_xlabel("Days to Expiry")
            axs[1].set_ylabel(greek.capitalize())
            axs[1].grid(True)

            # style axes explicitly
            _style_axes(axs[0])
            _style_axes(axs[1])

            # tighten layout once (will be refined on resize)
            fig.tight_layout()

            # create the tab/frame and attach FigureCanvasTkAgg
            chart_frame = ttk.Frame(self.notebook)
            self.notebook.add(chart_frame, text=f"📊 {greek.capitalize()} Chart")

            canvas = FigureCanvasTkAgg(fig, master=chart_frame)
            widget = canvas.get_tk_widget()
            widget.pack(expand=True, fill=tk.BOTH)

            # debounce redraw when frame resizes so matplotlib computes bounding box correctly
            last_after = {"id": None}
            def _on_config(e, c=canvas, f=fig, frame=chart_frame):
                # throttle frequent configure events
                if last_after["id"]:
                    try:
                        frame.after_cancel(last_after["id"])
                    except Exception:
                        pass
                def _do_resize_and_draw():
                    try:
                        w = frame.winfo_width() or frame.winfo_reqwidth()
                        h = frame.winfo_height() or frame.winfo_reqheight()
                        dpi = f.get_dpi()
                        # set figure size to match widget size (in inches)
                        f.set_size_inches(max(0.1, w / dpi), max(0.1, h / dpi))
                        f.tight_layout()
                        c.draw_idle()
                        c.get_tk_widget().update_idletasks()
                    except Exception:
                        pass
                last_after["id"] = frame.after(60, _do_resize_and_draw)

            chart_frame.bind("<Configure>", _on_config)

            # store for tab-change redraw
            self._canvases.append((chart_frame, canvas, fig))

        # ensure the notebook tab-change handler is bound once
        try:
            # bind only once
            if not getattr(self, "_notebook_tab_bound", False):
                self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
                self._notebook_tab_bound = True
        except Exception:
            pass


    # Add this helper method (inside the class)
    def _on_tab_changed(self, event):
        """
        When user switches tabs, force the active tab's canvas/figure to resize and redraw.
        This resolves the common Matplotlib-on-Notebook cropping problem.
        """
        try:
            current_frame = event.widget.nametowidget(event.widget.select())
        except Exception:
            current_frame = None

        for frame, canvas, fig in getattr(self, "_canvases", []):
            if frame is current_frame:
                try:
                    w = frame.winfo_width() or frame.winfo_reqwidth()
                    h = frame.winfo_height() or frame.winfo_reqheight()
                    dpi = fig.get_dpi()
                    fig.set_size_inches(max(0.1, w / dpi), max(0.1, h / dpi))
                    fig.tight_layout()
                    canvas.draw_idle()
                    canvas.get_tk_widget().update_idletasks()
                except Exception:
                    pass



    def create_multi_greek_plot(self):
        if self.dark_mode:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="\ud83d\udcca Multi-Greek Plot")

        fig, ax = plt.subplots(figsize=(6, 4))
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.get_tk_widget().pack(expand=True, fill=tk.BOTH)

        checkbox_frame = ttk.Frame(frame)
        checkbox_frame.pack(pady=5)

        greeks = ['delta', 'gamma', 'vega', 'theta', 'rho']
        vars = {g: tk.BooleanVar(value=True) for g in greeks}

        def plot():
            ax.clear()
            x = np.linspace(self.S0 * 0.8, self.S0 * 1.2, 100)
            for g in greeks:
                if vars[g].get():
                    val = self.greek_inputs.get(g, 0)
                    if g == 'delta':
                        y = val * (1 / (1 + np.exp(-0.2 * (x - self.S0))))
                    elif g == 'gamma':
                        y = val * np.exp(-((x - self.S0) ** 2) / (2 * (self.S0 * 0.05) ** 2))
                    elif g == 'vega':
                        y = val * np.exp(-((x - self.S0) ** 2) / (2 * (self.S0 * 0.1) ** 2))
                    else:
                        y = np.full_like(x, val)
                    ax.plot(x, y, label=g.capitalize())
            ax.set_title("Greeks vs Price")
            ax.set_xlabel("Stock Price")
            ax.set_ylabel("Greek Value")
            ax.grid(True)
            ax.legend()
            canvas.draw()

        for g in greeks:
            ttk.Checkbutton(checkbox_frame, text=g.capitalize(), variable=vars[g], command=plot).pack(side=tk.LEFT, padx=4)

        plot()

    def create_second_order_tab(self):
        if self.dark_mode:
            plt.style.use('dark_background')
        else:
            plt.style.use('default')

        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📉 2nd Order Greeks")

        control_frame = ttk.Frame(frame)
        control_frame.pack(pady=10)

        greek_var = tk.StringVar(value="vomma")
        dropdown = ttk.OptionMenu(control_frame, greek_var, "vomma", 
            "vomma", "vanna", "charm", "zomma", "color", 
            "speed", "ultima", "epsilon", "lambda")
        dropdown.pack(side=tk.LEFT, padx=10)

        mode_var = tk.StringVar(value="price")
        toggle = ttk.Checkbutton(control_frame, text="X-Axis: Time", variable=mode_var, onvalue="time", offvalue="price", command=lambda: plot())
        toggle.pack(side=tk.LEFT, padx=10)

        fig, ax = plt.subplots(figsize=(7, 4))
        canvas = FigureCanvasTkAgg(fig, master=frame)
        canvas.get_tk_widget().pack(expand=True, fill=tk.BOTH)

        desc_var = tk.StringVar()
        desc_label = ttk.Label(frame, textvariable=desc_var, wraplength=1000, font=("Helvetica", 9, "italic"))
        desc_label.pack(pady=10)

        descriptions = {
            'vomma': "Vomma (Volga): Measures sensitivity of Vega to volatility. Affects volatility-based pricing changes.",
            'vanna': "Vanna: Measures sensitivity of Delta to volatility or Vega to price. Important for skew changes.",
            'charm': "Charm (Delta decay): Measures how Delta changes over time. Affects early assignment risk.",
            'zomma': "Zomma: Measures sensitivity of Gamma to volatility. Affects curvature as volatility shifts.",
            'color': "Color: Measures sensitivity of Gamma to time. Important for Gamma decay and risk management.", 
            'speed': "Speed: Measures change in Gamma with respect to price. Captures convexity acceleration in directional moves.",
            'ultima': "Ultima: Measures how Vomma changes with volatility. Shows how Vega acceleration explodes with vol-of-vol.",
            'epsilon': "Epsilon: Measures change in option price with respect to dividend. Relevant for dividend-paying underlyings.",
            'lambda': "Lambda: Measures option leverage — % change in option value for % move in underlying stock."
        }

        def compute_lambda(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            C = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
            delta = norm.cdf(d1)
            with np.errstate(divide='ignore', invalid='ignore'):
                lam = np.where(C > 0, (delta * S) / C, 0)
            return lam
        
        def compute_vomma(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            vega = S * norm.pdf(d1) * np.sqrt(T)
            vomma = vega * d1 * d2 / sigma
            return vomma
        
        def compute_vanna(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            vanna = -norm.pdf(d1) * d1 / sigma
            return vanna
        
        def compute_charm(S, K, T, r, sigma, option_type='call'):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            charm = -norm.pdf(d1) * (2 * r * T - d2 * sigma * np.sqrt(T)) / (2 * T * sigma * np.sqrt(T))
            if option_type == 'put':
                charm = -charm
            return charm
        
        def compute_zomma(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            zomma = norm.pdf(d1) * ((d1 * d2 - 1) / (S**2 * sigma**2 * T))
            return zomma

        def compute_color(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            color = -norm.pdf(d1) / (2 * S * T * sigma * np.sqrt(T)) * (2 * r * T + 1 + d1 * (d2 - d1))
            return color
        
        def compute_speed(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
            speed = -gamma / S * (d1 / (sigma * np.sqrt(T)) + 1)
            return speed
        
        def compute_ultima(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            vega = S * norm.pdf(d1) * np.sqrt(T)
            ultima = -vega * d1 * d2 * (1 - d1 * d2) / (sigma ** 2)
            return ultima
        
        def compute_epsilon(S, K, T, r, sigma):
            d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
            d2 = d1 - sigma * np.sqrt(T)
            epsilon = -norm.cdf(d2) * np.exp(-r * T)
            return epsilon



        def plot():
            greek = greek_var.get()
            x = np.linspace(self.S0 * 0.8, self.S0 * 1.2, 100) if mode_var.get() == 'price' else np.linspace(1, self.T * 365, 100)
            base = self.second_order.get(greek, 0)

            if greek == 'vomma':
                y = compute_vomma(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'vanna':
                y = compute_vanna(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'charm':
                y = compute_charm(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'zomma':
                y = compute_zomma(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'color':
                y = compute_color(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'speed':
                y = compute_speed(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'ultima':
                y = compute_ultima(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'epsilon':
                y = compute_epsilon(x, self.K, self.T, self.r, self.sigma)
            elif greek == 'lambda':
                delta = self.greek_inputs.get('delta', 0.6)
                r = self.r
                sigma = self.sigma
                T = self.T
                K = self.K

                d1 = (np.log(x / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
                d2 = d1 - sigma * np.sqrt(T)
                option_price = x * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)

                y = compute_lambda(x, K, T, r, sigma)  # correct full input set


            ax.clear()
            ax.plot(x, y)
            ax.set_title(f"{greek.capitalize()} vs {'Time' if mode_var.get() == 'time' else 'Price'}")
            ax.set_xlabel("Days to Expiry" if mode_var.get() == 'time' else "Stock Price")
            ax.set_ylabel(greek.capitalize())
            ax.grid(True)
            canvas.draw()
            desc_var.set(descriptions[greek])

        greek_var.trace_add("write", lambda *args: plot())
        plot()

    