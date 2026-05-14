# Win Task Scheduler 自动恢复 wrapper (WSL claude)
$ErrorActionPreference = "Continue"

$startTime = Get-Date
$logPath = "$env:USERPROFILE\claude-resume.log"

Add-Content -Path $logPath -Value ""
Add-Content -Path $logPath -Value "============================================================"
Add-Content -Path $logPath -Value "[$($startTime.ToString('yyyy-MM-dd HH:mm:ss'))] === Win Claude Resume START (WSL) ==="

# --- 额度检查：100% 时等到重置点 +1min 再跑 ---
$shouldSkip = $false
$waitUntil  = $null
try {
    $creds = Get-Content "$env:USERPROFILE\.claude\.credentials.json" | ConvertFrom-Json
    $qToken = $creds.claudeAiOauth.accessToken

    $qResp = Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" `
        -Headers @{ "Authorization" = "Bearer $qToken" } -ErrorAction Stop

    $u5 = [float]($qResp.five_hour.utilization ?? 0)
    $r5 = $qResp.five_hour.resets_at
    $u7 = [float]($qResp.seven_day.utilization ?? 0)
    $r7 = $qResp.seven_day.resets_at

    Add-Content -Path $logPath -Value "[$((Get-Date).ToString('HH:mm:ss'))] Quota: 5h=$([math]::Round($u5))% 7d=$([math]::Round($u7))%"

    if ($u5 -ge 100 -and $r5) {
        $shouldSkip = $true
        $waitUntil  = [DateTimeOffset]::Parse($r5).LocalDateTime.AddMinutes(1)
    } elseif ($u7 -ge 100 -and $r7) {
        $shouldSkip = $true
        $waitUntil  = [DateTimeOffset]::Parse($r7).LocalDateTime.AddMinutes(1)
    }
} catch {
    Add-Content -Path $logPath -Value "[$((Get-Date).ToString('HH:mm:ss'))] Quota check failed: $_ - proceeding"
}

if ($shouldSkip) {
    $waitStr = $waitUntil.ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $logPath -Value "[$((Get-Date).ToString('HH:mm:ss'))] 额度 100%，等到 $waitStr 再跑"
    & "C:\Users\game5090\bin\schedule-next-resume.ps1" -At $waitStr 2>&1 | Add-Content -Path $logPath
    Add-Content -Path $logPath -Value "=== Session SKIPPED (quota full) - rescheduled $waitStr ==="
    exit 0
}
# --- 额度检查结束 ---

# 用 WSL 里的 claude -c 续接上次 WSL 会话
$claudeOut = & wsl.exe -d Ubuntu-24.04 -- claude -c -p "额度已重置，继续。" --max-turns 200 --dangerously-skip-permissions 2>&1
$claudeOut | Add-Content -Path $logPath

$endTime = Get-Date
$duration = ($endTime - $startTime).TotalSeconds
Add-Content -Path $logPath -Value "[$($endTime.ToString('yyyy-MM-dd HH:mm:ss'))] === Win Claude Resume END (duration ${duration}s) ==="

# 调度下次：查 API 取实际重置时间
$schedOut = & "C:\Users\game5090\bin\schedule-next-resume.ps1" 2>&1
$schedOut | Add-Content -Path $logPath
