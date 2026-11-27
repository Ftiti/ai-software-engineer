# Feature Specification: Git Capability

**Feature Branch**: `001-git-capability` (work happens on `main`; the spec directory name is independent)

**Created**: 2026-11-27

**Status**: Approved (2026-11-27)

**Input**: User description: "Sprint 7 — Git Capability. Implement a production-ready Git Capability so the
agent can inspect and manipulate Git repositories through the existing Tool System, never executing Git
directly. Tools: git_status, git_diff, git_log, git_branch, git_checkout, git_add, git_commit, git_restore,
git_show, git_remote, git_fetch, git_pull, git_push (optional, disabled by default). Support repository
detection, current branch, staged / modified / untracked files and merge conflicts. Prevent execution outside
the workspace, dangerous repository operations, forced push, destructive reset and deleting repositories.
Every operation must be validated before execution."

## User Scenarios & Testing *(mandatory)*

The "user" is the developer who runs the agent; the agent acts on their behalf through tools.

### User Story 1 - Understand the state of the repository (Priority: P1)

Before changing anything, the agent needs to know where it stands: is the project a Git repository, which
branch is checked out, which files are staged, modified, untracked or in conflict, and what changed
recently.

**Why this priority**: every other Git action depends on this picture; it is also completely read-only, so
it delivers value with no risk.

**Independent Test**: on a repository with one staged, one modified, one untracked and one conflicting file,
ask for the status, a diff, the log and a commit's details, and check every answer against the repository.

**Acceptance Scenarios**:

1. **Given** a repository on branch `feature`, 2 commits ahead of its upstream, **When** the agent asks for
   the status, **Then** it receives the branch name, the upstream, "2 ahead / 0 behind", and the files
   grouped as staged, modified, untracked and conflicted.
2. **Given** a modified file, **When** the agent asks for the diff of that file, **Then** it receives the
   changes of that file only; with "staged", only the staged changes.
3. **Given** a history of 30 commits, **When** the agent asks for the last 5, **Then** it receives 5 entries
   with identifier, author, date and subject, most recent first.
4. **Given** a commit identifier, **When** the agent asks to show it, **Then** it receives its metadata and
   changes; with a file path, the content of that file at that commit.
5. **Given** a folder that is not a repository, **When** the agent asks for the status, **Then** it receives
   a clear "not a Git repository" error.

---

### User Story 2 - Save work as commits (Priority: P1)

After editing files, the agent stages the relevant files and records a commit with a meaningful message.

**Why this priority**: committing is the main reason an engineering agent needs Git; together with Story 1
it forms the minimum viable capability.

**Independent Test**: modify two files, stage one, commit it, and check that the new commit contains exactly
that file with the given message while the other file is still modified.

**Acceptance Scenarios**:

1. **Given** two modified files, **When** the agent stages one by path, **Then** only that file is staged.
2. **Given** staged changes, **When** the agent commits with a message, **Then** a commit is created on the
   current branch and its identifier, branch and file count are returned.
3. **Given** nothing is staged, **When** the agent commits, **Then** it is told there is nothing to commit.
4. **Given** a secret file (e.g. `.env`) is modified, **When** the agent stages "all changes", **Then** the
   secret is skipped and reported as skipped; **When** the agent stages it explicitly, **Then** it is refused.
5. **Given** unresolved merge conflicts, **When** the agent commits, **Then** it is refused with the list of
   conflicting files.

---

### User Story 3 - Work on branches (Priority: P2)

The agent lists branches, creates a branch for a task and switches between branches.

**Why this priority**: isolating work on a branch is good practice but not required for a first commit.

**Independent Test**: list branches, create `fix/login` from `main`, switch to it, switch back.

**Acceptance Scenarios**:

1. **Given** branches `main` and `dev`, **When** the agent lists branches, **Then** it receives both, with
   the current one marked; remote branches are included only when asked.
2. **Given** a valid new name, **When** the agent creates a branch (optionally from a start point),
   **Then** the branch exists; with "switch", it is also checked out.
3. **Given** uncommitted changes that a switch would overwrite, **When** the agent checks out another
   branch, **Then** the switch is refused and the changes are kept.
