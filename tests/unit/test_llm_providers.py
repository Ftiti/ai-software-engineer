import pytest
from langchain_core.language_models import BaseChatModel

from app.config import Settings
from app.providers.llm import LLMProvider, LLMProviderError, create_llm_provider


def test_ollama_provider_builds_chat_model() -> None:
    settings = Settings(_env_file=None, llm_provider="ollama", ollama_model="llama3.1:8b")
    provider = create_llm_provider(settings)

    assert isinstance(provider, LLMProvider)
    assert provider.name == "ollama"

    model = provider.chat_model()
    assert isinstance(model, BaseChatModel)
    assert model.model == "llama3.1:8b"  # type: ignore[attr-defined]


def test_chat_model_overrides() -> None:
    provider = create_llm_provider(Settings(_env_file=None, llm_provider="ollama"))
    model = provider.chat_model(model="qwen2.5-coder:7b", temperature=0.5)
    assert model.model == "qwen2.5-coder:7b"  # type: ignore[attr-defined]
    assert model.temperature == 0.5  # type: ignore[attr-defined]


@pytest.mark.parametrize("name", ["openai", "gemini", "groq"])
def test_hosted_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    for var in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(LLMProviderError, match="API_KEY"):
        create_llm_provider(Settings(_env_file=None, llm_provider=name))
