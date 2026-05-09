@echo off
title Install dependencies - StarRail Vote Tracker
cd /d "%~dp0"

echo.
echo ============================================
echo  StarRail 2026 Vote Tracker - Install
echo ============================================
echo.

where python >nul 2>nul
if %errorlevel%==0 (
    set "PY=python"
    goto found
)
where py >nul 2>nul
if %errorlevel%==0 (
    set "PY=py"
    goto found
)

echo [ERROR] Python not found.
echo.
echo Please install Python 3.11 from:
echo   https://www.python.org/downloads/
echo.
echo IMPORTANT: tick "Add python.exe to PATH" during install.
echo.
pause
exit /b 1

:found
echo Detected Python:
%PY% --version
echo.
echo Installing required libraries (Flask, requests)...
echo.

%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Install failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Done! Double-click "Start.bat" to run.
echo ============================================
echo.
pause
