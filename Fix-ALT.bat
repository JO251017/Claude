@echo off
:: 관리자 권한 자동 요청
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo == ALT 마이크 수정 중 ==

echo [1] camsvc 비활성화...
sc stop camsvc >nul 2>&1
sc config camsvc start= disabled >nul 2>&1
echo     완료

echo [2] 마이크 레지스트리 Allow 설정...
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone" /v Value /t REG_SZ /d Allow /f >nul
reg add "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone" /v Value /t REG_SZ /d Allow /f >nul
reg add "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone\NonPackaged" /v Value /t REG_SZ /d Allow /f >nul
echo     완료

echo [3] 오디오 서비스 재시작...
net stop AudioEndpointBuilder /y >nul 2>&1
net stop AudioSrv /y >nul 2>&1
net start AudioEndpointBuilder >nul 2>&1
net start AudioSrv >nul 2>&1
echo     완료

echo.
echo == 완료! ALT 실행해서 녹음해 보세요 ==
echo.
pause
