@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="

where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import PySide6" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3"
)

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import PySide6" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
  )
)

if not defined PYTHON_CMD (
  echo [ERROR] Python 3 with PySide6 was not found.
  echo Install Python 3.11 or 3.12 from python.org and select "Add python.exe to PATH".
  goto :failed
)

echo Starting src with %PYTHON_CMD%...
%PYTHON_CMD% -m src
if errorlevel 1 goto :failed
goto :end

:failed
echo.
echo The application failed to start. See the error message above.
echo Current folder: %CD%
pause

:end
endlocal
