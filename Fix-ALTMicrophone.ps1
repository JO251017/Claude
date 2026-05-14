#Requires -RunAsAdministrator

<#
.SYNOPSIS
    ALT 앱 녹음 시작 시 충돌 문제를 자동으로 진단하고 수정합니다.
#>

$consentBase = "SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
$logPath     = "$env:TEMP\Fix-ALTMicrophone.log"

function Write-Log {
    param([string]$Message, [string]$Color = "White")
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $Message"
    Add-Content -Path $logPath -Value $line -Encoding UTF8
    Write-Host $line -ForegroundColor $Color
}

function Write-Section {
    param([string]$Title)
    Write-Host ""
    Write-Host ("=" * 54) -ForegroundColor Cyan
    Write-Host "  $Title" -ForegroundColor Cyan
    Write-Host ("=" * 54) -ForegroundColor Cyan
    Add-Content -Path $logPath -Value "" -Encoding UTF8
    Add-Content -Path $logPath -Value "=== $Title ===" -Encoding UTF8
}

# 로그 초기화
"" | Out-File $logPath -Encoding UTF8
Write-Section "ALT 마이크 충돌 자동 수정 스크립트"
Write-Log "로그 위치: $logPath"

# ─────────────────────────────────────────────
# STEP 1: 마이크 레지스트리 설정
# ─────────────────────────────────────────────
Write-Section "STEP 1 - 마이크 권한 레지스트리 설정"

$regEntries = @(
    [PSCustomObject]@{ Label = "HKLM - microphone";              Path = "HKLM:\$consentBase" },
    [PSCustomObject]@{ Label = "HKCU - microphone";              Path = "HKCU:\$consentBase" },
    [PSCustomObject]@{ Label = "HKCU - microphone\NonPackaged";  Path = "HKCU:\$consentBase\NonPackaged" }
)

foreach ($entry in $regEntries) {
    if (-not (Test-Path $entry.Path)) {
        New-Item -Path $entry.Path -Force | Out-Null
        Write-Log "  생성됨: $($entry.Label)" DarkYellow
    }
    $before = try { (Get-ItemProperty $entry.Path -Name Value -EA Stop).Value } catch { "(없음)" }
    Set-ItemProperty -Path $entry.Path -Name "Value" -Value "Allow" -Type String
    $after  = (Get-ItemProperty $entry.Path -Name Value).Value
    $ok     = $after -eq "Allow"
    Write-Log ("  {0,-38} {1} → {2}  [{3}]" -f $entry.Label, $before, $after, $(if ($ok) { "OK" } else { "FAIL" })) $(if ($ok) { "Green" } else { "Red" })
}

# ─────────────────────────────────────────────
# STEP 2: Windows 오디오 서비스 재시작
# ─────────────────────────────────────────────
Write-Section "STEP 2 - Windows Audio 서비스 재시작"

$audioServices = @("AudioSrv", "AudioEndpointBuilder")
foreach ($svc in $audioServices) {
    $s = Get-Service -Name $svc -ErrorAction SilentlyContinue
    if ($null -eq $s) {
        Write-Log "  $svc : 서비스 없음 (스킵)" DarkYellow
        continue
    }
    Write-Log "  $svc : 현재 상태 = $($s.Status)"
    try {
        Restart-Service -Name $svc -Force -ErrorAction Stop
        Start-Sleep -Seconds 2
        $s.Refresh()
        Write-Log "  $svc : 재시작 후 상태 = $($s.Status)" $(if ($s.Status -eq "Running") { "Green" } else { "Red" })
    } catch {
        Write-Log "  $svc : 재시작 실패 - $($_.Exception.Message)" Red
    }
}

# ─────────────────────────────────────────────
# STEP 3: 마이크를 점유 중인 프로세스 감지 및 종료
# ─────────────────────────────────────────────
Write-Section "STEP 3 - 마이크 점유 프로세스 확인"

$audioProcs = @()
try {
    # 오디오 세션을 열고 있는 프로세스 목록 (WMI 기반)
    $audioProcs = Get-Process | Where-Object {
        $_.Modules -match "audioses|mmdevapi|avrt" -or
        $_.Name -match "zoom|teams|discord|skype|webex|obs|audacity|voicemeeter|lghub|nahimic|sonic|dts"
    } -ErrorAction SilentlyContinue
} catch {}

