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

## pi 用量怎么算（`statusline/usage`）

pi 的用量也计入状态栏的费用行：

- **逐条回复单独算**：每条 assistant 回复按**它自己的模型**单价算，再相加；不用 pi 自带的 `cost.total`。
- **按 provider 分栏**：`anthropic` 记进 Claude 一栏，`openai-codex` 记进 Codex 一栏。
- **三处来源，按 `responseId` 去重**：pi 会话（`~/.pi/agent/sessions`）、会话归档（`~/.pi-conversation-archive`）、记账本（`~/.pi/agent/usage-ledger`，由 [`pi/usage-ledger`](../pi/usage-ledger/README.md) 扩展写入，能覆盖 `--no-session` 的子进程）。同一条回复出现在多处只算一次。
- **pi 调 Claude（claude-bridge）记在 Claude 栏**：这类用量的来源是 `~/.claude/projects`（Claude Code 自己的日志），所以已经算在 Claude 栏里；pi 侧的记录只作说明，**不会重复相加**。
- **`usage --breakdown`**：在总览下多出两张表。「Codex」表把 Codex 栏拆成 codex CLI / pi 有会话 / pi 无会话（子进程）三类，按角色和模型列出 5h / 7d / 本期费用，合计等于 Codex 栏；「Claude 栏中 pi 经 claude-bridge 的部分」只是说明值，不加进 Claude 合计。每行不足 $0.01 的并入「其他」。
- **状态栏**：Codex 5h 费用后若有 pi / 子进程份额，会追加 ` (pi $x·子 $y)`；没有就和以前一样。
- **pi-flow 用户**：executor / reviewer 子进程按角色记账的改动在 [leonjean214/pi-flow](https://github.com/leonjean214/pi-flow) 的 `feature/report-language-toggle` 分支。

