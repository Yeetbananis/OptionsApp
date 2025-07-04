import tkinter as tk
from tkinter import ttk, messagebox

class LoadAnalysisWindow(tk.Toplevel):
    """
    A professional UI for loading, searching, and deleting saved analyses,
    now with a themed notes preview and right-click to edit.
    """
    def __init__(self, parent, controller, persistence_manager, load_callback):
        super().__init__(parent)
        self.title("Load Saved Analysis")
        self.geometry("850x700")
        self.transient(parent)
        self.grab_set()

        # Get a reference to the main app controller to access theme settings
        self.controller = controller
        self.manager = persistence_manager
        self.load_callback = load_callback
        self.all_data = self.manager.get_all_analyses()

        self._build_widgets()
        self._populate_tree()
        self.controller.apply_theme_to_window(self)

    def _build_widgets(self):
        main_pane = ttk.PanedWindow(self, orient=tk.VERTICAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        top_frame = ttk.Frame(main_pane)
        top_frame.rowconfigure(1, weight=1)
        top_frame.columnconfigure(0, weight=1)
        main_pane.add(top_frame, weight=3)

        filter_frame = ttk.Frame(top_frame)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self._on_filter_changed)
        ttk.Entry(filter_frame, textvariable=self.filter_var).pack(fill=tk.X, expand=True)

        cols = ('name', 'ticker', 'date')
        self.tree = ttk.Treeview(top_frame, columns=cols, show='headings', selectmode='browse')
        self.tree.heading('name', text='Analysis Name', command=lambda: self._sort_column('name', False))
        self.tree.heading('ticker', text='Ticker', command=lambda: self._sort_column('ticker', False))
        self.tree.heading('date', text='Date Saved', command=lambda: self._sort_column('date', False))
        self.tree.column('name', width=350); self.tree.column('ticker', width=100); self.tree.column('date', width=200)
        self.tree.grid(row=1, column=0, sticky='nsew')
        
        # --- Bind Events ---
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        self.tree.bind("<Double-1>", self._on_load)
        self.tree.bind("<Button-3>", self._on_tree_right_click) # **NEW**: Right-click binding

        scrollbar = ttk.Scrollbar(top_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky='ns')

        notes_frame = ttk.LabelFrame(main_pane, text="Notes Preview", padding=10)
        main_pane.add(notes_frame, weight=1)
        notes_frame.rowconfigure(0, weight=1)
        notes_frame.columnconfigure(0, weight=1)

        # **FIX**: Get theme colors and apply them to the tk.Text widget
        theme_settings = self.controller.theme_settings()
        text_bg = theme_settings['entry_bg']
        text_fg = theme_settings['fg']
        
        self.notes_preview = tk.Text(
            notes_frame, height=5, wrap='word', relief='flat', state='disabled',
            font=("Segoe UI", 9), background=text_bg, foreground=text_fg,
            selectbackground=theme_settings.get('select_bg', 'blue'),
            selectforeground=theme_settings.get('select_fg', 'white'),
            insertbackground=text_fg # Sets the cursor color
        )
        self.notes_preview.grid(row=0, column=0, sticky='nsew')

        btn_frame = ttk.Frame(self, padding=(10, 10, 10, 10))
        btn_frame.pack(fill=tk.X)
        btn_frame.columnconfigure(0, weight=1)
        ttk.Button(btn_frame, text="View/Edit Notes", command=self._on_edit_notes).grid(row=0, column=1, padx=5)
        ttk.Button(btn_frame, text="Delete Selected", command=self._on_delete).grid(row=0, column=2, padx=5)
        ttk.Button(btn_frame, text="Load Selected", style="Accent.TButton", command=self._on_load).grid(row=0, column=3, padx=5)
        ttk.Button(btn_frame, text="Close", command=self.destroy).grid(row=0, column=4, padx=5)

    def _populate_tree(self, data=None):
        self.tree.delete(*self.tree.get_children())
        records_to_show = data if data is not None else self.all_data
        for item in records_to_show:
            self.tree.insert('', 'end', iid=item['id'], values=(item['metadata']['name'], item['analysis_data'].get('ticker', 'N/A'), item['metadata']['timestamp'].split('T')[0]))
    
    def _on_filter_changed(self, *args):
        query = self.filter_var.get().lower()
        if not query: self._populate_tree(); return
        filtered_data = [item for item in self.all_data if query in item['metadata']['name'].lower() or query in item['analysis_data'].get('ticker', '').lower()]
        self._populate_tree(filtered_data)

    def _sort_column(self, col, reverse):
        key_map = {'name': lambda i: i['metadata']['name'], 'ticker': lambda i: i['analysis_data'].get('ticker', ''), 'date': lambda i: i['metadata']['timestamp']}
        if col in key_map:
            self.all_data.sort(key=key_map[col], reverse=reverse)
            self.tree.heading(col, command=lambda: self._sort_column(col, not reverse))
            self._populate_tree()

    def _on_selection_changed(self, event=None):
        selected_id = self.tree.focus()
        if not selected_id: return
        selected_item = next((item for item in self.all_data if item['id'] == selected_id), None)
        notes = selected_item['metadata'].get('notes', 'No notes for this analysis.') if selected_item else ''
        self.notes_preview.config(state='normal')
        self.notes_preview.delete('1.0', tk.END)
        self.notes_preview.insert('1.0', notes)
        self.notes_preview.config(state='disabled')

    def _on_tree_right_click(self, event):
        """Handles right-click on the treeview to show an edit menu."""
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id) # Select the item under the cursor
            self.tree.focus(item_id)
            
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="View/Edit Notes", command=self._on_edit_notes)
            menu.tk_popup(event.x_root, event.y_root)
            
    def _on_edit_notes(self):
        selected_id = self.tree.focus()
        if not selected_id:
            messagebox.showwarning("No Selection", "Please select an analysis to edit its notes.", parent=self)
            return
        
        selected_item = next((item for item in self.all_data if item['id'] == selected_id), None)
        if not selected_item: return

        win = tk.Toplevel(self)
        win.title(f"Edit Notes for: {selected_item['metadata']['name']}")
        win.geometry("500x400")
        win.transient(self)
        win.grab_set()
        self.controller.apply_theme_to_window(win)

        frame = ttk.Frame(win, padding=10)
        frame.pack(expand=True, fill=tk.BOTH)
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)

        theme_settings = self.controller.theme_settings()
        notes_text = tk.Text(
            frame, wrap='word', relief='solid', borderwidth=1, font=("Segoe UI", 10),
            background=theme_settings['entry_bg'], foreground=theme_settings['fg'],
            selectbackground=theme_settings.get('select_bg', 'blue'),
            selectforeground=theme_settings.get('select_fg', 'white'),
            insertbackground=theme_settings['fg']
        )
        notes_text.grid(row=0, column=0, sticky='nsew')
        notes_text.insert('1.0', selected_item['metadata'].get('notes', ''))
        
        btn_frame = ttk.Frame(frame, padding=(0,10,0,0))
        btn_frame.grid(row=1, column=0, sticky='e')

        def on_save():
            new_notes = notes_text.get("1.0", tk.END).strip()
            self.manager.update_analysis_notes(selected_id, new_notes)
            selected_item['metadata']['notes'] = new_notes
            self._on_selection_changed()
            win.destroy()

        ttk.Button(btn_frame, text="Save", command=on_save, style="Accent.TButton").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=win.destroy).pack(side=tk.LEFT)

    def _on_load(self, event=None):
        selected_id = self.tree.focus()
        if not selected_id: return
        selected_analysis = self.manager.analyses.get(selected_id)
        if selected_analysis:
            self.load_callback(selected_analysis['analysis_data'])
            self.destroy()

    def _on_delete(self):
        selected_id = self.tree.focus()
        if not selected_id: return
        name = self.tree.item(selected_id)['values'][0]
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the analysis:\n'{name}'?", parent=self):
            if self.manager.delete_analysis(selected_id):
                self.all_data = self.manager.get_all_analyses()
                self._populate_tree()