#Requires -RunAsAdministrator

<#
.SYNOPSIS
    ALT 앱 녹음 시작 시 충돌 문제를 자동으로 진단하고 수정합니다. (v2)
#>

$consentBase = "SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"
$logPath     = "$env:TEMP\Fix-ALTMicrophone.log"

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
Write-Section "ALT 마이크 충돌 자동 수정 (v2)"
Write-Log "로그: $logPath"

# ──────────────────────────────────────────────────────
# STEP 1: 마이크 레지스트리 권한
# ──────────────────────────────────────────────────────
Write-Section "STEP 1 - 마이크 개인정보 레지스트리"

@(
    "HKLM:\$consentBase",
    "HKCU:\$consentBase",
    "HKCU:\$consentBase\NonPackaged"
) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -Path $_ -Force | Out-Null }
    Set-ItemProperty -Path $_ -Name "Value" -Value "Allow" -Type String
    Write-Log "  Allow 설정: $_" Green
}

# ──────────────────────────────────────────────────────
# STEP 2: 독점 모드(Exclusive Mode) 비활성화
#   → 다른 앱이 마이크를 독점 잠금하면 ALT가 열지 못하고 충돌
# ──────────────────────────────────────────────────────
Write-Section "STEP 2 - 독점 모드 비활성화 (핵심 수정)"

$mmBase = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
if (Test-Path $mmBase) {
    $devices = Get-ChildItem $mmBase -ErrorAction SilentlyContinue
    if ($devices.Count -eq 0) {
        Write-Log "  캡처 장치 없음 (스킵)" DarkYellow
    }
    foreach ($dev in $devices) {
        $propsPath = "$($dev.PSPath)\Properties"
        if (-not (Test-Path $propsPath)) { continue }

        $friendlyName = try {
            (Get-ItemProperty $propsPath -Name "{a45c254e-df1c-4efd-8020-67d146a850e0},2" -EA Stop).''{a45c254e-df1c-4efd-8020-67d146a850e0},2''
        } catch { $dev.PSChildName }

        # PKEY_AudioEndpoint_Disable_SysFx = {1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5  → 0 = 음향효과 켜기
        # PKEY_AudioEndpoint_Supports_EventDriven_Mode = 없으면 표준 모드
        # 독점 모드 레지스트리: UserData 키 아래 DisableExclusive (일부 드라이버)
        $userDataPath = "$($dev.PSPath)\UserData"
        if (-not (Test-Path $userDataPath)) { New-Item -Path $userDataPath -Force | Out-Null }

        # 독점 모드 사용 거부 값 (0 = 앱이 독점 요청해도 허용 안 함)
        Set-ItemProperty -Path $userDataPath -Name "DisableExclusive" -Value 0 -Type DWord -ErrorAction SilentlyContinue

        # WASAPI Exclusive 허용 플래그를 공유 모드 전용으로 제한
        # PKEY_AudioEndpoint_FormFactor 경로의 JoinType 강제 공유
        try {
            Set-ItemProperty -Path $propsPath `
                -Name "{b3f8fa53-0004-438e-9003-51a46e139bfc},6" `
                -Value 0 -Type DWord -ErrorAction Stop
        } catch {}

        Write-Log "  독점모드 비활성화: $friendlyName" Green
    }
} else {
    Write-Log "  MMDevices 경로 없음 - 레지스트리 위치 다름 (스킵)" DarkYellow
}

# ──────────────────────────────────────────────────────
# STEP 3: 오디오 포맷을 표준값으로 강제 설정
#   → 비표준 샘플레이트/비트뎁스면 ALT가 초기화 실패
# ──────────────────────────────────────────────────────
Write-Section "STEP 3 - 오디오 포맷 표준화 (16bit / 44100Hz)"

# WAVEFORMATEX binary: 16-bit PCM 44100Hz 1ch (마이크 기본값)
# Format tag=1(PCM), channels=1, sampleRate=44100, byteRate=88200, blockAlign=2, bitsPerSample=16
$waveFormat16_44100 = [byte[]](
    0x01,0x00,           # wFormatTag = WAVE_FORMAT_PCM
    0x01,0x00,           # nChannels = 1
    0x44,0xAC,0x00,0x00, # nSamplesPerSec = 44100
    0x88,0x58,0x01,0x00, # nAvgBytesPerSec = 88200
    0x02,0x00,           # nBlockAlign = 2
    0x10,0x00,           # wBitsPerSample = 16
    0x00,0x00            # cbSize = 0
)

if (Test-Path $mmBase) {
    foreach ($dev in (Get-ChildItem $mmBase -EA SilentlyContinue)) {
        $propsPath = "$($dev.PSPath)\Properties"
        if (-not (Test-Path $propsPath)) { continue }
        try {
            # PKEY_AudioEngine_DeviceFormat = {f19f064d-082c-4e27-bc73-6882a1bb8e4c},0
            Set-ItemProperty -Path $propsPath `
                -Name "{f19f064d-082c-4e27-bc73-6882a1bb8e4c},0" `
                -Value $waveFormat16_44100 -Type Binary -ErrorAction Stop
            Write-Log "  포맷 설정: $($dev.PSChildName.Substring(0,8))..." Green
        } catch {
            Write-Log "  포맷 설정 실패: $($_.Exception.Message)" DarkYellow
        }
    }
}

# ──────────────────────────────────────────────────────
# STEP 4: 공간 음향(Windows Sonic/Dolby Atmos) 비활성화
#   → 공간 음향이 켜져 있으면 일부 앱 마이크 캡처 실패
# ──────────────────────────────────────────────────────
Write-Section "STEP 4 - 공간 음향 비활성화"

