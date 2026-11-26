"""LLM provider contract.

The rest of the application depends only on :class:`LLMProvider`, never on a vendor SDK.
A provider turns settings into a LangChain chat model and offers ``invoke`` / ``stream``
(sync and async) on top of it.

Template method: this base class owns everything shared by providers (resolving model,
temperature and timeout, caching the chat model, invoking, streaming). A concrete provider
only declares its configured model and temperature and how to build its vendor chat model.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass
from functools import cached_property
from importlib import import_module
from typing import Any, ClassVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage
from pydantic import SecretStr

from app.config import Settings


class LLMProviderError(RuntimeError):
    """Raised when a provider is misconfigured or its integration package is missing."""


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Resolved configuration of a chat model."""

    provider: str
    model: str
    temperature: float
    timeout: float | None


class LLMProvider(ABC):
    """Creates and calls chat models for one LLM backend."""

    name: ClassVar[str]

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # -- Provider-specific hooks -------------------------------------------------------------

    @abstractmethod
    def _configured_model(self) -> str:
        """Model name from this provider's settings."""

    @abstractmethod
    def _configured_temperature(self) -> float | None:
        """Provider-specific temperature, or ``None`` to use ``LLM_TEMPERATURE``."""

    @abstractmethod
    def _create_chat_model(self, info: ModelInfo) -> BaseChatModel:
        """Build the vendor chat model. Validate credentials here, not in ``__init__``."""

    # -- Model information and creation ------------------------------------------------------

    @property
    def model_info(self) -> ModelInfo:
        """Configuration of the default chat model. Never contacts the provider."""
        return self._resolve()

    def chat_model(self, *, model: str | None = None, temperature: float | None = None) -> BaseChatModel:
        """Return a chat model. Overrides let different agents use different models.

        The default model is created once and reused.
        """
        if model is None and temperature is None:
            return self._default_chat_model
        return self._create_chat_model(self._resolve(model, temperature))

    @cached_property
    def _default_chat_model(self) -> BaseChatModel:
        return self._create_chat_model(self.model_info)

    def _resolve(self, model: str | None = None, temperature: float | None = None) -> ModelInfo:
        if temperature is None:
            temperature = self._configured_temperature()
        if temperature is None:
            temperature = self._settings.llm_temperature
        return ModelInfo(
            provider=self.name,
            model=model or self._configured_model(),
            temperature=temperature,
            timeout=self._settings.llm_timeout,
        )

    # -- Invocation --------------------------------------------------------------------------

    def invoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        return _expect_ai_message(self.chat_model().invoke(list(messages)))

    async def ainvoke(self, messages: Sequence[BaseMessage]) -> AIMessage:
        return _expect_ai_message(await self.chat_model().ainvoke(list(messages)))

    def stream(self, messages: Sequence[BaseMessage]) -> Iterator[AIMessageChunk]:
        yield from self.chat_model().stream(list(messages))

    async def astream(self, messages: Sequence[BaseMessage]) -> AsyncIterator[AIMessageChunk]:
        async for chunk in self.chat_model().astream(list(messages)):
            yield chunk

    # -- Helpers for concrete providers ------------------------------------------------------

    @staticmethod
    def _require_api_key(key: SecretStr | None, env_var: str) -> SecretStr:
        if key is None or not key.get_secret_value():
            raise LLMProviderError(f"{env_var} must be set to use this LLM provider")
        return key

    @staticmethod
    def _import_optional(module: str, attribute: str, extra: str) -> Any:
        """Import a vendor class from an optional extra, with an actionable error if missing."""
        try:
            return getattr(import_module(module), attribute)
        except ImportError as exc:
            raise LLMProviderError(f"Install the '{extra}' extra: uv sync --extra {extra}") from exc


def _expect_ai_message(message: BaseMessage) -> AIMessage:
    if not isinstance(message, AIMessage):
        raise LLMProviderError(f"Chat model returned {type(message).__name__}, expected AIMessage")
    return message