4. **Given** an invalid branch name (`-x`, `a..b`, `bad name`), **When** the agent creates it, **Then** it
   is refused with the naming rule that was broken.

---

### User Story 4 - Undo local changes safely (Priority: P2)

The agent unstages a file it staged by mistake, or discards its own edits to specific files.

**Why this priority**: lets the agent recover from its own mistakes without destructive whole-repository
commands.

**Independent Test**: modify and stage a file, unstage it (changes kept), then discard it (file back to its
committed content); other files untouched.

**Acceptance Scenarios**:

1. **Given** a staged file, **When** the agent restores it from the staging area, **Then** it is unstaged and
   its working-copy changes are kept.
2. **Given** a modified file, **When** the agent discards its changes, **Then** the file returns to its last
   committed content and no other file changes.
3. **Given** a request without explicit paths, or for the whole repository, **When** the agent restores,
   **Then** it is refused.

---

### User Story 5 - Synchronise with remotes (Priority: P3)

The agent lists remotes, fetches, fast-forwards the current branch and — only when the developer enabled it —
pushes the current branch.

**Why this priority**: useful for keeping up to date, but remote writes are the riskiest operations and are
off by default.

**Independent Test**: with a local bare repository as `origin`, list remotes, fetch, pull a new upstream
commit, and verify push is refused by default and works once enabled.

**Acceptance Scenarios**:

1. **Given** a remote whose URL embeds credentials, **When** the agent lists remotes, **Then** names and URLs
   are returned with the credentials masked.
2. **Given** new commits upstream, **When** the agent fetches then pulls, **Then** the current branch is
   fast-forwarded; **Given** diverged branches, **Then** the pull is refused (no automatic merge or rebase).
3. **Given** push is disabled (default), **Then** no push tool is offered to the agent, and a push request
   reaching the capability anyway is refused with how to enable it.
4. **Given** push is enabled, **When** the agent pushes the current branch, **Then** it is pushed without
   force; a force push, deleting a remote branch or pushing a protected branch is refused.

---

### Edge Cases

- The workspace is a sub-folder of a larger repository whose root is outside the workspace → refused
  (an operation would affect files outside the workspace).
- A nested repository inside the workspace is targeted with an explicit repository path → allowed if inside.
- Empty repository (no commit yet): status works, log is empty, commit creates the first commit, diff against
  HEAD is not possible and is reported clearly.
- Detached HEAD: status reports "detached" with the commit; a commit is allowed and its result says the HEAD
  is detached; push of a detached HEAD is refused (no branch to push).
- Paths with spaces, unicode or leading dashes are handled literally (never read as options or patterns).
- Path patterns (`*`, `:(glob)`) are treated as literal file names.
- Very large diffs or logs are truncated with a visible marker; log entries are capped.
- Git not installed → clear error; repository locked by another Git process → Git's message is returned.
- Commit identity (name/email) not configured → clear error telling the developer how to set it.
- Remote unreachable or slow → the operation stops at its timeout and reports it; no hanging prompts for
  credentials.
- Merge in progress (after a conflicting pull done outside the agent) → status lists conflicts; commit
  refused until resolved.

## Requirements *(mandatory)*

### Functional Requirements

**Repository detection**

- **FR-001**: The system MUST detect whether a given folder (default: the workspace root) belongs to a Git
  repository and return its root, current branch (or detached commit) and whether it has commits.
- **FR-002**: The system MUST refuse any operation whose repository root is outside the workspace.

**Inspection (read-only)**

- **FR-003**: `git_status` MUST return branch, upstream, ahead/behind counts and files grouped as staged,
  modified (not staged), untracked and conflicted, each with its change type (added, modified, deleted,
  renamed).
- **FR-004**: `git_diff` MUST return the changes of the working copy, of the staging area, or between two
  references, optionally limited to given paths, optionally as a per-file summary only.
- **FR-005**: `git_log` MUST return the most recent commits (default 20, maximum configurable, default 100)
  of the current branch or a given reference/range, optionally limited to given paths.
- **FR-006**: `git_show` MUST return a commit's metadata and changes, or the content of a file at a commit.
- **FR-007**: `git_branch` MUST list local branches (and remote-tracking branches on request) with the
  current branch marked, and MUST be able to create a branch from the current HEAD or a start point.