# ALT 프로세스 찾기 (이름 변형 포함)
$altProcs = Get-Process | Where-Object { $_.Name -match "^alt$|altapp|alt\.exe" } -ErrorAction SilentlyContinue

if ($altProcs) {
    Write-Log "  ALT 프로세스 감지됨 - 종료 중..." Yellow
    $altProcs | ForEach-Object {
        Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        Write-Log "    종료: $($_.Name) (PID $($_.Id))" Yellow
    }
    Start-Sleep -Seconds 1
} else {
    Write-Log "  ALT 프로세스 없음 (이미 꺼져 있음)" Gray
}

if ($audioProcs) {
    Write-Log "  마이크 사용 가능성 있는 앱:" Yellow
    $audioProcs | ForEach-Object {
        Write-Log "    - $($_.Name) (PID $($_.Id))" Yellow
    }
    Write-Log "  → 위 앱들이 마이크를 점유 중이면 충돌 원인일 수 있습니다." Yellow
} else {
    Write-Log "  마이크 점유 경쟁 프로세스 없음" Green
}

# ─────────────────────────────────────────────
# STEP 4: 오디오 드라이버 및 장치 상태 확인
# ─────────────────────────────────────────────
Write-Section "STEP 4 - 마이크 장치 상태 확인"

$mics = Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue |
        Where-Object { $_.FriendlyName -match "마이크|microphone|mic|input|recording" -or $_.Status -ne "OK" }

if ($mics) {
    foreach ($mic in $mics) {
        $color = if ($mic.Status -eq "OK") { "Green" } else { "Red" }
        Write-Log "  [$($mic.Status)] $($mic.FriendlyName)" $color
        if ($mic.Status -ne "OK") {
            Write-Log "    → 장치 오류 감지: 드라이버 재설치 권장" Red
        }
    }
} else {
    # 전체 오디오 입력 장치 출력
    Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue | ForEach-Object {
        $color = if ($_.Status -eq "OK") { "Green" } else { "Red" }
        Write-Log "  [$($_.Status)] $($_.FriendlyName)" $color
    }
}

# ─────────────────────────────────────────────
# STEP 5: 오디오 컴포넌트 재등록
# ─────────────────────────────────────────────
Write-Section "STEP 5 - 오디오 DLL 재등록"

$dlls = @("audiosrv.dll","mmdevapi.dll","audioses.dll","mfplat.dll")
foreach ($dll in $dlls) {
    $path = "$env:SystemRoot\System32\$dll"
    if (Test-Path $path) {
        $result = & regsvr32.exe /s $path 2>&1
        Write-Log "  재등록: $dll → 완료" Green
    } else {
        Write-Log "  재등록: $dll → 파일 없음 (스킵)" DarkYellow
    }
}

# ─────────────────────────────────────────────
# STEP 6: ALT 앱 권한 확인 및 이벤트 로그 수집
# ─────────────────────────────="────────────────
Write-Section "STEP 6 - 이벤트 뷰어에서 ALT 충돌 로그 수집"

$since = (Get-Date).AddHours(-24)
$crashEvents = Get-WinEvent -FilterHashtable @{
    LogName   = "Application"
    StartTime = $since
    Level     = 1, 2   # Critical, Error
} -ErrorAction SilentlyContinue |
Where-Object { $_.Message -match "alt|crash|audio|microphone|faulting" } |
Select-Object -First 5

if ($crashEvents) {
    Write-Log "  최근 24시간 관련 오류 이벤트:" Yellow
    foreach ($ev in $crashEvents) {
        Write-Log "  [$($ev.TimeCreated.ToString('MM-dd HH:mm'))] $($ev.ProviderName): $($ev.Message.Substring(0, [Math]::Min(120, $ev.Message.Length)))..." Yellow
    }
} else {
    Write-Log "  관련 오류 이벤트 없음" Green
}

# ─────────────────────────────────────────────
# 최종 결과
# ─────────────────────────────────────────────
Write-Section "완료 - 다음 단계"
Write-Log "  1. ALT 앱을 다시 실행해서 녹음을 시작해 보세요." White
Write-Log "  2. 여전히 튕기면 PC를 재부팅 후 재시도하세요." White
Write-Log "  3. 재부팅 후에도 동일하면 로그 파일을 확인하세요:" White
Write-Log "     $logPath" Cyan
Write-Host ""
