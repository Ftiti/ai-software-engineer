# Quickstart: validating the Git capability

## Prerequisites

- Git ≥ 2.30 (`git --version`), uv, the project installed (`uv sync`).
- Graphify installed (`graphify --help`) for the architecture checks.

## 1. Automated checks

```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run pytest -q tests/unit/git          # real temporary repositories + a local bare remote
uv run pytest -q                         # whole suite, including architecture rules
```

Expected: everything passes. `tests/unit/git` covers every User Story scenario in `spec.md` and every
SEC requirement.

## 2. Architecture against the knowledge graph

```bash
graphify update .
$(cat graphify-out/.graphify_python) specs/001-git-capability/graphify/validate_design.py --phase implemented
```

Expected: `OK`. All EXISTING and PLANNED dependencies are found; no FORBIDDEN path (agents → providers,
providers → capabilities, git ↔ terminal capability) exists.

## 3. Manual run on this repository

```bash
uv run python scripts/test_tools.py
```

Expected results for the Git requests:

- `git_status` returns branch `main`, the upstream and the changed files;
- `git_log` with `limit=3` returns 3 commits;
- `git_show` with `path=".env"` is refused (secret);
- `git_diff` with `ref="--output=x"` is refused (invalid reference);
- `git_push` is not in the tool list (push disabled);
- `git_restore` with `paths=["."]` is refused.

## 4. Scenario walk-through (temporary repository)

1. Create a folder in `/tmp` with `git init -b main`, set `FS_WORKSPACE_ROOT` to it, add a file.
2. `git_status` shows the file as untracked; `git_add` with `paths` set to it, then `git_commit` with a
   message, creates the first commit.
3. `git_checkout` with `branch="fix/x"` and `create=true`, edit the file, then `git_add` with `all=true`
   and `git_commit`. `git_log` shows 2 commits.
4. Create `.env` and run `git_add` with `all=true`: `.env` is listed in `skipped_secrets`.
