"""Ollama (local) LLM provider."""

from langchain_core.language_models import BaseChatModel
from langchain_ollama import ChatOllama

from app.config import Settings
from app.providers.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def chat_model(self, *, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
        return ChatOllama(
            base_url=self._settings.ollama_base_url,
            model=model or self._settings.ollama_model,
            temperature=self._settings.llm_temperature if temperature is None else temperature,
        )
