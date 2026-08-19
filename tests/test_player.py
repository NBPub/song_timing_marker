import numpy as np

from player import AudioEngine


def make_engine(seconds=10.0, samplerate=10):
    frames = int(seconds * samplerate)
    samples = np.zeros((frames, 1), dtype=np.float32)
    return AudioEngine(samples=samples, samplerate=samplerate)


def test_duration_is_frames_over_samplerate():
    eng = make_engine(seconds=10.0, samplerate=10)
    assert eng.duration == 10.0


def test_duration_zero_when_unloaded():
    eng = AudioEngine()
    assert eng.duration == 0.0


def test_position_zero_when_unloaded():
    eng = AudioEngine()
    assert eng.position() == 0.0


def test_position_reflects_cursor():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.cursor = 55
    assert eng.position() == 5.5


def test_seek_sets_cursor():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.seek(3.0)
    assert eng.cursor == 30
    assert eng.position() == 3.0


def test_seek_clamps_below_zero():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.seek(-5.0)
    assert eng.cursor == 0


def test_seek_clamps_above_duration():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.seek(15.0)
    assert eng.cursor == 100  # total frames
    assert eng.position() == 10.0


def test_skip_moves_relative():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.seek(3.0)
    eng.skip(2.0)
    assert eng.position() == 5.0


def test_skip_clamps_at_end():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.seek(9.0)
    eng.skip(5.0)
    assert eng.position() == 10.0


def test_skip_backward_clamps_at_zero():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.seek(1.0)
    eng.skip(-5.0)
    assert eng.position() == 0.0


class _FakeStream:
    """Stand-in for sd.OutputStream so play()'s restart contract can be tested
    without an audio device. Records the order of start/stop/close calls."""

    def __init__(self, active=False):
        self.calls = []
        self.active = active

    def start(self):
        self.calls.append("start")

    def stop(self, ignore_errors=True):
        self.calls.append("stop")

    def close(self):
        self.calls.append("close")


def test_play_stops_existing_stream_before_start():
    # Regression: at end-of-song the callback raises CallbackStop, leaving the
    # stream in a finished state that start() will not resume until it has been
    # stopped first. play() must stop() an existing stream before start().
    # (seek-after-end case: cursor mid-song must be preserved, not rewound.)
    eng = make_engine(seconds=10.0, samplerate=10)
    fake = _FakeStream()
    eng._stream = fake
    eng.cursor = 50
    eng.play()
    assert fake.calls == ["stop", "start"]
    assert eng.cursor == 50


def test_play_from_end_resets_cursor_then_restarts():
    # End-of-song: cursor sits at total_frames; play() rewinds to 0 and restarts.
    eng = make_engine(seconds=10.0, samplerate=10)
    fake = _FakeStream()
    eng._stream = fake
    eng.cursor = 100
    eng.play()
    assert eng.cursor == 0
    assert fake.calls == ["stop", "start"]


def test_speed_defaults_to_one():
    assert make_engine().speed == 1.0


def test_metadata_defaults_to_empty():
    assert AudioEngine().metadata == {}


def test_set_speed_updates_speed():
    eng = make_engine()
    eng.set_speed(0.5)
    assert eng.speed == 0.5


def test_position_and_duration_independent_of_speed():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.cursor = 50
    eng.set_speed(0.5)
    assert eng.position() == 5.0
    assert eng.duration == 10.0


def test_set_speed_same_value_is_noop_on_stream():
    eng = make_engine()
    eng.pitch_correct = False
    fake = _FakeStream(active=False)
    eng._stream = fake
    eng.set_speed(1.0)  # already the default
    assert fake.calls == []
    assert eng._stream is fake


def test_set_speed_change_closes_existing_stream_when_not_playing():
    eng = make_engine()
    eng.pitch_correct = False
    fake = _FakeStream(active=False)
    eng._stream = fake
    eng.set_speed(0.5)
    assert fake.calls == ["stop", "close"]
    assert eng._stream is None
    assert eng.speed == 0.5


from player import original_to_stretched, stretched_to_original


def test_map_identity_when_equal_lengths():
    assert original_to_stretched(50, 100, 100) == 50
    assert stretched_to_original(50, 100, 100) == 50


def test_map_original_to_stretched_doubles():
    # stretched buffer 2x longer -> index doubles
    assert original_to_stretched(50, 100, 200) == 100


def test_map_stretched_to_original_halves():
    assert stretched_to_original(100, 100, 200) == 50


