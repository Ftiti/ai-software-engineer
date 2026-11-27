# Implementation Plan: Git Capability

**Branch**: `001-git-capability` (work on `main`) | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-git-capability/spec.md`

## Summary

A fourth capability, `app/capabilities/git/`, exposes 12 Git tools, plus `git_push` when it is enabled,
through the existing Tool System.

- **Layers**: tools → `GitService` (workflows) → `GitValidator` (rules, reusing the filesystem
  `PathValidator`) → `GitProvider` (`app/providers/git/`).
- **Execution**: the provider runs the `git` executable through the Terminal's `TerminalProvider`. No new
  process code, so no shell, plus the existing timeouts, cancellation and output limits.
- **Output**: machine-readable Git formats are parsed into structured results (`repository.py`).
- **Safety**: dangerous operations are never built, and a final argument guard proves it. Secrets are
  filtered from add, commit, diff and show. Push is off by default.
- **Terminal**: if Q3 is accepted, Git is removed from the Terminal capability.

Design decisions and their alternatives: [research.md](research.md). Diagrams: [diagrams.md](diagrams.md),
validated in [graphify/validation.md](graphify/validation.md).

## Technical Context

**Language/Version**: Python 3.12 (uv), `mypy --strict`

**Primary Dependencies**: none new. Uses pydantic and pydantic-settings, the Git executable ≥ 2.30 and the
existing `TerminalProvider`.

**Storage**: N/A (Git repositories on disk)

**Testing**: pytest + pytest-asyncio against real temporary repositories (`git init` in `tmp_path`) and a
local bare repository as the remote; no network.

**Target Platform**: POSIX (Linux, macOS)

**Project Type**: single Python project (library + agent)

**Performance Goals**: local inspection < 2 s on 10,000 files (one Git process per operation, plus one
`rev-parse` and at most one `status` / listing for pre-checks)

**Constraints**: `GIT_TIMEOUT` (30 s) and `GIT_NETWORK_TIMEOUT` (50 s) < `TOOL_TIMEOUT` (60 s), checked at
startup; text output ≤ `GIT_MAX_OUTPUT_BYTES` (64 KB); log ≤ `GIT_MAX_LOG_ENTRIES` (100)

**Scale/Scope**: 13 tools; about 10 source files, 6 test files

## Constitution Check

*Gate before Phase 0 and re-checked after Phase 1 design: **PASS** (one justified deviation from the
sprint prompt, none from the constitution).*

| Principle | How the design complies | Status |
|---|---|---|
| I. Layered architecture & composition root | capability package + one line in `container.py`; provider contract in `providers/git/base.py` so providers never import capabilities (R2); Graphify FORBIDDEN rules | PASS |
| II. OS isolation | Git runs through `TerminalProvider` (R1): `providers/terminal` stays the only process starter; service has no `os`/`subprocess`; new architecture test | PASS |
| III. Tool system as the only gateway | tools extend `AsyncCapabilityTool`; errors become `ToolResult` errors; agents → providers path absent (Graphify) | PASS |
| IV. Secure by default | validate-before-execute, workspace root check, secrets filtered, push off, read-only respected, argv guard (R4–R11) | PASS |
| V. Test-backed quality gates | real repositories in `tmp_path`, local bare remote, no network; ruff/format/mypy/pytest | PASS |
| VI. Simplicity & reuse | reuses `TerminalProvider`, `PathValidator`, `AsyncCapabilityTool`, settings/timeout validator; environment helper and output decoding moved down to `providers/terminal` and shared (R9); Git removed from the Terminal (R12) | PASS |

## Project Structure

### Documentation (this feature)

```text
specs/001-git-capability/
├── spec.md                 # what and why (Spec Kit /speckit-specify)
├── checklists/requirements.md
├── plan.md                 # this file
├── research.md             # decisions R1–R13
├── data-model.md           # entities, validation rules, errors
├── contracts/git-tools.md  # tool inputs/outputs as seen by the LLM
├── quickstart.md           # how to validate end to end
├── diagrams.md             # 7 design diagrams + Graphify as-is diagram
├── graphify/
│   ├── validate_design.py  # checks the design against graphify-out/graph.json
│   └── validation.md       # design-phase report
└── tasks.md                # next step (/speckit-tasks), after approval
```

### Source Code (repository root)

```text
app/
├── capabilities/
│   ├── base.py                      # unchanged (AsyncCapabilityTool reused)
│   ├── git/                         # NEW
│   │   ├── __init__.py
│   │   ├── exceptions.py            # GitError hierarchy
│   │   ├── schemas.py               # request models (tool inputs) + result models
│   │   ├── repository.py            # pure parsers (status v2, log, branches, remotes) + URL masking
│   │   ├── validator.py             # GitPolicy, GitOperation, GitValidator (+ argv guard)
│   │   ├── service.py               # GitService: repository detection and workflows
│   │   ├── tool.py                  # 13 tool classes, git_tools(service, policy)
│   │   ├── prompts.py               # GIT_PROMPT
│   │   └── capability.py            # build_git_service / build_git_capability
│   └── terminal/
│       ├── executor.py              # CHANGED: uses the shared environment + StreamOutput.text()
│       └── tool.py                  # CHANGED (Q3): RunGitCommandTool removed
├── providers/
│   ├── git/                         # NEW
│   │   ├── __init__.py
│   │   ├── base.py                  # GitProvider, GitInvocation, GitOutput (R2)
│   │   └── local.py                 # LocalGitProvider(TerminalProvider)
│   └── terminal/
│       ├── base.py                  # CHANGED: StreamOutput.text()
│       └── environment.py           # NEW (moved): process_environment(), NON_INTERACTIVE_ENV
├── config/settings.py               # CHANGED: GIT_* settings + timeout check; Q3: git out of terminal lists
└── container.py                     # CHANGED: + git capability

