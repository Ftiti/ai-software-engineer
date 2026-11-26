"""Resolves the configured :class:`LLMProvider`.

This is the only place that maps ``LLM_PROVIDER`` to a concrete class. Provider modules are
imported lazily, so selecting Ollama never loads the OpenAI, Gemini or Groq packages.
New providers are added with :func:`register_provider`, without editing this module.
"""

from importlib import import_module

from app.config import Settings, get_settings
from app.providers.llm.base import LLMProvider, LLMProviderError

_REGISTRY: dict[str, str] = {
    "ollama": "app.providers.llm.ollama:OllamaProvider",
    "openai": "app.providers.llm.openai:OpenAIProvider",
    "gemini": "app.providers.llm.gemini:GeminiProvider",
    "groq": "app.providers.llm.groq:GroqProvider",
}


def register_provider(name: str, target: str) -> None:
    """Register a provider as ``"package.module:ClassName"`` under ``name``."""
    if ":" not in target:
        raise ValueError(f"Provider target must look like 'module:Class', got {target!r}")
    _REGISTRY[name] = target


def available_providers() -> list[str]:
    return sorted(_REGISTRY)


def create_llm_provider(settings: Settings | None = None) -> LLMProvider:
    """Instantiate the provider selected by ``settings.llm_provider``.

    Creating a provider never contacts the backend and never requires an API key; keys are
    checked when the chat model is first built.
    """
    settings = settings or get_settings()
    target = _REGISTRY.get(settings.llm_provider)
    if target is None:
        raise LLMProviderError(
            f"Unknown LLM provider {settings.llm_provider!r}. Available: {', '.join(available_providers())}"
        )

    module_path, class_name = target.split(":")
    provider_cls = getattr(import_module(module_path), class_name)
    if not (isinstance(provider_cls, type) and issubclass(provider_cls, LLMProvider)):
        raise LLMProviderError(f"{target} is not an LLMProvider subclass")
    return provider_cls(settings)
