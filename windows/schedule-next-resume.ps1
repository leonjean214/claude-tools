<#
.SYNOPSIS
    schedule-next-resume - 把 Task Scheduler 的 ClaudeResume 任务设为最优时间触发

.DESCRIPTION
    用法：
      schedule-next-resume.ps1              # 自动选最优时间（now+5h 与最近重置点+1min 取较早）
      schedule-next-resume.ps1 -At 1234567  # 指定 Unix timestamp

    依赖：$env:USERPROFILE\bin\claude-resume.ps1
#>
param(
    [long]$At = 0
)

$ErrorActionPreference = "Stop"
$ResumeScript = "$env:USERPROFILE\bin\claude-resume.ps1"
$TaskName     = "ClaudeResume"
$Log          = "$env:USERPROFILE\claude-resume.log"

function Get-Token {
    $creds = Get-Content "$env:USERPROFILE\.claude\.credentials.json" -Raw | ConvertFrom-Json
    return $creds.claudeAiOauth.accessToken
}

function Get-EarliestReset($token) {
    try {
        $data = Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" `
            -Headers @{ "Authorization" = "Bearer $token" } -TimeoutSec 10
        $candidates = @()
        foreach ($key in @("five_hour", "seven_day")) {
            $w = $data.$key
            if ($null -eq $w -or -not $w.resets_at) { continue }
            $dt = [DateTimeOffset]::Parse($w.resets_at)
            $candidates += $dt.ToUnixTimeSeconds()
        }
        if ($candidates.Count -gt 0) { return ($candidates | Measure-Object -Minimum).Minimum }
    } catch {
        # API failure is non-fatal — caller falls back to now+5h
    }
    return $null
}

# ── Determine target Unix timestamp ────────────────────────────────────────────

if ($At -gt 0) {
    $TargetTs = $At
} else {
    $NowTs      = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
    $DefaultTs  = $NowTs + 5 * 3600

    $token = $null
    try { $token = Get-Token } catch {}

    # Retry once if initial token read fails (credentials file may be mid-write)
    if (-not $token) {
        Start-Sleep -Seconds 2
        try { $token = Get-Token } catch {}
    }

    $TargetTs = $DefaultTs
    if ($token) {
        $ResetTs = Get-EarliestReset $token
        if ($null -ne $ResetTs -and ($ResetTs + 60) -lt $DefaultTs) {
            $TargetTs = $ResetTs + 60
        }
    }
}

# ── Convert Unix timestamp to local DateTime ────────────────────────────────────

$TargetDt = [DateTimeOffset]::FromUnixTimeSeconds($TargetTs).LocalDateTime

# ── Register (or overwrite) Task Scheduler task ────────────────────────────────

$Action   = New-ScheduledTaskAction `
                -Execute "powershell.exe" `
                -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ResumeScript`""

$Trigger  = New-ScheduledTaskTrigger -Once -At $TargetDt

$Settings = New-ScheduledTaskSettingsSet `
                -StartWhenAvailable `
                -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
                -MultipleInstances IgnoreNew

# Unregister silently if already exists so we can re-register with new trigger
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $Action   `
    -Trigger  $Trigger  `
    -Settings $Settings `
    -RunLevel Highest   `
    -Force | Out-Null

# ── Print confirmation ──────────────────────────────────────────────────────────

$NowTs2    = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$MinsAway  = [int](($TargetTs - $NowTs2) / 60)
$HumanTime = $TargetDt.ToString("yyyy-MM-dd HH:mm:ss")

Write-Host "🔁 auto-resume scheduled: $HumanTime (${MinsAway}m後)"
Add-Content -Path $Log -Value "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Scheduled next resume at $HumanTime (${MinsAway}m後)" -Encoding UTF8
