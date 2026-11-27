# Research: Git Capability

Phase 0 of the plan. Each decision lists what was chosen, why, and what was rejected.

## R1. How Git is executed

- **Decision**: run the `git` executable through the existing `TerminalProvider` (Sprint 6). A new
  `LocalGitProvider` (`app/providers/git/local.py`) builds the argument vector and a `ProcessRequest`, and
  returns the raw output. It never starts processes itself.
- **Rationale**: reuses the audited process code: no shell, own process group, timeout, cancellation and
  bounded output (constitution II and VI). The architecture rule "only `providers/terminal` starts processes"
  stays true.
- **Alternatives rejected**:
  - GitPython / pygit2 (a new dependency, a second execution path, and GitPython itself shells out to `git`);
  - calling the Terminal *capability* (`TerminalService`), which would couple two capabilities and apply the
    terminal's command whitelist to Git;
  - a separate `subprocess` call (duplicated process code).

## R2. Where the provider contract lives (deviation from the sprint prompt)

- **Decision**: the `GitProvider` contract is in `app/providers/git/base.py` and the implementation in
  `app/providers/git/local.py`. There is **no** `app/capabilities/git/provider.py`.
- **Rationale**:
  - a contract in `capabilities/git/provider.py` would make `providers/git/local.py` import from
    `capabilities/`, i.e. a provider depending on a layer above it. That violates constitution I, and the
    Graphify rule `app/providers -/-> app/capabilities` checks it.
  - the Filesystem and Terminal capabilities both keep their contract in `providers/<name>/base.py`, so
    this keeps the pattern consistent.
- **Alternative rejected**: a ports-and-adapters layout with the port in the capability. It is valid in
  general, but inconsistent with the rest of this code base.
- **Needs owner approval** (it deviates from the expected file list).

## R3. Machine-readable Git output

- **Decision**: one format per command, chosen to be stable across Git versions:

  | Command | Format |
  |---|---|
  | status | `git status --porcelain=v2 --branch -z --untracked-files=all` |
  | log | `git log -z --format=%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%b` |
  | branches | `git for-each-ref --format=...%00...` |
  | remotes | `git remote -v` |
  | file lists | `--name-only -z` |

  Parsing lives in `capabilities/git/repository.py` as pure functions.
- **Rationale**: porcelain v2 is the documented, stable script interface, and `-z` makes paths with spaces,
  quotes or unicode exact. Pure parsers can be unit-tested without Git.
- **Alternative rejected**: parsing human output, which depends on the locale and the Git version.

## R4. Arguments never become options or patterns (SEC-003)

- **Decision**:
  - every call passes the global flags `--no-pager --literal-pathspecs -c color.ui=never -c core.quotepath=off`;
  - paths always come after `--`;
  - references are validated so they never start with `-`;
  - the service builds every argument vector itself. The agent never supplies raw Git arguments.
- **Rationale**: `--literal-pathspecs` makes `*` or `:(glob)` literal file names, and `--` ends option
  parsing. Leading-dash references are rejected because they cannot be placed after `--`.

## R5. Workspace confinement

- **Decision**:
  - the repository path given by the agent is resolved by the Filesystem `PathValidator` (inside the
    workspace, not secret, existing directory);
  - `git rev-parse --show-toplevel` gives the repository root, which must itself be inside the workspace;
  - every path argument is resolved relative to the repository root through `PathValidator`.
- **Rationale**: if the root were outside the workspace (the workspace being a sub-folder of a bigger repo),
  a status, an add or a checkout would touch files outside the workspace. Reusing `PathValidator` gives one
  definition of "workspace" and "secret" for every capability.

## R6. Secret protection (SEC-004)

- **Decision**:
  - **add**: explicit secret paths are refused; "add all" stages the changed files from `status` minus the
    secrets, and reports the skipped secrets.
  - **commit**: refused if a secret is staged (it may have been staged outside the agent).
  - **diff and show**: list the affected files first (`--name-only -z`), drop the secrets, then diff or show
    only the remaining files. `show <ref>:<path>` refuses secret paths.
- **Rationale**: these are the operations that can expose a secret file's content or put it in history.

## R7. Which Git sub-commands are used, and which never are (SEC-002)

