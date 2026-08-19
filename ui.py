import os
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox, filedialog
import sv_ttk

AUDIO_TYPES = [("Audio files", "*.flac *.wav *.mp3"), ("All files", "*.*")]


def x_to_seconds(x: float, width: int, duration: float) -> float:
    if width <= 0:
        return 0.0
    frac = min(1.0, max(0.0, x / width))
    return frac * duration


def seconds_to_x(seconds: float, width: int, duration: float) -> float:
    if duration <= 0:
        return 0.0
    frac = min(1.0, max(0.0, seconds / duration))
    return frac * width


def format_mss(seconds: float) -> str:
    seconds = max(0.0, seconds)
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}:{s:02d}"


def format_mssmmm(seconds: float) -> str:
    total_ms = round(max(0.0, seconds) * 1000)
    m, rem_ms = divmod(total_ms, 60000)
    return f"{m}:{rem_ms / 1000:06.3f}"


def format_song_label(metadata: dict, filename: str) -> str:
    def clean(key):
        return ((metadata or {}).get(key) or "").strip()
    artist = clean("artist")
    title = clean("title")
    if artist and title:
        return f"{artist} - {title}"
    if title:
        return title
    if artist:
        return f"{artist} - {filename}"
    return filename


def format_marks_for_clipboard(marks: list) -> str:
    return "\n".join(f"{m:.3f}" for m in marks)


POLL_MS = 50
FLASH_MS = 150
SEEKBAR_WIDTH = 560
SEEKBAR_HEIGHT = 26
CALC_BAR_WIDTH = 120
CALC_BAR_HEIGHT = 14
CALC_TROUGH = "#4a4a4a"
CALC_FILL = "#e0a000"
MARK_FLASH = "#22aa44"
MARK_IDLE_DARK = "#3a3a3a"
MARK_IDLE_LIGHT = "#c8c8c8"
SEEKBAR_BG_DARK = "#4a4a4a"
SEEKBAR_BG_LIGHT = "#d0d0d0"
LISTBOX_BG_DARK = "#2b2b2b"
LISTBOX_FG_DARK = "#eaeaea"
LISTBOX_BG_LIGHT = "#ffffff"
LISTBOX_FG_LIGHT = "#111111"


