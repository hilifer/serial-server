@echo off
chcp 65001 >nul
echo ================================================
echo   打包绿色安装包 (ZIP)
echo ================================================

cd /d "%~dp0\.."

REM Create temp folder
set PACKDIR=%TEMP%\yaorong_pack
if exist "%PACKDIR%" rmdir /s /q "%PACKDIR%"
mkdir "%PACKDIR%"

REM Copy project files (exclude venv, __pycache__, .git, lizi)
echo 复制项目文件...
xcopy /s /e /q /y server.py "%PACKDIR%\" >nul
xcopy /s /e /q /y serial_manager.py "%PACKDIR%\" >nul
xcopy /s /e /q /y meter.py "%PACKDIR%\" >nul
xcopy /s /e /q /y meter_api.py "%PACKDIR%\" >nul
xcopy /s /e /q /y parking.py "%PACKDIR%\" >nul
xcopy /s /e /q /y state.py "%PACKDIR%\" >nul
xcopy /s /e /q /y deps.py "%PACKDIR%\" >nul
xcopy /s /e /q /y colors.py "%PACKDIR%\" >nul
xcopy /s /e /q /y config.yaml "%PACKDIR%\" >nul
xcopy /s /e /q /y requirements.txt "%PACKDIR%\" >nul
xcopy /s /e /q /y web "%PACKDIR%\web\" >nul
xcopy /s /e /q /y docs "%PACKDIR%\docs\" >nul
xcopy /s /e /q /y installer\launch.bat "%PACKDIR%\" >nul
xcopy /s /e /q /y installer\install.bat "%PACKDIR%\" >nul
xcopy /s /e /q /y installer\create_shortcut.vbs "%PACKDIR%\installer\" >nul

REM Create zip
echo 打包中...
set ZIPNAME=耀嵘光储充管理系统_v1.0.zip
powershell -Command "Compress-Archive -Path '%PACKDIR%\*' -DestinationPath '%~dp0\%ZIPNAME%' -Force"

REM Cleanup
rmdir /s /q "%PACKDIR%"

echo.
echo ================================================
echo   打包完成: installer\%ZIPNAME%
echo.
echo   使用方法:
echo     1. 解压到任意目录
echo     2. 双击 install.bat 安装
echo     3. 以后双击桌面快捷方式启动
echo ================================================
pause
