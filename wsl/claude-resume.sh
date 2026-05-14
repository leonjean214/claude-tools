#!/bin/bash
# Auto-resume OpenClaw setup for WSL, self-rescheduling chain
# 每次触发 = 读上次留言 → 干活 → 写本次留言 → 排下次到 START+5h
set -u

LOG="$HOME/claude-resume.log"
SCHEDULE="$HOME/bin/schedule-next-resume"

START_TS=$(date +%s)
START_HUMAN=$(date '+%Y-%m-%d %H:%M:%S %Z')

exec >>"$LOG" 2>&1

echo
echo "============================================================"
echo "[$START_HUMAN] === Resume session START (id=$START_TS) ==="

export PATH="$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"
cd "$HOME"

# ── Token resolution (Linux creds → Windows creds fallback) ────────────────────

_get_token() {
    local creds_linux="$HOME/.claude/.credentials.json"
    local win_user
    win_user=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r\n')
    local creds_win="/mnt/c/Users/${win_user}/.claude/.credentials.json"

    local creds_file=""
    if [ -f "$creds_linux" ]; then
        creds_file="$creds_linux"
    elif [ -n "$win_user" ] && [ -f "$creds_win" ]; then
        creds_file="$creds_win"
    fi

    [ -z "$creds_file" ] && return 1
    python3 -c "import json,sys; print(json.load(sys.stdin)['claudeAiOauth']['accessToken'])" \
        < "$creds_file" 2>/dev/null
}

# ── 额度检查：100% 时等到重置点 +1min 再跑 ────────────────────────────────────

_QUOTA_TOKEN=$(_get_token 2>/dev/null || true)
if [ -n "$_QUOTA_TOKEN" ]; then
    _QUOTA_JSON=$(curl -s "https://api.anthropic.com/api/oauth/usage" \
        -H "Authorization: Bearer $_QUOTA_TOKEN" 2>/dev/null)
    _RESULT=$(echo "$_QUOTA_JSON" | python3 -c "
import json, sys, datetime
d = json.load(sys.stdin)
fh = d.get('five_hour') or {}
sd = d.get('seven_day') or {}
u5 = fh.get('utilization') or 0
r5 = fh.get('resets_at') or ''
u7 = sd.get('utilization') or 0
r7 = sd.get('resets_at') or ''
print(f'5h={u5:.0f}% 7d={u7:.0f}%')
if u5 >= 100 and r5:
    dt = datetime.datetime.fromisoformat(r5).astimezone()
    print(f'WAIT:{int(dt.timestamp())+60}:5h@{dt.strftime(\"%H:%M\")}')
elif u7 >= 100 and r7:
    dt = datetime.datetime.fromisoformat(r7).astimezone()
    print(f'WAIT:{int(dt.timestamp())+60}:7d@{dt.strftime(\"%H:%M\")}')
else:
    print('OK')
" 2>/dev/null || true)
    echo "[$(date '+%H:%M:%S')] Quota: $(echo "$_RESULT" | head -1)"
    _WAIT_LINE=$(echo "$_RESULT" | grep "^WAIT:" || true)
    if [ -n "$_WAIT_LINE" ]; then
        _WAIT_TS=$(echo "$_WAIT_LINE" | cut -d: -f2)
        _WAIT_DESC=$(echo "$_WAIT_LINE" | cut -d: -f3-)
        _WAIT_HUMAN=$(date -d "@$_WAIT_TS" '+%Y-%m-%d %H:%M:%S %Z' 2>/dev/null)
        echo "[$(date '+%H:%M:%S')] 额度 100%（$_WAIT_DESC），等到 $_WAIT_HUMAN 再跑"
        "$SCHEDULE" "$_WAIT_TS"
        echo "=== Session SKIPPED (quota full) - rescheduled $_WAIT_HUMAN ==="
        exit 0
    fi
fi
# ── 额度检查结束 ────────────────────────────────────────────────────────────────

# 续接上次被中断的会话（Stop hook 保存了工作目录）
RESUME_DIR=$(cat ~/.claude-resume-dir 2>/dev/null | tr -d '\n' || true)
if [ -z "$RESUME_DIR" ] || [ ! -d "$RESUME_DIR" ]; then
    RESUME_DIR="$HOME"
fi
echo "[$(date '+%H:%M:%S')] 续接目录: $RESUME_DIR"
cd "$RESUME_DIR"

# Prefer explicit path, fall back to PATH lookup
CLAUDE_BIN="claude"
if [ -x "$HOME/.local/bin/claude" ]; then
    CLAUDE_BIN="$HOME/.local/bin/claude"
fi

"$CLAUDE_BIN" -c -p "额度已重置，继续。" \
    --max-turns 200 --permission-mode acceptEdits

END_TS=$(date +%s)
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] === Session end (duration $((END_TS - START_TS))s) ==="

# 排下次：查实际重置时间，取 now+5h 与重置点+1min 的最小值
"$SCHEDULE"
