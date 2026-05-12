@echo off
title Build StarRail Vote Tracker EXE
cd /d "%~dp0"

echo.
echo ============================================
echo  Build Customer EXE (windowed, single file)
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
echo [ERROR] Python not found. Run the install-deps bat first.
pause
exit /b 1

:found
echo Using:
%PY% --version
echo.

REM --- ensure runtime deps are installed (PyInstaller scans them) ---
echo Checking runtime dependencies ...
%PY% -m pip install -r requirements.txt >nul

REM --- ensure PyInstaller is available ---
REM Note: %errorlevel% inside (...) is expanded ONCE at parse time, so we
REM keep the post-install check OUTSIDE the install block (re-probe instead).
%PY% -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller ...
    %PY% -m pip install --upgrade pyinstaller
)
%PY% -m pip show pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller install failed. Check internet connection.
    pause
    exit /b 1
)

REM --- clean previous build artifacts ---
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist StarRailVoteTracker.spec del /f /q StarRailVoteTracker.spec

echo.
echo Building EXE (1-3 minutes, please wait)...
echo.
%PY% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --noconfirm ^
    --clean ^
    --icon "vote/256x256.ico" ^
    --name "StarRailVoteTracker" ^
    --add-data "templates;templates" ^
    --add-data "static;static" ^
    --add-data "characters.json;." ^
    app.py

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed. See messages above.
    pause
    exit /b 1
)

REM --- tidy: keep only the EXE, drop intermediates ---
if exist build rmdir /s /q build
if exist StarRailVoteTracker.spec del /f /q StarRailVoteTracker.spec

echo.
echo ============================================
echo  Done!
echo  EXE: dist\StarRailVoteTracker.exe
echo ============================================
echo.
echo Ship the single .exe to the customer.
echo On first run, votes.db and an updated characters.json
echo will appear next to the .exe (and persist across launches).
echo.
pause
