# AI Software Engineer Agent

An AI coding assistant, similar in concept to Claude Code or Cursor, that reads a codebase, plans changes, edits files, runs tests and reviews its own work.

It is built on:

- **LangGraph** for agent orchestration (stateful graphs, checkpoints, human-in-the-loop)
- **LangChain** for LLM and tool integration
- **Ollama** as the default local LLM, with OpenAI, Gemini and Groq available
- **MCP (Model Context Protocol)** as the main way to add tools

> **Status: Sprint 7.** The LangGraph engine runs end to end on a provider-independent LLM layer (Ollama, OpenAI, Gemini, Groq). The tool system (registry, manager, local and MCP adapters, real MCP client) carries four capabilities: safe filesystem access, code intelligence, safe command execution and safe Git operations. Tools are not yet connected to the agent graph; no memory or multi-agent yet.

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

Try the tool pipeline on this project (filesystem tools plus the tools of any MCP server in `MCP_CONFIG_PATH`; only reads, including requests the safety rules refuse):

```bash
uv run python scripts/test_tools.py
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
│   registry · manager ·        │                              │
│   adapters (local, mcp)       │                              │
├───────────────────────────────┤                              │
│  capabilities/                │                              │
│   filesystem                  │                              │
│   code_intelligence           │                              │
│   terminal                    │                              │
│   git                         │                              │
├───────────────────────────────┴──────────────────────────────┤
│  providers/   llm/  mcp/  filesystem/  terminal/  git/       │
│               embeddings/  vectorstore/                      │
├──────────────────────────────────────────────────────────────┤
│  config/   models/   utils/          (shared by all layers)  │
└──────────────────────────────────────────────────────────────┘
```

