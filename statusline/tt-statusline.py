#!/usr/bin/env python3
"""Claude Code statusLine — 状态栏显示 + 数据持久化到 tt-status.json"""
__version__ = "1.5"
import json, os, re, subprocess, sys, tempfile
from datetime import datetime, timezone

STATUS_FILE = os.path.expanduser("~/.claude/tt-status.json")
CODEX_STATUS_FILE = os.path.expanduser("~/.codex/quota-status.json")
USAGE_COSTS_FILE = os.path.expanduser("~/.cache/usage-costs.json")
USAGE_REFRESH_LOCK = os.path.join(tempfile.gettempdir(), "usage-costs-refresh.lock")
# usage 脚本默认和本文件放在同一目录；也可用环境变量 TT_USAGE_CMD 指定路径。找不到就不显示费用行。
_USAGE = os.environ.get("TT_USAGE_CMD") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage")
USAGE_REFRESH_CMD = [sys.executable, _USAGE]
USAGE_REFRESH_MAX_AGE = 120
ANSI_RE = re.compile(r'\033\[[0-9;]*m')
C = {
    "green": "\033[32m", "yellow": "\033[33m", "red": "\033[31m",
    "cyan": "\033[36m", "blue": "\033[34m", "magenta": "\033[35m",
    "peach": "\033[38;5;216m", "dim": "\033[2m", "reset": "\033[0m",
}

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def vlen(s):
    return len(ANSI_RE.sub("", s))


def get_width():
    try:
        return max(1, os.get_terminal_size(2).columns - 4)
    except Exception:
        pass
    if os.name != "nt":
        try:
            import fcntl, struct, termios
            with open('/dev/tty', 'r') as tty:
                res = fcntl.ioctl(tty, termios.TIOCGWINSZ, b'\x00' * 8)
                return max(1, struct.unpack('hh', res[:4])[1] - 4)
        except Exception:
            pass
    return 116


def color_by_pct(pct):
    return C["green"] if pct < 50 else C["yellow"] if pct < 80 else C["red"]


def fmt_tokens(n):
    if n >= 1_000_000: return f"{n/1_000_000:.1f}M"
    if n >= 1_000: return f"{n/1_000:.0f}k"
    return str(n)


def progress_bar(value, bar_width=8):
    filled_char, empty_char = "█", "░"
    if value is None:
        return empty_char * bar_width + " n/a"
    pct = max(0.0, min(100.0, float(value)))
    filled = round(pct / 100 * bar_width)
    return f"{color_by_pct(pct)}{filled_char * filled}{C['reset']}{empty_char * (bar_width - filled)} {pct:.0f}%"


def fmt_duration(seconds):
    if seconds >= 86400:
        d, rem = int(seconds // 86400), int(seconds % 86400)
        return f"{d}d{rem // 3600}h"
    if seconds >= 3600:
        h, m = int(seconds // 3600), int((seconds % 3600) // 60)
        return f"{h}h{m}m"
    if seconds >= 60:
        return f"{int(seconds // 60)}min"
    return f"{int(seconds)}s"


def git_branch(cwd):
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=cwd,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        ).strip()
    except Exception:
        return ""
    if not branch:
        return ""
    try:
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=cwd,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
        ).strip()
        if dirty:
            branch += "*"
    except Exception:
        pass
    return branch


def save_data(data, now):
    # Claude Code 偶尔传 rate_limits: null(窗口重置/overage 期间);
    # 保留上一帧非空值并标旧,额度条和 quota-wait 的 resets_at 不至于瞎掉
    if not data.get("rate_limits"):
        data["_rl_null_frame"] = True
        try:
            with open(STATUS_FILE) as f:
                old = json.load(f)
            if old.get("rate_limits"):
                data["rate_limits"] = old["rate_limits"]
                data["_rate_limits_stale_since"] = old.get(
                    "_rate_limits_stale_since"
                ) or old.get("_received_at")
        except (OSError, json.JSONDecodeError):
            pass
    data["_received_at"] = now.isoformat()
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(STATUS_FILE), suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, STATUS_FILE)
    except OSError:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def load_codex_status():
    try:
        with open(CODEX_STATUS_FILE) as f:
            data = json.load(f)
        age = datetime.now().timestamp() - os.path.getmtime(CODEX_STATUS_FILE)
        return data, age
    except (OSError, json.JSONDecodeError):
        return None, None