def test_map_round_trip_within_one_frame():
    orig_len, stretched_len = 44100, 84992  # real-ish 0.5x ratio
    for x in (0, 1234, 22050, 44100):
        back = stretched_to_original(
            original_to_stretched(x, orig_len, stretched_len),
            orig_len, stretched_len)
        assert abs(back - x) <= 1


def test_map_zero_length_guards():
    assert original_to_stretched(10, 0, 200) == 0
    assert stretched_to_original(10, 100, 0) == 0


def make_real_engine(seconds=0.5, samplerate=8000):
    frames = int(seconds * samplerate)
    samples = np.random.randn(frames, 2).astype(np.float32) * 0.1
    return AudioEngine(samples=samples, samplerate=samplerate)


def join_stretches(eng, timeout=15):
    """Wait for every in-flight stretch worker (one per ratio)."""
    for thread in list(eng._stretch_threads.values()):
        thread.join(timeout=timeout)


def test_pitch_correct_defaults_true():
    assert AudioEngine().pitch_correct is True


def test_uses_stretch_only_for_slow_pitch_correct():
    eng = make_real_engine()
    assert eng.uses_stretch() is False          # speed 1.0
    eng.speed = 0.5
    assert eng.uses_stretch() is True
    eng.pitch_correct = False
    assert eng.uses_stretch() is False


def test_set_speed_slow_pauses_and_precomputes_stretch():
    eng = make_real_engine()
    eng.set_speed(0.5)
    assert eng.speed == 0.5
    join_stretches(eng)
    assert eng.stretch_ready() is True
    # stretched buffer is longer than the original (slower), same channel count
    assert 0.5 in eng._stretch_cache
    assert eng._stretch_cache[0.5].shape[0] > eng._samples.shape[0]
    assert eng._stretch_cache[0.5].shape[1] == eng._samples.shape[1]


def test_load_clears_stretch_cache(tmp_path):
    import soundfile as sf
    eng = make_real_engine()
    eng.set_speed(0.5)
    join_stretches(eng)
    assert eng.stretch_ready()
    p = tmp_path / "s.wav"
    sf.write(p, np.zeros((8000, 2), dtype=np.float32), 8000)
    eng.load(str(p))
    assert eng._stretch_cache == {}
    assert eng.stretch_ready() is False


def test_set_speed_back_to_one_uses_normal_path():
    eng = make_real_engine()
    eng.set_speed(0.5)
    eng.set_speed(1.0)
    assert eng.uses_stretch() is False


def test_load_blocks_stale_stretch_from_repopulating(tmp_path):
    import soundfile as sf
    eng = make_real_engine(seconds=2.0)   # song A (longer -> slower stretch)
    eng.set_speed(0.5)                     # spawn worker for A
    p = tmp_path / "b.wav"
    sf.write(p, np.zeros((8000, 2), dtype=np.float32), 8000)
    eng.load(str(p))                       # clears cache; speed stays 0.5
    join_stretches(eng)
    # A's stale buffer must never be reported ready for song B
    assert 0.5 not in eng._stretch_cache
    assert eng.stretch_ready() is False


def test_switching_slow_speeds_midstretch_computes_new_ratio(monkeypatch):
    # Regression: clicking 0.5x then 0.25x while the first stretch is still
    # running must still compute the 0.25x buffer (not strand the engine with
    # no worker for the current speed).
    import time
    import player as player_mod
    real_wsola = player_mod.wsola

    def slow_wsola(*args, **kwargs):
        time.sleep(0.3)                    # keep the first worker alive
        return real_wsola(*args, **kwargs)

    monkeypatch.setattr(player_mod, "wsola", slow_wsola)

    eng = make_real_engine(seconds=1.0)
    eng.set_speed(0.5)     # spawns a slow worker for 0.5 (still running)
    eng.set_speed(0.25)    # must spawn a worker for 0.25 despite 0.5 alive
    join_stretches(eng)
    assert eng.stretch_ready() is True
    assert 0.25 in eng._stretch_cache
    assert eng.speed == 0.25


def test_mark_position_defaults_to_position_no_lead():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.cursor = 50
    assert eng._output_latency == 0.0
    assert eng._cursor_leads is False
    assert eng.mark_position() == 5.0


def test_mark_position_compensates_latency_when_cursor_leads():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.cursor = 50
    eng._output_latency = 0.5
    eng._cursor_leads = True
    assert eng.mark_position() == 4.5


def test_mark_position_no_compensation_when_not_leading():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.cursor = 50
    eng._output_latency = 0.5
    eng._cursor_leads = False
    assert eng.mark_position() == 5.0


def test_mark_position_clamps_at_zero():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng.cursor = 2                      # 0.2s
    eng._output_latency = 0.5
    eng._cursor_leads = True
    assert eng.mark_position() == 0.0


