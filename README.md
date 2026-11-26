# AI Software Engineer Agent

An AI coding assistant, similar in concept to Claude Code or Cursor, that reads a codebase, plans changes, edits files, runs tests and reviews its own work.

It is built on:

- **LangGraph** for agent orchestration (stateful graphs, checkpoints, human-in-the-loop)
- **LangChain** for LLM and tool integration
- **Ollama** as the default local LLM, with OpenAI, Gemini and Groq available
- **MCP (Model Context Protocol)** as the main way to add tools

> **Status: Sprint 3.** The LangGraph engine runs end to end on a provider-independent LLM layer (Ollama, OpenAI, Gemini, Groq), and the tool system (registry, manager, local and MCP adapters, real MCP client) is in place. Tools are not yet connected to the agent graph; no business tools, memory or multi-agent yet.

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

Try the tool pipeline (the demo `echo` tool plus the tools of any MCP server in `MCP_CONFIG_PATH`):

```bash
uv run python scripts/test_tools.py "Hello"
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
| `app/providers/llm/` | `LLMProvider` abstraction (`invoke`, `stream`, `model_info`) plus Ollama, OpenAI, Gemini and Groq providers. `create_llm_provider()` picks one from `LLM_PROVIDER`. See [LLM providers](#llm-providers). |
| `app/container.py` | Composition root: the only place that creates the provider, the agent, the graph and the tool manager. |
| `app/providers/mcp/` | MCP client side: `transport.py` (stdio, HTTP, SSE, WebSocket), `config.py` (the `mcpServers` file), `registry.py` (known servers), `client.py` (`connect` / `list_tools` / `execute_tool`). |
| `app/providers/embeddings/`, `vectorstore/` | Embedding and vector store backends for RAG (planned). |
| `app/services/` | Side-effecting operations (filesystem, git, terminal, project detection). No LLM code. |
| `app/tools/` | Tool system: `interfaces.py` (contracts), `base.py` (`BaseTool`), `registry.py`, `manager.py`, `adapters/` (local, MCP) and `local/` (tool implementations). See [Tool system](#tool-system). |
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
          │                                       LLMProvider.invoke  ◄── injected by app/container.py
          │                                         │
          │      {"messages": [AIMessage(name=…)]} ◄┘   (appended by add_messages)
          │
   route_after_agent ──► END   (Sprint 3 adds: ──► tools ──► agent)
```

- `build_graph(agent)` only wires nodes. It never creates providers or agents; `app/container.py` does.
- The system prompt is added on each model call and never stored in state, so agents sharing one history keep their own instructions.
- Each agent reply carries `AIMessage.name`, so a shared multi-agent history stays attributable.
- Nodes support both `invoke` and `ainvoke` natively.
- `graph.stream(..., stream_mode="messages")` yields LLM tokens as they are generated, although nodes call `invoke`: LangGraph captures them through callbacks.

### Design rules

- **Nothing outside `providers/llm/` imports a vendor SDK.** Enforced by `tests/unit/test_architecture.py`.
- **Hosted vendor packages are optional extras** and are imported lazily, so an Ollama-only install never loads them.
- **All tool calls go through `ToolManager`.** Local and MCP tools share the `ToolAdapter` interface, so callers cannot tell them apart. The tool system does not depend on LangGraph.
- **Services hold no LLM logic** and can be tested without a model.
- **Settings are injected.** Constructors take a `Settings` object, which keeps tests hermetic.

---

## Configuration

All settings are environment variables (see [.env.example](.env.example)). Precedence: real environment variable > `.env` file > default in [settings.py](app/config/settings.py). Put only what you change, and every secret, in `.env`; it is git-ignored.

| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `openai` \| `gemini` \| `groq` |
| `LLM_TEMPERATURE` | `0.0` | 0.0–2.0, used by every provider unless overridden |
| `LLM_TIMEOUT` | unset | Request timeout in seconds; unset = no limit |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | |
| `OLLAMA_MODEL` / `OLLAMA_TEMPERATURE` | `llama3.1:8b` / unset | |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_TEMPERATURE` | – / `gpt-4o-mini` / unset | key checked only when OpenAI is used |
| `GOOGLE_API_KEY` / `GEMINI_MODEL` / `GEMINI_TEMPERATURE` | – / `gemini-2.0-flash` / unset | key checked only when Gemini is used |
| `GROQ_API_KEY` / `GROQ_MODEL` / `GROQ_TEMPERATURE` | – / `llama-3.1-8b-instant` / unset | key checked only when Groq is used |
| `TOOL_TIMEOUT` | `60` | Seconds per tool call |
| `MCP_CONFIG_PATH` | `mcp_servers.json` | A missing file means no MCP servers |

---

## LLM providers

| `LLM_PROVIDER` | Backend | API key | Package |
|---|---|---|---|
| `ollama` (default) | Local models via [Ollama](https://ollama.com) | none | `langchain-ollama` (always installed) |
| `openai` | OpenAI | `OPENAI_API_KEY` | `langchain-openai` (extra `openai`) |
| `gemini` | Google Gemini | `GOOGLE_API_KEY` | `langchain-google-genai` (extra `gemini`) |
| `groq` | Groq | `GROQ_API_KEY` | `langchain-groq` (extra `groq`) |

### Why an abstraction

Each vendor SDK names the same things differently (`model` vs `model_name`, `timeout` vs `request_timeout`, Ollama has no timeout field at all) and has its own error types. If agents used these classes directly, every agent, node and test would depend on one vendor, and changing provider would mean editing all of them.

Instead, everything goes through `LLMProvider`:

```
Settings (.env)
    │
    ▼
create_llm_provider()  ── the only code that maps LLM_PROVIDER to a class
    │
    ▼
LLMProvider  (base.py: invoke · ainvoke · stream · astream · model_info · chat_model)
    ├── OllamaProvider   ─► ChatOllama
    ├── OpenAIProvider   ─► ChatOpenAI
    ├── GeminiProvider   ─► ChatGoogleGenerativeAI
    └── GroqProvider     ─► ChatGroq
    │
    ▼  injected by app/container.py
BaseAgent ─► graph nodes ─► graph   (never see which provider is behind)
```

- **Template method.** The base class owns everything shared: resolving model, temperature (`<PROVIDER>_TEMPERATURE` > `LLM_TEMPERATURE`) and timeout, caching the chat model, `invoke` / `stream`. A provider is ~20 lines that only say which settings it reads and which vendor class it builds.
- **Lazy and safe.** Creating a provider never contacts the backend and never needs a key; the key is checked when the model is first built. Vendor packages are imported only when their provider is used, with an install hint if missing.
- **Open for extension.** `register_provider("name", "package.module:Class")` adds a provider without editing the factory.

### Switching provider

```bash
# .env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

No code changes. The same graph, agent and prompts now run on Groq. To try a provider for one run only: `LLM_PROVIDER=gemini GOOGLE_API_KEY=... uv run python scripts/test_agent.py`.

---

## Tool system

```
            Agent / graph node / CLI
                      │  ToolRequest(tool_name, arguments, call_id)
                      ▼
               ┌─────────────┐
               │ ToolManager │  single entry point: lookup, timeout, error handling
               └──────┬──────┘
                      │ get(name)
               ┌──────▼──────┐
               │ToolRegistry │  name ─► ToolAdapter (filled by app/container.py)
               └──────┬──────┘
          ┌───────────┴────────────┐
          ▼                        ▼
 ┌──────────────────┐     ┌──────────────────┐
 │ LocalToolAdapter │     │  MCPToolAdapter  │
 │ validates input, │     │ forwards to the  │
 │ runs BaseTool    │     │ MCP client       │
 └────────┬─────────┘     └────────┬─────────┘
          ▼                        ▼
   BaseTool.execute()       MCPClient.execute_tool()
   (in-process code)        ─► transport (stdio/HTTP/SSE/WS) ─► MCP server
          │                        │
          └──────────┬─────────────┘
                     ▼
        ToolResult(output | error, call_id)
```

| Piece | File | Responsibility |
|---|---|---|
| Contracts | `tools/interfaces.py` | `ToolSpec`, `ToolRequest`, `ToolResult`, `ToolAdapter`, error types |
| `BaseTool` | `tools/base.py` | Base class for local tools: `name`, `description`, Pydantic `input_model` (validation + JSON Schema), `execute()` |
| Registry | `tools/registry.py` | `register`, `unregister`, `get`, `list_specs`. Names are unique; agents never instantiate tools |
| Manager | `tools/manager.py` | Runs a `ToolRequest` and always returns a `ToolResult`: unknown tool, invalid arguments, tool failure, timeout and crashes become error results the LLM can read. `execute_many` runs calls concurrently |
| Local adapter | `tools/adapters/local.py` | Validates arguments against the tool's input model, then runs it |
| MCP adapter | `tools/adapters/mcp.py` | Exposes an MCP tool as `<server>_<tool>` and forwards execution to the MCP client |

