@echo off
rem Double-click to launch with no console window. If a file is dropped onto
rem this .bat (or it is set as the "Open with" handler for an audio file),
rem that one path is forwarded, quoted, so paths with spaces work correctly.
if "%~1"=="" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
) else (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py" "%~1"
)
