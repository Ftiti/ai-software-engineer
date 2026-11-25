"""LLM provider contract.

The rest of the application depends only on :class:`LLMProvider` and on LangChain's
``BaseChatModel`` interface, never on a concrete vendor SDK. LangGraph nodes receive a
``BaseChatModel`` and can call ``invoke``/``stream``/``bind_tools`` regardless of the backend.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from langchain_core.language_models import BaseChatModel


class LLMProviderError(RuntimeError):
    """Raised when a provider is misconfigured or its integration package is missing."""


class LLMProvider(ABC):
    """Creates chat models for one LLM backend."""

    name: ClassVar[str]

    @abstractmethod
    def chat_model(self, *, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
        """Return a configured chat model.

        ``model`` and ``temperature`` override the configured defaults, which lets
        different agents use different models from the same provider.
        """
