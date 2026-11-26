"""Groq LLM provider. Requires the ``groq`` extra and ``GROQ_API_KEY``."""

from langchain_core.language_models import BaseChatModel

from app.providers.llm.base import LLMProvider, ModelInfo


class GroqProvider(LLMProvider):
    name = "groq"

    def _configured_model(self) -> str:
        return self._settings.groq_model

    def _configured_temperature(self) -> float | None:
        return self._settings.groq_temperature

    def _create_chat_model(self, info: ModelInfo) -> BaseChatModel:
        api_key = self._require_api_key(self._settings.groq_api_key, "GROQ_API_KEY")
        chat_groq = self._import_optional("langchain_groq", "ChatGroq", extra="groq")
        model: BaseChatModel = chat_groq(
            api_key=api_key,
            model=info.model,
            temperature=info.temperature,
            timeout=info.timeout,
        )
        return model
