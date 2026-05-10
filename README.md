# claude-tools

Claude Code quota check scripts for Mac and Windows.

## Scripts

### `mac/check-quota`
Reads OAuth token from macOS Keychain, makes a minimal Haiku API call, and displays current rate limit status.

```
=== Claude 额度 ⚠️ allowed_warning  [20:00:00] ===
5h  [█████████████████░░░] 87%  reset 22:00(1h59m后)  allowed
7d  [░░░░░░░░░░░░░░░░░░░░] 0%   reset 20:00(167h后)   allowed
```

**Install:**
```bash
cp mac/check-quota ~/bin/check-quota
chmod +x ~/bin/check-quota
```

Add to `~/.claude/settings.json` SessionStart hooks to see quota at every session start.

### `windows/check-quota.ps1`
Reads OAuth token from `~/.claude/.credentials.json`, same output format (ASCII bars).

**Install:**
```powershell
Copy-Item windows\check-quota.ps1 $env:USERPROFILE\bin\check-quota.ps1
```

## Rate limit headers used

| Header | Meaning |
|---|---|
| `anthropic-ratelimit-unified-status` | `allowed` / `allowed_warning` / exhausted |
| `anthropic-ratelimit-unified-5h-utilization` | 0.0–1.0, 5-hour window usage |
| `anthropic-ratelimit-unified-7d-utilization` | 0.0–1.0, 7-day window usage |
| `anthropic-ratelimit-unified-representative-claim` | which window is the binding constraint |
| `anthropic-ratelimit-unified-5h-reset` | Unix timestamp for 5h window reset |
| `anthropic-ratelimit-unified-7d-reset` | Unix timestamp for 7d window reset |

Token cost: 1 input token to `claude-haiku-4-5` per check — effectively free.
