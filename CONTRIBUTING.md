# Contributing

Contributions are welcome. This is a small personal tool, so for anything
non-trivial please open an issue first to discuss the approach before writing
code.

## Conventions

- Keep changes scoped and focused.
- The timing math (`marks.py`, the cursor/mapping functions in `player.py`,
  the seek-bar and format helpers in `ui.py`) is pure and unit-tested. Add or
  update tests for any change there.
- The audio device layer and the Tkinter widgets are thin, hand-verified
  shells with no unit tests by design: verify those by running the app.
- Run `pytest` before opening a PR.

## Running the tests

```
python -m pytest
```
