# w66 claude-tools：额度显示适配 Claude Ultra / ChatGPT Pro

## 背景

- Claude Ultra：`/api/oauth/usage` 返回 `five_hour=null`，只有 `seven_day`。
- ChatGPT Pro：wham/usage 的 `primary_window` 就是 7 天窗口、`secondary_window=null`
  （经 codex app-server 后表现为 `primary.windowDurationMins≈10080`、`secondary=null`）。

要求：无 5h 窗口时不显示 5h 或显示「无 5h 限制」；周额度与重置时间照常；旧格式兼容。

## 改动文件

### statusline/usage
- `WindowStatus` 新增 `missing: bool`：区分「订阅没有该窗口」与「有窗口但数据缺失」。
- 新增 `_rate_window()`：`rate_limits` 里值为 `null` → `missing=True`。
- `claude_status()`：改用 `_rate_window`；Ultra 的 `five_hour=null` → 5h missing。
- `codex_status()`：窗口槽位按 `windowDurationMins` 判（≥1440min→7d，否则→5h）；
  `secondary=null` 时 5h 槽 missing；无 `windowDurationMins` 的旧数据沿用 primary=5h、weekly=7d。
- `fallback_status()`：命令正常输出但缺某窗口行时，该窗口标 `missing`（配合 quota-wait/codex-quota-watch 只打印存在的窗口）。
- `print_service()`：`missing` 窗口显示 `5h 无 5h 限制`，其余照常。

### statusline/codex-quota-watch
- 新增 `window_hours()` / `window_label()` / `notify_label()`：按 `windowDurationMins`
  推导标签（Pro 的 primary → `7d` / `7 天额度`；无时长的旧数据沿用旧映射）。
- `print_status()`：跳过缺失窗口（Pro 只打印 `7d:` 行），标签按时长。
- `notify_crossings()`：跳过缺失窗口；通知标题按时长（不再把 7 天窗口叫「5 小时额度」）。
- `normalized_status()` 与 `quota-status.json` 文件格式未变（旧数据兼容）。

### mac/check-quota
- `five_hour=null` 时打印 `5h  无 5h 限制`，7d 行照常。

### mac/claude-resume.sh
- 内嵌 python：`five_hour` 非 dict 时 `u5=None`，日志打印 `5h=none`；
  跳过 5h 的 WAIT 分支（7d 判断不变）。

### windows/check-quota.ps1
- `anthropic-ratelimit-unified-5h-*` 头缺失时打印 `5h  无 5h 限制`（原来会打印 0%/崩溃风险）。

### windows/claude-resume.ps1
- `five_hour` 为 `$null` 时 `$u5=$null`，日志打印 `5h=none`，跳过 5h WAIT 分支。

### README.md / statusline/README.md
- API Details 注明 `five_hour` 可能为 `null`（Ultra）、Codex 侧 primary 可为 7 天窗口（Pro）。

## 未改但已兼容（审过）

- `statusline/tt-statusline.py`：Claude 侧 `five_hour=null` 本来就被跳过（pct=None 不渲染）；
  Codex 侧已按 `windowDurationMins` 打标签、null secondary 已跳过。单测已覆盖确认。
- `mac/quota-wait`、`mac/schedule-next-resume`、`windows/quota-wait.ps1`、
  `windows/schedule-next-resume.ps1`：本来就把没有 `resets_at` 的窗口跳过，
  null 窗口天然不显示、不参与阻塞/调度判断。

## 测试

新增 `statusline/test_quota_windows.py`（unittest，17 个用例），覆盖：

- usage：`claude_status` 新（five_hour=null）/旧格式；`codex_status` 新（primary=7d、
  secondary=null）/旧（5h+7d）/无时长的 legacy 格式；`fallback_status`；`print_service` 输出。
- codex-quota-watch：`print_status` 新旧格式、标签推导、`notify_crossings` 跳过缺失窗口。
- tt-statusline render：Ultra 隐藏 5h 保留 7d、旧格式双窗口、Pro Codex primary 标成 7d。

运行方式（需要能 importlib 加载无扩展名脚本，Python 3.8+ 即可，开发用 3.12 验证）：

```bash
cd statusline && python3 -m unittest test_quota_windows -v
```

本环境验证：17 tests 全部通过；`py_compile` 检查 usage / codex-quota-watch /
tt-statusline.py / check-quota 通过；`bash -n` 检查 claude-resume.sh /
schedule-next-resume 通过；claude-resume.sh 内嵌 python 用新旧 JSON 手工跑过。
本机无 pwsh，ps1 改动未实际执行（改动很小、与原有写法一致）。

未调用任何真实额度接口；所有数据均为构造的 mock。

## 分支/PR

- 目标分支：`feat/w66-quota-ultra`，PR base=`main`，不合并。
- 本环境是 worktree 文件副本（无 .git），未运行 git；commit/push/开 PR 由 Mac 端回传后处理。
