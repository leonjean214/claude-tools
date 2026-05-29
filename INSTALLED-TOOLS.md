# Claude Code CLI 已安装工具清单

> 记录在 Mac Claude Code 环境里配置/安装的工具。
> 最后更新:2026-05-29

---

## 1. `~/bin/` 自定义脚本(核心)

| 脚本 | 作用 |
|---|---|
| `ask` | SSH 调 Win RTX 5090 上的 Ollama 模型,gemma4 自动分类路由(code→qwen2.5-coder:32b / reason→qwq:32b / smart→qwen3-235b / 默认 gemma4) |
| `cc` | claude + 自动额度续命:在 tmux 里跑,额度重置后自动注入 Enter 解除 stop-and-wait |
| `ds` | DeepSeek-TUI → Win Ollama 启动器,带 SSH 端口转发,默认 gemma4 |
| `peer` | Mac Claude Code 直连 Win Claude Code,支持 `--session` 持续对话、stdin pipe、`--list` |
| `wm` | Mac↔Win Claude 异步信箱(Mac `~/claude-mailbox/`、Win `C:\Users\game5090\claude-mailbox\`) |
| `chat` / `chat_memory.py` | 多模型群聊 + 长期记忆系统(已推 GitHub `leonjean214/claude-tools`) |
| `quota-wait` | 额度检测三合一:`--status` 展示 / `--check` 退出码 / `--watch` 后台守护(监控并更新 launchd 续命时间,不自触发) |
| `schedule-next-resume` | 写 launchd plist,下次触发设为 now+5h 与最近重置点+1min 取更早 |
| `claude-resume.sh` | launchd 实际执行:**单实例锁** → 额度检查 → **交互窗口检测** → `claude -c` 续接上次任务 → 重排下次 |
| `claude-md-review-hook.sh` | Stop hook 用的 CLAUDE.md 审查脚本 |

> `check-quota` 已于 2026-05-29 删除(功能是 `quota-wait --status` 的子集)。

## 2. MCP Server

- `codegraph` — 唯一配置的 MCP server(代码图谱:callers / callees / impact / search / context / node / files / status)

## 3. Hooks(`~/.claude/settings.json`)

**SessionStart:**
1. 读 Win→Mac 信箱(`~/claude-mailbox/win-to-mac.md`)
2. `schedule-next-resume` 调度下次续命
3. 打印当前时间
4. `quota-wait --status` 检查额度
5. 后台启动 `quota-wait --watch`(日志 → `~/quota-watch.log`)

**Stop:**
1. 记录当前目录到 `~/.claude-resume-dir`
2. 跑 `claude-md-review-hook.sh`(CLAUDE.md 审查)

## 续命架构(2026-05-29 重构后)

三条路径,职责互不重叠:

| 路径 | 场景 | 行为 |
|---|---|---|
| **launchd 链** | 无人值守(无交互窗口) | 唯一触发器。定时跑 `claude-resume.sh`,续接上次任务 |
| **cc (tmux)** | 交互窗口 | UI stop-and-wait,额度重置后注入 Enter 继续当前任务 |
| **quota-watch** | 后台监控 | 只负责每 5min 把 launchd 触发时间更新到最近重置点,**不自己触发** |

**防冲突双保险**(本次新增):
- `claude-resume.sh` 开头**单实例锁**(`/tmp/claude-resume.lock`)→ launchd 与任何来源不会跑出两个 claude
- `claude-resume.sh` **交互窗口检测** → 若有 cc/交互窗口在跑,后台跳过续命交给 UI,避免争抢同一会话历史
- 续接 prompt:有未完成任务则继续做完,无任务则收尾退出,不乱开新任务

**⚠️ 进程检测用 `ps` 而非 `pgrep`**:实测 `pgrep`/`pgrep -f` 在 Claude Code 的 Bash 沙箱里匹配不到任何进程(全返回空),会导致交互检测漏报 → 后台误开 claude。改用 `ps -axo pid=,tty=,command= | grep -i "[c]laude"` 枚举,tty≠`??` 视为交互式;`while read` 用 here-doc 喂(非管道)以免子 shell 丢变量。

## 4. 其他配置(`~/.claude/settings.json`)

- **statusLine**:自定义 `~/.claude/tt-statusline.py`(Python 3.14)
- **permissions**:`defaultMode: bypassPermissions`,allow 列表 `Bash(*)`/Read/Write/Edit/WebFetch,`skipDangerousModePermissionPrompt: true`
- **theme**:dark
- **model**:opus(Opus 4.8)
- **autoUpdatesChannel**:latest

## 5. 未安装 / 占位

- `~/.claude/skills/` 目录不存在 —— 仅使用内置 skills
- `~/.claude/plugins/` 仅 marketplace 占位,无第三方插件

---

## 关联基础设施(非 CLI 工具,但配套)

- **Win 台式机**:9800X3D + RTX 5090(32GB) + 96GB DDR5 + 4TB NVMe
- **SSH 别名**:`win-desktop` / `win-claw` / `win-wan` / `win-claw-wan`
- **OpenClaw + Ollama**:Win 端已装,14 个模型按 tools/thinking/速度分类
- **双端续命链**:Mac launchd + Win Task Scheduler 各每 5h 接力,互通信箱互为后备
