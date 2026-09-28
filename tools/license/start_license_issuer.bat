@echo off
setlocal
cd /d "%~dp0..\.."
python -m tools.license.issuer_dialog
endlocal
