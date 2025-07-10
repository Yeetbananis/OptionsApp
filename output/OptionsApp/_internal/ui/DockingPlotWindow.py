import tkinter as tk
from tkinter import ttk
import traceback

# Import your existing plotting functions
from core.engine.MonteCarloSimulation import (
    plot_simulation_paths, plot_distribution,
    plot_profit_heatmap, plot_volatility_surface_3d
)

class DockingPlotWindow(tk.Toplevel):
    """
    A robust, 2x2 docking station for plots that supports dynamic adding,
    removing, and a highly sensitive drag-and-drop repositioning of plots.
    """
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.title("📈 Plot Docking Station")
        self.geometry("1600x900")
        self.controller = controller

        # --- State Management ---
        self.pane_contents = {}
        self.drag_data = {}

        # --- Create a fixed 2x2 grid layout ---
        self.main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        self.left_column = ttk.PanedWindow(self.main_pane, orient=tk.VERTICAL)
        self.right_column = ttk.PanedWindow(self.main_pane, orient=tk.VERTICAL)

        self.panes = {
            "top_left": ttk.Frame(self.left_column, padding=0, borderwidth=2),
            "top_right": ttk.Frame(self.right_column, padding=0, borderwidth=2),
            "bottom_left": ttk.Frame(self.left_column, padding=0, borderwidth=2),
            "bottom_right": ttk.Frame(self.right_column, padding=0, borderwidth=2)
        }
        
        self.main_pane.add(self.left_column, weight=1)
        self.main_pane.add(self.right_column, weight=1)

        self.controller.apply_theme_to_window(self)
        self._update_layout()

    def add_plot(self, plot_type: str, plot_data: dict):
        """Finds the next available pane and plots the data in it."""
        pane_order = ["top_left", "top_right", "bottom_left", "bottom_right"]
        for pane_name in pane_order:
            if pane_name not in self.pane_contents:
                self._plot_in_pane(pane_name, plot_type, plot_data)
                return
        tk.messagebox.showwarning("All Panes Full", "All 4 plot panes are currently in use.", parent=self)

    def remove_plot(self, pane_name: str):
        """Clears a pane, removes its content record, and updates the layout."""
        if pane_name in self.pane_contents:
            del self.pane_contents[pane_name]
        
        self._clear_pane_widgets(self.panes[pane_name])
        self._update_layout()

    def _plot_in_pane(self, pane_name: str, plot_type: str, plot_data: dict):
        """Internal method to render a plot and its controls in a specific pane."""
        pane = self.panes[pane_name]
        self._clear_pane_widgets(pane)

        try:
            self.pane_contents[pane_name] = {'type': plot_type, 'data': plot_data}
            
            is_dark_mode = self.controller.current_theme == 'dark'

            plot_function_map = {
                'simulation_paths': plot_simulation_paths, 'distribution': plot_distribution,
                'heatmap': plot_profit_heatmap, 'vol_surface': plot_volatility_surface_3d
            }
            plot_function = plot_function_map[plot_type]
            
            args, kwargs = [], {'dark_mode': is_dark_mode}
            if plot_type == 'simulation_paths':
                args = [plot_data['sim_days'], plot_data['sample_paths'], plot_data['S0'], plot_data['H'], plot_data['option_type'], plot_data['sigma'], plot_data['probability'], len(plot_data['sample_paths']), plot_data['paths_to_display']]
                kwargs['title'] = f"{plot_data['ticker']} Simulation Paths"
            elif plot_type == 'distribution':
                args = [plot_data['trigger_prices'], plot_data['H'], plot_data['probability'], plot_data['option_type'], plot_data['S0'], plot_data['correct_avg_trigger'], plot_data['correct_std_trigger']]
            elif plot_type == 'heatmap':
                prices, times, profit_m, percent_m, day_lbls, price_lbls, premium = plot_data['heatmap_data']
                args = [prices, times, profit_m, percent_m, day_lbls, price_lbls, premium, plot_data['option_type'], plot_data['strike']]
                kwargs['title'] = "Profit/Loss Heatmap"
            elif plot_type == 'vol_surface':
                p_grid, t_grid, iv_grid = plot_data['vol_surface_data']
                args = [p_grid, t_grid, iv_grid]
                kwargs['title'] = "3D Implied Volatility Surface"

            plot_function(pane, *args, **kwargs)
            
            self._bind_events_to_pane(pane_name)
            self._update_layout()

        except Exception as e:
            self.remove_plot(pane_name)
            ttk.Label(pane, text=f"Failed to render plot:\n{e}", wraplength=400).pack(expand=True)
            traceback.print_exc()

    def _bind_events_to_pane(self, pane_name):
        """Creates and binds all interactive elements for a pane."""
        pane = self.panes.get(pane_name)
        if not pane or not pane.winfo_children(): return
            
        canvas_widget = pane.winfo_children()[0]
        pane.bind("<Button-3>", lambda e, p=pane_name: self._show_context_menu(e, p))
        canvas_widget.bind("<Button-3>", lambda e, p=pane_name: self._show_context_menu(e, p))

        handle = ttk.Label(pane, text="⠿", cursor="hand2", font=("Segoe UI", 12))
        handle.place(x=6, y=6)
        handle.lift()
        handle.bind("<ButtonPress-1>", lambda e, p=pane_name: self._on_drag_start(e, p))

    def _update_layout(self):
        """Shows/hides panes and columns based on active content."""
        for name, pane in self.panes.items():
            parent_col = self.left_column if 'left' in name else self.right_column
            pane.configure(relief='flat') # Reset any drag highlights
            try:
                if name in self.pane_contents:
                    parent_col.add(pane, weight=1)
                else:
                    parent_col.forget(pane)
            except tk.TclError: pass

        for col in [self.left_column, self.right_column]:
            try:
                if col.panes():
                    self.main_pane.add(col, weight=1)
                else:
                    self.main_pane.forget(col)
            except tk.TclError: pass

    def _clear_pane_widgets(self, pane):
        for widget in pane.winfo_children(): widget.destroy()

    def _show_context_menu(self, event, pane_name):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Remove Plot", command=lambda: self.remove_plot(pane_name))
        menu.tk_popup(event.x_root, event.y_root)
        
    def _on_drag_start(self, event, source_pane_name):
        if source_pane_name not in self.pane_contents: return

        self.drag_data = {'source': source_pane_name, 'last_hover': None}
        
        ghost = tk.Toplevel(self)
        ghost.overrideredirect(True)
        ghost.attributes('-alpha', 0.75)
        plot_type = self.pane_contents[source_pane_name]['type'].replace('_', ' ').title()
        ttk.Label(ghost, text=f"  Moving: {plot_type}  ", style="Pill.TButton").pack(padx=10, pady=5)
        self.drag_data['ghost'] = ghost

        self.bind("<B1-Motion>", self._on_drag_motion)
        self.bind("<ButtonRelease-1>", self._on_drag_release)
        self._on_drag_motion(event)

    def _on_drag_motion(self, event):
        if 'ghost' not in self.drag_data: return
        self.drag_data['ghost'].geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
        
        # --- Real-time highlighting for a more sensitive feel ---
        target_name = self._get_pane_at_coords(event.x_root, event.y_root)
        last_hover = self.drag_data.get('last_hover')

        if target_name != last_hover:
            # Reset the old highlighted pane
            if last_hover and last_hover in self.panes:
                self.panes[last_hover].config(relief='flat')
            
            # Highlight the new pane if it's a valid drop target
            if target_name and target_name != self.drag_data['source'] and target_name in self.pane_contents:
                self.panes[target_name].config(relief='solid')
            
            self.drag_data['last_hover'] = target_name

    def _get_pane_at_coords(self, x, y):
        for name, pane in self.panes.items():
            if (pane.winfo_viewable() and
                pane.winfo_rootx() < x < pane.winfo_rootx() + pane.winfo_width() and
                pane.winfo_rooty() < y < pane.winfo_rooty() + pane.winfo_height()):
                return name
        return None

    def _on_drag_release(self, event):
        self.unbind("<B1-Motion>")
        self.unbind("<ButtonRelease-1>")

        if 'ghost' in self.drag_data and self.drag_data.get('ghost'):
            self.drag_data['ghost'].destroy()
        
        source_name = self.drag_data.get('source')
        target_name = self.drag_data.get('last_hover') # Use the last highlighted pane

        # Reset any lingering highlights
        if target_name and target_name in self.panes:
            self.panes[target_name].config(relief='flat')
        
        # Perform the swap
        if source_name and target_name and source_name != target_name:
            source_content = self.pane_contents.pop(source_name)
            
            if target_name in self.pane_contents:
                target_content = self.pane_contents.pop(target_name)
                self._plot_in_pane(source_name, target_content['type'], target_content['data'])

            self._plot_in_pane(target_name, source_content['type'], source_content['data'])
            # After a move to an empty slot, we need to clear the source
            if target_name not in self.pane_contents:
                 self.remove_plot(source_name)

        self.drag_data.clear()