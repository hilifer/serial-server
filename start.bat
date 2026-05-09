@echo off
chcp 65001 >nul
title 光储充管理系统

echo ============================================
echo   光储充管理系统
echo ============================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Pull latest code from git
echo [1/3] Updating code from git...
git pull origin claude/understand-project-TBDmP 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Git pull failed, continuing with current code...
)
echo.

REM Check Python and setup venv
echo [2/3] Setting up Python environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat

REM Only install if marker file missing (first run or requirements changed)
if not exist "venv\.deps_installed" (
    echo Installing dependencies...
    pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
    copy /y requirements.txt venv\.deps_installed >nul
    del /q venv\.deps_ok 2>nul
) else (
    fc /b requirements.txt venv\.deps_installed >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo Updating dependencies...
        pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple
        copy /y requirements.txt venv\.deps_installed >nul
        del /q venv\.deps_ok 2>nul
    ) else (
        echo Dependencies up to date.
    )
)
echo.

REM Start server (foreground), open browser after 5 seconds in background
echo [3/3] Starting server...
echo   停车场:    http://localhost:8000/
echo   能源看板:  http://localhost:8000/detail.html
echo   按 Ctrl+C 停止
echo ============================================

REM Background: wait for service ready, check serial, then open browser.
REM Edge flags disable every power-save / throttle path that has been
REM observed to delay or drop the kiosk's <meta refresh> rotation:
REM   - SleepingTabs / MsSleepingTabs       : tab freeze after idle
REM   - background-timer-throttling         : 1Hz cap on hidden timers
REM   - renderer-backgrounding              : whole-renderer pause
REM   - backgrounding-occluded-windows      : pause when not on top
start "" /B cmd /c "timeout /t 5 /nobreak >nul && start msedge --start-fullscreen --disable-features=MsSleepingTabs,SleepingTabs --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows http://localhost:8000/ 2>nul || start http://localhost:8000/"

REM Server runs in foreground (Ctrl+C to stop)
python server.py

echo.
echo 服务已停止
pause
