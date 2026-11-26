"""Composition root: settings select the provider; nothing else needs to change."""

import pytest

from app.agents.base import BaseAgent
from app.container import build_agent, build_application
from app.orchestration.nodes import NodeName
from tests.conftest import FakeProvider, fake_llm, make_settings


@pytest.mark.parametrize("name", ["ollama", "openai", "gemini", "groq"])
def test_build_agent_uses_configured_provider(name: str) -> None:
    agent = build_agent(make_settings(llm_provider=name))
    assert isinstance(agent, BaseAgent)
    assert agent.provider.name == name


def test_build_agent_accepts_injected_provider() -> None:
    provider = FakeProvider(fake_llm("injected"))
    assert build_agent(provider=provider).provider is provider


def test_build_application_compiles_graph_without_contacting_provider() -> None:
    graph = build_application(make_settings(llm_provider="openai"))  # no key: still builds
    assert NodeName.AGENT in graph.get_graph().nodes
