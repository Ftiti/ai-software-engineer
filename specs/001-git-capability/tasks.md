---
description: "Task list for the Git Capability"
---

# Tasks: Git Capability

**Input**: Design documents from `specs/001-git-capability/`: plan.md, spec.md, research.md, data-model.md,
contracts/git-tools.md, quickstart.md

**Tests**: requested by the sprint ("Write tests covering..."), so they are included. Tests run against real
temporary repositories (constitution V).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: user story from spec.md (US1–US5)

## Phase 1: Setup (shared infrastructure)

- [x] T001 Move the process environment helper and `NON_INTERACTIVE_ENV` from `app/capabilities/terminal/executor.py` to `app/providers/terminal/environment.py` (research R9)
- [x] T002 Add `StreamOutput.text()` (decoding + truncation marker) in `app/providers/terminal/base.py`; use it in `app/capabilities/terminal/executor.py` (R9)
- [x] T003 Add `GIT_*` settings and the timeout check in `app/config/settings.py`; add `GIT_` to `tests/conftest.py` prefixes; document them in `.env.example`

## Phase 2: Foundational (blocking prerequisites)

- [x] T004 [P] Create `GitProvider`, `GitInvocation`, `GitOutput` in `app/providers/git/base.py` (data-model.md `GitInvocation.*`, `GitOutput.*`; R2)
- [x] T005 Implement `LocalGitProvider` over `TerminalProvider` in `app/providers/git/local.py`: global flags, sub-command allow-list, environment, hooks switch (R1, R4, R7, R9, R10)
- [x] T006 [P] Create the `GitError` hierarchy in `app/capabilities/git/exceptions.py` (data-model.md Errors)
- [x] T007 [P] Create request and result models in `app/capabilities/git/schemas.py` (data-model.md Results: `Repository.*`, `FileChange.change`, `RepositoryStatus.*`, `LogResult.limit`, `RestoreResult.staged`...)
- [x] T008 Create the pure parsers and URL masking in `app/capabilities/git/repository.py` (R3; data-model.md `Remote.fetch_url` masked)
- [x] T009 Implement `GitPolicy`, `GitOperation`, `GitValidator` in `app/capabilities/git/validator.py` (data-model.md Validation rules; `GitPolicy.*`; R5, R7, R11)
- [x] T010 [P] Tests for the parsers in `tests/unit/git/test_repository.py`
- [x] T011 [P] Tests for the validator (every rule, argv guard) in `tests/unit/git/test_validator.py`
- [x] T012 [P] Tests for the provider in `tests/unit/git/test_local_provider.py`
- [x] T013 Create the repository fixtures (repo factory, bare remote, service) in `tests/unit/git/conftest.py`

**Checkpoint**: the foundation is ready.

## Phase 3: User Story 1 - Understand the state of the repository (P1) 🎯 MVP

**Goal**: detection, status, diff, log and show. **Independent test**: the US1 scenarios on a fixture repository.

- [x] T014 [US1] Implement repository detection (`_target`, root inside the workspace) in `app/capabilities/git/service.py` (FR-001, FR-002)
- [x] T015 [US1] Implement `status`, `diff` (secret filtering), `log`, `show` in `app/capabilities/git/service.py` (FR-003–006; data-model.md `DiffResult.omitted_secrets`, `LogResult.limit`)
- [x] T016 [US1] Tools `git_status`, `git_diff`, `git_log`, `git_show` in `app/capabilities/git/tool.py`
- [x] T017 [US1] Tests in `tests/unit/git/test_service.py` (staged, modified, untracked, conflicted; empty repository; detached HEAD; not a repository; root outside the workspace)

## Phase 4: User Story 2 - Save work as commits (P1)

- [x] T018 [US2] Implement `add` (paths / all minus secrets) and `commit` (nothing staged, conflicts, staged secret) in `app/capabilities/git/service.py` (FR-010, FR-011; data-model.md `AddResult.skipped_secrets`)
- [x] T019 [US2] Tools `git_add`, `git_commit` in `app/capabilities/git/tool.py`
- [x] T020 [US2] Tests in `tests/unit/git/test_service.py`

## Phase 5: User Story 3 - Work on branches (P2)

- [x] T021 [US3] Implement `branches`, `create_branch`, `checkout` (`switch`) in `app/capabilities/git/service.py` (FR-007, FR-009)
- [x] T022 [US3] Tools `git_branch`, `git_checkout` in `app/capabilities/git/tool.py`
- [x] T023 [US3] Tests in `tests/unit/git/test_service.py` (invalid names, a switch that would overwrite)

## Phase 6: User Story 4 - Undo local changes safely (P2)

- [x] T024 [US4] Implement `restore` (staged / worktree; root and directories refused) in `app/capabilities/git/service.py` (FR-012)
- [x] T025 [US4] Tool `git_restore` and tests

## Phase 7: User Story 5 - Synchronise with remotes (P3)

- [x] T026 [US5] Implement `remotes` (masked), `fetch`, `pull --ff-only`, `push` (disabled, protected, detached) in `app/capabilities/git/service.py` (FR-013–015)
- [x] T027 [US5] Tools `git_remote`, `git_fetch`, `git_pull`, `git_push` (registered only when enabled) in `app/capabilities/git/tool.py`
- [x] T028 [US5] Tests with a local bare remote in `tests/unit/git/test_service.py`

## Phase 8: Integration & Polish

- [x] T029 `GIT_PROMPT` in `app/capabilities/git/prompts.py`; assembly in `app/capabilities/git/capability.py`; exports in `app/capabilities/git/__init__.py`
- [x] T030 Register the capability in `app/container.py`
- [x] T031 Q3: remove `RunGitCommandTool`, deny `git` in the terminal (`app/capabilities/terminal/tool.py`, `app/config/settings.py`), update `tests/unit/terminal/*`
- [x] T032 Tool-level tests (registration, push only when enabled, readable errors) in `tests/unit/git/test_tools.py`
- [x] T033 Architecture tests in `tests/unit/test_architecture.py` (Git executed only through `providers/git`; the service does not import the terminal provider)
- [x] T034 Git demos in `scripts/test_tools.py`
- [x] T035 README: Git capability, architecture, security model, execution flow, examples, configuration, roadmap
- [x] T036 Validation: ruff, format, mypy, pytest; `graphify update .` then `validate_design.py --phase implemented`; record the result in `specs/001-git-capability/graphify/validation.md`

## Dependencies

- Setup (T001–T003) → Foundational (T004–T013) → US1 → US2 (needs status) → US3, US4, US5 (independent of
  each other) → Integration (T029–T036).
- Within the foundation: T004 → T005; T006 and T007 → T008 → T009.

## Parallel examples

- Foundational: T004, T006 and T007 together; then T010, T011 and T012 together.
- After US2: US3 (T021–T023), US4 (T024–T025) and US5 (T026–T028) touch different service methods and can
  be developed in parallel.

## Implementation strategy

MVP = Setup + Foundational + US1 + US2 (inspect and commit). Then US3 → US4 → US5, then integration. Each
story's tests must pass before the next story starts.
