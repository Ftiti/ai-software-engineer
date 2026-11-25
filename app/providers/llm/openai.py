"""OpenAI LLM provider. Requires the ``openai`` extra (``uv sync --extra openai``)."""

from langchain_core.language_models import BaseChatModel

from app.config import Settings
from app.providers.llm.base import LLMProvider, LLMProviderError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        if settings.openai_api_key is None:
            raise LLMProviderError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        self._settings = settings

    def chat_model(self, *, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise LLMProviderError("Install the 'openai' extra: uv sync --extra openai") from exc

        return ChatOpenAI(
            api_key=self._settings.openai_api_key,
            model=model or self._settings.openai_model,
            temperature=self._settings.llm_temperature if temperature is None else temperature,
        )
