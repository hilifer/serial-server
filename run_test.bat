@echo off
chcp 65001 >nul
title Energy Meter Protocol Test

echo ============================================
echo   Energy Meter Protocol Test (COM33)
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Updating code from git...
git pull
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Git pull failed, continuing with current code...
)
echo.

echo [2/3] Setting up Python environment...
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)
call venv\Scripts\activate.bat
pip install -r requirements.txt -q
echo.

echo [3/3] Running unit tests...
echo ============================================
python -m pytest tests/ -v
echo.
echo ============================================
echo   Running live meter test (COM33)...
echo ============================================
python test_meter_live.py --port COM33 --baudrate 9600

pause
