@echo off
rem DawnCMS 一键启动（Windows）：双击本文件即可
cd /d %~dp0

if not exist venv\Scripts\python.exe (
    echo [错误] 尚未安装，请先双击 install.bat
    echo.
    pause
    exit /b 1
)

venv\Scripts\python.exe dawn_main.py
pause
