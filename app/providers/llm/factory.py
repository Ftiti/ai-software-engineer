"""Resolves the configured :class:`LLMProvider`.

This is the only place that knows the mapping from ``LLM_PROVIDER`` to a concrete class.
Provider modules are imported lazily so an unused vendor's package is never loaded.
"""

from collections.abc import Callable
from importlib import import_module

from app.config import Settings, get_settings
from app.providers.llm.base import LLMProvider, LLMProviderError

_PROVIDERS: dict[str, str] = {
    "ollama": "app.providers.llm.ollama:OllamaProvider",
    "openai": "app.providers.llm.openai:OpenAIProvider",
    "gemini": "app.providers.llm.gemini:GeminiProvider",
    "groq": "app.providers.llm.groq:GroqProvider",
}


def create_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Instantiate the provider selected by ``settings.llm_provider``."""
    settings = settings or get_settings()
    target = _PROVIDERS.get(settings.llm_provider)
    if target is None:
        raise LLMProviderError(f"Unknown LLM provider: {settings.llm_provider!r}")

    module_path, class_name = target.split(":")
    provider_cls: Callable[[Settings], LLMProvider] = getattr(import_module(module_path), class_name)
    return provider_cls(settings)
