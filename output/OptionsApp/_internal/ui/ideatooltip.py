# tooltip.py
import tkinter as tk

class IdeaTooltip:
    """
    Creates a tooltip for a given widget on a Tkinter canvas.
    Binds to a specific canvas item ID for precise hovering.
    """
    def __init__(self, canvas: tk.Canvas, text: str, item_id: int):
        self.canvas = canvas
        self.text = text
        self.item_id = item_id
        self.tip_window = None
        self.id = None
        self.x = self.y = 0

        self.canvas.tag_bind(self.item_id, "<Enter>", self.enter)
        self.canvas.tag_bind(self.item_id, "<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.canvas.after(500, self.showtip) # 500ms delay

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.canvas.after_cancel(id)

    def showtip(self):
        if self.tip_window:
            return
        # Get coordinates relative to the root window
        x = self.canvas.winfo_rootx() + self.canvas.canvasx(0) + self.canvas.coords(self.item_id)[0] + 20
        y = self.canvas.winfo_rooty() + self.canvas.canvasy(0) + self.canvas.coords(self.item_id)[3] + 10
        
        self.tip_window = tw = tk.Toplevel(self.canvas)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{int(x)}+{int(y)}")
        
        label = tk.Label(tw, text=self.text, justify='left',
                      background="#ffffe0", relief='solid', borderwidth=1,
                      font=("Segoe UI", 9, "normal"))
        label.pack(ipadx=4)

    def hidetip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()