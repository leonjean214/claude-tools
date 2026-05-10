$creds = Get-Content "$env:USERPROFILE\.claude\.credentials.json" | ConvertFrom-Json
$token = $creds.claudeAiOauth.accessToken

$body = '{"model":"claude-haiku-4-5-20251001","max_tokens":1,"messages":[{"role":"user","content":"1"}]}'
try {
    $resp = Invoke-WebRequest -Uri "https://api.anthropic.com/v1/messages" `
        -Method POST `
        -Headers @{
            "Authorization"     = "Bearer $token"
            "anthropic-version" = "2023-06-01"
            "Content-Type"      = "application/json"
        } `
        -Body $body -UseBasicParsing -ErrorAction Stop
} catch {
    Write-Output "API call failed: $_"
    exit 1
}

$h = $resp.Headers

function GH($name) {
    $v = $h[$name]
    if ($v -is [System.Collections.IEnumerable] -and $v -isnot [string]) { $v[0] } else { "$v" }
}

function FmtTs($ts) {
    if (-not $ts -or $ts -eq "0") { return "?" }
    try {
        $dt = [DateTimeOffset]::FromUnixTimeSeconds([long]$ts).LocalDateTime
        $mins = [int]($dt - (Get-Date)).TotalMinutes
        $t = $dt.ToString("HH:mm")
        if ($mins -lt 0)  { return "${t}(passed)" }
        if ($mins -lt 60) { return "${t}(${mins}m)" }
        $h2 = [int]($mins/60); $m2 = $mins % 60
        return "${t}(${h2}h$($m2.ToString('D2'))m)"
    } catch { return $ts }
}

function Bar($u) {
    try {
        $f = [int]([float]$u * 20)
        ("#" * $f) + ("-" * (20 - $f))
    } catch { "?" * 20 }
}

$status  = GH "anthropic-ratelimit-unified-status"
$util5h  = GH "anthropic-ratelimit-unified-5h-utilization"
$reset5h = GH "anthropic-ratelimit-unified-5h-reset"
$st5h    = GH "anthropic-ratelimit-unified-5h-status"
$util7d  = GH "anthropic-ratelimit-unified-7d-utilization"
$reset7d = GH "anthropic-ratelimit-unified-7d-reset"
$st7d    = GH "anthropic-ratelimit-unified-7d-status"

$emoji = if ($status -eq "allowed") { "[OK]" } elseif ($status -like "*warning*") { "[WARN]" } else { "[FULL]" }
$now   = (Get-Date).ToString("HH:mm:ss")

Write-Output "=== Claude Quota $emoji $status  [$now] ==="
Write-Output "5h  [$(Bar $util5h)] $([math]::Round([float]$util5h*100))%  reset $(FmtTs $reset5h)  $st5h"
Write-Output "7d  [$(Bar $util7d)] $([math]::Round([float]$util7d*100))%  reset $(FmtTs $reset7d)  $st7d"
