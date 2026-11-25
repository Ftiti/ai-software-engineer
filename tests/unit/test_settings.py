from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run each test away from the developer's real .env and LLM-related environment."""
    monkeypatch.chdir(tmp_path)
    for var in ("LLM_PROVIDER", "LLM_TEMPERATURE", "OLLAMA_MODEL", "OLLAMA_BASE_URL", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    get_settings.cache_clear()


def test_defaults() -> None:
    settings = Settings()
    assert settings.llm_provider == "ollama"
    assert settings.ollama_model == "llama3.1:8b"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.openai_api_key is None


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    settings = Settings()
    assert settings.llm_provider == "groq"
    assert settings.ollama_model == "qwen2.5-coder:7b"
    assert settings.llm_temperature == 0.7


def test_reads_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OLLAMA_MODEL=mistral:7b\nOPENAI_API_KEY=sk-test\n")
    settings = Settings()
    assert settings.ollama_model == "mistral:7b"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test"


def test_secrets_are_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    assert "sk-secret" not in repr(Settings())


@pytest.mark.parametrize(("var", "value"), [("LLM_PROVIDER", "unknown"), ("LLM_TEMPERATURE", "5")])
def test_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, var: str, value: str) -> None:
    monkeypatch.setenv(var, value)
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
