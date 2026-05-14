# Win 端：调度下次 ClaudeResume 任务
# 无参数时查 API 拿实际重置时间，取 reset+1min（与 Mac 逻辑一致）
# 用法：
#   schedule-next-resume.ps1                            # 查 API，取最近重置点+1min
#   schedule-next-resume.ps1 -At "2026-05-01 09:00:00" # 显式指定
param([string]$At = "")

$ErrorActionPreference = "Continue"

$taskName  = "ClaudeResume"
$scriptPath = "C:\Users\game5090\bin\claude-resume.ps1"

if (-not [string]::IsNullOrWhiteSpace($At)) {
    $next = [DateTime]::ParseExact($At.Trim(), 'yyyy-MM-dd HH:mm:ss', [System.Globalization.CultureInfo]::InvariantCulture)
} else {
    $fallback = (Get-Date).AddHours(5)
    $next = $fallback

    try {
        $creds  = Get-Content "$env:USERPROFILE\.claude\.credentials.json" -Raw | ConvertFrom-Json
        $token  = $creds.claudeAiOauth.accessToken
        $qResp  = Invoke-RestMethod -Uri "https://api.anthropic.com/api/oauth/usage" `
                      -Headers @{ "Authorization" = "Bearer $token" } -ErrorAction Stop

        $candidates = @()
        foreach ($window in @($qResp.five_hour, $qResp.seven_day)) {
            if ($window -and $window.resets_at) {
                $candidates += [DateTimeOffset]::Parse($window.resets_at).LocalDateTime
            }
        }
        if ($candidates.Count -gt 0) {
            $earliest = ($candidates | Sort-Object)[0].AddMinutes(1)
            if ($earliest -lt $fallback) {
                $next = $earliest
            }
        }
    } catch {
        # fallback 到 now+5h
    }
}

schtasks /delete /tn $taskName /f 2>$null | Out-Null

$dateStr = $next.ToString("yyyy/MM/dd")
$timeStr = $next.ToString("HH:mm")
$tr = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$result = schtasks /create /tn $taskName /tr $tr /sc once /sd $dateStr /st $timeStr /f 2>&1
$mins = [math]::Round(($next - (Get-Date)).TotalMinutes)
Write-Output "next ClaudeResume fire: $($next.ToString('yyyy-MM-dd HH:mm:ss')) (${mins}m后)"
Write-Output ("schtasks: " + ($result -join ' | '))
