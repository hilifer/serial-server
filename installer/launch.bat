@echo off
chcp 65001 >nul
title 耀嵘光储充管理系统

REM Navigate to install directory
cd /d "%~dp0"

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ================================================
    echo   错误：未找到 Python！
    echo   请先安装 Python 3.10+
    echo   下载地址：https://www.python.org/downloads/
    echo   安装时请勾选 "Add Python to PATH"
    echo ================================================
    pause
    exit /b 1
)

REM Setup venv if not exists
if not exist "venv" (
    echo [1/3] 首次运行，创建虚拟环境...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo 创建虚拟环境失败！
        pause
        exit /b 1
    )
)

REM Activate venv
call venv\Scripts\activate.bat

REM Install/update dependencies
if not exist "venv\.deps_ok" (
    echo [2/3] 安装依赖...
    pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
    if %ERRORLEVEL% EQU 0 (
        echo ok > venv\.deps_ok
    ) else (
        pip install -r requirements.txt -q
        if %ERRORLEVEL% EQU 0 echo ok > venv\.deps_ok
    )
) else (
    REM Check if requirements changed
    fc /b requirements.txt venv\.deps_ok >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo 更新依赖...
        pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
        echo ok > venv\.deps_ok
    )
)

REM Open browser after 2 seconds
echo [3/3] 启动服务...
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000/"

REM Start server
echo.
echo ================================================
echo   耀嵘光储充管理系统 已启动
echo   停车场:  http://localhost:8000/
echo   能源看板: http://localhost:8000/detail.html
echo   按 Ctrl+C 停止
echo ================================================
echo.
python server.py

pause
