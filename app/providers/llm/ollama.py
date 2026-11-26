"""Ollama (local) LLM provider. No API key; talks to ``OLLAMA_BASE_URL``."""

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from app.providers.llm.base import LLMProvider, ModelInfo


class OllamaProvider(LLMProvider):
    name = "ollama"

    def _configured_model(self) -> str:
        return self._settings.ollama_model

    def _configured_temperature(self) -> float | None:
        return self._settings.ollama_temperature

    def _create_chat_model(self, info: ModelInfo) -> BaseChatModel:
        return ChatOllama(
            base_url=self._settings.ollama_base_url,
            model=info.model,
            temperature=info.temperature,
            # ChatOllama has no timeout field; it is passed to the underlying httpx client.
            client_kwargs={"timeout": info.timeout},
        )
