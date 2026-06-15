@echo off
chcp 65001 >nul
title 智能温室 - Windows 打包

echo ============================================
echo   智能温室监控系统 - Windows 桌面应用打包
echo ============================================
echo.

cd /d "%~dp0"

:: 检查 Python
python --version >nul 2>&1 || py --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python！
    pause
    exit /b 1
)

:: 安装依赖
echo [安装] 安装依赖...
pip install -r requirements.txt

:: 打包
echo [构建] 开始打包...
py -3 -m PyInstaller ^
    --name=SmartGreenhouse ^
    --windowed ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --hidden-import=serial ^
    --hidden-import=serial.tools.list_ports ^
    --hidden-import=matplotlib ^
    --hidden-import=matplotlib.backends.backend_tkagg ^
    --hidden-import=matplotlib.figure ^
    --hidden-import=matplotlib.backends.backend_agg ^
    --hidden-import=kiwisolver ^
    --hidden-import=matplotlib.font_manager ^
    main.py

if %errorlevel% neq 0 (
    echo [错误] 打包失败！
    pause
    exit /b 1
)

echo.
echo ============================================
echo   ✅ 打包完成！
echo   位置: dist\SmartGreenhouse\SmartGreenhouse.exe
echo   双击即可运行，无需任何依赖！
echo ============================================
pause
