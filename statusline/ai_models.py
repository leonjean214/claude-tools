#!/usr/bin/env python3
"""usage 用到的那一小部分：选出当前 Codex 主力模型（codex_model）。

~/.config/ai-models.env 是运行时的准绳；只有该文件不存在时才读 Codex 模型目录
（~/.codex/models_cache.json）初始化。读不到时 usage 会回落到内置默认模型。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

STATE_KEYS = ("AI_CODEX_MODEL", "AI_PI_MODEL")
EXCLUDED = (
    "mini",
    "nano",
    "micro",
    "luna",
    "spark",
    "experimental",
    "preview",
    "auto-review",
    "reserve",
)
MODEL_RE = re.compile(r"^gpt-(\d+(?:\.\d+)*)(?:-|$)", re.IGNORECASE)
SAFE_CODEX_RE = re.compile(r"^gpt-[A-Za-z0-9][A-Za-z0-9._-]*$")
SAFE_PI_RE = re.compile(r"^openai-codex/gpt-[A-Za-z0-9][A-Za-z0-9._-]*$")


class ModelError(RuntimeError):
    pass


def state_path() -> Path:
    return Path(os.environ.get("AI_MODELS_FILE", "~/.config/ai-models.env")).expanduser()


def cache_path() -> Path:
    return Path(os.environ.get("CODEX_MODELS_CACHE", "~/.codex/models_cache.json")).expanduser()


def parse_version(slug: str) -> tuple[int, ...] | None:
    match = MODEL_RE.match(slug or "")
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def _catalog_models(catalog: Any) -> list[dict[str, Any]]:
    if isinstance(catalog, dict):
        catalog = catalog.get("models")
    if not isinstance(catalog, list):
        raise ModelError("Codex 模型目录缺少 models 数组")
    return [item for item in catalog if isinstance(item, dict)]


def select_latest_model(catalog: Any) -> str:
    candidates: list[tuple[tuple[int, ...], int, str]] = []
    for item in _catalog_models(catalog):
        slug = item.get("slug")
        if not isinstance(slug, str):
            continue
        version = parse_version(slug)
        text = " ".join(
            str(item.get(key) or "") for key in ("slug", "display_name", "description")
        ).lower()
        if (
            version is None
            or item.get("visibility") != "list"
            or item.get("supported_in_api") is not True
            or any(word in text for word in EXCLUDED)
        ):
            continue
        try:
            priority = int(item.get("priority", 1_000_000))
        except (TypeError, ValueError):
            priority = 1_000_000
        candidates.append((version, priority, slug))
    if not candidates:
        raise ModelError("Codex 模型目录里没有可用的主力 GPT 模型")
    # 用户 2026-09-27：跟随最新版本的 sol 档（写代码主力），不选更费额度的 astra 顶级档。
    # AI_MODEL_TIER 可改档位；设为空串或目录里没有该档位时，回落为最新版本里 Codex 优先级最高的那个。
    tier = os.environ.get("AI_MODEL_TIER", "sol").strip().lower()
    if tier:
        tiered = [item for item in candidates if item[2].lower().endswith("-" + tier)]
        if tiered:
            return max(tiered, key=lambda x: (x[0], -x[1]))[2]
    newest = max(version for version, _, _ in candidates)
    return min((item for item in candidates if item[0] == newest), key=lambda x: (x[1], x[2]))[2]


def load_catalog(refresh: bool = True) -> Any:
    if refresh:
        codex = os.environ.get("CODEX_BIN", "codex")
        try:
            proc = subprocess.run(
                [codex, "debug", "models"],
                capture_output=True,
                text=True,
                check=False,
                timeout=float(os.environ.get("LATEST_MODEL_TIMEOUT", "30")),
            )
            if proc.returncode == 0:
                return json.loads(proc.stdout)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    try:
        return json.loads(cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelError(f"无法读取 Codex 模型目录：{cache_path()}") from exc


def _validate_models(codex: str, pi: str) -> tuple[str, str]:
    if not SAFE_CODEX_RE.fullmatch(codex or ""):
        raise ModelError(f"共享 Codex 模型值无效：{codex!r}")
    if not SAFE_PI_RE.fullmatch(pi or ""):
        raise ModelError(f"共享 pi 模型值无效：{pi!r}")
    if pi != f"openai-codex/{codex}":
        raise ModelError("AI_CODEX_MODEL 与 AI_PI_MODEL 不一致")
    return codex, pi


def parse_state(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ModelError("共享模型文件包含无效行")
        key, value = line.split("=", 1)
        if key not in STATE_KEYS or key in values:
            raise ModelError(f"共享模型文件包含未知或重复键：{key}")
        values[key] = value.strip().strip("'\"")
    if set(values) != set(STATE_KEYS):
        raise ModelError("共享模型文件必须同时包含 AI_CODEX_MODEL 与 AI_PI_MODEL")
    return values


def atomic_write(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(name, mode)
        os.replace(name, path)
    except BaseException:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def write_state(codex: str, pi: str, path: Path | None = None) -> None:
    codex, pi = _validate_models(codex, pi)
    target = path or state_path()
    atomic_write(target, f"AI_CODEX_MODEL={codex}\nAI_PI_MODEL={pi}\n", 0o600)


def shared_models(env: Mapping[str, str] | None = None) -> tuple[str, str]:
    env = os.environ if env is None else env
    env_codex = env.get("AI_CODEX_MODEL")
    env_pi = env.get("AI_PI_MODEL")
    if env_codex or env_pi:
        if not env_codex and env_pi and env_pi.startswith("openai-codex/"):
            env_codex = env_pi.split("/", 1)[1]
        if env_codex and not env_pi:
            env_pi = f"openai-codex/{env_codex}"
        return _validate_models(env_codex or "", env_pi or "")

    path = state_path()
    if not path.exists():
        selected = select_latest_model(load_catalog(refresh=False))
        write_state(selected, f"openai-codex/{selected}", path)
    values = parse_state(path.read_text(encoding="utf-8"))
    return _validate_models(values["AI_CODEX_MODEL"], values["AI_PI_MODEL"])


def codex_model() -> str:
    return shared_models()[0]
