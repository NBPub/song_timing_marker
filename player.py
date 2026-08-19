import os
import threading

import numpy as np
import soundfile as sf
import sounddevice as sd
from audiotsm import wsola
from audiotsm.io.array import ArrayReader, ArrayWriter


MIN_STRETCH_FRAMES = 2048   # shorter clips can't be meaningfully time-stretched


def original_to_stretched(orig_index: int, orig_len: int, stretched_len: int) -> int:
    if orig_len <= 0:
        return 0
    return round(orig_index * stretched_len / orig_len)


def stretched_to_original(stretched_index: int, orig_len: int, stretched_len: int) -> int:
    if stretched_len <= 0:
        return 0
    return round(stretched_index * orig_len / stretched_len)


class AudioEngine:
    """Frame-cursor transport over an in-memory sample array.

    The cursor<->seconds math needs no audio device and is unit-tested by
    constructing an engine over a dummy array. The sounddevice wiring
    (play/pause/stop/close/_callback) is a thin, hand-verified shell.

    Threading note: `cursor` is written by the PortAudio callback thread and by
    seek/skip on the UI thread without a lock. That is a deliberate, accepted
    trade — a seek landing mid-callback can be transiently overwritten by that
    callback's increment, but it self-corrects on the next buffer (tens of ms)
    via the resync check in `_callback_stretch`. Marks are unaffected.
    """

    def __init__(self, samples=None, samplerate: int = 0):
        self._samples = samples          # np.ndarray (frames, channels) or None
        self.samplerate = samplerate
        self.cursor = 0
        self._stream = None
        self.speed = 1.0
        self.metadata = {}
        self.pitch_correct = True
        self._stretched = None          # active stretched buffer (set in play())
        self._stretch_cache = {}        # speed -> stretched buffer (np.ndarray)
        self._cache_both = True         # cache both slow ratios (small files only)
        self._stretch_error = False     # a stretch failed (e.g. out of memory)
        self._stretch_progress = 0.0    # 0..1 progress of the active stretch
        self._stretch_cancel = False    # ask a running stretch worker to bail out
        self._stretch_threads = {}      # speed -> in-flight worker Thread
        self._stretch_lock = threading.Lock()
        self._stretch_pos = 0
        self._load_generation = 0
        self._output_latency = 0.0   # output-stream latency; cursor leads audio by this
        self._cursor_leads = False   # True when cursor came from playback (not a seek)

    # --- pure cursor<->seconds math (tested) ---

    def _total_frames(self) -> int:
        return 0 if self._samples is None else len(self._samples)

    @property
    def duration(self) -> float:
        if self.samplerate == 0 or self._samples is None:
            return 0.0
        return self._total_frames() / self.samplerate

    def position(self) -> float:
        if self.samplerate == 0:
            return 0.0
        return self.cursor / self.samplerate

    def seek(self, seconds: float) -> None:
        frame = int(round(seconds * self.samplerate))
        self.cursor = max(0, min(frame, self._total_frames()))
        self._cursor_leads = False   # a seek sets an exact position, no lead

    def skip(self, delta_seconds: float) -> None:
        self.seek(self.position() + delta_seconds)

    def mark_position(self) -> float:
        """Audible-position estimate for marking. During/after playback the
        frame cursor leads the sound you actually hear by the output-stream
        latency, so subtract it — but only when the cursor came from playback,
        not from a deliberate seek. Marks then reflect what you heard, and the
        offset stays a pure human-reaction-delay knob."""
        pos = self.position()
        if self._cursor_leads:
            pos -= self._output_latency
        return max(0.0, pos)

    def set_speed(self, factor: float) -> None:
        if factor == self.speed:
            return
        was_playing = self.is_playing
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self.speed = factor
        if self.uses_stretch():
            # pitch-corrected slow: pause (no auto-resume), precompute in bg
            self.start_stretch()
        elif was_playing:
            # 1x or pitch-drop path: resume from the current cursor
            self.play()

    # --- device-touching shell (hand-verified, not unit-tested) ---

    def load(self, path: str) -> None:
        with sf.SoundFile(path) as f:
            metadata = f.copy_metadata()
            samplerate = f.samplerate
            data = f.read(dtype="float32", always_2d=True)
        self.close()
        self._samples = data
        self.samplerate = samplerate
        self.metadata = metadata
        with self._stretch_lock:
            self._stretch_cache = {}
            self._stretched = None
            self._stretch_error = False
            self._load_generation += 1
        self.cursor = 0
        self._cursor_leads = False
        try:
            self._cache_both = os.path.getsize(path) <= 100 * 1024 * 1024
        except OSError:
            self._cache_both = False

    @property
    def is_playing(self) -> bool:
        return self._stream is not None and self._stream.active

    def uses_stretch(self) -> bool:
        # Clips shorter than a stretch frame can't be time-stretched; treating
        # them as non-stretch keeps the UI out of a permanent "calculating" state.
        return (self.pitch_correct and self.speed < 1.0
                and self._samples is not None
                and self._samples.shape[0] >= MIN_STRETCH_FRAMES)

    def stretch_ready(self) -> bool:
        with self._stretch_lock:
            return self.speed in self._stretch_cache

    @property
    def stretch_failed(self) -> bool:
        return self._stretch_error

    def clear_stretch_error(self) -> None:
        self._stretch_error = False

    @property
    def stretch_progress(self) -> float:
        return self._stretch_progress

    def start_stretch(self) -> None:
        if not self.uses_stretch() or self.stretch_ready():
            return
        speed = self.speed
        running = self._stretch_threads.get(speed)
        if running is not None and running.is_alive():
            return  # a worker for this exact ratio is already running
        samples = self._samples
        generation = self._load_generation
        cache_both = self._cache_both

        def worker():
            try:
                data = np.ascontiguousarray(samples.T)   # (channels, samples)
                total = data.shape[1]
                reader = ArrayReader(data)
                writer = ArrayWriter(channels=samples.shape[1])
                tsm = wsola(channels=samples.shape[1], speed=speed)
                # Drive the streaming loop (equivalent to tsm.run) so progress
                # can be reported from how much input has been consumed.
                finished = False
                while not (finished and reader.empty):
                    if self._stretch_cancel:
                        return          # shutting down / song changed
                    tsm.read_from(reader)
                    _, finished = tsm.write_to(writer)
                    if speed == self.speed:
                        try:
                            done = total - reader._data.shape[1]
                            self._stretch_progress = (
                                min(0.99, done / total) if total else 0.99)
                        except Exception:
                            pass
                finished = False
                while not finished:
                    if self._stretch_cancel:
                        return
                    _, finished = tsm.flush_to(writer)
                tsm.clear()
                stretched = np.ascontiguousarray(
                    writer.data.T).astype("float32")      # (samples, channels)
            except MemoryError:
                with self._stretch_lock:
                    self._stretch_cache.clear()   # free RAM; fall back gracefully
                    self._stretch_error = True
                return
            except Exception:
                return
            with self._stretch_lock:
                # Cache the result even if the user has switched ratios since —
                # that is the point of caching both. `generation` still guards
                # against a song change.
                if generation == self._load_generation:
                    if cache_both or speed == self.speed:
                        self._stretch_cache[speed] = stretched
                    if not cache_both:       # keep only the ACTIVE ratio
                        for other in [k for k in self._stretch_cache
                                      if k != self.speed]:
                            del self._stretch_cache[other]
            if speed == self.speed:
                self._stretch_progress = 1.0

        self._stretch_progress = 0.0
        self._stretch_cancel = False
        thread = threading.Thread(target=worker, daemon=True)
        self._stretch_threads[speed] = thread
        thread.start()

    def _callback(self, outdata, frames, time, status):
        self._cursor_leads = True
        chunk = self._samples[self.cursor:self.cursor + frames]
        n = len(chunk)
        outdata[:n] = chunk
        if n < frames:
            outdata[n:] = 0
            self.cursor += n
            raise sd.CallbackStop
        self.cursor += frames

    def _callback_stretch(self, outdata, frames, time, status):
        self._cursor_leads = True
        buf = self._stretched
        orig_len = self._samples.shape[0]
        buf_len = buf.shape[0]
        # resync if an external seek/skip moved the original cursor
        expected = stretched_to_original(self._stretch_pos, orig_len, buf_len)
        if abs(self.cursor - expected) > 1:
            self._stretch_pos = original_to_stretched(self.cursor, orig_len, buf_len)
        i = self._stretch_pos
        chunk = buf[i:i + frames]
        n = len(chunk)
        outdata[:n] = chunk
        self._stretch_pos += n
        self.cursor = stretched_to_original(self._stretch_pos, orig_len, buf_len)
        if self.cursor > orig_len:
            self.cursor = orig_len
        if n < frames:
            outdata[n:] = 0
            raise sd.CallbackStop

    def play(self) -> None:
        if self._samples is None:
            return
        if self.cursor >= self._total_frames():
            self.cursor = 0
        if self.uses_stretch():
            if not self.stretch_ready():
                return  # buffer not ready; UI defers Play until stretch_ready()
            with self._stretch_lock:
                self._stretched = self._stretch_cache.get(self.speed)
            if self._stretched is None:
                return
            self._stretch_pos = original_to_stretched(
                self.cursor, self._samples.shape[0], self._stretched.shape[0])
            if self._stream is None:
                self._stream = sd.OutputStream(
                    samplerate=self.samplerate,
                    channels=self._samples.shape[1],
                    callback=self._callback_stretch,
                )
                self._capture_latency()
            else:
                self._stream.stop()
            try:
                self._stream.start()
            except Exception:
                self._stream.close()
                self._stream = None
                raise
            return
        # --- normal (pitch-drop / 1x) path ---
        if self._stream is None:
            self._stream = sd.OutputStream(
                samplerate=round(self.samplerate * self.speed),
                channels=self._samples.shape[1],
                callback=self._callback,
            )
            self._capture_latency()
        else:
            self._stream.stop()
        try:
            self._stream.start()
        except Exception:
            self._stream.close()
            self._stream = None
            raise

    def _capture_latency(self) -> None:
        lat = self._stream.latency
        self._output_latency = float(
            lat[-1] if isinstance(lat, (tuple, list)) else lat)

    def pause(self) -> None:
        if self._stream is not None:
            self._stream.stop()

    def toggle(self) -> None:
        if self.is_playing:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
        self.cursor = 0
        self._cursor_leads = False

    def close(self) -> None:
        """Release the audio device and every cached stretch buffer. Called on
        window close and on load(), so a session never holds a previous song's
        (potentially hundreds of MB) stretched audio."""
        self._stretch_cancel = True      # ask a running stretch worker to stop
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._stretch_lock:
            self._stretch_cache.clear()
            self._stretched = None
        self._stretch_progress = 0.0
