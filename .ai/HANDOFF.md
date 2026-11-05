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

## 审查修复（w66fix94，commit 6825e3a）

Codex 审查阻塞：`_rate_window` 用 `limits.get(key)`，把「key 缺失」「rate_limits 为 null」也当成「无限制」，导致错报。

- `statusline/usage`：`claude_status()` 中 `rate_limits` 非 dict（null/缺失）→ 5h/7d 都未知（`??%`）；`_rate_window()` 中 key 缺失 → 未知，只有 key 存在且值为 null 才 `missing=True`。
- `statusline/test_quota_windows.py`：新增 rate_limits=null / 缺失 / `{}`、两窗口都 null、`print_service` 输出层共 6 个用例。
- `windows/claude-resume.ps1`：five_hour key 缺失日志记 `5h=?`，显式 null 记 `5h=none`；等待逻辑不变。
- 验证：`uvx --from pytest pytest statusline/ -q` → 23 passed；`python3 -m unittest statusline/test_quota_windows.py` → OK；新增用例在旧版上有 4 个失败。
- 既有问题（未修）：`claude-resume.ps1` 用了 PS 7 才支持的 `??`，在 Windows PowerShell 5.1 下解析失败（base 起就这样）。`codex_status()` 对 primary/weekly 缺失同样标 missing，同类语义，不在本次范围。

## 第二轮审查修复（w66fix94 plan2）

本节是当前交付状态；上文关于 fallback 省略即 missing、Codex 缺字段暂不修的描述属于历史记录，已由本轮修正。

### 假设与范围

- 基线：`8cad0bed620fe9405f4ab30264ed36a8c38b7832`；在现有 `feat/w66-quota-ultra` 分支同步后修改，更新现有 PR #3（base `main`），不新开、不合并。
- 只有缓存明确存在且为 null 的窗口才有无限制证据；文本输出省略窗口无法区分套餐无窗口和解析失败，一律保留未知。
- Pro 的 `primary=10080min, weekly=null` 仍表示 7d 有读数、5h 无限制；不能仅因 primary 为 7d 就把缺失或无效 weekly 推断成无限制。
- `criteriaChanged`：无。未修改缓存 schema、额度生产脚本、费用计算、可执行位或 PowerShell 既有问题。

### 文件与行为

- `statusline/usage`：Codex 默认两个窗口未知；区分缺字段、错误类型和明确 null，先映射实际窗口再处理 null，防止 Pro 的周窗口被 null 覆盖。空窗口 dict 不覆盖有效 Pro 周读数；Claude/Codex 的非对象缓存不再因 `.get()` 崩溃。
- `statusline/usage`：fallback 只填确实解析出的百分比，不再因另一窗口有读数就把省略或 `?%` 的窗口标无限制。
- `statusline/test_quota_windows.py`：由 23 个测试扩展为 36 个，含两个 parser 的子场景、缺字段/错误类型/null/Pro/旧格式、缓存与回退到显示的集成，以及真实 quota-wait 解析/输出函数省略缺 resets_at 窗口的集成。
- `.ai/HANDOFF.md`：追加本节，保留历史证据。

### 验证证据（全部在 Win WSL）

测试前均按共用规则通过 rsync 镜像 worktree（排除 `.git`、`node_modules`、`.flow`），经 `win-wsl-run --cwd "$WSL_MIRROR" -- ...` 执行。公开交接不记录机器用户路径；以下为远端实际命令。

- 修复前仅增加回归测试：`python3 -m unittest statusline/test_quota_windows.py -v` → 31 tests，exit 1，22 failures / 4 errors（含 subTest）。Codex 缺失/错误类型和两个 fallback 的省略/问号均触发 `missing=True` 的错误断言；非对象缓存出现 AttributeError，证明重现两类原缺陷而非只测新实现。
- 缓存定向：`python3 -m unittest statusline.test_quota_windows.CodexStatusTest statusline.test_quota_windows.ClaudeStatusTest -v` → 17 tests，OK。
- 回退定向：`python3 -m unittest statusline.test_quota_windows.FallbackStatusTest -v` → 4 tests，OK。
- 修复后定向：`python3 -m unittest statusline/test_quota_windows.py -v` → 36 tests，OK，exit 0。
- 全目录回归：`python3 -m unittest discover -s statusline -p 'test_*.py' -v` → 36 tests，OK，exit 0；原有 Claude Ultra、Codex Pro/旧格式、通知与状态栏渲染测试仍通过。
- 真实 CLI 冒烟：WSL 内在三个独立临时 HOME 下执行真实 `python3 statusline/usage` 子进程，使用合成缓存；无缓存输出双 `??%`，缺 primary 输出 5h `??%` / 7d 25%，Pro 明确 null 输出「无 5h 限制」/ 7d 40%，最终 `CLI SMOKE PASSED: 3 scenarios`。临时 HOME 内无真实凭据或额度命令，未调用真实 API、钥匙串或通知。
- 显示集成：未知输出含 `??%` 且不含该窗口的「无 … 限制」；明确 null 仍显示无限制；另一有效窗口保留百分比。quota-wait 缺 resets_at 的实际省略输出不再被解释为无限制。

### 全文件语义审阅与文档

运行 `rg -n 'missing|WindowStatus|fallback_status|无限制|无 .*限制' statusline/usage` 后逐项复核：

- `WindowStatus`：默认 `missing=False, used_pct=None`，表示未知。
- `fallback_status`：只解析数字，从不凭省略标 missing；异常或空输出保持未知。
- `_rate_window`：只在 key 存在且为 null 时设 missing；缺字段和非 dict entry 是未知。
- `claude_status`：非 dict 的 rate_limits / 非对象缓存是未知，不推断无限制。
- `codex_status`：唯一的 missing 赋值来自显式 null 收集；有效槽位不被 null 覆盖。
- `print_service`：只消费 WindowStatus，不从显示或另一窗口反推状态。

已阅读 `README.md` 的 API Details 和 `statusline/README.md` 的显示/安装说明：本轮不新增接口、数据格式或运行方式，现有新旧套餐说明仍成立，无需修改。项目目录不存在 AGENTS.md，不新建；全局规则无需变化。

### 已知风险

- 仅有文本回退输出、没有明确 null 证据时，真实无窗口的套餐也会保守显示未知；这是本轮要求的行为，不通过新增协议或修改生产者猜测恢复无限制。
- 验证使用合成额度数据和隔离 HOME，未读取真实账户数据；PowerShell 5.1 的历史解析问题未处理。