| Path | Responsibility |
|---|---|
| `app/config/` | Typed settings (`pydantic-settings`) loaded from the environment and `.env`. The only place that reads environment variables. |
| `app/providers/llm/` | `LLMProvider` abstraction (`invoke`, `stream`, `model_info`) plus Ollama, OpenAI, Gemini and Groq providers. `create_llm_provider()` picks one from `LLM_PROVIDER`. See [LLM providers](#llm-providers). |
| `app/container.py` | Composition root: the only place that creates the provider, the agent, the graph, the capabilities and the tool manager. |
| `app/capabilities/` | Domain features exposed to agents as tools plus usage instructions. `filesystem/`, `code_intelligence/`, `terminal/` and `git/`. See [Filesystem capability](#filesystem-capability), [Code intelligence](#code-intelligence), [Terminal capability](#terminal-capability) and [Git capability](#git-capability). |
| `app/providers/filesystem/` | The only code that touches the operating system's filesystem. |
| `app/providers/terminal/` | The only code that starts operating-system processes. |
| `app/providers/git/` | Talks to the git executable, through the terminal provider. |
| `app/providers/mcp/` | MCP client side: `transport.py` (stdio, HTTP, SSE, WebSocket), `config.py` (the `mcpServers` file), `registry.py` (known servers), `client.py` (`connect` / `list_tools` / `execute_tool`). |
| `app/providers/embeddings/`, `vectorstore/` | Embedding and vector store backends for RAG (planned). |
| `app/services/` | Reserved for future side-effecting services (project detection). No LLM code. |
| `app/tools/` | Tool system: `interfaces.py` (contracts), `base.py` (`BaseTool`), `registry.py`, `manager.py`, `adapters/` (local, MCP) and `local/echo.py` (demo tool). See [Tool system](#tool-system). |
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
   route_after_agent ──► END   (Sprint 8 adds: ──► tools ──► agent)
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
- **Only `app/providers/filesystem/` touches the OS filesystem** (`os`, `shutil`, `tempfile`...). Enforced by `tests/unit/test_architecture.py`.
- **Only `app/providers/terminal/` starts processes** (`subprocess`, `asyncio.create_subprocess_*`): the agent never talks to the OS shell. Enforced by `tests/unit/test_architecture.py`.
- **Git runs only through the Git capability**: only `capabilities/git/` uses `app/providers/git/`, which runs git through the terminal provider; the terminal refuses `git`. Enforced by `tests/unit/test_architecture.py` and the Graphify check in `specs/001-git-capability/`.
- **Code intelligence is language-independent outside `parsers/`**: no module but a parser imports a parsing library (`ast`...), and code is read only through `FilesystemService`. Enforced by `tests/unit/test_architecture.py`.
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
| `FS_WORKSPACE_ROOT` | `.` | The only directory filesystem tools may access |
| `FS_READ_ONLY` | `false` | Refuse every modification |
| `FS_MAX_READ_BYTES` / `FS_MAX_WRITE_BYTES` | `1048576` | Size limits per file |
| `FS_MAX_LIST_ENTRIES` | `1000` | Entries returned by one listing (also bounds the files a project analysis sees; it reports `truncated`) |
| `FS_DENIED_PATTERNS` | `[".env", ".env.local", ".env.*.local", "*.pem", "*.key", "id_rsa*", "id_ed25519*"]` | No access at all, not even listing (JSON list) |
| `FS_PROTECTED_PATTERNS` | `[".git"]` | Readable, never modified |
| `FS_IGNORED_PATTERNS` | `[".git", ".venv", "node_modules", caches...]` | Skipped by recursive listings |
| `CODE_MAX_RESULTS` | `50` | Maximum symbols, imports or references returned by one code intelligence query |
| `TERMINAL_ENABLED` | `true` | Register the terminal tools |
| `TERMINAL_ALLOWED_COMMANDS` | `["python", "python3", "pytest", "ruff", "mypy", "make", "npm", "node", "composer", "php", "ls", "pwd", "echo"]` | Whitelist of program names (JSON list); `"*"` allows every program that is not denied |
| `TERMINAL_DENIED_COMMANDS` | `["git", "rm", "sudo", "curl", "ssh", "bash", "sh", "env", "npx", ...]` | Blacklist, always refused, even with `"*"` |
| `TERMINAL_ALLOWED_SUBCOMMANDS` | npm: `install`, `ci`, `test`, `run`...; composer: `install`, `update`, `test`... | JSON object: for these programs the first argument must be listed |
| `TERMINAL_DENIED_ARGUMENTS` | `["--exec*", "--upload-pack*", "--output*", ...]` | Arguments refused for every program (fnmatch) |
| `TERMINAL_DENIED_ENV` | `["PATH", "LD_*", "GIT_*", "PYTHONPATH", "NODE_OPTIONS", ...]` | Variables a command may not set |
| `TERMINAL_INHERITED_ENV` | `["PATH", "HOME", "USER", "LANG", ...]` | Host variables passed to commands; all others (API keys, tokens) are not |
| `TERMINAL_DEFAULT_TIMEOUT` / `TERMINAL_MAX_TIMEOUT` | `30` / `50` | Seconds. The max must stay below `TOOL_TIMEOUT` (checked at startup) |
| `TERMINAL_MAX_OUTPUT_BYTES` | `64000` | Per stream; longer output keeps its beginning and end |
| `TERMINAL_PYTHON` | `python3` | Interpreter used by `run_python`, `run_pytest` and `run_tests` |
| `GIT_ENABLED` | `true` | Register the Git tools |
| `GIT_ALLOW_PUSH` | `false` | `git_push` is offered to the agent only when true (never forced) |
| `GIT_PROTECTED_BRANCHES` | `[]` | Branches `git_push` refuses, e.g. `["main", "master"]` |
| `GIT_ALLOW_HOOKS` | `true` | Repository hooks run, like the project's Makefile; `false` disables them |
| `GIT_TIMEOUT` / `GIT_NETWORK_TIMEOUT` | `30` / `50` | Seconds for local / remote operations; both below `TOOL_TIMEOUT` (checked at startup) |
| `GIT_MAX_OUTPUT_BYTES` / `GIT_MAX_LOG_ENTRIES` | `64000` / `100` | Diff and show text returned to the agent; commits per log |
| `GIT_EXECUTABLE` | `git` | |
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

**Adding tools** means adding a capability (see [Filesystem capability](#filesystem-capability)): its tools subclass `BaseTool`, receive their service through the constructor, and the capability is listed once in `build_capabilities()` in `app/container.py`. Nothing in the tool system changes.

`app/tools/local/echo.py` is a demonstration tool used by tests and `scripts/test_tools.py`; the application does not register it.

---

## Filesystem capability

The first capability: lets the agent inspect and edit the project, safely. Tools: `list_files`, `read_file`, `write_file`, `create_file`, `delete_file`. The service also offers `create_directory`, `move_file` and `copy_file` for future capabilities.

```
 ToolManager ─► LocalToolAdapter ─► Filesystem tool          capabilities/filesystem/tool.py
                                    │  input model = request schema (schemas.py)
                                    │  runs the service in a worker thread
                                    │  FilesystemError ─► ToolExecutionError
                                    ▼
                             FilesystemService              capabilities/filesystem/service.py
                                    │  business logic: listing, recursion, text decoding,
                                    │  create vs overwrite, OS error translation
                         ┌──────────┴───────────┐
                         ▼                      ▼
                  PathValidator          FilesystemProvider  providers/filesystem/
                  (validator.py)         (base.py / local.py)
                  all safety rules       the ONLY code touching the OS:
                  in one place           stat, scandir, atomic write, move, copy
                                                │
                                                ▼
                                         Operating system
```

| Layer | File | Responsibility |
|---|---|---|
| Tools | `capabilities/filesystem/tool.py` | One small class per tool, mapping its input to one service call |
| Schemas | `capabilities/filesystem/schemas.py` | Typed requests (also the tools' JSON Schemas) and responses |
| Service | `capabilities/filesystem/service.py` | Business logic. Never touches the OS or builds paths itself |
| Validator | `capabilities/filesystem/validator.py` | Every safety rule, plus existence, type and size checks |
| Exceptions | `capabilities/filesystem/exceptions.py` | `FileNotFound`, `AccessDenied`, `InvalidPath`, `FileTooLarge`... with LLM-readable messages |
| Prompt | `capabilities/filesystem/prompts.py` | How the agent should use the tools (inspect first, never guess, read before editing) |
| Assembly | `capabilities/filesystem/capability.py` | provider ─► validator ─► service ─► tools, returned as a `Capability` |
| Provider | `providers/filesystem/` | `FilesystemProvider` interface and `LocalFilesystemProvider` |

### Safety model

Every path an LLM sends goes through `PathValidator.resolve()` before anything touches the disk:

1. **Well-formed**: not empty, no NUL byte.
2. **Confined to the workspace**: the *real* path (``..`` collapsed, symlinks followed) must be inside `FS_WORKSPACE_ROOT`. `../../etc/passwd`, absolute paths elsewhere and symlinks pointing outside are refused.
3. **Secrets are invisible**: paths with a component matching `FS_DENIED_PATTERNS` cannot be read, written or listed.
4. **Operation allowed**: modifications are refused in read-only mode, on `FS_PROTECTED_PATTERNS` (`.git`) and on the workspace root.
5. **Limits**: file size for reads and writes, entry count for listings; binary and non-UTF-8 files are refused as text.

Writes are atomic (temporary file + rename, permissions kept), so an interrupted write never leaves a half-written file. Every refusal is a normal tool error the LLM can read and react to.

---

## Code intelligence

Lets the agent **understand** the code instead of only reading text: what a project contains, where a symbol is defined, who uses it, which classes inherit from it, what a module depends on. Everything comes from parsed source (Python's `ast`), never from text search.

Tools: `analyze_project`, `analyze_file`, `find_symbol`, `find_class`, `find_function`, `search_import`, `find_definition`, `find_references`, `class_hierarchy`, `module_dependencies`.

```
 ToolManager ─► LocalToolAdapter ─► code intelligence tool      tool.py
                                    ▼
                          CodeIntelligenceService               service.py
                          builds a fresh index per query, applies limits
                 ┌──────────────────┼───────────────────────┐
                 ▼                  ▼                       ▼
           SymbolSearch       CodeNavigator           (analysis summary)
           search.py          navigator.py
           ranked lookups     resolution, definitions,
                              references, hierarchy, dependencies
                 └────────┬─────────┘
                          ▼
                    SymbolIndex  ◄── SymbolIndexer             indexer.py
                    dict lookups by qualified name, name, kind,
                    import binding, referenced name
                          ▲
                    CodeAnalyzer                               analyzer.py
                    lists + reads files, picks the parser,
                    caches parses by content hash
                 ┌────────┴──────────────┐
                 ▼                       ▼
         FilesystemService        ParserRegistry ─► LanguageParser   parsers/base.py
         (Sprint 4: same safety   by extension      └ PythonParser   parsers/python.py
          rules: workspace,                         └ (PHP, JS, TS, Java, Go: future)
          secrets, .venv ignored)
```

| Piece | File | Responsibility |
|---|---|---|
| Schemas | `schemas.py` | Language-neutral model: `Symbol` (module, class, function, method, variable), `ImportInfo`, `Reference`, `FileAnalysis`, plus tool requests and responses |
| Parser abstraction | `parsers/base.py` | `LanguageParser` (`language`, `extensions`, `module_name()`, `parse()`) and `ParserRegistry` (extension ─► parser) |
| Python parser | `parsers/python.py` | `ast`-based: symbols with signatures, bases, decorators, docstrings and lines; imports with relative ones made absolute; references with their dotted expression |
| Analyzer | `analyzer.py` | `CodeAnalyzer.analyze_file()` / `analyze_project()`. Unreadable or invalid files are reported as `failures`, not fatal |
| Index | `indexer.py` | `SymbolIndex`: every lookup is a dictionary access. `SymbolIndexer` builds an up-to-date one on demand |
| Search engine | `search.py` | `SymbolSearch`: symbols ranked exact ─► case-insensitive ─► prefix ─► substring; dotted queries match qualified names; import search |
| Navigator | `navigator.py` | `CodeNavigator`: name resolution (Go To Definition), references, parent and child classes, module dependencies |
| Service | `service.py` | `CodeIntelligenceService`: the API used by the tools |
| Errors | `exceptions.py` | `UnsupportedLanguage`, `ParserError`, `SymbolNotFound`, `AmbiguousSymbol`, `InvalidProject` |
| Prompt | `prompts.py` | Inspect code before modifying it, never guess implementations, analyze dependencies before editing |
| Assembly | `capability.py` | filesystem service ─► analyzer ─► indexer ─► service ─► tools |

### Parser abstraction

The parser is the **only** language-specific part. A parser converts one file into the neutral model; qualified names always use `.` (`package.module.Class.method`) whatever the language. To add a language:

```python
class GoParser(LanguageParser):
    language = "go"
    extensions = (".go",)

    def module_name(self, path: str) -> str: ...
    def parse(self, path: str, source: str) -> FileAnalysis: ...
```

and add `GoParser()` to `default_parsers()` in `parsers/__init__.py`. The analyzer, index, search engine, navigator, service and tools do not change (a test registers a toy language to prove it).

### Analyzer and index

`CodeAnalyzer` reads the project **through `FilesystemService`**, so code analysis obeys the filesystem safety rules: nothing outside the workspace, secrets never read, `.venv`/`node_modules` skipped, size limits. Parse results are cached by content hash, so each query sees the files as they are now and only changed files are parsed again.

`SymbolIndex` reorganises the analyses into dictionaries: by qualified name, by name, by kind, by referenced name, and per file the **bindings** created by imports (`from app.tools import BaseTool` binds `BaseTool` to `app.tools.BaseTool`).

### Search engine and navigation

- **Search** matches parsed definitions only: searching `execute` finds the methods named `execute`, not comments or strings containing the word.
- **Go To Definition**: a name used in a file is resolved through that file's imports, its own definitions and its star imports, then looked up while following re-exports (`app.tools.BaseTool` ─► `app.tools.base.BaseTool`).
- **References**: uses of the symbol's name and of its import aliases. A use resolved to the symbol is `confirmed`; a use that cannot be resolved statically (`self.method()`, `obj.run()`) is kept with `confirmed=false`; a use resolved to something else (another class, a library) is dropped.
- **Class hierarchy**: base classes resolved across files (or `null` when outside the project) and direct subclasses.
- **Module dependencies**: what a file imports (internal or external, with the file defining each import) and which files import it, including through re-exports.

Results are capped by `CODE_MAX_RESULTS` (default 50); responses include the `total` before the cap.

---

## Terminal capability

Lets the agent **run** things: tests, linters, type checkers, builds and package managers, so it can check its own changes. Commands run in the filesystem workspace, never through a shell, and go through the tool system like every other tool: the agent never reaches `subprocess`.

Tools: `execute_command`, `run_tests`, `run_python`, `run_pytest`, `run_make`, `run_npm`, `run_composer`. Git is not available here: it has its own [capability](#git-capability). Each returns `stdout`, `stderr`, `exit_code`, `succeeded`, `timed_out`, `duration_seconds` and `truncated`. Every tool accepts `working_directory` (relative to the workspace), `timeout` and `env`.

```
 ToolManager ─► LocalToolAdapter ─► terminal tool                 capabilities/terminal/tool.py
                                    │  async: runs on the event loop, so cancelling the
                                    │  call (ToolManager timeout) stops the process
                                    │  TerminalError ─► ToolExecutionError
                                    ▼
                             TerminalService                      service.py
                                    │  business logic: request ─► argument vector
                                    │  (python -m pytest, npm test -- ..., runner detection)
                                    ▼
                             CommandValidator                     validator.py
                                    │  every safety rule ─► ValidatedCommand
                                    │  workspace checks delegated to the filesystem PathValidator
                                    ▼
                             CommandExecutor                      executor.py
                                    │  environment (filtered), OS error translation,
                                    │  output decoding and truncation ─► CommandResult
                                    ▼
                             TerminalProvider                     providers/terminal/
                             (base.py / local.py)                 the ONLY code starting processes:
                                    │                             own process group, timeout,
                                    ▼                             bounded capture, kill on cancel
                             Operating system
```

| Layer | File | Responsibility |
|---|---|---|
| Tools | `capabilities/terminal/tool.py` | One small class per tool, mapping its input to one service call |
| Schemas | `capabilities/terminal/schemas.py` | `CommandOptions` (working directory, timeout, env), one request per tool, `CommandResult` |
| Service | `capabilities/terminal/service.py` | Business logic only: which command a request means. No process or OS code |
| Validator | `capabilities/terminal/validator.py` | `TerminalPolicy` and every safety rule |
| Executor | `capabilities/terminal/executor.py` | Runs a `ValidatedCommand` through the provider and builds the result |
| Exceptions | `capabilities/terminal/exceptions.py` | `InvalidCommand`, `CommandNotAllowed`, `WorkspaceViolation`, `CommandNotFound`, `CommandPermissionDenied` |
| Prompt | `capabilities/terminal/prompts.py` | How the agent should use the tools (dedicated tools first, read failures, never work around a refusal) |
| Assembly | `capabilities/terminal/capability.py` | provider ─► validator ─► executor ─► service ─► tools, returned as a `Capability` |
| Provider | `providers/terminal/` | `TerminalProvider` interface and `LocalTerminalProvider` (asyncio subprocesses) |

### Execution flow

1. The LLM calls, say, `run_tests` with `{"args": ["-x"]}`. `ToolManager` validates the arguments against the tool's input model.
2. `TerminalService` picks the runner from the project files (`pyproject.toml` ─► pytest, `package.json` ─► `npm test`, `composer.json` ─► `composer test`, `Makefile` ─► `make test`) and builds `["python3", "-m", "pytest", "-x"]`.
3. `CommandValidator` checks the program, subcommand, arguments, working directory, timeout and environment, and returns a `ValidatedCommand`.
4. `CommandExecutor` builds the environment and calls the provider.
5. `LocalTerminalProvider` starts the process in its own process group with an empty stdin, reads stdout and stderr concurrently, and stops the whole group on timeout (SIGTERM, then SIGKILL after 2 s).
6. The result comes back as data. **A failing command is a normal result** (`succeeded: false`, exit code, stderr) for the agent to read and fix; only a refused or impossible command is a tool error.

### Security model

- **No shell, ever.** A command line is split with POSIX quoting (`shlex`) and executed as an argument vector. Pipes, redirections, `&&`, `;`, globs and `$VARIABLES` cannot do anything; shell operators are refused with an explanation instead of being passed as arguments.
- **Whitelist and blacklist.** The program must be a bare name (no `/usr/bin/x`, no `./script`) in `TERMINAL_ALLOWED_COMMANDS`. `TERMINAL_DENIED_COMMANDS` always wins, even over `"*"`. Shells and wrappers (`bash`, `sh`, `env`, `xargs`, `npx`) are blacklisted because they would run a command that skipped these checks.
- **Subcommands.** npm and composer are limited to development commands. Options before the subcommand (`npm --prefix /x test`) are refused. `git` is blacklisted: Git goes through the Git capability.
- **Dangerous arguments.** `TERMINAL_DENIED_ARGUMENTS` blocks options that run other programs or write files (`--exec`, `--upload-pack`, `--output`...).
- **Workspace confinement.** The working directory must be inside `FS_WORKSPACE_ROOT`. Path arguments that leave it (absolute paths, `..`) are refused, and so are arguments naming a secret (`FS_DENIED_PATTERNS`), so `python3 .env` fails just like `read_file(".env")`. Both capabilities share the filesystem `PathValidator`: one definition of the workspace.
- **Clean environment.** Commands receive only `TERMINAL_INHERITED_ENV` from the host, so API keys and tokens in the agent's environment do not leak. Variables that change what runs (`PATH`, `LD_PRELOAD`, `GIT_*`...) cannot be set. `NO_COLOR`, `PAGER=cat` and `GIT_TERMINAL_PROMPT=0` keep commands non-interactive.
- **Limits.** Timeout per command (max `TERMINAL_MAX_TIMEOUT`, below `TOOL_TIMEOUT`); output capped per stream, keeping the beginning and the end; cancellation and timeout kill child processes too.

**Limits of the model.** These rules prevent mistakes and obvious misuse; they are not a sandbox. An allowed interpreter (`python3 -c ...`, `node -e ...`) or a project script (`make`, `npm run`) can do anything the user running the agent can. For untrusted work, run the agent in a container (Sprint 12), or trim `TERMINAL_ALLOWED_COMMANDS`, or set `TERMINAL_ENABLED=false`.

### Integration with the next sprints

- **Git capability (Sprint 7)**: done. It reuses the same `TerminalProvider`, through `app/providers/git/`, with its own rules (see [Git capability](#git-capability)).
- **Planner and supervisor (Sprints 9–10)**: they call tools through `ToolManager` like the agent does; per-agent tool allowlists will give the tester `run_tests` and the reviewer read-only tools, without changes here.
- **MCP**: terminal tools are ordinary `BaseTool`s, so they can be exposed by the agent's own MCP server later, and a remote MCP terminal would sit next to them unchanged.

---

## Git capability

Lets the agent **inspect and change Git repositories** safely: see what changed, save work as commits on a branch, undo its own edits, and keep up to date with remotes. Git is never run directly. Every operation goes through the Tool Manager, is validated, and runs the `git` executable through the terminal provider (no shell, timeout, cancellation).

It was built with the Spec Kit workflow. Spec, plan, research, data model, contracts, tasks and the 7 architecture diagrams are in [specs/001-git-capability/](specs/001-git-capability/), and the design was validated against the Graphify graph of the code before and after implementation ([validation report](specs/001-git-capability/graphify/validation.md)).

| Tool | What it does | Changes the repository |
|---|---|---|
| `git_status` | branch, upstream, ahead/behind, staged / modified / untracked / conflicted files | no |
| `git_diff` | changes of the working copy, the staging area (`staged`), or between commits (`ref`, `target`) | no |
| `git_log` | recent commits (hash, author, date, subject), optionally for a ref, a range or paths | no |
| `git_show` | a commit's changes, or a file's content at a commit (`path`) | no |
| `git_branch` | list branches (`include_remote`), or create one (`create`) | only with `create` |
| `git_checkout` | switch branch, or create and switch (`create`); never overwrites local changes | yes |
| `git_add` | stage changed files under `paths`, or `all`; secret files are never staged | yes |
| `git_commit` | commit the staged changes with a message | yes |
| `git_restore` | unstage (`staged=true`) or discard the changes of named files | yes |
| `git_remote` | remotes and URLs, credentials masked | no |
| `git_fetch` | download from a remote | only `.git` |
| `git_pull` | fast-forward the current branch; refused when histories diverged | yes |
| `git_push` | push the current branch; **only registered when `GIT_ALLOW_PUSH=true`**, never forced | remote |

Every tool takes `repository` (default `.`): the repository folder relative to the workspace. Inspection results are structured data (lists of files, commits, branches), so the agent never parses Git's text output.

### Architecture

```
 ToolManager ─► LocalToolAdapter ─► git tool                   capabilities/git/tool.py
                                    │  AsyncCapabilityTool: GitError ─► readable tool error
                                    ▼
                               GitService                       service.py
                                    │  workflows: find the repository, read its state when
                                    │  needed (secrets, conflicts, staged files), build the
                                    │  git arguments, parse the result
              ┌─────────────────────┼──────────────────────┐
              ▼                     ▼                      ▼
        GitValidator           repository.py          GitProvider            providers/git/
        validator.py           pure parsers:          (base.py / local.py)
        policy + every rule    porcelain v2 status,   global flags, non-interactive
        + final argv guard     log, branches,         environment, hooks switch
        │                      remotes, URL masking         │
        ▼                                                   ▼
  PathValidator (filesystem)                         TerminalProvider       providers/terminal/
  same workspace and secrets                         the ONLY code starting processes
                                                            │
                                                            ▼
                                                   git executable ─► repository
```

| Layer | File | Responsibility |
|---|---|---|
| Tools | `capabilities/git/tool.py` | One class per tool; `git_tools(service, allow_push=...)` |
| Schemas | `capabilities/git/schemas.py` | Requests (the tools' JSON Schemas) and structured results |
| Service | `capabilities/git/service.py` | Business logic and Git workflows. No process or OS code |
| Repository analysis | `capabilities/git/repository.py` | Pure parsers of machine-readable Git output, URL masking |
| Validator | `capabilities/git/validator.py` | `GitPolicy`, `GitOperation`, every rule, the final argument guard |
| Exceptions | `capabilities/git/exceptions.py` | `NotARepository`, `RepositoryOutsideWorkspace`, `InvalidGitArgument`, `GitOperationNotAllowed`, `NothingToCommit`, `ConflictsPresent`, `GitCommandFailed`, `GitNotInstalled`, `GitTimeout` |
| Prompt | `capabilities/git/prompts.py` | How the agent should use Git (status first, branch per task, stage only what belongs to the change...) |
| Assembly | `capabilities/git/capability.py` | terminal provider ─► git provider ─► validator ─► service ─► tools |
| Provider | `providers/git/` | `GitProvider` interface and `LocalGitProvider` (runs git through `TerminalProvider`) |

### Execution flow (example: `git_commit`)

1. The LLM calls `git_commit` with `{"message": "Fix login"}`. `ToolManager` checks the arguments against the input model.
2. `GitService.commit` checks the operation is allowed (not in a read-only workspace) and validates the message.
3. The repository folder is resolved by the filesystem `PathValidator`. `git rev-parse --show-toplevel` gives the repository root, which must be inside the workspace.
4. `git status --porcelain=v2 -z` is parsed. The commit is refused if conflicts remain, if nothing is staged, or if a secret file was staged.
5. The argument vector `commit --cleanup=strip --message=...` goes through the validator's final guard, then `LocalGitProvider` adds its global flags and hands it to `TerminalProvider`.
6. The new commit is read back with `git log -1` and returned as a `CommitResult`. Any refusal or Git failure becomes a readable tool error.

### Security model

- **Validated before execution.** Paths stay inside the workspace (and inside the repository), references and branch names follow Git's rules, remotes must exist, messages are checked. Nothing the agent sends can start with `-`, and paths always come after `--`, so an argument is never read as an option. Patterns are literal (`--literal-pathspecs`).
- **Repository root inside the workspace.** If the workspace is a sub-folder of a bigger repository, operations are refused: they would affect files outside the workspace.
- **No destructive or history-rewriting operation exists.** There is no reset, clean, rebase, amend, stash, tag, config, init, branch or tag deletion, and no force push. `git_checkout` uses `git switch`, which refuses to overwrite local changes. `git_restore` only discards files named one by one (never `.` or a folder). `git_pull` is `--ff-only`. A final guard rejects any argument vector with a forbidden sub-command or flag (`--force`, `--hard`, `-D`, `--delete`, `--mirror`, `--amend`, `--no-verify`, `+refspec`...), so a bug in the service could not run one either.
- **Secrets stay invisible**, like in the filesystem capability:
  - `.env` and keys are hidden from `git_status` (only counted);
  - they are skipped by `git_add` (even for `.` or a folder) and refused when named;
  - `git_commit` refuses when one was staged outside the agent;
  - they are left out of `git_diff` and `git_show`, including old commits.
- **Push is off by default.** The `git_push` tool does not even exist for the agent until `GIT_ALLOW_PUSH=true`. When enabled, it pushes only the current branch, never forced, never deleting, and refuses `GIT_PROTECTED_BRANCHES`.
- **Read-only workspace.** `FS_READ_ONLY=true` refuses every Git operation that changes the repository; inspection still works.
- **No prompts, no leaks.** Git runs without input or terminal (`GIT_TERMINAL_PROMPT=0`, `GIT_EDITOR=true`), so it never waits for a password or an editor. It receives only the allowed host variables: your `HOME` (identity, credential helper) and ssh agent, but not the agent's API keys. Credentials in remote URLs are masked.

**Limits of the model.** Repository hooks are the project's own code and run like its Makefile. Disable them with `GIT_ALLOW_HOOKS=false`. The developer's own Git configuration (identity, credential helpers) applies as usual.

### Examples

```jsonc
// git_status
{"repository": {"repository": ".", "branch": "fix/login", "detached": false, "head": "3f2a9c1", "has_commits": true},
 "upstream": "origin/fix/login", "ahead": 1, "behind": 0,
 "staged": [{"path": "app/auth.py", "change": "modified", "original_path": null}],
 "modified": [], "untracked": ["notes.txt"], "conflicted": [],
 "clean": false, "secrets_hidden": 1, "truncated": false}

// git_add {"all": true}
{"repository": ".", "staged": ["app/auth.py", "notes.txt"], "skipped_secrets": [".env"]}

// git_commit {"message": "Fix login redirect"}  (nothing staged)
"Nothing to commit: no staged changes (use git_add first)"

// git_push  (GIT_ALLOW_PUSH=false)
"Unknown tool 'git_push'. Available: ..."
```

Run the demo on this repository: `uv run python scripts/test_tools.py`.

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

1. **Single agent (Sprints 1–8).** One agent node (`BaseAgent` from `agents/base/`) and, from Sprint 8, a tool node that calls `ToolManager`.
2. **Plan and execute (Sprint 9).** `planner.py` splits a request into steps, and `router.py` loops through the steps and stops when a step fails.
3. **Supervisor and specialists (Sprint 10+).** The supervisor routes work to the architect, coder, tester and reviewer. Each runs as its own subgraph with its own prompt, provider or model and tool set. Agents communicate only through the shared graph state (`app/orchestration/state.py`); each reply is tagged with the agent's name.
4. **Review loops.** Tester and reviewer findings send work back to the coder, with a limit on iterations and human-in-the-loop interrupts before destructive actions.

---

## Roadmap

| Sprint | Goal |
|---|---|
| **0** ✅ | Architecture, configuration, LLM provider abstraction, MCP client wiring, tests |
| **1** ✅ | LangGraph engine: graph state, base agent, agent node, router foundation, end-to-end script |
| **2** ✅ | LLM provider layer: `invoke`/`stream`/`model_info` abstraction, per-provider settings, timeout, factory registry, dependency injection via `app/container.py` |
| **3** ✅ | Tool system: `BaseTool`, registry, manager, local and MCP adapters, MCP transports, server registry and client (`connect` / `list_tools` / `execute_tool`) |
| **4** ✅ | Filesystem capability: provider, validator (workspace confinement, secrets, protection, limits), service, 5 tools, usage prompt |
| **5** ✅ | Code intelligence: parser abstraction, Python parser, analyzer, symbol index, search engine, navigator (definitions, references, hierarchy, dependencies), 10 tools |
| **6** ✅ | Terminal capability: provider (process groups, timeout, cancellation, bounded output), validator (no shell, whitelist/blacklist, subcommands, workspace, environment), executor, service, usage prompt (7 tools; Git moved to its own capability in Sprint 7) |
| **7** ✅ | Git capability (Spec Kit spec + Graphify-validated design): git provider over the terminal provider, validator (workspace, secrets, names, read-only, argument guard), repository parsers, service, 12 tools + `git_push` when enabled |
| **8** | Agent tool loop: tools bound to the LLM, tool node calling `ToolManager`, capability prompts in the system prompt |
| **9** | Planner and router; checkpointing (short-term memory) and resumable sessions |
| **10** | Multi-agent: supervisor plus architect, coder, tester and reviewer subgraphs |
| **11** | RAG over the workspace (embeddings, vector store, code-aware chunking) |
| **12** | Long-term memory, evaluation harness, Docker packaging, observability |

---

## Project layout

```
app/          application package (see Architecture)
tests/        pytest suite: unit/, integration/ (real MCP server), fixtures/
specs/        Spec Kit feature specs (spec, plan, diagrams, tasks, Graphify validation)
scripts/      developer and maintenance scripts
docs/         design notes and ADRs
docker/       container build files
```
