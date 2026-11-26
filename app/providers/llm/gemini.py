"""Google Gemini LLM provider. Requires the ``gemini`` extra and ``GOOGLE_API_KEY``."""

from langchain_core.language_models import BaseChatModel

from app.providers.llm.base import LLMProvider, ModelInfo


class GeminiProvider(LLMProvider):
    name = "gemini"

    def _configured_model(self) -> str:
        return self._settings.gemini_model

    def _configured_temperature(self) -> float | None:
        return self._settings.gemini_temperature

    def _create_chat_model(self, info: ModelInfo) -> BaseChatModel:
        api_key = self._require_api_key(self._settings.google_api_key, "GOOGLE_API_KEY")
        chat_gemini = self._import_optional(
            "langchain_google_genai", "ChatGoogleGenerativeAI", extra="gemini"
        )
        model: BaseChatModel = chat_gemini(
            google_api_key=api_key,
            model=info.model,
            temperature=info.temperature,
            timeout=info.timeout,
        )
        return model
