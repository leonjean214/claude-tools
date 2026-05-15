param(
    [string]$MessagesFile = "",
    [string]$Model        = "",
    [int]$Timeout         = 300
)

[Console]::InputEncoding  = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding           = [System.Text.Encoding]::UTF8

$OLLAMA = "http://127.0.0.1:11434"

if (-not $MessagesFile -or -not (Test-Path $MessagesFile)) {
    [Console]::Error.WriteLine("MessagesFile not found: $MessagesFile")
    exit 1
}

$messagesJson = (Get-Content $MessagesFile -Raw -Encoding UTF8).Trim()
$parsed = @($messagesJson | ConvertFrom-Json)
$lastUserMsg = ($parsed | Where-Object { $_.role -eq "user" } | Select-Object -Last 1).content

if (-not $lastUserMsg) {
    [Console]::Error.WriteLine("No user message in messages")
    exit 1
}

# ── 分类 ────────────────────────────────────────────────────────────
$knownCategories = @("code","reason","smart","llama","phi","gemma3","qwen3","fast","claude","default")

$category = "default"
if (-not $Model) {
    $classPrompt = "Reply with exactly one word only. Categories: code (writing/debugging/reviewing code, scripts, SQL, regex), reason (math, logic, step-by-step analysis, proofs, deep thinking), smart (system/architecture design, research, long-form writing, multi-topic), claude (needs file access/web browsing/shell commands/real-time info), default (facts, translation, casual chat, quick Q&A). Query: " + $lastUserMsg
    $classBody = @{ model = "gemma4"; prompt = $classPrompt; stream = $false } | ConvertTo-Json -Depth 3
    try {
        $cr = Invoke-RestMethod -Uri "$OLLAMA/api/generate" -Method Post `
                  -Body $classBody -ContentType "application/json; charset=utf-8" -TimeoutSec 15
        $word = ($cr.response.Trim().ToLower() -split '\s+')[0]
        if ($word -in $knownCategories) { $category = $word }
    } catch { }
} elseif ($Model -match ":") {
    # 直接传入完整模型名（如 llama3.3:70b），跳过分类
    $category = "__direct__"
} else {
    $category = $Model.ToLower()
}

if ($category -eq "claude") { exit 42 }


# ── 路由 ────────────────────────────────────────────────────────────
$ollamaModel = switch ($category) {
    "code"       { "qwen2.5-coder:32b" }
    "reason"     { "qwq:32b" }
    "smart"      { "llama4:scout" }
    "llama"      { "llama3.3:70b" }
    "phi"        { "phi4:14b" }
    "gemma3"     { "gemma3:27b" }
    "qwen3"      { "qwen3:30b-a3b" }
    "fast"       { "qwen2.5:3b" }
    "gemma4"     { "gemma4" }
    "__direct__" { $Model }
    default      { "gemma4" }
}

[Console]::Out.WriteLine("[used_model] $ollamaModel")
[Console]::Out.Flush()

# ── 调用 Ollama（直接用原始 JSON 拼接 body，绕开 PS5 数组序列化 bug）──────
$body = "{`"model`":`"$ollamaModel`",`"messages`":$messagesJson,`"stream`":false}"
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($body)

try {
    $resp = Invoke-RestMethod -Uri "$OLLAMA/api/chat" -Method Post `
                -Body $bodyBytes -ContentType "application/json; charset=utf-8" `
                -TimeoutSec $Timeout
    [Console]::Out.WriteLine($resp.message.content)
    [Console]::Out.Flush()
    exit 0
} catch {
    [Console]::Error.WriteLine("[oc-chat] Ollama failed: $_")
    exit 1
}
