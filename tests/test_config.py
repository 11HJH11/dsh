from __future__ import annotations

import pytest

from dsh.config import Config, ConfigError, load_dotenv

_ENV_VARS = (
    "DSH_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "DSH_BASE_URL",
    "DSH_MODEL",
    "DSH_MAX_STEPS",
    "DSH_SEARCH_BACKEND",
    "DSH_SEARXNG_URL",
    "DSH_TIMEOUT",
    "DSH_MAX_FETCH_CHARS",
    "DSH_MAX_DOWNLOAD_BYTES",
    "DSH_ALLOW_PRIVATE_NETWORK",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_missing_api_key_raises():
    with pytest.raises(ConfigError, match="API Key"):
        Config.from_env()


def test_defaults(monkeypatch):
    monkeypatch.setenv("DSH_API_KEY", "sk-test")
    config = Config.from_env()
    assert config.base_url == "https://api.deepseek.com"
    assert config.model == "deepseek-chat"
    assert config.max_steps == 8
    assert config.search_backend == "auto"
    assert config.allow_private_network is False
    assert config.max_fetch_chars == 12000


def test_overrides(monkeypatch):
    monkeypatch.setenv("DSH_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ignored")
    monkeypatch.setenv("DSH_BASE_URL", "https://example.com/v1/")
    monkeypatch.setenv("DSH_MODEL", "custom-model")
    monkeypatch.setenv("DSH_MAX_STEPS", "3")
    monkeypatch.setenv("DSH_SEARCH_BACKEND", "bing")
    monkeypatch.setenv("DSH_ALLOW_PRIVATE_NETWORK", "true")
    config = Config.from_env()
    assert config.api_key == "sk-test"
    assert config.base_url == "https://example.com/v1"
    assert config.model == "custom-model"
    assert config.max_steps == 3
    assert config.search_backend == "bing"
    assert config.allow_private_network is True


def test_invalid_backend(monkeypatch):
    monkeypatch.setenv("DSH_API_KEY", "sk-test")
    monkeypatch.setenv("DSH_SEARCH_BACKEND", "google")
    with pytest.raises(ConfigError, match="DSH_SEARCH_BACKEND"):
        Config.from_env()


def test_searxng_requires_url(monkeypatch):
    monkeypatch.setenv("DSH_API_KEY", "sk-test")
    monkeypatch.setenv("DSH_SEARCH_BACKEND", "searxng")
    with pytest.raises(ConfigError, match="DSH_SEARXNG_URL"):
        Config.from_env()


def test_dotenv_does_not_override_existing(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DSH_API_KEY=from-file\nDSH_MODEL=\"file-model\"\nDSH_TIMEOUT=12\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DSH_API_KEY", "from-env")

    load_dotenv(env_file)

    assert Config.from_env().api_key == "from-env"
    assert Config.from_env().model == "file-model"
    assert Config.from_env().request_timeout == 12.0


def test_dotenv_found_in_parent_directory(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("DSH_API_KEY=from-parent\n", encoding="utf-8")
    nested = tmp_path / "src" / "package"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    load_dotenv()

    assert Config.from_env().api_key == "from-parent"
