@echo off
title StarRail 2026 - Clear Database
cd /d "%~dp0"

echo.
echo ============================================
echo  Clear Vote Tracking Database
echo ============================================
echo.
echo This will DELETE all collected vote history:
echo   - votes.db
echo   - votes.db-wal
echo   - votes.db-shm
echo.
echo Make sure the tracker window is CLOSED first,
echo otherwise the files will be locked.
echo.

set /p CONFIRM=Type YES to confirm (anything else cancels):
if /i not "%CONFIRM%"=="YES" (
    echo.
    echo Cancelled. Nothing was deleted.
    pause
    exit /b 0
)

echo.
set "FAIL=0"
set "FOUND=0"
for %%F in (votes.db votes.db-wal votes.db-shm) do (
    if exist "%%F" (
        set "FOUND=1"
        del /f /q "%%F" >nul 2>nul
        if exist "%%F" (
            echo [FAIL] %%F  -- file is locked, is the tracker still running?
            set "FAIL=1"
        ) else (
            echo [OK]   %%F  deleted
        )
    )
)

echo.
if "%FOUND%"=="0" (
    echo No database files found. Nothing to clear.
) else if "%FAIL%"=="1" (
    echo Some files could NOT be deleted. Close the tracker first, then retry.
) else (
    echo Done. Database cleared - next run starts with empty history.
)
echo.
pause
