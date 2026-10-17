#Requires -RunAsAdministrator

<#
.SYNOPSIS
    Windows 마이크 개인정보 보호 레지스트리 값을 Allow로 설정합니다.

.DESCRIPTION
    다음 3가지 레지스트리 키의 Value를 "Allow"로 설정합니다.
    - HKLM\...\ConsentStore\microphone
    - HKCU\...\ConsentStore\microphone
    - HKCU\...\ConsentStore\microphone\NonPackaged
    키가 없으면 자동으로 생성하며, 변경 전후 값을 출력합니다.
#>

$consentBase = "SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

$entries = @(
    [PSCustomObject]@{
        Label    = "HKLM - microphone"
        FullPath = "HKLM:\$consentBase"
    },
    [PSCustomObject]@{
        Label    = "HKCU - microphone"
        FullPath = "HKCU:\$consentBase"
    },
    [PSCustomObject]@{
        Label    = "HKCU - microphone\NonPackaged"
        FullPath = "HKCU:\$consentBase\NonPackaged"
    }
)

$results = @()

Write-Host ""
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  마이크 레지스트리 개인정보 보호 설정 스크립트" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
Write-Host ""

foreach ($entry in $entries) {
    Write-Host "[ $($entry.Label) ]" -ForegroundColor Yellow
    Write-Host "  경로: $($entry.FullPath)"

    # 키 존재 여부 확인 및 생성
    if (-not (Test-Path $entry.FullPath)) {
        Write-Host "  상태: 키가 없음 → 새로 생성합니다." -ForegroundColor DarkYellow
        New-Item -Path $entry.FullPath -Force | Out-Null
    } else {
        Write-Host "  상태: 키 존재 확인됨." -ForegroundColor Green
    }

    # 변경 전 값 읽기
    $beforeValue = $null
    try {
        $beforeValue = (Get-ItemProperty -Path $entry.FullPath -Name "Value" -ErrorAction Stop).Value
    } catch {
        $beforeValue = "(없음)"
    }
    Write-Host "  변경 전 Value: $beforeValue" -ForegroundColor Gray

    # 값을 Allow로 설정
    Set-ItemProperty -Path $entry.FullPath -Name "Value" -Value "Allow" -Type String

    # 변경 후 값 읽기
    $afterValue = (Get-ItemProperty -Path $entry.FullPath -Name "Value").Value
    Write-Host "  변경 후 Value: $afterValue" -ForegroundColor Green
    Write-Host ""

    $results += [PSCustomObject]@{
        "레지스트리 경로" = $entry.FullPath
        "변경 전"        = $beforeValue
        "변경 후"        = $afterValue
        "결과"           = if ($afterValue -eq "Allow") { "성공" } else { "실패" }
    }
}

Write-Host "====================================================" -ForegroundColor Cyan
Write-Host "  결과 요약" -ForegroundColor Cyan
Write-Host "====================================================" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$successCount = ($results | Where-Object { $_.결과 -eq "성공" }).Count
Write-Host "총 $($results.Count)개 항목 중 $successCount개 성공적으로 'Allow' 설정 완료." -ForegroundColor Cyan
Write-Host ""
