"""Google Gemini LLM provider. Requires the ``gemini`` extra (``uv sync --extra gemini``)."""

from langchain_core.language_models import BaseChatModel

from app.config import Settings
from app.providers.llm.base import LLMProvider, LLMProviderError


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, settings: Settings) -> None:
        if settings.google_api_key is None:
            raise LLMProviderError("GOOGLE_API_KEY is required when LLM_PROVIDER=gemini")
        self._settings = settings

    def chat_model(self, *, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:
            raise LLMProviderError("Install the 'gemini' extra: uv sync --extra gemini") from exc

        return ChatGoogleGenerativeAI(
            google_api_key=self._settings.google_api_key,
            model=model or self._settings.gemini_model,
            temperature=self._settings.llm_temperature if temperature is None else temperature,
        )