tests/unit/git/                      # NEW
├── conftest.py                      # repo factory (git init -b main, identity), bare remote, service
├── test_repository.py               # parsers on recorded Git output (no Git needed)
├── test_validator.py                # paths, refs, branch names, remotes, messages, policy, argv guard
├── test_local_provider.py           # global flags, env, hooks switch, not installed
├── test_service.py                  # User Stories 1–5 on real repositories
└── test_tools.py                    # registration, push only when enabled, errors via ToolManager
tests/unit/test_architecture.py      # CHANGED: git executed only via providers/git → TerminalProvider
tests/unit/terminal/*                # CHANGED (Q3): git expectations removed
```

**Structure Decision**: the single-project layout already used by every capability. The file list matches
the sprint prompt except `capabilities/git/provider.py`, see Complexity Tracking.

## Implementation Phases (input for /speckit-tasks)

1. **Shared plumbing**: move the environment helper to `providers/terminal/environment.py`, add
   `StreamOutput.text()`, adapt the terminal executor. The existing tests must stay green.
2. **Provider**: `providers/git/base.py` + `local.py`, with tests.
3. **Core**: `exceptions.py`, `schemas.py`, `repository.py` (parsers tested on recorded output), then
   `validator.py` (tested exhaustively).
4. **Service and tools**, by priority:
   - P1: detection, status, diff, log, show, add, commit;
   - P2: branch, checkout, restore;
   - P3: remote, fetch, pull, push.
5. **Integration**: settings, `capability.py`, `container.py`, prompt, Q3 terminal changes, architecture
   tests, `scripts/test_tools.py` demos.
6. **Validation**: full suite, `validate_design.py --phase implemented` after `graphify update .`, README.

## Test Plan (maps to the spec)

| Spec item | Test |
|---|---|
| US1 / FR-001–008 | `test_service.py::status/diff/log/show/branches/remotes` (staged + modified + untracked + conflict fixture; empty repo; detached HEAD; not a repository) |
| US2 / FR-010–011 | add by path, add all skips `.env`, commit, nothing to commit, conflicts block commit, staged secret blocks commit |
| US3 / FR-007, 009 | create branch, switch, switch refused when it would overwrite, invalid names |
| US4 / FR-012 | unstage keeps changes; discard restores content; root and directory refused |
| US5 / FR-013–015 | bare remote: remotes masked, fetch, ff pull, diverged pull refused, push disabled (no tool + refusal), push enabled, protected branch, detached push refused |
| SEC-001–007 | `test_validator.py` (every rule) + read-only workspace + repository root outside workspace + `--output=x` ref + `*` literal path + env has no API key |
| ERR-001–003 | messages asserted in `test_tools.py` via `ToolManager` (never a crash) |
| AC-4 | architecture test + Graphify `--phase implemented` |

## Complexity Tracking

| Deviation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| No `capabilities/git/provider.py`; the provider contract lives in `providers/git/base.py` (R2) | keeps providers independent of capabilities (constitution I) and consistent with the filesystem and terminal | the prompt's layout would make `providers/git/local.py` import from `capabilities/`, a layering violation that Graphify's rule detects |
| Git removed from the Terminal capability (Q3) | the sprint requires every Git operation to go through the Git capability | keeping `run_git_command` leaves a second, differently secured path to Git |
