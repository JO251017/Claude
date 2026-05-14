# 관리자 권한 자동 요청
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]"Administrator")) {
    Start-Process powershell -ArgumentList "-ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

$logPath = "$env:TEMP\Fix-ALTMicrophone.log"

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $ts   = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Add-Content -Path $logPath -Value $line -Encoding UTF8
    Write-Host $line -ForegroundColor $Color
}
function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ("=" * 60) -ForegroundColor Cyan
    Add-Content -Path $logPath -Value "`n=== $Title ===" -Encoding UTF8
}

"" | Out-File $logPath -Encoding UTF8
Write-Section "ALT 마이크 충돌 수정 v4"

# ──────────────────────────────────────────────────────
# STEP 1: camsvc 완전 비활성화 (Manual은 재시작될 수 있음)
# ──────────────────────────────────────────────────────
Write-Section "STEP 1 - camsvc 완전 비활성화"

$camsvc = Get-Service "camsvc" -ErrorAction SilentlyContinue
if ($camsvc) {
    Write-Log "  현재: $($camsvc.Status) / $($camsvc.StartType)"
    Stop-Service "camsvc" -Force -ErrorAction SilentlyContinue
    # Disabled로 설정 (Manual은 트리거로 재시작 가능)
    & sc.exe config camsvc start= disabled | Out-Null
    # 트리거 제거 (서비스 트리거로 자동 시작되는 것 방지)
    & sc.exe triggerinfo camsvc delete 2>$null | Out-Null
    Start-Sleep -Milliseconds 500
    $camsvc.Refresh()
    Write-Log "  변경 후: $($camsvc.Status) / $(& sc.exe qc camsvc | Select-String 'START_TYPE')" Green
} else {
    Write-Log "  camsvc 없음" Gray
}

# ──────────────────────────────────────────────────────
# STEP 2: f_svcmgr.exe / f_icosvc.dll 충돌 원인 파악
#   이 프로세스가 무엇인지 찾아서 ALT와의 관계 파악
# ──────────────────────────────────────────────────────
Write-Section "STEP 2 - f_svcmgr.exe 정체 파악"

$fSvcPath = (Get-Process "f_svcmgr" -ErrorAction SilentlyContinue).Path
if (-not $fSvcPath) {
    # 프로세스 없으면 설치 경로 검색
    $fSvcPath = Get-ChildItem -Path "C:\Program Files","C:\Program Files (x86)","$env:LOCALAPPDATA\Programs" `
        -Filter "f_svcmgr.exe" -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}

if ($fSvcPath) {
    Write-Log "  발견: $fSvcPath" Yellow
    $info = (Get-Item $fSvcPath).VersionInfo
    Write-Log "  제조사: $($info.CompanyName)" Yellow
    Write-Log "  설명:   $($info.FileDescription)" Yellow
    Write-Log "  버전:   $($info.FileVersion)" Yellow
} else {
    Write-Log "  f_svcmgr.exe 실행 중 아님 / 경로 미확인" Gray
}

# f_icosvc.dll 위치 확인
$fDllPath = Get-ChildItem -Path "C:\Program Files","C:\Program Files (x86)","$env:LOCALAPPDATA\Programs" `
    -Filter "f_icosvc.dll" -Recurse -ErrorAction SilentlyContinue |
    Select-Object -First 1 -ExpandProperty FullName

if ($fDllPath) {
    $info = (Get-Item $fDllPath).VersionInfo
    Write-Log "  f_icosvc.dll 위치: $fDllPath" Yellow
    Write-Log "  제조사: $($info.CompanyName)" Yellow
    Write-Log "  설명:   $($info.FileDescription)" Yellow
}

# ──────────────────────────────────────────────────────
# STEP 3: ALT 설치 경로 및 실행 파일 확인
# ──────────────────────────────────────────────────────
Write-Section "STEP 3 - ALT 앱 설치 경로 확인"

$altSearchPaths = @(
    "$env:LOCALAPPDATA\Programs",
    "$env:LOCALAPPDATA",
    "C:\Program Files",
    "C:\Program Files (x86)"
)
$altExe = $null
foreach ($base in $altSearchPaths) {
    $found = Get-ChildItem -Path $base -Filter "*.exe" -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "^alt" -or $_.DirectoryName -match "\\alt" } |
        Select-Object -First 1
    if ($found) { $altExe = $found.FullName; break }
}

if ($altExe) {
    Write-Log "  ALT 실행파일: $altExe" Green
    $altDir = Split-Path $altExe
    Write-Log "  ALT 디렉토리: $altDir" Green
    # f_svcmgr이 ALT 폴더 안에 있는지 확인
    $fInAlt = Get-ChildItem -Path $altDir -Filter "f_svcmgr.exe" -Recurse -ErrorAction SilentlyContinue
    if ($fInAlt) {
        Write-Log "  ★ f_svcmgr.exe 가 ALT 폴더 안에 있음! ALT 내부 서비스 충돌입니다." Red
        Write-Log "    경로: $($fInAlt.FullName)" Red
    }
} else {
    Write-Log "  ALT 실행파일 자동 탐색 실패" DarkYellow
    Write-Log "  아래 경로들을 직접 확인하세요:" DarkYellow
    $altSearchPaths | ForEach-Object { Write-Log "    $_" Gray }
}

# ──────────────────────────────────────────────────────
# STEP 4: 마이크 권한 레지스트리
# ──────────────────────────────────────────────────────
Write-Section "STEP 4 - 마이크 권한 레지스트리"

$consentBase = "SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
@("HKLM:\$consentBase","HKCU:\$consentBase","HKCU:\$consentBase\NonPackaged") | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item $_ -Force | Out-Null }
    Set-ItemProperty $_ -Name "Value" -Value "Allow" -Type String
    Write-Log "  Allow: $_" Green
}

# ──────────────────────────────────────────────────────
# STEP 5: Windows Audio 서비스 재시작
# ──────────────────────────────────────────────────────
Write-Section "STEP 5 - Windows Audio 서비스 재시작"

foreach ($svc in @("AudioEndpointBuilder","AudioSrv")) {
    Restart-Service $svc -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    $s = Get-Service $svc
    Write-Log "  $svc → $($s.Status)" $(if ($s.Status -eq "Running") {"Green"} else {"Red"})
}

# ──────────────────────────────────────────────────────
# 완료
# ──────────────────────────────────────────────────────
Write-Section "완료"
Write-Log "  camsvc Disabled 설정 완료." Cyan
Write-Log "  ALT를 실행해 녹음을 시작해 보세요." Cyan
Write-Log ""
Write-Log "  ※ STEP 2에서 f_svcmgr.exe 제조사/설명이 출력됐다면" White
Write-Log "    그 내용을 캡처해서 알려주세요." White
Write-Log "  로그: $logPath" Gray
Write-Host ""
Read-Host "엔터를 누르면 창이 닫힙니다"
