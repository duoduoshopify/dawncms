@echo off
rem ============================================================
rem DawnCMS — 独立博客内容管理系统
rem Copyright (c) 2026 DawnCMS. All rights reserved.
rem ============================================================
rem DawnCMS 一键安装（Windows）：双击本文件即可
cd /d %~dp0

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 install.py
    goto :done
)

where python >nul 2>nul
if %errorlevel%==0 (
    python install.py
    goto :done
)

echo [错误] 未找到 Python。请先安装 Python 3.12：
echo   https://www.python.org/downloads/
echo   安装时务必勾选 "Add python.exe to PATH"

:done
echo.
pause
