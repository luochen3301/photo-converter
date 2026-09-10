@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 图片转换助手...
python main.py
if errorlevel 1 pause
