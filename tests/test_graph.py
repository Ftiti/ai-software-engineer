"""Agent graph tests. A fake provider replaces the LLM, so no backend is contacted."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END

from app.agents.base import BASE_SYSTEM_PROMPT, BaseAgent
from app.orchestration import AgentState, build_graph
from app.orchestration.nodes import NodeName, create_agent_node
from app.orchestration.router import route_after_agent
from tests.conftest import FakeProvider, RecordingChatModel, fake_llm


def agent_with(llm: RecordingChatModel) -> BaseAgent:
    return BaseAgent(FakeProvider(llm))


def ask(text: str) -> AgentState:
    return {"messages": [HumanMessage(content=text)]}


def test_graph_initializes() -> None:
    graph = build_graph(agent_with(fake_llm()))
    assert NodeName.AGENT in graph.get_graph().nodes


def test_graph_returns_llm_response() -> None:
    graph = build_graph(agent_with(fake_llm("I can help with code.")))

    result = graph.invoke(ask("Explain what you can do."))

    human, reply = result["messages"]
    assert isinstance(human, HumanMessage)
    assert human.content == "Explain what you can do."
    assert isinstance(reply, AIMessage)
    assert reply.content == "I can help with code."
    assert reply.name == "assistant"


def test_llm_receives_system_prompt_and_history() -> None:
    llm = fake_llm("ok")
    build_graph(agent_with(llm)).invoke(ask("hello"))

    (sent,) = llm.received
    assert isinstance(sent[0], SystemMessage)
    assert sent[0].content == BASE_SYSTEM_PROMPT
    assert [m.content for m in sent[1:]] == ["hello"]


def test_system_prompt_is_not_stored_in_state() -> None:
    result = build_graph(agent_with(fake_llm("ok"))).invoke(ask("hello"))
    assert not any(isinstance(m, SystemMessage) for m in result["messages"])


def test_state_carries_conversation_history() -> None:
    llm = fake_llm("first answer", "second answer")
    graph = build_graph(agent_with(llm))

    state = graph.invoke(ask("first question"))
    state = graph.invoke({"messages": [*state["messages"], HumanMessage(content="second question")]})

    assert [m.content for m in state["messages"]] == [
        "first question",
        "first answer",
        "second question",
        "second answer",
    ]
    assert [m.content for m in llm.received[-1][1:]] == ["first question", "first answer", "second question"]


def test_custom_agent_name_and_prompt() -> None:
    llm = fake_llm("done")
    agent = BaseAgent(FakeProvider(llm), name="coder", system_prompt="You write code.")

    result = build_graph(agent).invoke(ask("write a function"))

    assert result["messages"][-1].name == "coder"
    assert llm.received[0][0].content == "You write code."


def test_agent_node_returns_only_new_messages() -> None:
    node = create_agent_node(agent_with(fake_llm("reply")))
    update = node.invoke(ask("hi"))

    (message,) = update["messages"]
    assert isinstance(message, AIMessage)
    assert message.content == "reply"


async def test_graph_async_invocation() -> None:
    graph = build_graph(agent_with(fake_llm("async reply")))
    result = await graph.ainvoke(ask("hi"))
    assert result["messages"][-1].content == "async reply"


def test_router_ends_turn() -> None:
    assert route_after_agent(ask("hi")) == END


def test_graph_streams_tokens_from_agent_node() -> None:
    graph = build_graph(agent_with(fake_llm("token by token")))

    tokens = [
        chunk.text
        for chunk, meta in graph.stream(ask("hi"), stream_mode="messages")
        if meta["langgraph_node"] == NodeName.AGENT
    ]

    assert "".join(tokens) == "token by token"
    assert len(tokens) > 1
