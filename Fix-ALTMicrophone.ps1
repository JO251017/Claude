#Requires -RunAsAdministrator

<#
.SYNOPSIS
    ALT 앱 녹음 시작 시 충돌 문제를 자동으로 진단하고 수정합니다. (v3)

.DESCRIPTION
    확인된 핵심 원인:
    Windows 11 24H2 KB5066835 (2025-10 누적 업데이트)가
    Capability Access Manager Service(camsvc)에 데드락 버그를 유발.
    마이크에 접근하는 모든 앱(ALT, Zoom, Teams 등)이 무음 종료됨.

    해결 우선순위:
    1. KB5066835 설치 여부 확인 → 제거 시도
    2. 제거 불가 시 camsvc 서비스 비활성화 (데드락 우회)
    3. 마이크 레지스트리 권한 직접 설정 (camsvc 없이도 동작)
    4. 오디오 서비스 재시작
#>

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
Write-Section "ALT 마이크 충돌 수정 v3 - KB5066835 버그 대응"
Write-Log "로그: $logPath"

# ──────────────────────────────────────────────────────
# STEP 1: KB5066835 설치 여부 확인 및 제거
#   원인: 이 업데이트가 camsvc에 데드락 버그를 주입
# ──────────────────────────────────────────────────────
Write-Section "STEP 1 - KB5066835 버그 업데이트 확인 및 제거"

$buggyKBs = @("KB5066835", "KB5068861")
$removedAny = $false

foreach ($kb in $buggyKBs) {
    $installed = Get-HotFix -Id $kb -ErrorAction SilentlyContinue
    if ($installed) {
        Write-Log "  발견: $kb (설치일: $($installed.InstalledOn)) — 제거 시도 중..." Yellow
        try {
            $proc = Start-Process -FilePath "wusa.exe" `
                -ArgumentList "/uninstall /kb:$($kb -replace 'KB','') /quiet /norestart" `
                -Wait -PassThru -ErrorAction Stop
            if ($proc.ExitCode -eq 0) {
                Write-Log "  $kb 제거 완료. 재부팅 후 효과 적용됩니다." Green
                $removedAny = $true
            } elseif ($proc.ExitCode -eq 3010) {
                Write-Log "  $kb 제거 완료 (재부팅 필요)." Green
                $removedAny = $true
            } else {
                Write-Log "  $kb 제거 실패 (ExitCode: $($proc.ExitCode)) — STEP 2로 우회합니다." Yellow
            }
        } catch {
            Write-Log "  $kb 제거 중 오류: $($_.Exception.Message)" Red
        }
    } else {
        Write-Log "  $kb 미설치 (해당 없음)" Gray
    }
}

if (-not $removedAny) {
    # 현재 설치된 관련 최신 KB 목록 출력 (진단용)
    Write-Log "  최근 설치된 오디오 관련 업데이트:" Gray
    Get-HotFix | Where-Object { $_.InstalledOn -gt (Get-Date).AddDays(-90) } |
        Sort-Object InstalledOn -Descending | Select-Object -First 5 |
        ForEach-Object { Write-Log "    $($_.HotFixID)  $($_.InstalledOn.ToString('yyyy-MM-dd'))" Gray }
}

# ──────────────────────────────────────────────────────
# STEP 2: camsvc 서비스 데드락 우회
#   KB 제거가 불가능하거나 다른 원인일 때 직접 우회
#   camsvc를 Manual로 전환하고 현재 인스턴스를 중지
# ──────────────────────────────────────────────────────
Write-Section "STEP 2 - camsvc 서비스 데드락 우회"

