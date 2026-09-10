@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] 检查 PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo      正在安装 PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 ( echo 安装失败！ & pause & exit /b 1 )
)

echo [2/3] 正在打包（约 1-2 分钟）...
python -m PyInstaller --noconfirm --clean --windowed --onedir ^
    --name "图片转换助手" ^
    --icon "assets\icon.ico" ^
    --add-data "assets\icon.ico;assets" ^
    main.py
if errorlevel 1 ( echo 打包失败！ & pause & exit /b 1 )

echo [3/3] 完成！程序位于：dist\图片转换助手\图片转换助手.exe
pause
