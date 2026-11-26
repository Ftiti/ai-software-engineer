from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings


@pytest.fixture(autouse=True)
def in_empty_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Run away from the project's real .env file."""
    monkeypatch.chdir(tmp_path)


def test_defaults() -> None:
    settings = Settings()
    assert settings.llm_provider == "ollama"
    assert settings.llm_temperature == 0.0
    assert settings.llm_timeout is None
    assert settings.ollama_model == "llama3.1:8b"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_temperature is None
    assert settings.openai_api_key is None
    assert settings.google_api_key is None
    assert settings.groq_api_key is None


def test_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    monkeypatch.setenv("OLLAMA_TEMPERATURE", "0.7")
    monkeypatch.setenv("LLM_TIMEOUT", "30")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    settings = Settings()
    assert settings.llm_provider == "groq"
    assert settings.ollama_model == "qwen2.5-coder:7b"
    assert settings.ollama_temperature == 0.7
    assert settings.llm_timeout == 30
    assert settings.groq_model == "llama-3.3-70b-versatile"


def test_reads_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OLLAMA_MODEL=mistral:7b\nOPENAI_API_KEY=sk-test\n")
    settings = Settings()
    assert settings.ollama_model == "mistral:7b"
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "sk-test"


def test_environment_overrides_dotenv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("OLLAMA_MODEL=from-dotenv\n")
    monkeypatch.setenv("OLLAMA_MODEL", "from-env")
    assert Settings().ollama_model == "from-env"


def test_secrets_are_masked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    assert "sk-secret" not in repr(Settings())


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("LLM_PROVIDER", "unknown"),
        ("LLM_TEMPERATURE", "5"),
        ("OLLAMA_TEMPERATURE", "-1"),
        ("GROQ_TEMPERATURE", "2.5"),
        ("LLM_TIMEOUT", "0"),
    ],
)
def test_rejects_invalid_values(monkeypatch: pytest.MonkeyPatch, var: str, value: str) -> None:
    monkeypatch.setenv(var, value)
    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