$camsvc = Get-Service -Name "camsvc" -ErrorAction SilentlyContinue
if ($camsvc) {
    Write-Log "  camsvc 현재 상태: $($camsvc.Status) / 시작유형: $($camsvc.StartType)"

    if ($camsvc.Status -eq "Running") {
        try {
            Stop-Service -Name "camsvc" -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 500
            $camsvc.Refresh()
            Write-Log "  camsvc 중지 완료: $($camsvc.Status)" Green
        } catch {
            Write-Log "  camsvc 중지 실패: $($_.Exception.Message)" Red
        }
    }

    # Manual로 변경 (자동 시작 방지, 필요 시 수동 시작 가능)
    try {
        Set-Service -Name "camsvc" -StartupType Manual -ErrorAction Stop
        Write-Log "  camsvc 시작 유형 → Manual (자동 시작 해제)" Green
    } catch {
        # sc.exe fallback
        & sc.exe config camsvc start= demand | Out-Null
        Write-Log "  camsvc 시작 유형 → Manual (sc.exe 사용)" Green
    }
} else {
    Write-Log "  camsvc 서비스 없음 (Windows 버전 다름)" DarkYellow
}

# ──────────────────────────────────────────────────────
# STEP 3: 마이크 레지스트리 권한 직접 설정
#   camsvc 없이도 동작하는 레지스트리 직접 설정
# ──────────────────────────────────────────────────────
Write-Section "STEP 3 - 마이크 권한 레지스트리 직접 설정"

$consentBase = "SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
@(
    "HKLM:\$consentBase",
    "HKCU:\$consentBase",
    "HKCU:\$consentBase\NonPackaged"
) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -Path $_ -Force | Out-Null }
    Set-ItemProperty -Path $_ -Name "Value" -Value "Allow" -Type String
    Write-Log "  Allow 설정 완료: $_" Green
}

# ──────────────────────────────────────────────────────
# STEP 4: Windows Audio 서비스 재시작
# ──────────────────────────────────────────────────────
Write-Section "STEP 4 - Windows Audio 서비스 재시작"

foreach ($svc in @("AudioEndpointBuilder", "AudioSrv")) {
    try {
        Restart-Service -Name $svc -Force -ErrorAction Stop
        Start-Sleep -Milliseconds 800
        $s = Get-Service -Name $svc
        Write-Log "  $svc → $($s.Status)" $(if ($s.Status -eq "Running") { "Green" } else { "Red" })
    } catch {
        Write-Log "  $svc 재시작 실패: $($_.Exception.Message)" Red
    }
}

# ──────────────────────────────────────────────────────
# STEP 5: 경쟁 프로세스 확인
# ──────────────────────────────────────────────────────
Write-Section "STEP 5 - 마이크 경쟁 프로세스 확인"

$rivals = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "zoom|teams|discord|skype|webex|obs|audacity|voicemeeter|nahimic|sonic|dts|razer" }

if ($rivals) {
    Write-Log "  마이크 점유 가능 앱 감지 — ALT 실행 전 종료 권장:" Yellow
    $rivals | ForEach-Object { Write-Log "    - $($_.Name) (PID $($_.Id))" Yellow }
} else {
    Write-Log "  경쟁 프로세스 없음" Green
}

# ──────────────────────────────────────────────────────
# 완료 및 안내
# ──────────────────────────────────────────────────────
Write-Section "완료 — 다음 단계"

if ($removedAny) {
    Write-Log "  KB 업데이트 제거 완료 → PC를 반드시 재부팅하세요." Cyan
    Write-Log "  재부팅 후 ALT를 실행해 녹음을 시작해 보세요." Cyan
} else {
    Write-Log "  camsvc 데드락 우회 완료." Cyan
    Write-Log "  지금 ALT를 실행해 녹음을 시작해 보세요. (재부팅 불필요)" Cyan
    Write-Log ""
    Write-Log "  여전히 문제가 지속되면 Windows를 최신 버전으로 업데이트하거나" White
    Write-Log "  인플레이스 복구 설치(Windows 11 ISO 실행)를 권장합니다." White
}
Write-Log "  로그 위치: $logPath" Gray
Write-Host ""
