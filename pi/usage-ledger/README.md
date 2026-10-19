# pi usage-ledger：把每条 pi 回复的用量记进账本

pi 的 `--no-session` 子进程（比如 pi-flow 派生的 executor / reviewer）不留会话文件，用量就丢了。这个全局扩展在每条 assistant 回复结束时往一个共享账本追加一行，`statusline/usage` 再把账本和会话、归档合并统计。

## 安装

```bash
mkdir -p ~/.pi/agent/extensions
ln -s ~/claude-tools/pi/usage-ledger ~/.pi/agent/extensions/usage-ledger
```

重开 pi 即生效。扩展出任何错都会被吞掉，不会打断 pi。

## 账本格式

目录默认 `~/.pi/agent/usage-ledger/`，可用环境变量 `PI_USAGE_LEDGER_DIR` 改。按月一个文件 `YYYY-MM.jsonl`，每行一条 JSON（超过 4096 字节的行会被丢弃，保证多进程并发 append 不撕裂）：

```json
{"ts":"2026-10-19T07:00:00.000Z","pid":123,"ppid":100,"provider":"openai-codex","model":"gpt-6-sol",
 "responseId":"resp_abc","usage":{"input":10,"output":2,"cacheRead":3,"cacheWrite":4,"totalTokens":19,"costTotal":0.25},
 "session":null,"cwd":"/work","role":"reviewer","parent":"parent-123"}
```

- `usage.input` 已扣掉 `cacheRead` / `cacheWrite`（pi 的口径）。
- `costTotal` 仅供参考，`statusline/usage` 不用它，而是按模型单价重算。
- `session` 为 `null` 表示 `--no-session`。

## 环境变量

| 变量 | 含义 |
|---|---|
| `PI_USAGE_LEDGER_DIR` | 账本目录，扩展和 `statusline/usage` 都读它 |
| `PI_USAGE_ROLE` | 这个 pi 进程的角色（如 `executor`、`reviewer`），原样写进 `role` |
| `PI_USAGE_PARENT` | 父任务/父进程的标识，原样写进 `parent`，用来把子进程用量归到父任务 |

两个变量都是可选的，不设就记 `null`。

## 子进程怎么覆盖到

- `--no-session`：扩展挂在 `message_end` 事件上，不依赖会话文件，所以照常记账。
- `--no-extensions`（`-ne`）会关掉扩展自动发现，**但显式的 `-e <路径>` 仍然加载**。要在这类子进程里记账，启动时加 `-e ~/.pi/agent/extensions/usage-ledger/index.ts`，并用环境变量传 `PI_USAGE_ROLE` / `PI_USAGE_PARENT`。
- 子进程会继承父进程的环境变量，所以只在父进程设一次 `PI_USAGE_LEDGER_DIR` 就够了。

## 测试

需要 Node 22.6+（能直接跑 `.ts`）：

```bash
cd pi/usage-ledger
node --experimental-strip-types --test index.test.mjs
```

测试里的 `import type` 来自 pi 的类型包，被类型剥离掉，不需要安装。
