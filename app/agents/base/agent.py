"""Reusable agent abstraction.

An agent is a name and a system prompt bound to an :class:`LLMProvider`. The provider is
injected (built by the factory in the composition root), so an agent never knows which LLM
backend is behind it.

Specialised agents (architect, coder, tester, reviewer) subclass :class:`BaseAgent` and
override ``system_prompt`` or :meth:`build_messages`.
"""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, AnyMessage, BaseMessage, SystemMessage

from app.agents.base.prompt import BASE_SYSTEM_PROMPT
from app.providers.llm import LLMProvider


class BaseAgent:
    def __init__(
        self, provider: LLMProvider, *, name: str = "assistant", system_prompt: str | None = None
    ) -> None:
        self.provider = provider
        self.name = name
        self.system_prompt = system_prompt or BASE_SYSTEM_PROMPT

    def build_messages(self, history: Sequence[AnyMessage]) -> list[BaseMessage]:
        """Return the messages sent to the model: the system prompt followed by the history.

        The system prompt is added on every call and never stored in the graph state, so each
        agent in a shared history keeps its own instructions.
        """
        return [SystemMessage(content=self.system_prompt), *history]

    def invoke(self, history: Sequence[AnyMessage]) -> AIMessage:
        return self._tag(self.provider.invoke(self.build_messages(history)))

    async def ainvoke(self, history: Sequence[AnyMessage]) -> AIMessage:
        return self._tag(await self.provider.ainvoke(self.build_messages(history)))

    def _tag(self, response: AIMessage) -> AIMessage:
        """Attribute the reply to this agent, so a shared history stays readable."""
        response.name = self.name
        return response
