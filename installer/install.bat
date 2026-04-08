@echo off
chcp 65001 >nul
title 光储充管理系统 — 安装

cd /d "%~dp0"

echo ================================================
echo   光储充管理系统 — 一键安装
echo ================================================
echo.

REM Check if yriot.exe exists
if not exist "yriot.exe" (
    REM Maybe we're in installer subfolder, check parent
    if exist "..\yriot.exe" (
        cd /d "%~dp0\.."
    ) else (
        echo [!] 未找到 yriot.exe
        echo     请确保 install.bat 和 yriot.exe 在同一目录
        pause
        exit /b 1
    )
)

echo [1/2] 创建桌面快捷方式...

REM Create desktop shortcut using PowerShell (more reliable than vbs)
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut([System.IO.Path]::Combine($ws.SpecialFolders('Desktop'), '光储充管理系统.lnk')); $s.TargetPath = '%CD%\yriot.exe'; $s.WorkingDirectory = '%CD%'; $s.Description = '光储充管理系统'; $s.Save()"

if %ERRORLEVEL% EQU 0 (
    echo [OK] 桌面快捷方式已创建
) else (
    echo [!] 快捷方式创建失败，请手动双击 yriot.exe 运行
)
echo.

echo [2/2] 测试启动...
echo.

REM Quick test — start server, wait, check, then stop
start "" /B yriot.exe
timeout /t 5 /nobreak >nul
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/' -TimeoutSec 3 -UseBasicParsing; if($r.StatusCode -eq 200) { Write-Host '[OK] 服务启动正常' } } catch { Write-Host '[!] 服务未响应，可能端口被占用' }"
taskkill /f /im yriot.exe >nul 2>&1

echo.
echo ================================================
echo   安装完成！
echo.
echo   使用方法:
echo     双击桌面上的 "光储充管理系统" 图标
echo     或直接双击 yriot.exe
echo.
echo   浏览器访问:
echo     停车场:    http://localhost:8000/
echo     能源看板:  http://localhost:8000/detail.html
echo ================================================
echo.
pause
