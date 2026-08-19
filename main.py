import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sv_ttk

from player import AudioEngine
from marks import MarkList
from ui import TimingMarkerApp, AUDIO_TYPES


def enable_dpi_awareness():
    """On Windows, declare the process DPI-aware so the app and its native
    file dialogs render crisply on high-DPI displays instead of being
    bitmap-scaled (blurry). Must be called before the Tk root is created."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()    # older fallback
        except (AttributeError, OSError):
            pass


def apply_dpi_scaling(root):
    """Now that the process is DPI-aware, keep point-sized fonts/widgets at
    their intended physical size (otherwise they render tiny on high-DPI
    displays). tk scaling is pixels-per-point = dpi / 72."""
    try:
        dpi = root.winfo_fpixels("1i")
        if dpi > 0:
            root.tk.call("tk", "scaling", dpi / 72.0)
    except tk.TclError:
        pass


def choose_file(root):
    return filedialog.askopenfilename(parent=root, title="Open audio file",
                                      filetypes=AUDIO_TYPES)


def main(argv):
    enable_dpi_awareness()
    root = tk.Tk()
    apply_dpi_scaling(root)
    sv_ttk.set_theme("dark")
    root.title("Song Timing Marker")
    root.geometry("620x580")

    placeholder = ttk.Label(root, text="Choose a song to begin…")
    placeholder.pack(expand=True)
    root.update()  # render the window before the modal dialog appears

    engine = AudioEngine()
    marks = MarkList()
    path = argv[1] if len(argv) > 1 else None

    while True:
        if not path:
            path = choose_file(root)
            if not path:
                root.destroy()
                return 0
        try:
            engine.load(path)
            break
        except Exception as exc:
            messagebox.showerror("Cannot open file",
                                 f"Could not load:\n{path}\n\n{exc}")
            path = None

    placeholder.destroy()
    TimingMarkerApp(root, engine, marks, path=path)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
