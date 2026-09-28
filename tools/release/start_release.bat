@echo off
setlocal
cd /d "%~dp0..\.."
py -3 tools\release\release_gui.py
if errorlevel 1 python tools\release\release_gui.py
endlocal
