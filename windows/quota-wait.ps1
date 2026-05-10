<#
.SYNOPSIS
    quota-wait - 等到 Claude 额度可用再退出，或后台守护触发续命

.DESCRIPTION
    用法：
      quota-wait.ps1                    # 额度满则阻塞等到重置
      quota-wait.ps1 -Status            # 只打印当前状态
      quota-wait.ps1 -Watch             # 后台守护：满了等重置后触发 claude-resume.ps1
      quota-wait.ps1 -Threshold 90      # 超过 90% 就等（默认 100）

    退出码：0=可用  1=失败
#>
param(
    [switch]$Status,
    [switch]$Watch,
    [float]$Threshold = 100
)

$ErrorActionPreference = "Stop"
$LockFile    = "$env:TEMP\quota-watch.lock"
$ResumeScript = "$env:USERPROFILE\bin\claude-resume.ps1"
$WatchLog    = "$env:USERPROFILE\quota-watch.log"

function Get-Token {
    $creds = Get-Content "$env:USERPROFILE\.claude\.credentials.json" | ConvertFrom-Json
    return $creds.claudeAiOauth.accessToken
}

function Get-Usage($token) {
    return Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" `
        -Headers @{ "Authorization" = "Bearer $token" } -TimeoutSec 10
}

function Parse-Windows($data) {
    $out = @()
    foreach ($key in @("five_hour", "seven_day")) {
        $w = $data.$key
        if ($null -eq $w -or $null -eq $w.resets_at) { continue }
        $uRaw = $w.utilization
        $u = if ($null -ne $uRaw) { [float]$uRaw } else { 0.0 }
        $dt = [DateTimeOffset]::Parse($w.resets_at).LocalDateTime
        $out += [PSCustomObject]@{ Name = $key; Util = $u; ResetDt = $dt }
    }
    return $out
}

function Format-Dt($dt) {
    $now = Get-Date
    $mins = [int]($dt - $now).TotalMinutes
    $t = $dt.ToString("HH:mm")
    if ($mins -le 0)  { return "${t}(passed)" }
    if ($mins -lt 60) { return "${t}(${mins}m)" }
    $h = [int]($mins / 60); $m = $mins % 60
    return "${t}(${h}h$($m.ToString('D2'))m)"
}

function Show-Bar($u) {
    $f = [math]::Min([int]($u / 100 * 20), 20)
    ("#" * $f) + ("-" * (20 - $f))
}

function Show-Status($windows) {
    $now = (Get-Date).ToString("HH:mm:ss")
    $maxU = if ($windows) { ($windows | Measure-Object -Property Util -Maximum).Maximum } else { 0 }
    $icon = if ($maxU -ge 100) { "[FULL]" } elseif ($maxU -ge 75) { "[WARN]" } else { "[OK]" }
    Write-Host "=== Claude Quota $icon  [$now] ==="
    foreach ($w in $windows) {
        $label = if ($w.Name -like "*five*") { "5h" } else { "7d" }
        Write-Host "$label  [$(Show-Bar $w.Util)] $([math]::Round($w.Util))%  reset $(Format-Dt $w.ResetDt)"
    }
}

function Write-Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $WatchLog -Value $line -Encoding UTF8
}

function Start-WatchMode($token) {
    # 防多实例
    if (Test-Path $LockFile) {
        $oldPid = Get-Content $LockFile -ErrorAction SilentlyContinue
        $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "quota-watch already running (PID $oldPid), exiting."
            exit 0
        }
    }
    $PID | Out-File -FilePath $LockFile -Encoding ASCII

    # /api/oauth/usage 是纯状态查询，不走 Messages API，不消耗 Claude 额度
    $Poll = 300  # 5min 查一次
    Write-Log "quota-watch started (PID=$PID, threshold=$Threshold%, poll=${Poll}s)"

    try {
        $fired = $false
        while (-not $fired) {
            try {
                $data    = Get-Usage $token
                $windows = Parse-Windows $data
            } catch {
                Write-Log "API failed: $_ - retry in 60s"
                Start-Sleep -Seconds 60
                continue
            }

            $maxU = if ($windows) { ($windows | Measure-Object -Property Util -Maximum).Maximum } else { 0 }
            $summary = ($windows | ForEach-Object { "$( if($_.Name -like '*five*'){'5h'}else{'7d'} )=$([math]::Round($_.Util))%" }) -join "  "
            Write-Log "Quota: $summary"

            $blocked = $windows | Where-Object { $_.Util -ge $Threshold }
            if (-not $blocked) {
                Start-Sleep -Seconds $Poll
                continue
            }

            $earliest  = ($blocked | Sort-Object ResetDt | Select-Object -First 1).ResetDt
            $waitUntil = $earliest.AddMinutes(1)
            $waitSecs  = [int]($waitUntil - (Get-Date)).TotalSeconds

            if ($waitSecs -gt 0) {
                Write-Log "Quota $([math]::Round($maxU))%, waiting until $($waitUntil.ToString('HH:mm:ss')) ($([int]($waitSecs/60))m)"
                while ($true) {
                    $remaining = [int]($waitUntil - (Get-Date)).TotalSeconds
                    if ($remaining -le 0) { break }
                    Start-Sleep -Seconds ([math]::Min($Poll, $remaining))
                    $remaining = [int]($waitUntil - (Get-Date)).TotalSeconds
                    if ($remaining -gt 0) {
                        Write-Log "Waiting... $([int]($remaining/60))m$($($remaining%60).ToString('D2'))s left"
                    }
                }
            }

            Write-Log "Reset time reached, firing claude-resume.ps1"
            try {
                Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$ResumeScript`"" -WindowStyle Hidden
                Write-Log "claude-resume.ps1 launched, quota-watch exiting."
            } catch {
                Write-Log "Failed to launch claude-resume.ps1: $_"
            }
            $fired = $true
        }
    } finally {
        Remove-Item $LockFile -ErrorAction SilentlyContinue
    }
}

# Main
try {
    $token = Get-Token
} catch {
    Write-Error "Failed to get token: $_"
    exit 1
}

if ($Watch) {
    Start-WatchMode $token
    exit 0
}

while ($true) {
    try {
        $data    = Get-Usage $token
        $windows = Parse-Windows $data
    } catch {
        Write-Error "API failed: $_"
        exit 1
    }

    Show-Status $windows
    if ($Status) { exit 0 }

    $blocked = $windows | Where-Object { $_.Util -ge $Threshold }
    if (-not $blocked) {
        Write-Host "OK quota available, proceeding."
        exit 0
    }

    $earliest  = ($blocked | Sort-Object ResetDt | Select-Object -First 1).ResetDt
    $waitUntil = $earliest.AddMinutes(1)
    $waitSecs  = [int]($waitUntil - (Get-Date)).TotalSeconds

    if ($waitSecs -le 0) {
        Write-Host "OK reset time passed, proceeding."
        exit 0
    }

    $maxU = ($blocked | Measure-Object -Property Util -Maximum).Maximum
    Write-Host "WAIT $([math]::Round($maxU))%, until $($waitUntil.ToString('HH:mm:ss')) ($([int]($waitSecs/60))m$($($waitSecs%60).ToString('D2'))s)"
    Start-Sleep -Seconds ([math]::Min(60, $waitSecs))
    Write-Host ""
}
