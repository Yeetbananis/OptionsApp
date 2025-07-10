import tkinter as tk
from tkinter import ttk
import sys
import threading
import queue

class TextRedirector:
    """A helper class to redirect stdout/stderr to a Tkinter Text widget."""
    def __init__(self, widget, queue):
        self.widget = widget
        self.queue = queue
        self.stdout = sys.stdout # Keep a reference to the original stdout
        self.stderr = sys.stderr # Keep a reference to the original stderr

    def write(self, text):
        self.queue.put(text)
        # Also write to the original stdout/stderr for continued console visibility in dev
        self.stdout.write(text)

    def flush(self):
        self.stdout.flush()

class DebugConsoleWindow(tk.Toplevel):
    """A Toplevel window that displays console output."""
    def __init__(self, parent, theme="dark"):
        super().__init__(parent)
        self.title("Debug Console Output")
        self.geometry("800x600")
        self.protocol("WM_DELETE_WINDOW", self.hide_window) # Hide on close, don't destroy

        # Apply theme
        bg_color = '#1c1e22' if theme == 'dark' else '#f0f0f0'
        fg_color = '#f0f0f0' if theme == 'dark' else '#000000'
        text_bg = '#333b4f' if theme == 'dark' else '#e0e0e0'
        text_fg = '#f0f0f0' if theme == 'dark' else '#000000'

        self.config(bg=bg_color)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.console_text = tk.Text(self, wrap="word", bg=text_bg, fg=text_fg,
                                    font=("Consolas", 10), bd=0, highlightthickness=0)
        self.console_text.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.console_text.config(state="disabled") # Make it read-only

        # Scrollbar
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.console_text.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.console_text.config(yscrollcommand=vsb.set)

        self.output_queue = queue.Queue()
        self.redirector = TextRedirector(self.console_text, self.output_queue)
        
        # This will be called by OptionAnalyzerApp to actually redirect stdout/stderr
        self.is_active = False # Flag to manage redirection

        self._poll_queue() # Start polling for new output

    def start_redirection(self):
        if not self.is_active:
            sys.stdout = self.redirector
            sys.stderr = self.redirector
            self.is_active = True
            print("Console output redirected to debug window.") # This will appear in the window itself

    def stop_redirection(self):
        if self.is_active:
            sys.stdout = self.redirector.stdout # Restore original stdout
            sys.stderr = self.redirector.stderr # Restore original stderr
            self.is_active = False
            print("Console output redirection stopped.") # This will appear in original console (if any)

    def _poll_queue(self):
        """Polls the queue for new text and updates the Text widget."""
        try:
            while True:
                line = self.output_queue.get_nowait()
                self.console_text.config(state="normal")
                self.console_text.insert(tk.END, line)
                self.console_text.see(tk.END) # Auto-scroll to the bottom
                self.console_text.config(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_queue) # Poll every 100 ms

    def hide_window(self):
        """Hides the window instead of destroying it."""
        self.withdraw()

    def show_window(self):
        """Shows the window if it's hidden."""
        self.deiconify()
        self.lift() # Bring to front