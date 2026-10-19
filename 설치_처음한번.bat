@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python -m pip install -r requirements.txt
python -m src.cli init
echo.
pause
