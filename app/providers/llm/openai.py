"""OpenAI LLM provider. Requires the ``openai`` extra and ``OPENAI_API_KEY``."""

from langchain_core.language_models import BaseChatModel

from app.providers.llm.base import LLMProvider, ModelInfo


class OpenAIProvider(LLMProvider):
    name = "openai"

    def _configured_model(self) -> str:
        return self._settings.openai_model

    def _configured_temperature(self) -> float | None:
        return self._settings.openai_temperature

    def _create_chat_model(self, info: ModelInfo) -> BaseChatModel:
        api_key = self._require_api_key(self._settings.openai_api_key, "OPENAI_API_KEY")
        chat_openai = self._import_optional("langchain_openai", "ChatOpenAI", extra="openai")
        model: BaseChatModel = chat_openai(
            api_key=api_key,
            model=info.model,
            temperature=info.temperature,
            timeout=info.timeout,
        )
        return model
