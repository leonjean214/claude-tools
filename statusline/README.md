# Claude Code status line（额度进度条 + 重置倒计时）



显示内容：
- **5h / 7d 额度进度条**、已用百分比、距离重置的时间（来自 Claude Code 传给 status line 的 `rate_limits`，订阅用户才有）
- 上下文窗口占用条、tokens 进出、缓存命中
- git 分支和是否有未提交改动、会话时长、模型 / effort / fast
- 可选：等价 API 费用（需要同目录的 `usage`）、Codex 额度（需要 `codex-quota-watch` 写出的 `~/.codex/quota-status.json`）

每一帧还会写到 `~/.claude/tt-status.json`，别的脚本（比如本仓库的 `quota-wait`、自动续跑）可以直接读。

## 安装（macOS / Linux / Windows，需要 Python 3.8+）

```bash
git clone https://github.com/leonjean214/claude-tools.git ~/claude-tools
chmod +x ~/claude-tools/statusline/*
```

在 `~/.claude/settings.json` 加：

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ~/claude-tools/statusline/tt-statusline.py"
  }
}
```

Windows 把 `python3` 换成 `python`，路径写成 `%USERPROFILE%\\claude-tools\\statusline\\tt-statusline.py`。重开 Claude Code 就能看到。

## 可选部件
- **费用行**：`usage` 读 `~/.claude/projects` 和 `~/.codex/sessions` 本地日志，按 API 单价估算等价费用。不用装，status line 会在后台自动调用；想放在别处就设环境变量 `TT_USAGE_CMD=/path/to/usage`。
- **Codex 额度行**：装了 Codex CLI 的话，定时跑 `codex-quota-watch`（例如 cron / launchd 每分钟一次）。没装 Codex 这一行就不显示。
- 订阅月费在 `tt-statusline.py` 的 `CLAUDE_SUB_MONTHLY` / `CODEX_SUB_MONTHLY`，默认都是 20 美元，按自己套餐改。
