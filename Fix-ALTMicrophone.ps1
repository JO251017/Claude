# 관리자 권한 자동 요청
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Host "== ALT 마이크 수정 시작 ==" -ForegroundColor Cyan

# 1. camsvc 완전 비활성화
Write-Host "[1] camsvc 비활성화..." -ForegroundColor Yellow
Stop-Service "camsvc" -Force -ErrorAction SilentlyContinue
sc.exe config camsvc start= disabled | Out-Null
Write-Host "    완료" -ForegroundColor Green

# 2. 마이크 레지스트리 Allow
Write-Host "[2] 마이크 권한 설정..." -ForegroundColor Yellow
$base = "SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
foreach ($p in @("HKLM:\$base","HKCU:\$base","HKCU:\$base\NonPackaged")) {
    if (-not (Test-Path $p)) { New-Item $p -Force | Out-Null }
    Set-ItemProperty $p -Name "Value" -Value "Allow" -Type String
}
Write-Host "    완료" -ForegroundColor Green

# 3. 오디오 서비스 재시작
Write-Host "[3] 오디오 서비스 재시작..." -ForegroundColor Yellow
Restart-Service AudioEndpointBuilder -Force -ErrorAction SilentlyContinue
Restart-Service AudioSrv -Force -ErrorAction SilentlyContinue
Write-Host "    완료" -ForegroundColor Green

# 4. f_svcmgr.exe 정보 출력
Write-Host "[4] f_svcmgr.exe 정체 확인..." -ForegroundColor Yellow
$proc = Get-Process "f_svcmgr" -ErrorAction SilentlyContinue
if ($proc -and $proc.Path) {
    Write-Host "    경로: $($proc.Path)" -ForegroundColor Red
    $v = (Get-Item $proc.Path -ErrorAction SilentlyContinue).VersionInfo
    Write-Host "    제조사: $($v.CompanyName)" -ForegroundColor Red
    Write-Host "    설명: $($v.FileDescription)" -ForegroundColor Red
} else {
    Write-Host "    현재 실행 중 아님" -ForegroundColor Gray
}

Write-Host ""
Write-Host "== 완료. ALT 실행해서 녹음해 보세요 ==" -ForegroundColor Cyan
Write-Host ""
Read-Host "엔터를 누르면 닫힘"
