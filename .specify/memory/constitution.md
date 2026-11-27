<!--
Sync Impact Report
- Version change: template → 1.0.0 (first ratified version)
- Principles defined: I. Layered Architecture & Composition Root, II. Operating-System Isolation,
  III. Tool System as the Only Gateway, IV. Secure by Default, V. Test-Backed Quality Gates,
  VI. Simplicity & Reuse
- Added sections: Technology Constraints, Development Workflow, Governance
- Removed sections: none
- Templates: plan-template.md "Constitution Check" gates map to principles I–VI (no file change needed)
- Deferred TODOs: none
-->

# AI Software Engineer Agent Constitution

## Core Principles

### I. Layered Architecture & Composition Root

- Dependencies MUST point inward: orchestration and agents use the tool system (`app/tools`);
  capabilities implement the tool system's contracts and use providers; providers depend on
  nothing above them. The tool system MUST NOT import capabilities, and agents MUST NOT import
  capabilities or providers other than `providers/llm`.
- Objects MUST receive their collaborators through their constructor (dependency injection).
  Only `app/container.py` (the composition root) creates and wires application objects.
- A capability MUST be a self-contained package (`app/capabilities/<name>/`) exposing tools and a
  usage prompt through `Capability`; adding one MUST only add a line to the composition root.

Rationale: swapping a provider or adding a capability must never ripple through the code base.

### II. Operating-System Isolation

- Only `app/providers/` may touch the operating system: `providers/filesystem/` for files,
  `providers/terminal/` for processes, `providers/llm/` for vendor SDKs.
- Services hold business logic only: no `os`, `subprocess`, `shutil` or vendor imports.
- These rules MUST be enforced by architecture tests (`tests/unit/test_architecture.py`).

Rationale: one audited place per kind of side effect; everything else is testable without the OS.

### III. Tool System as the Only Gateway

- Agents MUST act on the world only through `ToolManager`. They never call services, providers or
  executables directly.
- Every tool has a typed Pydantic input model (its JSON Schema is what the LLM reads) and returns
  plain data. Expected failures MUST become readable `ToolResult` errors, never crashes.
- Local and MCP tools MUST stay interchangeable behind the `ToolAdapter` interface.

Rationale: one entry point gives one place for validation, timeouts, logging and future permissions.

### IV. Secure by Default (NON-NEGOTIABLE)

- Every request coming from an LLM MUST be validated before any side effect.
- Work MUST stay inside the configured workspace (`FS_WORKSPACE_ROOT`); secrets matching
  `FS_DENIED_PATTERNS` MUST stay invisible to every capability; `.git` is never modified as files.
- Defaults MUST be the least dangerous option: destructive or remote-writing operations are
  disabled or refused unless explicitly enabled by configuration.
- Refusals MUST explain the rule to the LLM. Security limits that are not a sandbox MUST be
  documented as such.

Rationale: the agent executes text produced by a model; mistakes must be stopped, not trusted.

### V. Test-Backed Quality Gates

- Every feature ships with unit tests; behaviour that crosses the OS boundary is tested against the
  real thing in a temporary directory (real files, real processes, real repositories).
- No test contacts a real LLM or the network.
- `ruff check`, `ruff format --check`, `mypy --strict` and `pytest` MUST pass before a commit.

Rationale: a beginner-friendly code base stays trustworthy only if every claim is checked.

### VI. Simplicity & Reuse

- Reuse existing components (validators, providers, base tools, settings patterns) before writing
  new ones; duplicated logic MUST be extracted to the lowest shared layer.
- Follow SOLID; prefer small classes with one responsibility and explicit names.
- No speculative features: build what the sprint specifies, document what is deferred.

Rationale: every line has to be explainable to a beginner reading the project.

## Technology Constraints

- Python 3.12 managed with uv; LangGraph, LangChain, Ollama (default local model), MCP.
- Configuration comes only from environment variables / `.env` through `app/config/settings.py`
  (pydantic-settings); `.env` and `mcp_servers.json` are never committed.
- Supported platform: POSIX (Linux, macOS).

## Development Workflow

- Work is organised in sprints. Each sprint follows Spec Kit: specify → plan (with architecture
  diagrams validated against the Graphify knowledge graph) → review/approval → tasks → implement.
- The README is updated in the same sprint (architecture, security model, configuration, roadmap).
- Commits are made only on request, with short one-line messages; secrets are never committed.

## Governance

- This constitution supersedes ad-hoc practices. Specs and plans MUST include a Constitution Check;
  a violation MUST be justified in the plan's Complexity Tracking table or the design changed.
- Amendments are proposed in a sprint, approved by the project owner and versioned semantically
  (MAJOR: principle removed/redefined, MINOR: principle or section added, PATCH: wording).
- `README.md` is the runtime guidance for contributors.

**Version**: 1.0.0 | **Ratified**: 2026-11-27 | **Last Amended**: 2026-11-27
