@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% -m pip install -q -r requirements.txt
%PY% -m src.cli check
echo.
echo 위의 [정상]/[실패] 줄을 복사해서 보내 주세요. 아무 키나 누르면 닫힙니다.
pause >nul