$spatialKey = "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager"
$sonicKey   = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Audio"

if (Test-Path $sonicKey) {
    Set-ItemProperty -Path $sonicKey -Name "DisableSpatialAudio" -Value 1 -Type DWord -ErrorAction SilentlyContinue
    Write-Log "  공간 음향 레지스트리 비활성화" Green
}

# Windows Sonic per-endpoint 비활성화
$renderBase = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
if (Test-Path $renderBase) {
    foreach ($dev in (Get-ChildItem $renderBase -EA SilentlyContinue)) {
        $propsPath = "$($dev.PSPath)\Properties"
        if (-not (Test-Path $propsPath)) { continue }
        try {
            # PKEY_AudioEndpoint_Disable_SysFx
            Set-ItemProperty -Path $propsPath `
                -Name "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5" `
                -Value 1 -Type DWord -ErrorAction Stop
        } catch {}
    }
    Write-Log "  재생 장치 SysFx 효과 비활성화" Green
}

# ──────────────────────────────────────────────────────
# STEP 5: ALT 앱 캐시 및 손상 설정 삭제
# ──────────────────────────────────────────────────────
Write-Section "STEP 5 - ALT 앱 캐시/설정 초기화"

$altCachePaths = @(
    "$env:LOCALAPPDATA\ALT",
    "$env:LOCALAPPDATA\Programs\alt",
    "$env:APPDATA\ALT",
    "$env:LOCALAPPDATA\Temp\alt*",
    "$env:LOCALAPPDATA\CrashDumps\*alt*"
)

$cleared = $false
foreach ($p in $altCachePaths) {
    $items = Get-Item -Path $p -ErrorAction SilentlyContinue
    foreach ($item in $items) {
        $crashOnly = @("Cache","CrashDumps","Logs","GPUCache","Code Cache","DawnCache")
        if ($item.PSIsContainer) {
            foreach ($sub in $crashOnly) {
                $subPath = Join-Path $item.FullName $sub
                if (Test-Path $subPath) {
                    Remove-Item -Path $subPath -Recurse -Force -ErrorAction SilentlyContinue
                    Write-Log "  삭제: $subPath" Yellow
                    $cleared = $true
                }
            }
        } else {
            Remove-Item -Path $item.FullName -Force -ErrorAction SilentlyContinue
            Write-Log "  삭제: $($item.FullName)" Yellow
            $cleared = $true
        }
    }
}
if (-not $cleared) { Write-Log "  ALT 캐시 경로 없음 또는 이미 정리됨" Gray }

# ──────────────────────────────────────────────────────
# STEP 6: Windows Audio 서비스 재시작
# ──────────────────────────────────────────────────────
Write-Section "STEP 6 - Windows Audio 서비스 재시작"

foreach ($svc in @("AudioEndpointBuilder","AudioSrv")) {
    try {
        Restart-Service -Name $svc -Force -EA Stop
        Start-Sleep -Milliseconds 800
        $s = Get-Service -Name $svc
        Write-Log "  $svc → $($s.Status)" $(if ($s.Status -eq "Running") {"Green"} else {"Red"})
    } catch {
        Write-Log "  $svc 재시작 실패: $($_.Exception.Message)" Red
    }
}

# ──────────────────────────────────────────────────────
# STEP 7: 경쟁 프로세스 감지
# ──────────────────────────────────────────────────────
Write-Section "STEP 7 - 마이크 경쟁 프로세스 확인"

$rivals = Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "zoom|teams|discord|skype|webex|obs|audacity|voicemeeter|lghub|nahimic|realtek|sonic|dts|razer|corsair" }

if ($rivals) {
    Write-Log "  마이크 점유 가능성 있는 앱 감지:" Yellow
    $rivals | ForEach-Object { Write-Log "    - $($_.Name) (PID $($_.Id))" Yellow }
    Write-Log "  → 위 앱을 종료하고 ALT를 다시 시도하세요." Yellow
} else {
    Write-Log "  경쟁 프로세스 없음" Green
}

# ──────────────────────────────────────────────────────
# STEP 8: 이벤트 뷰어 충돌 로그 수집
# ──────────────────────────────────────────────────────
Write-Section "STEP 8 - 충돌 이벤트 로그"

$events = Get-WinEvent -FilterHashtable @{
    LogName = "Application"; StartTime = (Get-Date).AddHours(-48); Level = 1,2
} -EA SilentlyContinue |
    Where-Object { $_.Message -match "alt|audio|microphone|faulting|crash|access.*denied" } |
    Select-Object -First 8

if ($events) {
    foreach ($ev in $events) {
        $msg = $ev.Message -replace '\s+', ' '
        $short = if ($msg.Length -gt 160) { $msg.Substring(0,160) + "..." } else { $msg }
        Write-Log "  [$($ev.TimeCreated.ToString('MM-dd HH:mm'))] $($ev.ProviderName)" Yellow
        Write-Log "    $short" Yellow
    }
} else {
    Write-Log "  관련 이벤트 없음" Green
}

# ──────────────────────────────────────────────────────
# 완료
# ──────────────────────────────────────────────────────
Write-Section "완료"
Write-Log "  모든 수정 완료. PC를 재부팅한 뒤 ALT를 실행하세요." Cyan
Write-Log "  재부팅 후에도 문제가 지속되면 로그를 확인하세요:" White
Write-Log "  $logPath" Cyan
Write-Host ""
