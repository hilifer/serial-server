@echo off
chcp 65001 >nul
title 光储充管理系统

echo ============================================
echo   光储充管理系统
echo ============================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM ----------------------------------------------------------
REM Self-register for boot autostart (one-time, idempotent).
REM Drops a .lnk into the user's Startup folder pointing back
REM at this very file. Windows then runs start.bat at every
REM user logon — no Task Scheduler / admin needed. If the
REM shortcut already exists this block does nothing.
REM ----------------------------------------------------------
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "STARTUP_LNK=%STARTUP_DIR%\光储充管理系统.lnk"
if not exist "%STARTUP_LNK%" (
  echo [0/3] Installing boot autostart shortcut...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$s=(New-Object -COM WScript.Shell).CreateShortcut('%STARTUP_LNK%');" ^
    "$s.TargetPath='%~f0';" ^
    "$s.WorkingDirectory='%~dp0';" ^
    "$s.WindowStyle=1;" ^
    "$s.Save()" >nul 2>&1
  if exist "%STARTUP_LNK%" (
    echo   Installed: %STARTUP_LNK%
  ) else (
    echo   WARNING: Could not create autostart shortcut.
  )
  echo.
)

REM ----------------------------------------------------------
REM Boot delay — on a cold boot the network adapter is usually
REM not up yet (DHCP / static IP still settling). Wait a fixed
REM window before anything network-dependent runs (git pull,
REM serial bus, meter/BMS reads) so a freshly booted kiosk has
REM time to get online — and so the operator has a chance to fix
REM the static IP before the fullscreen browser takes over.
REM Press any key to skip (useful when launching manually).
REM ----------------------------------------------------------
set "BOOT_DELAY=90"
echo Waiting %BOOT_DELAY%s for network to settle (press any key to skip)...
timeout /t %BOOT_DELAY%
echo.

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

REM Bulletproof: forcibly mark Edge's last session as clean in the
REM Preferences JSON before launching. The --disable-session-crashed-bubble
REM flag alone is unreliable on recent Edge builds, and a full system
REM shutdown (power button, blackout) never lets Edge write a clean exit
REM either. Rewriting these two keys to Normal/true makes Edge skip the
REM 还原页面 prompt regardless of how the previous session ended.
REM Loop over every profile dir (Default + Profile *) so multi-profile
REM installs are also covered.
echo Marking Edge session as clean...
for /d %%P in ("%LOCALAPPDATA%\Microsoft\Edge\User Data\Default" "%LOCALAPPDATA%\Microsoft\Edge\User Data\Profile*") do (
  if exist "%%~P\Preferences" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$f='%%~P\Preferences';" ^
      "$t=Get-Content -Raw -LiteralPath $f;" ^
      "$t=$t -replace '\"exit_type\":\"[^\"]*\"','\"exit_type\":\"Normal\"';" ^
      "$t=$t -replace '\"exited_cleanly\":false','\"exited_cleanly\":true';" ^
      "[System.IO.File]::WriteAllText($f,$t)" 2>nul
  )
)

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
