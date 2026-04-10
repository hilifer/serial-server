@echo off
chcp 65001 >nul

echo ================================================
echo   设置开机自启动
echo ================================================
echo.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%~dp0start.bat"
set "SHORTCUT=%STARTUP%\光储充管理系统.lnk"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0'; $s.Description = '光储充管理系统'; $s.WindowStyle = 7; $s.Save()"

if %ERRORLEVEL% EQU 0 (
    echo [OK] 已设置开机自启动
    echo     快捷方式: %SHORTCUT%
    echo     启动项:   %TARGET%
) else (
    echo [!] 设置失败
)

echo.
echo 取消自启动：删除以下文件即可
echo   %SHORTCUT%
echo.
pause
