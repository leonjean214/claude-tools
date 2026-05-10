<#
.SYNOPSIS
    quota-wait - 等到 Claude 额度可用再退出

.DESCRIPTION
    用法：
      quota-wait.ps1                    # 额度满则等到重置，否则立即退出
      quota-wait.ps1 -Status            # 只打印当前状态，不等待
      quota-wait.ps1 -Threshold 90      # 超过 90% 就等（默认 100）

    退出码：
      0 = 额度可用
      1 = 无法获取 token 或 API 失败
#>
param(
    [switch]$Status,
    [float]$Threshold = 100
)

$ErrorActionPreference = "Stop"

function Get-Token {
    $creds = Get-Content "$env:USERPROFILE\.claude\.credentials.json" | ConvertFrom-Json
    return $creds.claudeAiOauth.accessToken
}

function Get-Usage($token) {
    $resp = Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" `
        -Headers @{ "Authorization" = "Bearer $token" } -TimeoutSec 10
    return $resp
}

function Format-Dt($dt) {
    $now = Get-Date
    $mins = [int]($dt - $now).TotalMinutes
    $t = $dt.ToString("HH:mm")
    if ($mins -le 0)  { return "${t}(已过)" }
    if ($mins -lt 60) { return "${t}(${mins}m后)" }
    $h = [int]($mins / 60); $m = $mins % 60
    return "${t}(${h}h$($m.ToString('D2'))m后)"
}

function Show-Bar($u) {
    $f = [math]::Min([int]($u / 100 * 20), 20)
    ("#" * $f) + ("-" * (20 - $f))
}

function Show-Status($windows) {
    $now = (Get-Date).ToString("HH:mm:ss")
    $maxU = ($windows | Measure-Object -Property Util -Maximum).Maximum
    $icon = if ($maxU -ge 100) { "[FULL]" } elseif ($maxU -ge 75) { "[WARN]" } else { "[OK]" }
    Write-Host "=== Claude Quota $icon  [$now] ==="
    foreach ($w in $windows) {
        $label = if ($w.Name -like "*five*") { "5h" } else { "7d" }
        Write-Host "$label  [$(Show-Bar $w.Util)] $([math]::Round($w.Util))%  reset $(Format-Dt $w.ResetDt)"
    }
}

function Parse-Windows($data) {
    $out = @()
    foreach ($key in @("five_hour", "seven_day")) {
        $w = $data.$key
        if ($null -eq $w) { continue }
        if ($null -eq $w.resets_at) { continue }
        $uRaw = $w.utilization
        $u = if ($null -ne $uRaw) { [float]$uRaw } else { 0.0 }
        $dt = [DateTimeOffset]::Parse($w.resets_at).LocalDateTime
        $out += [PSCustomObject]@{ Name = $key; Util = $u; ResetDt = $dt }
    }
    return $out
}

# Main
try {
    $token = Get-Token
} catch {
    Write-Error "获取 token 失败: $_"
    exit 1
}

while ($true) {
    try {
        $data    = Get-Usage $token
        $windows = Parse-Windows $data
    } catch {
        Write-Error "API 失败: $_"
        exit 1
    }

    Show-Status $windows

    if ($Status) { exit 0 }

    $blocked = $windows | Where-Object { $_.Util -ge $Threshold }

    if (-not $blocked) {
        Write-Host "OK 额度可用，继续。"
        exit 0
    }

    $earliestReset = ($blocked | Sort-Object ResetDt | Select-Object -First 1).ResetDt
    $waitUntil     = $earliestReset.AddMinutes(1)
    $now           = Get-Date
    $waitSecs      = [int]($waitUntil - $now).TotalSeconds

    if ($waitSecs -le 0) {
        Write-Host "OK 重置时间已过，继续。"
        exit 0
    }

    $maxU    = ($blocked | Measure-Object -Property Util -Maximum).Maximum
    $wakeStr = $waitUntil.ToString("HH:mm:ss")
    $mins    = [int]($waitSecs / 60)
    $secs    = $waitSecs % 60
    Write-Host "WAIT 额度 $([math]::Round($maxU))%，等到 $wakeStr 再继续… (还有 ${mins}m$($secs.ToString('D2'))s)"

    $sleep = [math]::Min(60, $waitSecs)
    Start-Sleep -Seconds $sleep
    Write-Host ""
}
