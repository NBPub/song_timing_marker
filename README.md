# Song Timing Marker

A small desktop tool for capturing millisecond-accurate timestamps from an audio file, built with Python. Select and play a song, record timestamps at your desired locations, and then read/copy timestamps to millisecond resolution.

*Built to accompany alignment adjustment for [karaoke_vid_gen](https://github.com/NBPub/karaoke_vid_gen/tree/main#karaoke-video-generator).*

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![GUI](https://img.shields.io/badge/GUI-Tkinter%20%2B%20sv--ttk-blue)
![Audio](https://img.shields.io/badge/Audio-sounddevice%20%2B%20soundfile-blue)
![License](https://img.shields.io/badge/License-MIT-green)

<p align="center">
  <img src="docs/images/home_dark.png" alt="Main window" width="49%">
  <img src="docs/images/playing_dark.png" alt="Capturing timestamps" width="49%">
</p>

**[Documentation](docs/README.md#gui-and-design-notes)**

**Contents:**

| [Quickstart](#quickstart) | [Features](#features) | [Docs](docs/README.md#gui-and-design-notes) | [Motivation](#motivation) | [AI Disclaimer](#ai-disclaimer) | [Contributing](CONTRIBUTING.md#contributing) |

## Quickstart

Requires Python 3.12 or newer (developed on 3.14) and a working audio output 
device. Dependencies listed [below](#dependencies) and in [requirements.txt](requirements.txt).
```powershell
git clone https://github.com/NBPub/song_timing_marker
cd song_timing_marker
python -m venv .venv

.venv\Scripts\activate           # Windows; for macOS/Linux: source .venv/bin/activate 

pip install -r requirements.txt
python main.py                   # OR python main.py "path\to\song.flac"
```

Supported playback for various audio formats may depend on the bundled
`libsndfile` version.

### Launching

As shown in the installation example above, the tool can be launched by navigating to its directory, activating the virtual environment, and launching with `python main.py`. For convenience [run.bat](run.bat) can be used for  double-click launching.

- `run.bat` also works as an "Open with" handler or drop target: a single 
  file path dropped onto it is forwarded to the app.
- A desktop shortcut (or a file-type association) can point at `run.bat` on
  Windows, or at a `python main.py` command on any platform, to get the same
  one-click launch.
- macOS and Linux launcher scripts (a `.command` and a `.sh`) are drafted in the
  [documentation](docs/README.md#macos-and-linux-launchers); until then,
  `python main.py` is the portable entry point.

### Keyboard Shortcuts

*all actions can be toggled by pressing buttons on the GUI*

| Key | Action |
| --- | --- |
| `Space` | Play / pause |
| `Enter` | Mark the current position |
| `Left` / `Right` | Skip back / forward |
| `Delete` | Remove the last mark |
| `Esc` | Stop |
| `Ctrl+C` | Copy the selected marks |

### Dependencies

`sounddevice`, `soundfile`, `numpy`, `sv-ttk`, and `audiotsm`. All ship
pure-Python wheels, so the tool stays self-contained in its virtual environment
with no external application to install.

> Note: `audiotsm` (the pitch-preserving time-stretch behind slow playback) is
> effectively unmaintained. It is kept because it is the only pure-Python WSOLA
> option, and it runs on already-decoded, in-memory audio: a bug there
> would surface as a playback artifact, not a security concern. Remove it from
> `requirements.txt` if slowed playback is not needed.

Versions are unpinned, so `pip install` fetches the latest compatible release of each. Built in Python 3.14 and tested against sounddevice 0.5.5, soundfile 0.14.0, numpy 2.5.1, sv-ttk 2.6.1, audiotsm 0.1.2. 

## Features

- Transport controls (play, pause, stop, skip) and a click-and-drag seek bar
  with a hover tooltip.
- Large current time position readout to three decimals.
- Mark capture on keypress: records `position - offset`, rounded to three
  decimals, into a transient on-screen list. Timestamp list is selectable and copyable.
- A live, adjustable reaction-delay offset.
- Slow playback options at 0.25x and 0.5x that preserves pitch, computed in the
  background so the interface never freezes.
- A modern themed interface with a light/dark toggle, crisp on high-DPI Windows
  displays.

See for more details: [GUI and Design Notes](docs/README.md#gui-and-design-notes)

## Motivation

[Karaoke Videos](https://github.com/NBPub/karaoke_vid_gen/tree/main#karaoke-video-generator) need per-word timing data: when each lyric should appear or fill.
Adjusting timings by hand means finding the exact moment a word is sung, and 
normal media players typically show whole seconds, therefore requiring finer resolution to be guessed.

This tool was built to make that step easier. It plays a song, shows the
position to millisecond precision, and turns a keypress into a timestamp, which is biased slightly early to account for reaction speed and to match the karaoke feel. These timestamps can be copied into [files](https://github.com/NBPub/karaoke_vid_gen/blob/main/docs/Features.md#timingjson) that control how lyrics in karaoke videos are filled.

## AI Disclaimer

Architecture, feature scope, dependency choices, and the QA loops were
human-planned and human-directed; the assistant did much of the implementation
and documentation drafting under that direction.

## Contributing

Contributions are welcome. See [Contributing](CONTRIBUTING.md#contributing).
