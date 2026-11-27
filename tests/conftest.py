"""Shared test doubles. No test in this suite contacts a real LLM."""

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import Field

from app.config import Settings, get_settings
from app.providers.llm import LLMProvider, ModelInfo

_CONFIG_PREFIXES = (
    "LLM_",
    "OLLAMA_",
    "OPENAI_",
    "GOOGLE_",
    "GEMINI_",
    "GROQ_",
    "MCP_",
    "TOOL_",
    "FS_",
    "CODE_",
    "TERMINAL_",
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hide the developer's real configuration (environment variables and the settings cache)."""
    import os

    for var in list(os.environ):
        if var.startswith(_CONFIG_PREFIXES):
            monkeypatch.delenv(var)
    get_settings.cache_clear()


def make_settings(**overrides: Any) -> Settings:
    """Settings built from defaults and ``overrides`` only, ignoring any ``.env`` file."""
    return Settings(_env_file=None, **overrides)


class RecordingChatModel(GenericFakeChatModel):
    """Fake chat model that replies from a fixed list and records what it was sent."""

    received: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        self.received.append(list(messages))
        return super()._generate(messages, *args, **kwargs)


def fake_llm(*replies: str) -> RecordingChatModel:
    return RecordingChatModel(messages=iter([AIMessage(content=r) for r in replies]))


class FakeProvider(LLMProvider):
    """Provider whose chat model is the given fake, for testing agents and graphs."""

    name = "fake"

    def __init__(self, llm: BaseChatModel, settings: Settings | None = None) -> None:
        super().__init__(settings or make_settings())
        self.llm = llm

    def _configured_model(self) -> str:
        return "fake-model"

    def _configured_temperature(self) -> float | None:
        return None

    def _create_chat_model(self, info: ModelInfo) -> BaseChatModel:
        return self.llm
