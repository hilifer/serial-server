@echo off
chcp 65001 >nul
echo ================================================
echo   耀嵘光储充管理系统 — 构建 EXE 安装包
echo ================================================
echo.

cd /d "%~dp0\.."

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [!] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

REM Setup venv
if not exist "venv" (
    echo [1/4] 创建虚拟环境...
    python -m venv venv
)
call venv\Scripts\activate.bat

REM Install dependencies
echo [2/4] 安装依赖...
pip install -r requirements.txt -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
pip install pyinstaller -q -i https://pypi.tuna.tsinghua.edu.cn/simple 2>nul
echo.

REM Build with PyInstaller
echo [3/4] 编译打包中（约2-3分钟）...
pyinstaller --noconfirm ^
    --onefile ^
    --name "耀嵘光储充管理系统" ^
    --console ^
    --strip ^
    --optimize 2 ^
    --add-data "config.yaml;." ^
    --add-data "requirements.txt;." ^
    --add-data "web;web" ^
    --hidden-import serial_manager ^
    --hidden-import meter ^
    --hidden-import meter_api ^
    --hidden-import parking ^
    --hidden-import state ^
    --hidden-import deps ^
    --hidden-import colors ^
    --hidden-import flask ^
    --hidden-import yaml ^
    --hidden-import paho.mqtt.client ^
    --hidden-import serial ^
    --hidden-import requests ^
    --hidden-import jinja2 ^
    --hidden-import markupsafe ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --exclude-module scipy ^
    --exclude-module PIL ^
    --distpath installer\output ^
    --workpath installer\build ^
    --specpath installer ^
    server.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] 编译失败！
    pause
    exit /b 1
)

echo.
echo [4/4] 创建安装包...

REM Copy config.yaml next to exe (user may need to edit)
copy /y config.yaml installer\output\config.yaml >nul

REM Create launcher script for the exe
(
echo @echo off
echo chcp 65001 ^>nul
echo title 耀嵘光储充管理系统
echo echo 正在启动...
echo start "" cmd /c "timeout /t 3 /nobreak ^>nul ^&^& start http://localhost:8000/"
echo "%%~dp0耀嵘光储充管理系统.exe"
echo pause
) > installer\output\启动.bat

echo.
echo ================================================
echo   构建完成!
echo.
echo   输出文件:
echo     installer\output\耀嵘光储充管理系统.exe
echo     installer\output\config.yaml
echo     installer\output\启动.bat
echo.
echo   使用方法:
echo     1. 把 output 文件夹拷贝到目标电脑
echo     2. 双击 启动.bat
echo     3. 浏览器自动打开 http://localhost:8000/
echo.
echo   注意: 目标电脑不需要安装 Python!
echo ================================================
pause