class TimingMarkerApp:
    """Thin Tkinter shell. All timing math is delegated to the pure
    functions above and to MarkList / AudioEngine."""

    def __init__(self, root, engine, marks, path=""):
        self.root = root
        self.engine = engine
        self.marks = marks
        self.skip_seconds = 10.0
        self._flash_after = None
        self._poll_after = None
        self._resume_pending = False   # auto-resume playback once a stretch is ready
        self._calc_shown = False       # whether the "calculating" bar is visible

        root.title("Song Timing Marker")
        self._init_fonts()
        self._build_widgets()
        self._set_song(path)
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll()

    # --- construction ---

    def _init_fonts(self):
        self.readout_font = tkfont.nametofont("TkFixedFont").copy()
        self.readout_font.configure(size=22, weight="bold")
        self.mark_font = tkfont.nametofont("TkDefaultFont").copy()
        self.mark_font.configure(size=14, weight="bold")
        self.footer_font = tkfont.nametofont("TkDefaultFont").copy()
        self.footer_font.configure(size=9)
        self.tooltip_font = tkfont.nametofont("TkFixedFont").copy()
        self.tooltip_font.configure(size=9)

    def _build_widgets(self):
        pad = {"padx": 8, "pady": 4}

        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, **pad)
        self.filename_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.filename_var).pack(side=tk.LEFT)
        ttk.Button(header, text="◑ Theme", takefocus=0,
                   command=self._toggle_theme).pack(side=tk.RIGHT)
        ttk.Button(header, text="Change Song", takefocus=0,
                   command=self._open_song).pack(side=tk.RIGHT, padx=(0, 6))

        self.pos_var = tk.StringVar(value="0.000 s")
        ttk.Label(self.root, textvariable=self.pos_var,
                  font=self.readout_font).pack()

        self.canvas = tk.Canvas(self.root, width=SEEKBAR_WIDTH,
                                height=SEEKBAR_HEIGHT, highlightthickness=1)
        self.canvas.pack(**pad)
        self._playhead = self.canvas.create_line(0, 0, 0, SEEKBAR_HEIGHT,
                                                  fill="#cc2222", width=2)
        self.canvas.bind("<Button-1>", self._on_seek_click)
        self.canvas.bind("<B1-Motion>", self._on_seek_click)
        self.canvas.bind("<Motion>", self._on_hover)
        self.canvas.bind("<Leave>", self._on_hover_leave)
        self._tooltip = None

        self.dur_var = tk.StringVar(value="of 0.000 s")
        ttk.Label(self.root, textvariable=self.dur_var,
                  font="TkFixedFont").pack()

        transport = ttk.Frame(self.root)
        transport.pack(**pad)
        ttk.Button(transport, text="◀◀ back", width=9, takefocus=0,
                   command=lambda: self._skip(-1)).pack(side=tk.LEFT, padx=3)
        self.play_btn = ttk.Button(transport, text="▶ Play", width=9,
                                   takefocus=0, command=self._toggle)
        self.play_btn.pack(side=tk.LEFT, padx=3)
        ttk.Button(transport, text="■ Stop", width=9, takefocus=0,
                   command=self._stop).pack(side=tk.LEFT, padx=3)
        ttk.Button(transport, text="fwd ▶▶", width=9, takefocus=0,
                   command=lambda: self._skip(1)).pack(side=tk.LEFT, padx=3)

        speed_row = ttk.Frame(self.root)
        speed_row.pack(**pad)
        ttk.Label(speed_row, text="Speed:").pack(side=tk.LEFT, padx=(0, 6))
        self._speed_buttons = {}
        for factor, label in [(0.25, "0.25x"), (0.5, "0.5x"), (1.0, "1x")]:
            btn = ttk.Button(speed_row, text=label, width=6, takefocus=0,
                             command=lambda f=factor: self._set_speed(f))
            btn.pack(side=tk.LEFT, padx=3)
            self._speed_buttons[factor] = btn
        self.calc_canvas = tk.Canvas(speed_row, width=CALC_BAR_WIDTH,
                                     height=CALC_BAR_HEIGHT, highlightthickness=0,
                                     bg=CALC_TROUGH)
        # packed on demand by _refresh_calculating while a stretch computes
        self._refresh_speed_buttons()

        fields = ttk.Frame(self.root)
        fields.pack(**pad)
        ttk.Label(fields, text="Offset (s):").pack(side=tk.LEFT)
        self.offset_var = tk.StringVar(value=f"{self.marks.offset:.3f}")
        offset_entry = ttk.Entry(fields, textvariable=self.offset_var, width=7)
        offset_entry.pack(side=tk.LEFT, padx=(2, 16))
        offset_entry.bind("<FocusOut>", lambda e: self._apply_offset())
        offset_entry.bind("<Return>",
                          lambda e: self._commit_field(self._apply_offset))
        ttk.Label(fields, text="Skip (s):").pack(side=tk.LEFT)
        self.skip_var = tk.StringVar(value=f"{self.skip_seconds:g}")
        skip_entry = ttk.Entry(fields, textvariable=self.skip_var, width=7)
        skip_entry.pack(side=tk.LEFT, padx=2)
        skip_entry.bind("<FocusOut>", lambda e: self._apply_skip())
        skip_entry.bind("<Return>",
                        lambda e: self._commit_field(self._apply_skip))

        self.mark_indicator = tk.Label(self.root, text="●  MARK  (Enter)",
                                       font=self.mark_font, fg="white",
                                       width=28, height=2)
        self.mark_indicator.pack(**pad)
        self.mark_indicator.bind("<Button-1>", lambda e: self._mark())

        marks_header = ttk.Frame(self.root)
        marks_header.pack(fill=tk.X, **pad)
        ttk.Label(marks_header,
                  text="Marks (transient — not saved)").pack(side=tk.LEFT)
        ttk.Button(marks_header, text="Del", takefocus=0,
                   command=self._delete_last).pack(side=tk.RIGHT, padx=3)
        ttk.Button(marks_header, text="Clear", takefocus=0,
                   command=self._clear).pack(side=tk.RIGHT, padx=3)
        ttk.Button(marks_header, text="Copy", takefocus=0,
                   command=self._copy_all_marks).pack(side=tk.RIGHT, padx=3)

        self.marks_list = tk.Listbox(self.root, height=6, font="TkFixedFont",
                                     selectmode=tk.EXTENDED, exportselection=False,
                                     borderwidth=0, highlightthickness=1)
        self.marks_list.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.path_var = tk.StringVar(value="")
        ttk.Label(self.root, textvariable=self.path_var, font=self.footer_font,
                  foreground="#888888").pack(fill=tk.X, padx=8, pady=(0, 4))

        self._apply_widget_theming()

    def _toggle_theme(self):
        sv_ttk.toggle_theme()
        self._apply_widget_theming()

    def _apply_widget_theming(self):
        dark = sv_ttk.get_theme() == "dark"
        self.canvas.configure(bg=SEEKBAR_BG_DARK if dark else SEEKBAR_BG_LIGHT)
        self.mark_indicator.configure(
            bg=MARK_IDLE_DARK if dark else MARK_IDLE_LIGHT,
            fg="white" if dark else "#111111")
        self.marks_list.configure(
            bg=LISTBOX_BG_DARK if dark else LISTBOX_BG_LIGHT,
            fg=LISTBOX_FG_DARK if dark else LISTBOX_FG_LIGHT)

    def _global_key(self, action):
        """Wrap a key handler so it ignores presses that originate in an
        Entry widget (Offset/Skip fields), leaving normal text editing intact."""
        def handler(event):
            if isinstance(event.widget, tk.Entry):
                return
            action()
        return handler

    def _bind_keys(self):
        self.root.bind("<space>", self._global_key(self._toggle))
        self.root.bind("<Left>", self._global_key(lambda: self._skip(-1)))
        self.root.bind("<Right>", self._global_key(lambda: self._skip(1)))
        self.root.bind("<Return>", self._global_key(self._mark))
        self.root.bind("<Delete>", self._global_key(self._delete_last))
        self.root.bind("<Escape>", self._global_key(self._stop))
        # Clicking anywhere outside the Offset/Skip entries drops focus back to
        # the window so the keyboard shortcuts above work again.
        self.root.bind("<Button-1>", self._on_click)
        # Ctrl+C copies the selected marks — bound at the window level so it
        # works even though clicking the list drops focus back to the window.
        self.root.bind("<Control-c>", self._on_copy_key)

    def _commit_field(self, apply_fn):
        """Apply an edited Offset/Skip field, then return focus to the window
        so keyboard shortcuts resume (the field no longer swallows keys)."""
        apply_fn()
        self.root.focus_set()

    def _on_click(self, event):
        if not isinstance(event.widget, tk.Entry):
            self.root.focus_set()

    def _on_copy_key(self, event):
        # Copy the selected marks, unless a text field has focus (there, let the
        # field's own Ctrl+C copy its text).
        if isinstance(event.widget, tk.Entry):
            return
        self._copy_selected_marks()

    # --- actions ---

    def _toggle(self):
        if self.engine.uses_stretch() and not self.engine.stretch_ready():
            return  # still calculating; playback isn't available yet
        try:
            self.engine.toggle()
        except Exception as exc:
            messagebox.showerror("Audio error", str(exc))
        self._refresh_play_button()

    def _safe_play(self):
        try:
            self.engine.play()
        except Exception as exc:
            messagebox.showerror("Audio error", str(exc))

    def _set_speed(self, factor):
        was_playing = self.engine.is_playing
        self._resume_pending = False
        try:
            self.engine.set_speed(factor)   # pauses on a slow speed; 1x resumes
        except Exception as exc:
            messagebox.showerror("Audio error", str(exc))
        if was_playing and self.engine.uses_stretch():
            # switched to a pitch-corrected slow speed while playing
            if self.engine.stretch_ready():
                self._safe_play()             # seamless: ratio already cached
            else:
                self._resume_pending = True   # auto-resume once the stretch is ready
        self._refresh_speed_buttons()
        self._refresh_play_button()
        self._refresh_calculating()

    def _refresh_speed_buttons(self):
        for factor, btn in self._speed_buttons.items():
            btn.configure(style="Accent.TButton"
                          if factor == self.engine.speed else "TButton")

    def _refresh_calculating(self):
        computing = self.engine.uses_stretch() and not self.engine.stretch_ready()
        if computing != self._calc_shown:
            if computing:
                self.calc_canvas.pack(side=tk.LEFT, padx=(10, 0))
            else:
                self.calc_canvas.pack_forget()
            self._calc_shown = computing
        if computing:
            self._draw_calc_bar()
        self.play_btn.state(["disabled"] if computing else ["!disabled"])

    def _draw_calc_bar(self):
        c = self.calc_canvas
        c.delete("all")
        c.create_rectangle(0, 0, CALC_BAR_WIDTH, CALC_BAR_HEIGHT,
                           fill=CALC_TROUGH, width=0)
        frac = max(0.0, min(1.0, self.engine.stretch_progress))
        if frac > 0:
            c.create_rectangle(0, 0, int(CALC_BAR_WIDTH * frac), CALC_BAR_HEIGHT,
                               fill=CALC_FILL, width=0)

    def _on_stretch_failed(self):
        self._resume_pending = False
        self.engine.set_speed(1.0)          # revert to normal speed
        self.engine.clear_stretch_error()
        self._refresh_speed_buttons()
        self._refresh_calculating()
        messagebox.showerror(
            "Out of memory",
            "Not enough memory to slow this song at that speed. "
            "Returning to normal speed.")

    def _set_song(self, path):
        basename = os.path.basename(path) if path else ""
        self.filename_var.set(format_song_label(self.engine.metadata, basename))
        self.path_var.set(path)

    def _open_song(self):
        path = filedialog.askopenfilename(parent=self.root,
                                          title="Open audio file",
                                          filetypes=AUDIO_TYPES)
        if not path:
            return
        try:
            self.engine.load(path)
        except Exception as exc:
            messagebox.showerror("Cannot open file",
                                 f"Could not load:\n{path}\n\n{exc}")
            return
        self.marks.clear()
        self.marks_list.delete(0, tk.END)
        self._set_song(path)
        self._set_speed(1.0)  # also refreshes the play button

    def _stop(self):
        self._resume_pending = False
        self.engine.stop()
        self._refresh_play_button()

    def _skip(self, direction):
        self.engine.skip(direction * self.skip_seconds)

    def _mark(self):
        value = self.marks.mark(self.engine.mark_position())
        self.marks_list.insert(tk.END, f"{value:.3f}")
        self.marks_list.see(tk.END)
        self._flash()

    def _delete_last(self):
        self.marks.delete_last()
        if self.marks_list.size() > 0:
            self.marks_list.delete(tk.END)

    def _clear(self):
        self.marks.clear()
        self.marks_list.delete(0, tk.END)

    def _copy_all_marks(self):
        text = format_marks_for_clipboard(self.marks.marks)
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)

    def _copy_selected_marks(self):
        sel = self.marks_list.curselection()
        if not sel:
            return
        text = "\n".join(self.marks_list.get(i) for i in sel)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _apply_offset(self):
        # Clamp at 0: a negative offset would make marks land *after* the word
        # (the offset is a reaction-delay knob, not a shift in both directions).
        try:
            self.marks.offset = max(0.0, float(self.offset_var.get()))
        except ValueError:
            pass                        # unparseable: keep the previous offset
        self.offset_var.set(f"{self.marks.offset:.3f}")

    def _apply_skip(self):
        try:
            self.skip_seconds = float(self.skip_var.get())
        except ValueError:
            self.skip_var.set(f"{self.skip_seconds:g}")

    def _flash(self):
        self.mark_indicator.config(bg=MARK_FLASH)
        if self._flash_after is not None:
            self.root.after_cancel(self._flash_after)
        dark = sv_ttk.get_theme() == "dark"
        idle = MARK_IDLE_DARK if dark else MARK_IDLE_LIGHT
        self._flash_after = self.root.after(
            FLASH_MS, lambda: self.mark_indicator.config(bg=idle))

    # --- seek bar ---

    def _on_seek_click(self, event):
        secs = x_to_seconds(event.x, SEEKBAR_WIDTH, self.engine.duration)
        self.engine.seek(secs)

    def _on_hover(self, event):
        secs = x_to_seconds(event.x, SEEKBAR_WIDTH, self.engine.duration)
        text = format_mss(secs)
        if self._tooltip is None:
            self._tooltip = tk.Toplevel(self.root)
            self._tooltip.wm_overrideredirect(True)
            self._tooltip_label = tk.Label(self._tooltip, text=text,
                                           bg="#ffffe0", fg="black",
                                           relief=tk.SOLID, borderwidth=1,
                                           font=self.tooltip_font)
            self._tooltip_label.pack()
        self._tooltip_label.config(text=text)
        self._tooltip.wm_geometry(
            f"+{event.x_root + 12}+{event.y_root + 12}")

    def _on_hover_leave(self, event):
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None

    # --- poll loop ---

    def _poll(self):
        if self.engine.stretch_failed:
            self._on_stretch_failed()
        elif self._resume_pending and self.engine.stretch_ready():
            self._resume_pending = False
            self._safe_play()   # seamless auto-resume once the stretch is ready
        # Show the audible position (same latency compensation the marks use) so
        # the readout matches what you hear and the offset equals the visible
        # readout->mark gap.
        pos = self.engine.mark_position()
        dur = self.engine.duration
        self.pos_var.set(f"{pos:.3f} s   ({format_mssmmm(pos)})")
        self.dur_var.set(f"of {dur:.3f} s   ({format_mssmmm(dur)})")
        x = seconds_to_x(pos, SEEKBAR_WIDTH, dur)
        self.canvas.coords(self._playhead, x, 0, x, SEEKBAR_HEIGHT)
        self._refresh_play_button()
        self._refresh_calculating()
        self._poll_after = self.root.after(POLL_MS, self._poll)

    def _refresh_play_button(self):
        self.play_btn.config(text="⏸ Pause" if self.engine.is_playing
                             else "▶ Play")

    # --- clean shutdown ---

    def _on_close(self):
        if self._flash_after is not None:
            self.root.after_cancel(self._flash_after)
        if self._poll_after is not None:
            self.root.after_cancel(self._poll_after)
        self.engine.close()
        self.root.destroy()
