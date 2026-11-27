# Data Model: Git Capability

All models are immutable Pydantic models (`frozen=True, extra="forbid"`) in `capabilities/git/schemas.py`,
except the provider-level dataclasses. Paths are repository-relative with `/` separators; `repository` is
the repository root relative to the workspace (`.` = workspace root).

## Provider level (`providers/git/base.py`)

| Entity | Fields | Notes |
|---|---|---|
| `GitInvocation` | `repository: Path` (absolute), `args: tuple[str, ...]`, `timeout: float`, `max_output_bytes: int` | what the service asks the provider to run |
| `GitOutput` | `exit_code: int`, `stdout: str`, `stderr: str`, `timed_out: bool`, `truncated: bool` | raw result; `stdout` decoded with `surrogateescape` |

## Policy (`capabilities/git/validator.py`)

| Entity | Fields |
|---|---|
| `GitPolicy` | `allow_push: bool = False`, `protected_branches: tuple[str, ...] = ()`, `read_only: bool` (from `FS_READ_ONLY`), `timeout: float = 30`, `network_timeout: float = 50`, `max_output_bytes: int = 64_000`, `max_log_entries: int = 100` |
| `GitOperation` (enum) | `STATUS DIFF LOG SHOW BRANCH_LIST BRANCH_CREATE SWITCH ADD COMMIT RESTORE REMOTE FETCH PULL PUSH`, with `.mutating` and `.network` |
| `RepositoryTarget` | `root: ResolvedPath` (from the filesystem validator), validated to be inside the workspace |

## Results (`capabilities/git/schemas.py`)

| Entity | Fields | Validation / rules |
|---|---|---|
| `Repository` | `repository`, `branch: str \| None`, `detached: bool`, `head: str \| None` (short hash), `has_commits: bool` | `branch is None` ⇔ detached HEAD (a repository without commits still has its branch name) |
| `FileChange` | `path`, `change: Literal["added","modified","deleted","renamed","copied","type_changed","unmerged"]`, `original_path: str \| None` | `original_path` only for renamed/copied |
| `RepositoryStatus` | `repository: Repository`, `upstream: str \| None`, `ahead: int`, `behind: int`, `staged: list[FileChange]`, `modified: list[FileChange]`, `untracked: list[str]`, `conflicted: list[str]`, `clean: bool`, `truncated: bool` | `clean` ⇔ all lists empty |
| `DiffResult` | `repository`, `files: list[str]`, `diff: str`, `stat_only: bool`, `omitted_secrets: list[str]`, `truncated: bool` | secrets never in `files` / `diff` |
| `Commit` | `hash`, `short_hash`, `author`, `email`, `date` (ISO 8601), `subject`, `body` | |
| `LogResult` | `repository`, `commits: list[Commit]`, `limit: int` | `len(commits) <= limit <= max_log_entries` |
| `ShowResult` | `repository`, `commit: Commit`, `path: str \| None`, `content: str` (patch, or file content when `path`), `omitted_secrets`, `truncated` | |
| `Branch` | `name`, `current: bool`, `remote: bool`, `upstream: str \| None`, `commit: str`, `subject: str` | |
| `BranchList` | `repository`, `current: str \| None`, `branches: list[Branch]` | |
| `BranchCreated` | `repository`, `branch`, `start_point`, `switched: bool` | |
| `CheckoutResult` | `repository`, `branch`, `created: bool`, `previous: str \| None` | |
| `AddResult` | `repository`, `staged: list[str]`, `skipped_secrets: list[str]` | |
| `CommitResult` | `repository`, `commit: Commit`, `branch: str \| None`, `detached: bool`, `files_changed: int` | |
| `RestoreResult` | `repository`, `paths: list[str]`, `staged: bool` | `staged=True`: unstaged only |
| `Remote` | `name`, `fetch_url`, `push_url` | URLs masked |
| `RemoteList` | `repository`, `remotes: list[Remote]` | |
| `RemoteOperationResult` | `repository`, `operation: Literal["fetch","pull","push"]`, `remote`, `branch: str \| None`, `output: str` (Git's summary), `truncated` | |

## Validation rules (`GitValidator`)

| Input | Rule |
|---|---|
| repository path | inside the workspace, existing directory, not secret; root from `rev-parse --show-toplevel` inside the workspace |
| file paths | non-empty, no NUL, inside the workspace after resolution against the repository root, not secret; `restore` (working copy): not the root, not a directory |
| reference (`ref`, `start_point`) | 1–256 chars, no leading `-`, no whitespace or control characters, charset `[A-Za-z0-9._/@{}~^+-]`; ranges `a..b` / `a...b` only for diff and log |
| branch name | Git ref-format rules: no leading `-` or `.`, no `..`, `@{`, `//`, trailing `/` or `.lock`, no `~^:?*[\` or space, not `HEAD` / `@` |
| remote name | `[A-Za-z0-9._-]+`, no leading `-`, must be an existing remote |
| commit message | non-empty after stripping, ≤ 10,000 characters, no NUL |
| log limit | 1 ≤ limit ≤ `max_log_entries` |
| operation | refused if mutating and read-only; push refused if disabled, detached, or protected branch |
| final argv | sub-command in the allow-list; no dangerous flag before `--` (R7) |

## Errors (`capabilities/git/exceptions.py`)

```
GitError
├── NotARepository              folder is not inside a Git repository
├── RepositoryOutsideWorkspace  repository root or a path is outside the workspace / is a secret
├── InvalidGitArgument          bad path, reference, branch name, remote, message, limit
├── GitOperationNotAllowed      policy refusal (read-only, push disabled, protected, dangerous flag)
├── NothingToCommit
├── ConflictsPresent            unresolved conflicts (lists the files)
├── GitCommandFailed            git exited non-zero (carries Git's stderr)
├── GitNotInstalled
└── GitTimeout
```

## State transitions (working tree file)

```
untracked ──add──► staged(added) ──commit──► committed
committed ──edit──► modified ──add──► staged(modified) ──commit──► committed
staged ──restore(staged)──► modified           modified ──restore(worktree)──► committed
any ──pull/merge conflict (outside agent)──► conflicted ──edit+add──► staged ──commit──► committed
```