def load_usage_costs():
    try:
        with open(USAGE_COSTS_FILE) as f:
            data = json.load(f)
        age = datetime.now().timestamp() - os.path.getmtime(USAGE_COSTS_FILE)
        return data, age
    except (OSError, json.JSONDecodeError):
        return None, None


def maybe_refresh_usage_costs(age):
    if age is not None and age <= USAGE_REFRESH_MAX_AGE:
        return
    try:
        lock_age = datetime.now().timestamp() - os.path.getmtime(USAGE_REFRESH_LOCK)
        if lock_age < 30:
            return
    except OSError:
        pass
    try:
        with open(USAGE_REFRESH_LOCK, "w") as f:
            f.write(str(os.getpid()))
        subprocess.Popen(
            USAGE_REFRESH_CMD,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=(os.name != "nt"),
        )
    except Exception:
        pass


def fmt_cost(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "~$?.??"
    if value < 0.005:
        return "~$0.00"
    return f"~${value:.2f}"


# 订阅月费 (USD)：把等价 API 成本换算成"几倍订阅价值"用。改套餐改这里。
CLAUDE_SUB_MONTHLY = 20.0   # Claude Pro
CODEX_SUB_MONTHLY = 20.0    # ChatGPT Plus
HOURS_PER_MONTH = 730.0     # 30.4 天
WINDOW_HOURS = {"five_hour": 5.0, "seven_day": 168.0, "month": HOURS_PER_MONTH}


def api_multiple(cost, key, monthly):
    """该窗口等价 API 成本 ÷ 同窗口按月费摊算的订阅成本 = 几倍订阅价值。"""
    try:
        cost = float(cost)
    except (TypeError, ValueError):
        return None
    sub = monthly * WINDOW_HOURS.get(key, 0) / HOURS_PER_MONTH
    if sub <= 0:
        return None
    return cost / sub


def fmt_mult(value):
    if value is None:
        return "?x"
    if value <= 0:
        return "0x"
    return f"{value:.0f}x" if value >= 10 else f"{value:.1f}x"


def render(data, now):
    W = get_width()
    ctx = data.get("context_window") or {}
    bar_w = 8 if W >= 100 else 6 if W >= 60 else 4

    # --- Line 1: Project | 5h | 7d | CTX ---
    line1 = []

    project = (data.get("workspace") or {}).get("project_dir", "")
    if project:
        name = os.path.basename(project)
        branch = git_branch(project)
        if branch:
            line1.append(f"{C['green']}{name}{C['reset']}({C['magenta']}{branch}{C['reset']})")
        else:
            line1.append(f"{C['green']}{name}{C['reset']}")

    rl = data.get("rate_limits") or {}
    rl_parts = []
    for key, label in [("five_hour", "5h"), ("seven_day", "7d")]:
        entry = rl.get(key) or {}
        pct = entry.get("used_percentage")
        if pct is not None:
            reset_str = ""
            resets_at = entry.get("resets_at")
            if resets_at:
                remain = int(resets_at) - int(now.timestamp())
                if remain > 0:
                    reset_str = f" {C['dim']}({fmt_duration(remain)}){C['reset']}"
            stale_mark = f"{C['dim']}旧{C['reset']}" if data.get("_rate_limits_stale_since") else ""
            rl_parts.append((
                f"{C['blue']}{label}:{C['reset']}{progress_bar(pct, bar_w)}{reset_str}{stale_mark}",
                f"{C['blue']}{label}:{C['reset']}{progress_bar(pct, bar_w)}{stale_mark}",
                f"{C['blue']}{label}:{C['reset']}{pct:.0f}%{stale_mark}",
            ))

    # rate_limits 为 null 且本会话已产生成本 → 大概率在走 credits/extra usage 计费
    if data.get("_rl_null_frame") and ((data.get("cost") or {}).get("total_cost_usd") or 0) > 0.5:
        line1.append(f"{C['yellow']}⚠疑credits计费{C['reset']}")

    ctx_parts = []
    if ctx.get("used_percentage") is not None:
        size = ctx.get("context_window_size", 0)
        ctx_parts = [
            f"{C['blue']}{fmt_tokens(size)} Context:{C['reset']}{progress_bar(ctx['used_percentage'], bar_w)}",
            f"{C['blue']}{fmt_tokens(size)} CTX:{C['reset']}{ctx['used_percentage']:.0f}%",
        ]

    # 尝试完整版（带进度条+reset time）
    full = line1 + [p[0] for p in rl_parts] + (ctx_parts[:1] if ctx_parts else [])
    candidate = " | ".join(full)
    if vlen(candidate) <= W:
        line1 = full
    else:
        # 去掉 reset time
        no_reset = line1 + [p[1] for p in rl_parts] + (ctx_parts[:1] if ctx_parts else [])
        candidate = " | ".join(no_reset)
        if vlen(candidate) <= W:
            line1 = no_reset
        else:
            # 去掉进度条，只留百分比
            minimal = line1 + [p[2] for p in rl_parts] + (ctx_parts[1:2] if ctx_parts else [])
            line1 = minimal

    # --- Codex quota line: cached by codex-quota-watch, no live query here ---
    codex_line = []
    codex, codex_age = load_codex_status()
    usage_costs, usage_costs_age = load_usage_costs()
    maybe_refresh_usage_costs(usage_costs_age)

    claude_usage_cost = (usage_costs or {}).get("claude") or {}
    codex_usage_cost = (usage_costs or {}).get("codex") or {}

    claude_cost_line = []
    if claude_usage_cost:
        claude_cost_line = [
            f"{C['magenta']}Claude cost{C['reset']}",
            f"{C['blue']}5h:{C['reset']}{fmt_cost(claude_usage_cost.get('five_hour'))}",
            f"{C['blue']}7d:{C['reset']}{fmt_cost(claude_usage_cost.get('seven_day'))}",
        ]
        with_month = claude_cost_line + [
            f"{C['blue']}mo:{C['reset']}{fmt_cost(claude_usage_cost.get('month'))}"
        ]
        if vlen(" | ".join(with_month)) <= W:
            claude_cost_line = with_month

    codex_cost_line = []
    if codex_usage_cost:
        codex_cost_line = [
            f"{C['cyan']}Codex cost{C['reset']}",
            f"{C['blue']}5h:{C['reset']}{fmt_cost(codex_usage_cost.get('five_hour'))}",
            f"{C['blue']}7d:{C['reset']}{fmt_cost(codex_usage_cost.get('seven_day'))}",
        ]
        with_month = codex_cost_line + [
            f"{C['blue']}mo:{C['reset']}{fmt_cost(codex_usage_cost.get('month'))}"
        ]
        if vlen(" | ".join(with_month)) <= W:
            codex_cost_line = with_month

    def _total_cost(key):
        num = None
        for src in (claude_usage_cost, codex_usage_cost):
            try:
                num = (num or 0.0) + float(src.get(key))
            except (TypeError, ValueError):
                pass
        return num

    total_cost_line = []
    if claude_usage_cost or codex_usage_cost:
        total_cost_line = [
            f"{C['peach']}Total cost{C['reset']}",
            f"{C['blue']}5h:{C['reset']}{fmt_cost(_total_cost('five_hour'))}",
            f"{C['blue']}7d:{C['reset']}{fmt_cost(_total_cost('seven_day'))}",
        ]
        with_month = total_cost_line + [
            f"{C['blue']}mo:{C['reset']}{fmt_cost(_total_cost('month'))}"
        ]
        if vlen(" | ".join(with_month)) <= W:
            total_cost_line = with_month

    if codex:
        codex_full = [f"{C['cyan']}Codex{C['reset']}"]
        codex_no_reset = [f"{C['cyan']}Codex{C['reset']}"]
        codex_min = [f"{C['cyan']}Codex{C['reset']}"]
        for key, label in (("primary", "5h"), ("weekly", "7d")):
            entry = codex.get(key) or {}
            used = entry.get("usedPercent")
            if used is None:
                continue
            window_mins = entry.get("windowDurationMins")
            if window_mins:
                mins = int(window_mins)
                label = f"{mins // 1440}d" if mins >= 1440 else f"{mins // 60}h"
            reset_str = ""
            resets_at = entry.get("resetsAt")
            if resets_at:
                seconds = int(resets_at) - int(now.timestamp())
                if seconds > 0:
                    reset_str = f" {C['dim']}({fmt_duration(seconds)}){C['reset']}"
            bar = f"{C['blue']}{label}:{C['reset']}{progress_bar(float(used), bar_w)}"
            codex_full.append(f"{bar}{reset_str}")
            codex_no_reset.append(bar)
            codex_min.append(f"{C['blue']}{label}:{C['reset']}{int(used)}%")
        if codex_age is not None and codex_age > 180:
            codex_full.append(f"{C['red']}数据已过期{C['reset']}")
            codex_no_reset.append(f"{C['red']}数据已过期{C['reset']}")
            codex_min.append(f"{C['red']}过期{C['reset']}")
        if len(codex_full) > 1:
            if vlen(" | ".join(codex_full)) <= W:
                codex_line = codex_full
            elif vlen(" | ".join(codex_no_reset)) <= W:
                codex_line = codex_no_reset
            else:
                codex_line = codex_min

    # --- Line 2: Tokens + Cache + Cost ---
    line2 = []

    total_in = ctx.get("total_input_tokens", 0)
    total_out = ctx.get("total_output_tokens", 0)
    curr_usage = (ctx.get("current_usage") or {})
    turn_in_total = curr_usage.get("input_tokens", 0) + curr_usage.get("cache_creation_input_tokens", 0)
    turn_out = curr_usage.get("output_tokens", 0)
    turn_str = f" {C['dim']}(本轮: in {fmt_tokens(turn_in_total)}, out {fmt_tokens(turn_out)}){C['reset']}"
    if total_in or total_out:
        tok_full = f"{C['peach']}Tokens: in {fmt_tokens(total_in)}, out {fmt_tokens(total_out)}{turn_str}"
        tok_short = f"{C['peach']}Tokens: in {fmt_tokens(total_in)}, out {fmt_tokens(total_out)}{C['reset']}"
        line2.append(tok_full)
    cache_read = curr_usage.get("cache_read_input_tokens", 0)
    if cache_read > 0:
        line2.append(f"{C['cyan']}Cached: {fmt_tokens(cache_read)}{C['reset']}")

    cost = data.get("cost") or {}

    # 宽度不够时隐藏本轮数据
    if vlen(" | ".join(line2)) > W and (total_in or total_out):
        line2[0] = tok_short
        if vlen(" | ".join(line2)) > W:
            line2 = line2[1:]

    # --- Line 3: Duration + Model ---
    line3 = []

    duration_ms = cost.get("total_duration_ms")
    duration_part = ""
    if duration_ms and duration_ms > 0:
        duration_part = f"{C['dim']}{C['magenta']}会话时长: {fmt_duration(duration_ms / 1000)}{C['reset']}"
        line3.append(duration_part)

    model_name = (data.get("model") or {}).get("display_name", "")
    if model_name:
        effort = (data.get("effort") or {}).get("level", "")
        if effort:
            model_name += f"/{effort}"
        fast = data.get("fast_mode")
        model_name += f"/{'fast' if fast else 'nofast'}"
        line3.append(f"{C['dim']}{C['magenta']}{model_name}{C['reset']}")

    # 宽度不够时隐藏会话时长
    if vlen(" | ".join(line3)) > W and duration_part:
        line3 = [p for p in line3 if p != duration_part]

    output = [" | ".join(line) for line in (line1, claude_cost_line, codex_line, codex_cost_line, total_cost_line, line2, line3) if line]
    if output:
        print("\n".join(output))
        sys.stdout.flush()


def main():
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return
        data = json.loads(raw)
    except Exception:
        return

    now = datetime.now(timezone.utc)
    # TT_RENDER_ONLY=1：只渲染不落盘。pi 的状态栏（pi-statusline）拿 tt-status.json 的旧帧来渲染，
    # 若再 save_data 会把旧数据写回并刷新 _received_at，让 quota-wait / window-sync 误以为数据新鲜。
    if os.environ.get("TT_RENDER_ONLY") != "1":
        save_data(data, now)
    render(data, now)


if __name__ == "__main__":
    main()
