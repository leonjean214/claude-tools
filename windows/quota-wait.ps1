param(
    [switch]$Status,
    [switch]$Watch,
    [switch]$Install,
    [switch]$Uninstall
)

$ErrorActionPreference = "Continue"
$LockFile   = "$env:TEMP\quota-watch.lock"
$WatchLog   = "$env:USERPROFILE\quota-watch.log"
$ScriptPath = $MyInvocation.MyCommand.Path
$TaskName   = "ClaudeQuotaWatch"

function Get-Token {
    $creds = Get-Content "$env:USERPROFILE\.claude\.credentials.json" -Raw | ConvertFrom-Json
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
        $u  = if ($null -ne $w.utilization) { [float]$w.utilization } else { 0.0 }
        $dt = [DateTimeOffset]::Parse($w.resets_at).LocalDateTime
        $out += [PSCustomObject]@{ Name = $key; Util = $u; ResetDt = $dt }
    }
    return $out
}

function Format-Dt($dt) {
    $now  = Get-Date
    $mins = [int]($dt - $now).TotalMinutes
    $t    = $dt.ToString("HH:mm")
    if ($mins -le 0)  { return "${t}(passed)" }
    if ($mins -lt 60) { return "${t}(${mins}m)" }
    $h = [int]($mins / 60); $m = $mins % 60
    return "${t}($($h)h$($m.ToString('D2'))m)"
}

function Show-Bar($u) {
    $f = [math]::Min([int]($u / 100 * 20), 20)
    return ("#" * $f) + ("-" * (20 - $f))
}

function Write-WatchLog($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $WatchLog -Value $line -Encoding UTF8
}

function Show-Status($windows) {
    $now  = (Get-Date).ToString("HH:mm:ss")
    $maxU = if ($windows) { ($windows | Measure-Object -Property Util -Maximum).Maximum } else { 0 }
    $icon = if ($maxU -ge 100) { "[FULL]" } elseif ($maxU -ge 75) { "[WARN]" } else { "[OK]" }
    Write-Host "=== Claude Quota $icon  [$now] ==="
    foreach ($w in $windows) {
        $label = if ($w.Name -like "*five*") { "5h" } else { "7d" }
        Write-Host "$label  [$(Show-Bar $w.Util)] $([math]::Round($w.Util))%  reset $(Format-Dt $w.ResetDt)"
    }
}

function Install-Task {
    $tr     = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`" -Watch"
    schtasks /delete /tn $TaskName /f 2>$null | Out-Null
    $result = schtasks /create /tn $TaskName /tr $tr /sc onlogon /f 2>&1
    Write-Host "Installed $TaskName (onlogon): $($result -join ' ')"
}

function Uninstall-Task {
    schtasks /delete /tn $TaskName /f 2>&1 | Write-Host
}

function Start-WatchMode($token) {
    if (Test-Path $LockFile) {
        $oldPid = Get-Content $LockFile -ErrorAction SilentlyContinue
        $proc   = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "$TaskName already running (PID $oldPid), exiting."
            exit 0
        }
    }
    $PID | Out-File -FilePath $LockFile -Encoding ASCII

    # Rotate log if > 2MB
    if ((Test-Path $WatchLog) -and (Get-Item $WatchLog).Length -gt 2MB) {
        $lines = Get-Content $WatchLog -Tail 2000
        $lines | Set-Content $WatchLog -Encoding UTF8
    }

    $Poll = 300
    Write-WatchLog "quota-watch started (PID=$PID, poll=${Poll}s)"

    try {
        while ($true) {
            try {
                $data    = Get-Usage $token
                $windows = Parse-Windows $data
            } catch {
                Write-WatchLog "API failed: $_ - retry in 60s"
                Start-Sleep -Seconds 60
                continue
            }

            $maxU    = if ($windows) { ($windows | Measure-Object -Property Util -Maximum).Maximum } else { 0 }
            $summary = ($windows | ForEach-Object {
                $lbl = if ($_.Name -like "*five*") { "5h" } else { "7d" }
                "$lbl=$([math]::Round($_.Util))% reset=$(Format-Dt $_.ResetDt)"
            }) -join "  |  "
            Write-WatchLog "Quota: $summary"

            try {
                $schedOut = & "C:\Users\game5090\bin\schedule-next-resume.ps1" 2>&1
                Write-WatchLog "  -> $($schedOut -join ' | ')"
            } catch {
                Write-WatchLog "  schedule-next-resume failed: $_"
            }

            Start-Sleep -Seconds $Poll
        }
    } finally {
        Remove-Item $LockFile -ErrorAction SilentlyContinue
        Write-WatchLog "quota-watch stopped (PID=$PID)"
    }
}

# --- Main ---
if ($Install) { Install-Task; exit 0 }
if ($Uninstall) { Uninstall-Task; exit 0 }

try {
    $token = Get-Token
} catch {
    Write-Error "Failed to get token: $_"
    exit 1
}

if ($Watch) { Start-WatchMode $token; exit 0 }

try {
    $data    = Get-Usage $token
    $windows = Parse-Windows $data
} catch {
    Write-Error "API failed: $_"
    exit 1
}
Show-Status $windows
