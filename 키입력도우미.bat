@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install -q -r requirements.txt
%PY% -m src.setup_keys
echo.
%PY% -m src.cli check
echo.
echo 위 [정상]/[실패]/[입력 확인] 줄을 보내 주세요. 아무 키나 누르면 닫힙니다.
pause >nul
