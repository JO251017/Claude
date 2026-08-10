$logPath = "$env:TEMP\Fix-ALTMicrophone.log"

if (Test-Path $logPath) {
    Write-Host "=== Fix-ALTMicrophone 실행 결과 ===" -ForegroundColor Cyan
    Get-Content $logPath -Encoding UTF8
} else {
    Write-Host "로그 파일이 없습니다. Fix-ALTMicrophone.ps1 을 먼저 실행하세요." -ForegroundColor Red
}

Write-Host ""
Write-Host "=== ALT 앱 추가 진단 ===" -ForegroundColor Cyan

# KB 설치 현황
Write-Host "[KB 확인]" -ForegroundColor Yellow
@("KB5066835","KB5068861") | ForEach-Object {
    $h = Get-HotFix -Id $_ -ErrorAction SilentlyContinue
    if ($h) { Write-Host "  설치됨: $_ ($($h.InstalledOn))" -ForegroundColor Red }
    else     { Write-Host "  없음: $_" -ForegroundColor Green }
}

# camsvc 상태
Write-Host "[camsvc 상태]" -ForegroundColor Yellow
$s = Get-Service camsvc -ErrorAction SilentlyContinue
if ($s) { Write-Host "  $($s.Name): $($s.Status) / $($s.StartType)" }
else    { Write-Host "  camsvc 없음" }

# ALT 프로세스
Write-Host "[ALT 프로세스]" -ForegroundColor Yellow
$alt = Get-Process | Where-Object { $_.Name -match "alt" } -ErrorAction SilentlyContinue
if ($alt) { $alt | ForEach-Object { Write-Host "  실행 중: $($_.Name) (PID $($_.Id))" } }
else      { Write-Host "  ALT 실행 안 됨" }

# 최근 이벤트 로그 (ALT 관련)
Write-Host "[최근 충돌 로그]" -ForegroundColor Yellow
$evts = Get-WinEvent -FilterHashtable @{ LogName="Application"; StartTime=(Get-Date).AddHours(-1); Level=1,2 } -EA SilentlyContinue |
        Select-Object -First 5
if ($evts) {
    $evts | ForEach-Object {
        $msg = ($_.Message -replace '\s+',' ').Substring(0, [Math]::Min(200, $_.Message.Length))
        Write-Host "  [$($_.TimeCreated.ToString('HH:mm:ss'))] $($_.ProviderName): $msg" -ForegroundColor Yellow
    }
} else { Write-Host "  최근 1시간 오류 없음" -ForegroundColor Green }

Read-Host "`n결과를 캡처하거나 복사한 후 엔터를 누르세요"
