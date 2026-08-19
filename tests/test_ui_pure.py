from ui import x_to_seconds, seconds_to_x, format_mss, format_mssmmm, format_song_label


def test_x_to_seconds_midpoint():
    assert x_to_seconds(50, 100, 200.0) == 100.0


def test_x_to_seconds_clamps_low():
    assert x_to_seconds(-10, 100, 200.0) == 0.0


def test_x_to_seconds_clamps_high():
    assert x_to_seconds(150, 100, 200.0) == 200.0


def test_x_to_seconds_zero_width():
    assert x_to_seconds(50, 0, 200.0) == 0.0


def test_seconds_to_x_midpoint():
    assert seconds_to_x(100.0, 100, 200.0) == 50.0


def test_seconds_to_x_clamps_high():
    assert seconds_to_x(500.0, 100, 200.0) == 100.0


def test_seconds_to_x_zero_duration():
    assert seconds_to_x(50.0, 100, 0.0) == 0.0


def test_seek_map_round_trip():
    width, duration = 640, 205.1
    for x in (0, 123, 320, 640):
        secs = x_to_seconds(x, width, duration)
        back = seconds_to_x(secs, width, duration)
        assert abs(back - x) < 1e-6


def test_format_mss():
    assert format_mss(72.941) == "1:12"
    assert format_mss(5.0) == "0:05"
    assert format_mss(0.0) == "0:00"


def test_format_mssmmm():
    assert format_mssmmm(72.941) == "1:12.941"
    assert format_mssmmm(5.2) == "0:05.200"
    assert format_mssmmm(0.0) == "0:00.000"


def test_format_mssmmm_minute_boundary_rounds_up():
    assert format_mssmmm(59.9997) == "1:00.000"
    assert format_mssmmm(119.9999) == "2:00.000"


def test_song_label_artist_and_title():
    assert format_song_label({"artist": "Adele", "title": "Hello"},
                             "x.flac") == "Adele - Hello"


def test_song_label_title_only():
    assert format_song_label({"title": "Hello"}, "x.flac") == "Hello"


def test_song_label_artist_only_uses_filename():
    assert format_song_label({"artist": "Adele"}, "x.flac") == "Adele - x.flac"


def test_song_label_empty_uses_filename():
    assert format_song_label({}, "x.flac") == "x.flac"


def test_song_label_whitespace_treated_as_absent():
    assert format_song_label({"artist": "  ", "title": "  "},
                             "x.flac") == "x.flac"


def test_song_label_whitespace_title_keeps_artist():
    assert format_song_label({"artist": "Adele", "title": "  "},
                             "x.flac") == "Adele - x.flac"


from ui import format_marks_for_clipboard


def test_format_marks_multiple():
    assert format_marks_for_clipboard([14.725, 18.121, 72.941]) == \
        "14.725\n18.121\n72.941"


def test_format_marks_single():
    assert format_marks_for_clipboard([5.0]) == "5.000"


def test_format_marks_empty():
    assert format_marks_for_clipboard([]) == ""
