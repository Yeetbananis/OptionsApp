import time
import tkinter as tk

class BounceOverlay:
    BOUNCE_LOSS = 0.8    # energy retained on bounce
    THROW_FACTOR = 0.02  # mouse-throw speed multiplier
    FRAME_DELAY = 30     # ms between frames
    SQUASH_FRAMES = 5    # how many frames to show squash

    def __init__(self, master):
        self.win = master
        self._bouncing = False
        self._overlay = None
        self._ball = {}
        self._ball_grabbed = False

    def start(self):
        if self._bouncing:
            return
        self._bouncing = True

        # create transparent overlay
        self._overlay = tk.Toplevel(self.win)
        self._overlay.overrideredirect(True)
        self._overlay.lift(self.win)
        self._overlay.attributes("-topmost", True)

        magic = "#ff00ff"
        self._overlay.config(bg=magic)
        self._overlay.attributes("-transparentcolor", magic)

        # initial geometry + canvas
        self._update_geometry()
        w, h = self._size
        self._canvas = tk.Canvas(self._overlay, bg=magic, highlightthickness=0)
        self._canvas.pack(fill="both", expand=True)

        # initial ball state
        r = min(w, h) * 0.05
        self._ball = {
            "x": w/2, "y": h/2,
            "vx": w * 0.005, "vy": h * 0.004,
            "r": r,
            "squash_dir": None,
            "squash_frames": 0
        }
        self._last_drag = {"x": 0, "y": 0, "t": time.time()}

        # bind grab/throw
        self._canvas.bind("<ButtonPress-1>",   self._on_press)
        self._canvas.bind("<B1-Motion>",       self._on_motion)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)

        self._bounce_step()

    def stop(self):
        self._bouncing = False
        if self._overlay:
            self._overlay.destroy()
            self._overlay = None

    def _update_geometry(self):
        x = self.win.winfo_rootx()
        y = self.win.winfo_rooty()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        self._overlay.geometry(f"{w}x{h}+{x}+{y}")
        self._size = (w, h)

    def _bounce_step(self):
        if not self._bouncing or not self._overlay:
            return
        self._update_geometry()
        w, h = self._size
        b = self._ball

        if not self._ball_grabbed:
            # move
            b["x"] += b["vx"]
            b["y"] += b["vy"]

            # bounce X
            if b["x"] - b["r"] < 0:
                b["x"] = b["r"]
                b["vx"] = -b["vx"] * self.BOUNCE_LOSS
                b["squash_dir"], b["squash_frames"] = "x", self.SQUASH_FRAMES
            elif b["x"] + b["r"] > w:
                b["x"] = w - b["r"]
                b["vx"] = -b["vx"] * self.BOUNCE_LOSS
                b["squash_dir"], b["squash_frames"] = "x", self.SQUASH_FRAMES

            # bounce Y
            if b["y"] - b["r"] < 0:
                b["y"] = b["r"]
                b["vy"] = -b["vy"] * self.BOUNCE_LOSS
                b["squash_dir"], b["squash_frames"] = "y", self.SQUASH_FRAMES
            elif b["y"] + b["r"] > h:
                b["y"] = h - b["r"]
                b["vy"] = -b["vy"] * self.BOUNCE_LOSS
                b["squash_dir"], b["squash_frames"] = "y", self.SQUASH_FRAMES

        # squash effect
        if b["squash_frames"] > 0:
            sf = 0.5 + 0.5 * (b["squash_frames"] / self.SQUASH_FRAMES)
            if b["squash_dir"] == "x":
                rw, rh = 2*b["r"]*(2 - sf), 2*b["r"]*sf
            else:
                rw, rh = 2*b["r"]*sf, 2*b["r"]*(2 - sf)
            b["squash_frames"] -= 1
        else:
            rw = rh = 2*b["r"]

        # draw
        self._canvas.delete("ball")
        self._canvas.create_oval(
            b["x"] - rw/2, b["y"] - rh/2,
            b["x"] + rw/2, b["y"] + rh/2,
            fill="orange", outline="", tags="ball"
        )

        self._overlay.after(self.FRAME_DELAY, self._bounce_step)

    def _on_press(self, ev):
        b = self._ball
        if (ev.x - b["x"])**2 + (ev.y - b["y"])**2 <= b["r"]**2:
            self._ball_grabbed = True
            self._last_drag = {"x": ev.x, "y": ev.y, "t": time.time()}

    def _on_motion(self, ev):
        if not self._ball_grabbed:
            return
        now = time.time()
        prev = self._last_drag
        dt = now - prev["t"]
        if dt > 0:
            # update velocity from drag
            self._ball["vx"] = (ev.x - prev["x"]) / dt * self.THROW_FACTOR
            self._ball["vy"] = (ev.y - prev["y"]) / dt * self.THROW_FACTOR
        # move ball with cursor
        self._ball["x"], self._ball["y"] = ev.x, ev.y
        self._last_drag = {"x": ev.x, "y": ev.y, "t": now}

    def _on_release(self, ev):
        self._ball_grabbed = False
