@echo off
rem ============================================================
rem  IntDog one-click launcher. Creates/updates an isolated runtime on demand.
rem ============================================================
cd /d "%~dp0"

rem This batch file is for a native Windows checkout. For the production WSL
rem checkout under /home, use the desktop shortcut created by create_shortcut.ps1.

where py >nul 2>nul
if %errorlevel%==0 (
    start "" pyw -3 "%~dp0launch_intdog.py"
    goto :end
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0launch_intdog.py"
    goto :end
)
echo [ERROR] Python not found on PATH. Please install Python 3.10+ first.
pause
:end