- **FR-008**: `git_remote` MUST list remotes with their fetch/push URLs, credentials masked.

**Local changes**

- **FR-009**: `git_checkout` MUST switch to an existing branch, or create and switch to a new one; it MUST
  never discard local changes.
- **FR-010**: `git_add` MUST stage given paths, or all changes when asked; secret files MUST never be staged.
- **FR-011**: `git_commit` MUST create a commit from the staged changes with a required non-empty message;
  it MUST refuse when nothing is staged, when conflicts are unresolved, or when a secret file is staged.
- **FR-012**: `git_restore` MUST unstage given paths, and discard working-copy changes of explicitly named file paths;
  it MUST require explicit paths and refuse the repository root.

**Remotes**

- **FR-013**: `git_fetch` MUST update remote-tracking branches from a configured remote (default: the
  upstream's remote, else `origin`).
- **FR-014**: `git_pull` MUST only fast-forward the current branch; diverged history MUST be reported, not
  merged or rebased.
- **FR-015**: `git_push` MUST be disabled unless the developer enables it; when enabled it MUST push only
  branches, never with force, never deleting remote refs, never to a branch listed as protected (none by default).

**Integration**

- **FR-016**: All operations MUST be exposed as tools through the existing Tool System and registered
  automatically; Git MUST NOT be reachable through any other tool (the Terminal capability no longer runs Git).
- **FR-017**: Each tool MUST accept an optional repository path relative to the workspace.

### Non-Functional Requirements

- **NFR-001 (Reuse)**: process execution, timeouts, cancellation and output limits MUST reuse the Terminal
  capability's process provider; workspace and secret rules MUST reuse the Filesystem validator.
- **NFR-002 (Responsiveness)**: local operations (status, diff, log, branch, add, commit) on a repository of
  10,000 files MUST answer within 2 seconds; every operation MUST stop at a configurable timeout lower than
  the tool timeout.
- **NFR-003 (Bounded output)**: no answer may exceed the configured output size; truncation is visible.
- **NFR-004 (Structured results)**: inspection results MUST be structured data (fields, lists), not raw text
  only, so the agent does not parse Git output.
- **NFR-005 (Non-interactive)**: no operation may wait for input (editor, pager, credentials prompt).
- **NFR-006 (Quality)**: type-checked, linted, unit-tested against real temporary repositories (including a
  local bare remote); no network access in tests.
- **NFR-007 (Portability)**: works with Git ≥ 2.30 on POSIX systems.

### Security Requirements

- **SEC-001**: Every operation MUST be validated before Git runs: repository inside the workspace, paths
  inside the workspace and not secret, references and branch names well-formed, operation permitted.
- **SEC-002**: The following MUST be impossible through the capability: force push (any form), deleting
  remote refs, `reset` (any mode), `clean`, rebase, history rewriting (amend, filter), deleting branches or
  tags, changing Git configuration, deleting or re-initialising the repository.
- **SEC-003**: Arguments from the agent MUST never be interpreted as Git options or path patterns.
- **SEC-004**: Secrets (`FS_DENIED_PATTERNS`) MUST never be staged, committed, shown (including from past
  commits) or diffed.
- **SEC-005**: When the workspace is read-only, every modifying operation (checkout, add, commit, restore,
  branch creation, pull, push) MUST be refused; inspection still works.
- **SEC-006**: Credentials MUST never appear in results (remote URLs masked) and the agent's own secrets
  (API keys) MUST NOT be passed to Git.
- **SEC-007**: Push is disabled by default; enabling it is an explicit configuration choice.

### Error Handling

- **ERR-001**: Every refusal or failure MUST be a readable tool error naming the cause and, when possible,
  the fix (e.g. "Push is disabled. Set GIT_ALLOW_PUSH=true to enable it.").
- **ERR-002**: Error categories: not a repository; repository outside workspace; invalid argument (path,
  reference, branch name, message); operation not allowed (policy); nothing to commit; conflicts present;
  Git failed (with Git's own message, e.g. checkout would overwrite changes, diverged pull, unknown
  revision); Git not installed; timeout.
- **ERR-003**: A failed Git operation MUST leave the repository as Git leaves it (no partial follow-up
  actions by the capability).

### Key Entities

- **Repository**: root folder (relative to the workspace), current branch or detached commit, whether it
  has commits.
- **Repository status**: branch, upstream, ahead/behind, file changes grouped by state, conflict list,
  "clean" flag.
- **File change**: path, change type, original path for renames.
- **Commit**: identifier (full and short), author, date, subject, body.
- **Branch**: name, current flag, remote flag, upstream, last commit.
- **Remote**: name, fetch URL, push URL (masked).
- **Git policy**: push allowed, protected branches, timeouts, output and log limits.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The agent can go from "edited files" to "committed on a new branch" using only the Git tools,
  in at most 5 tool calls (status, branch create+switch, add, commit, status).
- **SC-002**: 100% of the forbidden operations listed in SEC-002 are refused in the test suite.
- **SC-003**: 0 secret files staged, committed or shown in the test suite, including "stage all".
- **SC-004**: Local inspection answers in under 2 seconds on a 10,000-file repository.
- **SC-005**: Every error in the test suite is a readable message, never an internal crash.
- **SC-006**: No existing tool, test or architecture rule has to change except the removal of Git from the
  Terminal capability (if Q3 is accepted).

## Constraints

- Must plug into the existing Tool System, capability pattern and composition root (constitution I, III).
- Must not start processes itself: Git runs through the existing process provider (constitution II).
- Must not duplicate the Terminal or Filesystem logic (constitution VI).
- No merge, rebase, stash, tag, submodule or worktree management in this sprint.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Agent discards the developer's uncommitted work | High | explicit paths only, no reset/clean, checkout never forces, Q2 |
| Secret committed or pushed | High | secret filter on add, commit and show; push off by default |
| Repository hooks run project code on commit/checkout | Medium | same trust level as `make`/`npm run` in the Terminal; documented, configurable |
| Credentials prompts hang the agent | Medium | non-interactive environment, timeouts |
| Credentials leak through remote URLs | Medium | URL masking |
| Git output format differences across versions | Low | machine-readable formats (porcelain v2, custom log format) |
| Overlap with the Terminal's `run_git_command` | Low | Q3: remove Git from the Terminal |

## Acceptance Criteria

- AC-1: The 12 tools are registered automatically and listed by the tool manager; `git_push` is registered
  only when push is enabled (an always-failing tool would only invite the model to try it), and the policy
  still refuses push when disabled.
- AC-2: User Stories 1–5 acceptance scenarios pass as automated tests on real temporary repositories.
- AC-3: Every SEC requirement has at least one test proving the refusal.
- AC-4: Architecture tests prove Git is executed only through the process provider and the agent cannot
  reach Git except through the Tool Manager.
- AC-5: README documents the capability, architecture, security model, execution flow and examples.
- AC-6: Existing tests keep passing; ruff, format and mypy strict pass.

## Assumptions

- Git ≥ 2.30 is installed on the developer's machine; the developer's Git identity and credential helpers
  (from their home configuration) are used as-is.
- Repository hooks are honoured by default (they belong to the project, like its Makefile); a setting can
  disable them.
- Branch protection for commits is not needed by default for a solo developer; only push protection is
  configurable.
- Merge/rebase conflict *resolution* is done by editing files with the Filesystem tools then `git_add` +
  `git_commit`; the capability only detects and reports conflicts.

## Clarifications

### Session 2026-11-27

- Q1: Which branches are protected from push by default? → A: none by default; `GIT_PROTECTED_BRANCHES`
  is a configurable list, and push itself is disabled by default.
- Q2: May `git_restore` discard working-copy changes? → A: yes, for explicitly named file paths only (never
  the repository root or a directory).
- Q3: Remove Git from the Terminal capability? → A: yes; `run_git_command` is removed and `git` is denied in
  the terminal, so the Git capability is the only way to run Git.
- Plan review (R2): the provider contract lives in `app/providers/git/base.py` instead of
  `app/capabilities/git/provider.py` → accepted (keeps providers independent of capabilities).
