"""Groq LLM provider. Requires the ``groq`` extra (``uv sync --extra groq``)."""

from langchain_core.language_models import BaseChatModel

from app.config import Settings
from app.providers.llm.base import LLMProvider, LLMProviderError


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, settings: Settings) -> None:
        if settings.groq_api_key is None:
            raise LLMProviderError("GROQ_API_KEY is required when LLM_PROVIDER=groq")
        self._settings = settings

    def chat_model(self, *, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            raise LLMProviderError("Install the 'groq' extra: uv sync --extra groq") from exc

        return ChatGroq(
            api_key=self._settings.groq_api_key,
            model_name=model or self._settings.groq_model,
            temperature=self._settings.llm_temperature if temperature is None else temperature,
        )