**Adding a local tool** means one new class, then one line in `build_local_tools()` in `app/container.py`:

```python
class ReadFileInput(BaseModel):
    path: str

class ReadFileTool(BaseTool[ReadFileInput]):
    name = "read_file"
    description = "Read a UTF-8 text file from the workspace."
    input_model = ReadFileInput

    def __init__(self, files: FileService) -> None:   # dependencies are injected
        self._files = files

    async def execute(self, params: ReadFileInput) -> str:
        return self._files.read_text(params.path)
```

`app/tools/local/echo.py` is a demonstration tool used by tests and `scripts/test_tools.py`; the application does not register it.

---

## MCP strategy

MCP is the **main way to add capabilities**. Built-in local tools cover only the essentials needed to work offline.

- **Client first.** The agent is an MCP *client*. Servers are configured in `mcp_servers.json`, using the same `mcpServers` format as Claude Desktop, Claude Code and Cursor, so existing server definitions can be copied in. See [mcp_servers.example.json](mcp_servers.example.json).
- **Transports.** `stdio` (inferred when `command` is set), `streamable_http` (inferred when `url` is set), `sse` and `websocket` (set explicitly). Each is a model in `transport.py` with `to_connection()`; adding one does not touch the client.
- **Client.** `SessionMCPClient` implements `connect()` (discover the tools of every enabled server), `list_tools()` and `execute_tool()`, opening one MCP session per operation. An unreachable server is logged and skipped (`failed_servers`); the others keep working. Tested against a real stdio MCP server (`tests/fixtures/echo_mcp_server.py`).
- **Uniform tools.** `load_mcp_tools()` wraps each discovered tool in an `MCPToolAdapter` named `<server>_<tool>`, registered next to local tools. Callers cannot tell MCP tools from local ones.
- **Per-server control.** Each server can be turned off with `"enabled": false`. Later sprints add per-agent tool allowlists, so for example the reviewer gets read-only tools.
- **Server mode (later).** The agent's own services can be exposed as an MCP server so other clients can use them.

---

## Multi-agent evolution

The graph is designed so that going from one agent to several only adds nodes; existing code does not change.

1. **Single agent (Sprints 1–5).** One agent node (`BaseAgent` from `agents/base/`) and, from Sprint 5, a tool node that calls `ToolManager`.
2. **Plan and execute (Sprint 6).** `planner.py` splits a request into steps, and `router.py` loops through the steps and stops when a step fails.
3. **Supervisor and specialists (Sprint 7+).** The supervisor routes work to the architect, coder, tester and reviewer. Each runs as its own subgraph with its own prompt, provider or model and tool set. Agents communicate only through the shared graph state (`app/orchestration/state.py`); each reply is tagged with the agent's name.
4. **Review loops.** Tester and reviewer findings send work back to the coder, with a limit on iterations and human-in-the-loop interrupts before destructive actions.

---

## Roadmap

| Sprint | Goal |
|---|---|
| **0** ✅ | Architecture, configuration, LLM provider abstraction, MCP client wiring, tests |
| **1** ✅ | LangGraph engine: graph state, base agent, agent node, router foundation, end-to-end script |
| **2** ✅ | LLM provider layer: `invoke`/`stream`/`model_info` abstraction, per-provider settings, timeout, factory registry, dependency injection via `app/container.py` |
| **3** ✅ | Tool system: `BaseTool`, registry, manager, local and MCP adapters, MCP transports, server registry and client (`connect` / `list_tools` / `execute_tool`) |
| **4** | Filesystem capability: sandboxed file service and `read_file` / `write_file` / `list_dir` / `search` tools |
| **5** | Agent tool loop: tools bound to the LLM, tool node calling `ToolManager`, `tools` route; git and terminal capabilities |
| **6** | Planner and router; checkpointing (short-term memory) and resumable sessions |
| **7** | Multi-agent: supervisor plus architect, coder, tester and reviewer subgraphs |
| **8** | RAG over the workspace (embeddings, vector store, code-aware chunking) |
| **9** | Long-term memory, evaluation harness, Docker packaging, observability |

---

## Project layout

```
app/          application package (see Architecture)
tests/        pytest suite: unit/, integration/ (real MCP server), fixtures/
scripts/      developer and maintenance scripts
docs/         design notes and ADRs
docker/       container build files
```
