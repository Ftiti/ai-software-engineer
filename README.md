# AI Software Engineer Agent

An AI coding assistant, similar in concept to Claude Code or Cursor, that reads a codebase, plans changes, edits files, runs tests and reviews its own work.

It is built on:

- **LangGraph** for agent orchestration (stateful graphs, checkpoints, human-in-the-loop)
- **LangChain** for LLM and tool integration
- **Ollama** as the default local LLM, with OpenAI, Gemini and Groq available
- **MCP (Model Context Protocol)** as the main way to add tools

> **Status: Sprint 1.** The LangGraph engine runs: a user message goes through the graph to the configured LLM and back. No tools, MCP servers, memory or multi-agent yet.

---

## Vision

A local-first engineering agent that:

1. Runs fully offline on a local model (Ollama), and can switch to a hosted model through configuration alone.
2. Gets its capabilities from MCP servers, so new tools need no change to agent code.
3. Starts as one agent and grows into a team of specialists (architect, coder, tester, reviewer) coordinated by a supervisor.
4. Understands large codebases through RAG and remembers context across sessions.

---

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/). uv installs Python 3.12 automatically. For local inference, install [Ollama](https://ollama.com).

```bash
uv sync                           # install runtime and dev dependencies
cp .env.example .env              # adjust provider and model
ollama pull llama3.1:8b           # default local model (needs ~5.6 GiB free RAM)
uv run pytest                     # run the test suite
```

On a machine with less free memory, pull a smaller model (e.g. `ollama pull phi3`) and set `OLLAMA_MODEL=phi3:latest` in `.env`.

Hosted providers (OpenAI, Gemini, Groq) are optional extras. `uv sync` installs all of them for development; a production install picks only the one it needs:

```bash
uv sync --no-dev --extra openai   # or: --extra gemini, --extra groq
```

Try the agent end to end. The reply is streamed token by token (needs the configured provider running, e.g. Ollama):

```bash
uv run python scripts/test_agent.py                         # "Explain what you can do."
uv run python scripts/test_agent.py "Review this design..."  # custom prompt
```

Quality checks:

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

---

## Architecture

Dependencies point **inward**: agents depend on abstractions (`LLMProvider`, LangChain `BaseTool`, services), and only the `providers` layer knows about vendors.

```
┌──────────────────────────────────────────────────────────────┐
│  orchestration/   LangGraph StateGraph · router · planner    │
├──────────────────────────────────────────────────────────────┤
│  agents/          supervisor · architect · coder · tester ·  │
│                   reviewer          (prompts/ feeds these)   │
├───────────────────────────────┬──────────────────────────────┤
│  tools/                       │  memory/        rag/         │
│   interfaces/ local/ mcp/     │                              │
├───────────────────────────────┤                              │
│  services/                    │                              │
│   filesystem git terminal     │                              │
│   project                     │                              │
├───────────────────────────────┴──────────────────────────────┤
│  providers/   llm/  mcp/  embeddings/  vectorstore/          │
├──────────────────────────────────────────────────────────────┤
│  config/   models/   utils/          (shared by all layers)  │
└──────────────────────────────────────────────────────────────┘
```

| Path | Responsibility |
|---|---|
| `app/config/` | Typed settings (`pydantic-settings`) loaded from the environment and `.env`. The only place that reads environment variables. |
| `app/providers/llm/` | `LLMProvider` interface plus Ollama, OpenAI, Gemini and Groq adapters. `create_llm_provider()` picks one from `LLM_PROVIDER`. Every provider returns a LangChain `BaseChatModel`. |
| `app/providers/mcp/` | MCP server config (`mcpServers` JSON format), the server registry, and `MCPClient`, which turns MCP tools into LangChain tools. |
| `app/providers/embeddings/`, `vectorstore/` | Embedding and vector store backends for RAG (planned). |
| `app/services/` | Side-effecting operations (filesystem, git, terminal, project detection). No LLM code. |
| `app/tools/` | What agents can call. `interfaces/` holds the shared contracts, `local/` wraps services, `mcp/` adapts MCP tools. |
| `app/agents/` | One package per agent role. `base/` holds `BaseAgent` (system prompt + injected chat model) and the shared prompt; specialised agents extend it. |
| `app/orchestration/` | LangGraph engine: `state.py` (graph state), `nodes.py` (node factories), `router.py` (conditional edges), `graph.py` (wiring + composition root), `planner.py` (planned). |
| `app/memory/` | Short-term memory (LangGraph checkpointer) and long-term memory (LangGraph store). |
| `app/rag/` | Codebase indexing, chunking and retrieval. |
| `app/prompts/` | Prompt templates, versioned separately from code. |
| `app/models/` | Shared Pydantic domain models, e.g. plans and task results (planned). |
| `app/utils/` | Small helpers with no dependencies. |

### Agent engine (Sprint 1)

```
user ──► graph.invoke / graph.stream({"messages": [HumanMessage]})
          │
        START
          │
        agent  ── create_agent_node(BaseAgent) ── BaseAgent.invoke(history)
          │                                         │  [SystemMessage, *history]
          │                                         ▼
          │                                       BaseChatModel  ◄── create_llm_provider(settings)
          │                                         │
          │      {"messages": [AIMessage(name=…)]} ◄┘   (appended by add_messages)
          │
   route_after_agent ──► END   (Sprint 2 adds: ──► tools ──► agent)
```

- `build_graph(agent)` only wires nodes; `create_graph(settings)` is the single composition root that picks the provider.
- The system prompt is added on each model call and never stored in state, so agents sharing one history keep their own instructions.
- Each agent reply carries `AIMessage.name`, so a shared multi-agent history stays attributable.
- Nodes support both `invoke` and `ainvoke` natively.
- `graph.stream(..., stream_mode="messages")` yields LLM tokens as they are generated, although nodes call `invoke`: LangGraph captures them through callbacks.

### Design rules

- **Nothing outside `providers/llm/` imports a vendor SDK.** Code asks for `create_llm_provider().chat_model()` and gets a `BaseChatModel`.
- **Hosted vendor packages are optional extras** and are imported lazily, so an Ollama-only install never loads them.
- **Tools are LangChain `BaseTool`s.** Local and MCP tools look the same to an agent.
- **Services hold no LLM logic** and can be tested without a model.
- **Settings are injected.** Constructors take a `Settings` object, which keeps tests hermetic.

---

## Configuration

All settings are environment variables (see [.env.example](.env.example)). Precedence: real environment variable > `.env` file > default in [settings.py](app/config/settings.py). Put only what you change, and every secret, in `.env`; it is git-ignored.

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `openai` \| `gemini` \| `groq` |
| `LLM_TEMPERATURE` | `0.0` | 0.0–2.0 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | |
| `OLLAMA_MODEL` | `llama3.1:8b` | |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | – / `gpt-4o-mini` | needs `--extra openai` |
| `GOOGLE_API_KEY` / `GEMINI_MODEL` | – / `gemini-2.0-flash` | needs `--extra gemini` |
| `GROQ_API_KEY` / `GROQ_MODEL` | – / `llama-3.1-8b-instant` | needs `--extra groq` |
| `MCP_CONFIG_PATH` | `mcp_servers.json` | A missing file means no MCP servers |

---

## MCP strategy

MCP is the **main way to add capabilities**. Built-in local tools cover only the essentials needed to work offline.

- **Client first.** The agent is an MCP *client*. Servers are configured in `mcp_servers.json`, using the same `mcpServers` format as Claude Desktop, Claude Code and Cursor, so existing server definitions can be copied in. See [mcp_servers.example.json](mcp_servers.example.json).
- **Transports.** `stdio` (inferred when `command` is set), `streamable_http` (inferred when `url` is set) and `sse` (set explicitly).
- **Uniform tools.** `MCPClient` uses `langchain-mcp-adapters` to expose MCP tools as LangChain `BaseTool`s, prefixed with their server name to avoid collisions. Agents cannot tell MCP tools from local ones.
- **Per-server control.** Each server can be turned off with `"enabled": false`. Later sprints add per-agent tool allowlists, so for example the reviewer gets read-only tools.
- **Server mode (later).** The agent's own services can be exposed as an MCP server so other clients can use them.

---

## Multi-agent evolution

The graph is designed so that going from one agent to several only adds nodes; existing code does not change.

1. **Single agent (Sprints 1–2).** One agent node (`BaseAgent` from `agents/base/`) and, from Sprint 2, one tool node in a LangGraph `StateGraph`.
2. **Plan and execute (Sprint 3).** `planner.py` splits a request into steps, and `router.py` loops through the steps and stops when a step fails.
3. **Supervisor and specialists (Sprint 4+).** The supervisor routes work to the architect, coder, tester and reviewer. Each runs as its own subgraph with its own prompt, model (via `chat_model(model=...)`) and tool set. Agents communicate only through the shared graph state (`app/orchestration/state.py`); each reply is tagged with the agent's name.
4. **Review loops.** Tester and reviewer findings send work back to the coder, with a limit on iterations and human-in-the-loop interrupts before destructive actions.

---

## Roadmap

| Sprint | Goal |
|---|---|
| **0** ✅ | Architecture, configuration, LLM provider abstraction, MCP client wiring, tests |
| **1** ✅ | LangGraph engine: graph state, base agent, agent node, router foundation, end-to-end script |
| **2** | Tool node and `tools` route; local tools on the services layer (files, git, terminal) with sandboxing; first MCP servers enabled |
| **3** | Planner and router; checkpointing (short-term memory) and resumable sessions |
| **4** | Multi-agent: supervisor plus architect, coder, tester and reviewer subgraphs |
| **5** | RAG over the workspace (embeddings, vector store, code-aware chunking) |
| **6** | Long-term memory, evaluation harness, Docker packaging, observability |

---

## Project layout

```
app/          application package (see Architecture)
tests/        pytest suite (unit/ + graph tests)
scripts/      developer and maintenance scripts
docs/         design notes and ADRs
docker/       container build files
```
