import tkinter as tk
import threading
import queue
import time

class AssistantHUD:
    """
    Sleek, modern floating overlay banner at the bottom-center of the screen,
    resembling Google Assistant / Siri / Windows Copilot glowing pill indicator.
    """
    def __init__(self):
        self.cmd_queue = queue.Queue()
        self.thread = threading.Thread(target=self._run_ui, daemon=True, name="JarvisHUDThread")
        self.root = None
        self.canvas = None
        self.label = None
        self.sub_label = None
        self.dots = []
        self.animating = False
        self.anim_step = 0
        self.state = "hidden"
        self.thread.start()

    def _run_ui(self):
        self.root = tk.Tk()
        self.root.title("Jarvis Voice HUD")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)

        # Style colors
        self.bg_color = "#10141D"
        self.accent_color = "#00D2FF"
        self.text_color = "#FFFFFF"
        self.dim_color = "#8A99AD"

        self.root.configure(bg=self.bg_color)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        # HUD Dimensions
        hud_w = 420
        hud_h = 74
        x = (screen_width - hud_w) // 2
        y = screen_height - hud_h - 45  # Floating just above the taskbar

        self.root.geometry(f"{hud_w}x{hud_h}+{x}+{y}")

        # Rounded Container Frame
        self.frame = tk.Frame(self.root, bg=self.bg_color, highlightbackground="#00A3FF", highlightthickness=2)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Left Glowing Indicator Canvas (Google Assistant / Siri Style Dots)
        self.canvas = tk.Canvas(self.frame, width=54, height=54, bg=self.bg_color, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, padx=(14, 8), pady=10)

        # Four animated glowing dots (Cyan, Blue, Indigo, Bright Cyan)
        self.dot_colors = ["#00F0FF", "#0080FF", "#7000FF", "#00FFC2"]
        self.dot_ids = []
        for i in range(4):
            dx = 8 + i * 11
            d = self.canvas.create_oval(dx, 22, dx + 8, 30, fill=self.dot_colors[i], outline="")
            self.dot_ids.append(d)

        # Center Text Box
        text_frame = tk.Frame(self.frame, bg=self.bg_color)
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=10)

        self.label = tk.Label(
            text_frame,
            text="JARVIS",
            font=("Segoe UI", 12, "bold"),
            fg=self.accent_color,
            bg=self.bg_color,
            anchor="w"
        )
        self.label.pack(fill=tk.X)

        self.sub_label = tk.Label(
            text_frame,
            text="Listening...",
            font=("Segoe UI", 9),
            fg=self.text_color,
            bg=self.bg_color,
            anchor="w"
        )
        self.sub_label.pack(fill=tk.X)

        # Start hidden initially
        self.root.withdraw()
        self._check_queue()
        self._animate()
        self.root.mainloop()

    def _animate(self):
        if self.state in ("listening", "thinking", "speaking"):
            self.anim_step = (self.anim_step + 1) % 100
            for i, dot_id in enumerate(self.dot_ids):
                # Bouncing sine wave animation like Google Assistant dots
                import math
                offset = math.sin((self.anim_step * 0.28) + (i * 0.8)) * 7
                dx = 8 + i * 11
                cy = 26 + offset
                self.canvas.coords(dot_id, dx, cy - 4, dx + 8, cy + 4)
        if self.root:
            self.root.after(30, self._animate)

    def _check_queue(self):
        try:
            while not self.cmd_queue.empty():
                cmd, args = self.cmd_queue.get_nowait()
                if cmd == "show":
                    title, msg, state = args
                    self.state = state
                    self.label.config(text=title.upper())
                    self.sub_label.config(text=msg)
                    if state == "listening":
                        self.label.config(fg="#00F0FF")
                        self.frame.config(highlightbackground="#00E5FF")
                    elif state == "thinking":
                        self.label.config(fg="#FFB800")
                        self.frame.config(highlightbackground="#FFB800")
                    elif state == "speaking":
                        self.label.config(fg="#00FF9D")
                        self.frame.config(highlightbackground="#00FF9D")
                    self.root.deiconify()
                elif cmd == "hide":
                    self.state = "hidden"
                    self.root.withdraw()
        except Exception:
            pass

        if self.root:
            self.root.after(50, self._check_queue)

    def show_listening(self, query: str = "Listening for your command..."):
        self.cmd_queue.put(("show", ("🎙️ Jarvis", query, "listening")))

    def show_thinking(self, query: str = "Thinking..."):
        self.cmd_queue.put(("show", ("⚡ Jarvis", query, "thinking")))

    def show_speaking(self, reply: str = "Responding..."):
        display_text = reply[:50] + "..." if len(reply) > 50 else reply
        self.cmd_queue.put(("show", ("🔊 Jarvis", display_text, "speaking")))

    def hide(self):
        self.cmd_queue.put(("hide", None))

# Global singleton instance
_hud_instance = None

def get_hud() -> AssistantHUD:
    global _hud_instance
    if _hud_instance is None:
        _hud_instance = AssistantHUD()
    return _hud_instance

def show_hud_listening(message: str = "Listening for your command..."):
    get_hud().show_listening(message)

def show_hud_thinking(message: str = "Thinking..."):
    get_hud().show_thinking(message)

def show_hud_speaking(message: str = "Responding..."):
    get_hud().show_speaking(message)

def hide_hud():
    get_hud().hide()

if __name__ == "__main__":
    hud = get_hud()
    print("Testing HUD...")
    hud.show_listening("Speak now, Sir...")
    time.sleep(3)
    hud.show_thinking("Analyzing your schedule...")
    time.sleep(2)
    hud.show_speaking("You have a meeting tomorrow at 10 AM.")
    time.sleep(3)
    hud.hide()
    time.sleep(1)
