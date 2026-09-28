@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\launch.py %*
  goto done
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 scripts\launch.py %*
  goto done
)
where python >nul 2>nul
if not errorlevel 1 (
  python scripts\launch.py %*
  goto done
)
echo Python not found. Install Python 3.13 and select Add Python to PATH.
pause
exit /b 1
:done
if errorlevel 1 pause
