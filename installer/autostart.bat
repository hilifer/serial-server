@echo off
chcp 65001 >nul

echo ================================================
echo   开机自启动
echo ================================================
echo.
echo 开机自启**已经是自动的**，无需单独设置。
echo.
echo start.bat 第一次运行时会自己在启动文件夹里注册一个
echo 快捷方式（幂等，已存在则跳过）。也就是说：
echo.
echo   运行一次 start.bat = 自动完成开机自启注册
echo.
echo 这个脚本以前会再独立创建一遍同名快捷方式，和 start.bat
echo 的自注册逻辑重复、还容易不一致，所以已改为只做提示。
echo.

set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\光储充管理系统.lnk"
if exist "%SHORTCUT%" (
  echo [状态] 已注册：%SHORTCUT%
) else (
  echo [状态] 尚未注册 —— 运行一次上层目录的 start.bat 即可。
)
echo.
echo 取消自启动：删除以下文件即可
echo   %SHORTCUT%
echo.
pause
