@echo off
setlocal enabledelayedexpansion
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
git pull origin claude/understand-project-TBDmP
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

REM Start unified server
echo [3/3] Starting server...
echo   停车场:    http://localhost:8000/
echo   能源看板:  http://localhost:8000/detail.html
echo   按 Ctrl+C 或关闭窗口停止
echo ============================================

REM Start server in background, wait for it to be ready
start "" /B python server.py

REM Wait for serial port and HTTP service to be ready (max 15 seconds)
set READY=0
for /L %%i in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/status' -TimeoutSec 2 -UseBasicParsing; if($r.StatusCode -eq 200) { exit 0 } } catch { exit 1 }" 2>nul
    if !ERRORLEVEL! EQU 0 (
        set READY=1
        goto :CHECK_SERIAL
    )
)

:CHECK_SERIAL
if %READY% EQU 0 (
    echo.
    echo ================================================
    echo   [!] 警告：服务启动超时！
    echo ================================================
    pause
    goto :WAIT_EXIT
)

REM Check serial port status
powershell -Command "$r = Invoke-WebRequest -Uri 'http://localhost:8000/status' -UseBasicParsing; $j = $r.Content | ConvertFrom-Json; $allOk = $true; foreach($p in $j.ports.PSObject.Properties) { if($p.Value.status -ne 'connected') { Write-Host ('[!] 警告：' + $p.Name + ' 串口未连接 - ' + $p.Value.last_error); $allOk = $false } else { Write-Host ('[OK] ' + $p.Name + ' 已连接') } }; if(-not $allOk) { Write-Host ''; Write-Host '部分串口未连接，请检查设备连接！'; Write-Host '' }" 2>nul

echo.

REM Open browser in fullscreen
start chrome --start-fullscreen http://localhost:8000/ 2>nul || start msedge --start-fullscreen http://localhost:8000/ 2>nul || start http://localhost:8000/

:WAIT_EXIT
REM Keep window open to show logs
echo 服务运行中，按 Ctrl+C 停止...
cmd /k
