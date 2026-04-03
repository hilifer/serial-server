@echo off
chcp 65001 >nul
title 耀嵘光储充管理系统 — 安装

echo ================================================
echo   耀嵘光储充管理系统 — 一键安装
echo ================================================
echo.

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] 未检测到 Python，正在下载安装...
    echo     请在弹出的安装界面中勾选 "Add Python to PATH"
    echo.
    REM Try to download Python installer
    powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.7/python-3.12.7-amd64.exe' -OutFile '%TEMP%\python_installer.exe'}" 2>nul
    if exist "%TEMP%\python_installer.exe" (
        echo 正在启动 Python 安装程序...
        "%TEMP%\python_installer.exe" /passive InstallAllUsers=1 PrependPath=1
        echo Python 安装完成，请关闭此窗口重新运行 install.bat
        pause
        exit /b
    ) else (
        echo [!] 无法自动下载 Python
        echo     请手动安装 Python 3.10+:
        echo     https://www.python.org/downloads/
        echo     安装时务必勾选 "Add Python to PATH"
        pause
        exit /b 1
    )
)

for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo [✓] 检测到 %PYVER%
echo.

REM Create venv
echo [1/4] 创建虚拟环境...
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat
echo [✓] 虚拟环境就绪
echo.

REM Install dependencies
echo [2/4] 安装依赖包...
pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
if %ERRORLEVEL% NEQ 0 (
    pip install -r requirements.txt -q
)
echo ok > venv\.deps_ok
echo [✓] 依赖安装完成
echo.

REM Create desktop shortcut
echo [3/4] 创建桌面快捷方式...
cscript //nologo installer\create_shortcut.vbs
echo [✓] 快捷方式已创建
echo.

REM Test run
echo [4/4] 测试启动...
python -c "import yaml, serial, flask, paho.mqtt; print('所有依赖正常')"
echo.

echo ================================================
echo   安装完成！
echo.
echo   启动方式:
echo     1. 双击桌面上的 "耀嵘光储充管理系统"
echo     2. 或运行 launch.bat
echo.
echo   访问地址:
echo     停车场:  http://localhost:8000/
echo     能源看板: http://localhost:8000/detail.html
echo ================================================
echo.

set /p START="是否立即启动？(Y/N): "
if /i "%START%"=="Y" (
    call launch.bat
)

pause
