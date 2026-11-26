"""Reusable agent abstraction.

An agent is a system prompt and a name bound to a chat model. It receives the chat model
already built (dependency injection), so it never knows which LLM provider is behind it.

Specialised agents (architect, coder, tester, reviewer) subclass :class:`BaseAgent` and
override ``system_prompt`` or :meth:`build_messages`.
"""

from collections.abc import Sequence

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage

from app.agents.base.prompt import BASE_SYSTEM_PROMPT


class BaseAgent:
    def __init__(
        self, llm: BaseChatModel, *, name: str = "assistant", system_prompt: str | None = None
    ) -> None:
        self.llm = llm
        self.name = name
        self.system_prompt = system_prompt or BASE_SYSTEM_PROMPT

    def build_messages(self, history: Sequence[AnyMessage]) -> list[AnyMessage]:
        """Return the messages sent to the model: the system prompt followed by the history.

        The system prompt is added on every call and never stored in the graph state, so each
        agent in a shared history keeps its own instructions.
        """
        return [SystemMessage(content=self.system_prompt), *history]

    def invoke(self, history: Sequence[AnyMessage]) -> AIMessage:
        return self._tag(self.llm.invoke(self.build_messages(history)))

    async def ainvoke(self, history: Sequence[AnyMessage]) -> AIMessage:
        return self._tag(await self.llm.ainvoke(self.build_messages(history)))

    def _tag(self, response: AnyMessage) -> AIMessage:
        if not isinstance(response, AIMessage):
            raise TypeError(f"Expected AIMessage from chat model, got {type(response).__name__}")
        response.name = self.name
        return response