- **Decision**: the validator's final guard (`GitValidator.guard`, run on every argument vector
  just before the provider) accepts only an allow-list of sub-commands:
  `status diff log show branch switch add commit restore remote fetch pull push rev-parse symbolic-ref for-each-ref`.
  - the guard also rejects dangerous flags anywhere before `--`: `--force*`, `-f`, `--hard`, `--delete`,
    `-d`, `-D`, `-M`, `-C`, `--mirror`, `--amend`, `--no-verify`, `--prune`, `--exec*`, `--upload-pack*`,
    `--receive-pack*` and `-c`. Push refspecs starting with `+` or `:` are rejected too.
  - the provider stays free of rules, like the filesystem and terminal providers (amended during
    implementation; the first draft placed the allow-list in the provider).
  - never used: `reset`, `clean`, `rebase`, `filter-branch`, `gc`, `prune`, `init`, `config`, `rm`, `tag`,
    `stash`, `submodule`, `worktree`, `checkout` (replaced by `switch` and `restore`, which cannot discard
    by accident).
- **Rationale**: defence in depth. The service never builds these arguments, and the guard proves it (and
  is tested).
- `git_checkout` uses `git switch` / `git switch --create`: it refuses to overwrite local changes and never forces.

## R8. Remote operations

- **Decision**:
  - **fetch**: `git fetch <remote>`. The remote must exist in `git remote`.
  - **pull**: `git pull --ff-only --no-rebase [<remote> <branch>]`. A diverged history is a Git error,
    reported as-is.
  - **push**: `git push [--set-upstream] <remote> <branch>`, where `<branch>` is the current branch. It is
    refused when push is disabled, on a detached HEAD, or when the branch is in `GIT_PROTECTED_BRANCHES`.
  - remote operations use `GIT_NETWORK_TIMEOUT` (default 50 s). Local operations use `GIT_TIMEOUT`
    (default 30 s). Both must stay below `TOOL_TIMEOUT` (checked at startup, as for the terminal).
- **Rationale**: fast-forward-only pulls never create merge commits or conflicts behind the agent's back.
  Push is the only remote write, and it is narrow and off by default.

## R9. Non-interactive environment and credentials (NFR-005, SEC-006)

- **Decision**:
  - the environment is the inherited allow-list (`TERMINAL_INHERITED_ENV` plus `SSH_AUTH_SOCK`), plus
    `GIT_TERMINAL_PROMPT=0`, `GIT_EDITOR=true`, `GIT_PAGER=cat` and `NO_COLOR=1`;
  - stdin is empty and the process has no controlling terminal (own session), so neither Git nor ssh can
    prompt;
  - API keys are not passed;
  - remote URLs are masked: `https://user:token@host/…` becomes `https://***@host/…`.
  - the helper that builds the environment moves from `capabilities/terminal/executor.py` to
    `providers/terminal/environment.py`, shared by both capabilities. `StreamOutput` gains a
    `text()` method (decoding + truncation marker), shared too.
- **Rationale**: the developer's own Git identity and credential helper (in `HOME`) keep working, while
  nothing waits for input and no secret leaks.

## R10. Repository hooks

- **Decision**: hooks run by default, like the project's Makefile or npm scripts in the terminal.
  `GIT_ALLOW_HOOKS=false` disables them (`-c core.hooksPath=/dev/null`). `--no-verify` is never used.
- **Rationale**: projects rely on pre-commit hooks (lint, tests), and the trust level is the same as the
  Terminal's `make`. This is documented as a limit of the model.

## R11. Read-only workspace (SEC-005)

- **Decision**: when `FS_READ_ONLY=true`, every mutating operation (`switch`, `branch` create, `add`,
  `commit`, `restore`, `pull`, `push`) is refused by the Git validator. `fetch` only updates `.git` and is
  allowed.
- **Rationale**: one switch for "the agent must not change the project", consistent across capabilities.

## R12. Git through the Terminal (spec Q3)

- **Decision (proposed)**: remove `run_git_command`, move `git` from the terminal allow-list to the deny-list,
  and drop the terminal's `git` sub-command defaults.
- **Rationale**: the sprint requires every Git operation to go through the Git capability. Two paths to Git
  would mean two security models.

## R13. Tool registration of push

- **Decision**: `git_push` is registered only when `GIT_ALLOW_PUSH=true`; the validator refuses push anyway
  when it is disabled.
- **Rationale**: a tool that can only fail wastes the model's context and invites attempts to work around it.
