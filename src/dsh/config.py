"""配置读取：.env 文件 + 环境变量。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


class ConfigError(RuntimeError):
    """配置缺失或不合法。"""


def load_dotenv(path: Path | None = None) -> None:
    """加载 .env；已存在的环境变量优先，不会被文件覆盖。

    未指定路径时，从当前目录开始向上最多查找 5 层。
    """
    if path is None:
        current = Path.cwd()
        for directory in (current, *list(current.parents)[:5]):
            candidate = directory / ".env"
            if candidate.is_file():
                path = candidate
                break
    if path is None or not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"环境变量 {name} 必须是整数，当前为 {raw!r}") from None


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model: str
    max_steps: int
    request_timeout: float
    search_backend: str
    searxng_url: str | None
    allow_private_network: bool
    max_fetch_chars: int
    max_download_bytes: int

    @classmethod
    def from_env(cls) -> Config:
        api_key = (
            os.environ.get("DSH_API_KEY") or os.environ.get("DEEPSEEK_API_KEY") or ""
        ).strip()
        if not api_key:
            raise ConfigError(
                "未找到 API Key。请把 .env.example 复制为 .env 并填写 DSH_API_KEY，"
                "或设置环境变量 DEEPSEEK_API_KEY。"
            )

        backend = (os.environ.get("DSH_SEARCH_BACKEND") or "auto").strip().lower()
        if backend not in {"auto", "ddg", "bing", "searxng"}:
            raise ConfigError("DSH_SEARCH_BACKEND 可选值为 auto、ddg、bing、searxng。")
        searxng_url = (os.environ.get("DSH_SEARXNG_URL") or "").strip() or None
        if backend == "searxng" and not searxng_url:
            raise ConfigError("DSH_SEARCH_BACKEND=searxng 时必须同时设置 DSH_SEARXNG_URL。")

        max_steps = _env_int("DSH_MAX_STEPS", 8)
        if max_steps < 1:
            raise ConfigError("DSH_MAX_STEPS 必须大于 0。")

        timeout_raw = os.environ.get("DSH_TIMEOUT", "30")
        try:
            request_timeout = float(timeout_raw)
        except ValueError:
            raise ConfigError(f"DSH_TIMEOUT 必须是数字，当前为 {timeout_raw!r}") from None
        if request_timeout <= 0:
            raise ConfigError("DSH_TIMEOUT 必须大于 0。")

        max_fetch_chars = _env_int("DSH_MAX_FETCH_CHARS", 12000)
        max_fetch_chars = max(500, min(max_fetch_chars, 50000))
        max_download_bytes = _env_int("DSH_MAX_DOWNLOAD_BYTES", 2_000_000)
        if max_download_bytes < 1:
            raise ConfigError("DSH_MAX_DOWNLOAD_BYTES 必须大于 0。")

        return cls(
            api_key=api_key,
            base_url=(os.environ.get("DSH_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            model=(os.environ.get("DSH_MODEL") or DEFAULT_MODEL).strip(),
            max_steps=max_steps,
            request_timeout=request_timeout,
            search_backend=backend,
            searxng_url=searxng_url,
            allow_private_network=_env_bool("DSH_ALLOW_PRIVATE_NETWORK"),
            max_fetch_chars=max_fetch_chars,
            max_download_bytes=max_download_bytes,
        )
