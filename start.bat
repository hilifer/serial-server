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

REM Stop any previous Edge instance GRACEFULLY (WM_CLOSE) before relaunch.
REM If we kill with /F instead, Edge marks the previous session as
REM "abnormally terminated" and shows a "还原页面 / Edge 意外关闭" bubble
REM on next launch every single time. /T (no /F) sends WM_CLOSE and gives
REM Edge a chance to mark the shutdown as clean.
echo Stopping any previous Edge...
taskkill /IM msedge.exe /T >nul 2>&1
REM Give Edge a moment to write a clean exit state, then force-kill any
REM stragglers (e.g. renderer that didn't honour WM_CLOSE).
timeout /t 2 /nobreak >nul
taskkill /IM msedge.exe /F >nul 2>&1

REM Background: wait for service ready, then open browser.
REM Edge flags break down into two groups:
REM   (a) anti-throttle (keep the kiosk page from being frozen by Edge
REM       when it's idle in the background):
REM         --disable-features=MsSleepingTabs,SleepingTabs
REM         --disable-background-timer-throttling
REM         --disable-renderer-backgrounding
REM         --disable-backgrounding-occluded-windows
REM   (b) suppress nag UI that would otherwise pop up on each boot:
REM         --disable-session-crashed-bubble  : suppress 还原页面 bubble
REM         --no-first-run                    : skip first-run setup
REM         --no-default-browser-check        : skip "set as default?"
REM         --noerrdialogs                    : suppress JS / network err popups
REM         --disable-infobars                : kill info bars
start "" /B cmd /c "timeout /t 5 /nobreak >nul && start msedge --start-fullscreen --disable-features=MsSleepingTabs,SleepingTabs --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-session-crashed-bubble --no-first-run --no-default-browser-check --noerrdialogs --disable-infobars http://localhost:8000/ 2>nul || start http://localhost:8000/"

REM Server runs in foreground (Ctrl+C to stop)
python server.py

echo.
echo 服务已停止
pause
