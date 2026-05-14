<#
.SYNOPSIS
    claude-resume - 自动续接被中断的 Claude 会话（Task Scheduler 触发）

.DESCRIPTION
    流程：
      1. 写日志头
      2. 查额度——100% 时调 schedule-next-resume.ps1 排到重置后再退
      3. 读 $env:USERPROFILE\.claude-resume-dir 获取工作目录
      4. 运行 claude -c -p "额度已重置，继续。" --max-turns 200 --permission-mode acceptEdits
      5. 调 schedule-next-resume.ps1（无参数，自动选最优时间）
#>

$ErrorActionPreference = "SilentlyContinue"   # 单步失败不中止整个脚本

$Log      = "$env:USERPROFILE\claude-resume.log"
$Schedule = "$env:USERPROFILE\bin\schedule-next-resume.ps1"

function Write-Log($msg) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $msg"
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Invoke-Schedule {
    param([long]$At = 0)
    $args_ = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Schedule)
    if ($At -gt 0) { $args_ += @("-At", "$At") }
    & powershell.exe @args_
}

# ── Banner ──────────────────────────────────────────────────────────────────────

$StartTs    = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$StartHuman = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")

Add-Content -Path $Log -Value "" -Encoding UTF8
Write-Log "============================================================"
Write-Log "=== Resume session START (id=$StartTs) ==="

# ── Quota check ─────────────────────────────────────────────────────────────────

function Get-Token {
    $creds = Get-Content "$env:USERPROFILE\.claude\.credentials.json" -Raw | ConvertFrom-Json
    return $creds.claudeAiOauth.accessToken
}

$token = $null
try { $token = Get-Token } catch { Write-Log "Could not read credentials, skipping quota check." }

# Retry once — credentials file may be mid-write after Claude Code refreshes token
if (-not $token) {
    Start-Sleep -Seconds 2
    try { $token = Get-Token } catch {}
}

if ($token) {
    $data = $null
    try {
        $data = Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" `
            -Headers @{ "Authorization" = "Bearer $token" } -TimeoutSec 10
    } catch {
        # Re-read token once in case Claude Code rotated credentials mid-flight
        try {
            $token = Get-Token
            $data  = Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" `
                -Headers @{ "Authorization" = "Bearer $token" } -TimeoutSec 10
        } catch {
            Write-Log "Quota API failed ($_ ), proceeding without quota check."
        }
    }

    if ($data) {
        $windows = @()
        foreach ($key in @("five_hour", "seven_day")) {
            $w = $data.$key
            if ($null -eq $w -or -not $w.resets_at) { continue }
            $uRaw = $w.utilization
            $u    = if ($null -ne $uRaw) { [float]$uRaw } else { 0.0 }
            $dt   = [DateTimeOffset]::Parse($w.resets_at).LocalDateTime
            $label = if ($key -like "*five*") { "5h" } else { "7d" }
            $windows += [PSCustomObject]@{ Label = $label; Util = $u; ResetDt = $dt }
        }

        $summary = ($windows | ForEach-Object { "$($_.Label)=$([math]::Round($_.Util))%" }) -join "  "
        Write-Log "Quota: $summary"

        # Check if any window is at 100 %
        $full = $windows | Where-Object { $_.Util -ge 100 }
        if ($full) {
            $earliest  = ($full | Sort-Object ResetDt | Select-Object -First 1).ResetDt
            $waitTs    = [DateTimeOffset]::new($earliest).ToUnixTimeSeconds() + 60
            $waitHuman = $earliest.AddSeconds(60).ToString("yyyy-MM-dd HH:mm:ss")
            Write-Log "额度 100%，等到 $waitHuman 再跑"
            Invoke-Schedule -At $waitTs
            Write-Log "=== Session SKIPPED (quota full) - rescheduled $waitHuman ==="
            exit 0
        }
    }
}

# ── Determine working directory ─────────────────────────────────────────────────

$ResumeDir = $null
$DirFile   = "$env:USERPROFILE\.claude-resume-dir"
if (Test-Path $DirFile) {
    $ResumeDir = (Get-Content $DirFile -Raw).Trim()
}
if (-not $ResumeDir -or -not (Test-Path $ResumeDir -PathType Container)) {
    $ResumeDir = $env:USERPROFILE
}
Write-Log "续接目录: $ResumeDir"
Set-Location $ResumeDir

# ── Run Claude ──────────────────────────────────────────────────────────────────

$claude = "claude"   # expected on PATH after `npm i -g @anthropic-ai/claude-code`

Write-Log "Launching: $claude -c -p '额度已重置，继续。' --max-turns 200 --permission-mode acceptEdits"
& $claude -c -p "额度已重置，继续。" --max-turns 200 --permission-mode acceptEdits

$EndTs    = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
$Duration = $EndTs - $StartTs
Write-Log "=== Session end (duration ${Duration}s) ==="

# ── Schedule next run ───────────────────────────────────────────────────────────

Invoke-Schedule