def test_seek_clears_cursor_leads():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng._cursor_leads = True
    eng.seek(3.0)
    assert eng._cursor_leads is False


def test_stop_clears_cursor_leads():
    eng = make_engine(seconds=10.0, samplerate=10)
    eng._cursor_leads = True
    eng.stop()
    assert eng._cursor_leads is False


def test_cache_both_keeps_both_ratios():
    eng = make_real_engine(seconds=1.0)
    eng._cache_both = True
    eng.set_speed(0.5)
    join_stretches(eng)
    eng.set_speed(0.25)
    join_stretches(eng)
    assert 0.5 in eng._stretch_cache
    assert 0.25 in eng._stretch_cache


def test_cache_active_only_evicts_other_ratio():
    eng = make_real_engine(seconds=1.0)
    eng._cache_both = False
    eng.set_speed(0.5)
    join_stretches(eng)
    assert 0.5 in eng._stretch_cache
    eng.set_speed(0.25)
    join_stretches(eng)
    assert 0.25 in eng._stretch_cache
    assert 0.5 not in eng._stretch_cache   # evicted (large-file policy)


def test_load_sets_cache_both_true_for_small_file(tmp_path):
    import soundfile as sf
    p = tmp_path / "s.wav"
    sf.write(p, np.zeros((8000, 2), dtype=np.float32), 8000)
    eng = AudioEngine()
    eng.load(str(p))
    assert eng._cache_both is True


def test_load_sets_cache_active_only_for_large_file(tmp_path, monkeypatch):
    import soundfile as sf
    p = tmp_path / "s.wav"
    sf.write(p, np.zeros((8000, 2), dtype=np.float32), 8000)
    monkeypatch.setattr("os.path.getsize", lambda path: 200 * 1024 * 1024)
    eng = AudioEngine()
    eng.load(str(p))
    assert eng._cache_both is False


def test_stretch_memoryerror_clears_cache_and_flags(monkeypatch):
    import player as player_mod

    def boom(*args, **kwargs):
        raise MemoryError()

    monkeypatch.setattr(player_mod, "wsola", boom)
    eng = make_real_engine(seconds=1.0)
    eng.set_speed(0.5)
    join_stretches(eng)
    assert eng.stretch_ready() is False
    assert eng.stretch_failed is True
    assert eng._stretch_cache == {}


def test_stretch_progress_reaches_one():
    eng = make_real_engine(seconds=1.0)
    assert eng.stretch_progress == 0.0
    eng.set_speed(0.5)
    join_stretches(eng)
    assert eng.stretch_ready() is True   # streaming loop produced a valid buffer
    assert eng.stretch_progress == 1.0


def test_close_releases_stretch_cache():
    eng = make_real_engine(seconds=1.0)
    eng.set_speed(0.5)
    join_stretches(eng)
    assert eng.stretch_ready() is True
    eng.close()
    assert eng._stretch_cache == {}      # cached buffers released on exit
    assert eng._stretched is None
    assert eng.stretch_ready() is False
    assert eng.stretch_progress == 0.0


def test_close_cancels_a_running_stretch(monkeypatch):
    import time
    import player as player_mod
    real_wsola = player_mod.wsola

    def slow_wsola(*args, **kwargs):
        time.sleep(0.3)                  # keep the worker alive past close()
        return real_wsola(*args, **kwargs)

    monkeypatch.setattr(player_mod, "wsola", slow_wsola)
    eng = make_real_engine(seconds=2.0)
    eng.set_speed(0.5)                   # worker starts
    eng.close()                          # cancel mid-flight
    join_stretches(eng)
    assert eng._stretch_cache == {}      # cancelled worker stored nothing


def test_switching_away_midstretch_still_caches_original_ratio(monkeypatch):
    # Regression: a worker whose ratio is no longer active must STILL cache its
    # result (that is the point of caching both), so switching back is instant
    # instead of recomputing.
    import time
    import player as player_mod
    real_wsola = player_mod.wsola

    def slow_wsola(*args, **kwargs):
        time.sleep(0.3)
        return real_wsola(*args, **kwargs)

    monkeypatch.setattr(player_mod, "wsola", slow_wsola)
    eng = make_real_engine(seconds=1.0)
    eng._cache_both = True
    eng.set_speed(0.5)     # worker for 0.5 starts (slow)
    eng.set_speed(0.25)    # switch away before it finishes
    join_stretches(eng)
    assert 0.5 in eng._stretch_cache    # kept despite no longer being active
    assert 0.25 in eng._stretch_cache
