@echo off
title StarRail 2026 Vote Tracker (close this window to stop)
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel%==0 (
    set "PY=python"
    goto run
)
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
    goto run
)

echo [ERROR] Python not found. Please run "Install.bat" first.
pause
exit /b 1

:run
echo.
echo ============================================
echo  StarRail 2026 Vote Tracker
echo ============================================
echo.
echo Starting... browser will open in a few seconds.
echo Close THIS BLACK WINDOW to stop the program.
echo.

start "" /min cmd /c "timeout /t 4 /nobreak >nul && start http://127.0.0.1:5000"

%PY% app.py

echo.
echo Service stopped.
pause
