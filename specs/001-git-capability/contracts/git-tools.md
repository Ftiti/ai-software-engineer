# Contract: Git tools

These are the interfaces the LLM sees through `ToolManager.list_tools()`. Every input model extends
`GitTarget`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `repository` | `str` | `"."` | repository folder, relative to the workspace root |

Results are the models in [data-model.md](../data-model.md), serialised as JSON. Failures are `ToolResult`
errors whose message names the rule (see `GitError` subclasses).

| Tool | Input (besides `repository`) | Result | Mutating | Git command built by the service |
|---|---|---|---|---|
| `git_status` | – | `RepositoryStatus` | no | `status --porcelain=v2 --branch -z --untracked-files=all` |
| `git_diff` | `staged: bool = false`, `ref: str \| None`, `target: str \| None`, `paths: list[str] = []`, `stat_only: bool = false` | `DiffResult` | no | `diff --name-only -z [--cached] [ref [target]] -- paths`, then `diff [--cached] [--stat] [ref [target]] -- allowed_files` |
| `git_log` | `limit: int = 20`, `ref: str \| None`, `paths: list[str] = []` | `LogResult` | no | `log -z --max-count=N --format=… [ref] -- paths` |
| `git_show` | `ref: str = "HEAD"`, `path: str \| None` | `ShowResult` | no | `show --format=… <ref> -- allowed_files`, or `show <ref>:<path>` |
| `git_branch` | `create: str \| None`, `start_point: str \| None`, `include_remote: bool = false` | `BranchList` or `BranchCreated` | only with `create` | `for-each-ref … refs/heads [refs/remotes]` / `branch <name> [start]` (name validated, never starts with `-`) |
| `git_checkout` | `branch: str`, `create: bool = false`, `start_point: str \| None` | `CheckoutResult` | yes | `switch <branch>` / `switch --create <branch> [start]` |
| `git_add` | `paths: list[str] = []`, `all: bool = false` (exactly one of them) | `AddResult` | yes | `status`, then `add -- <changed files under the paths, secrets removed>` |
| `git_commit` | `message: str` | `CommitResult` | yes | `status` checks, then `commit --cleanup=strip --message=<message>` |
| `git_restore` | `paths: list[str]` (≥1), `staged: bool = false` | `RestoreResult` | yes | `restore --staged -- paths` / `restore --worktree -- paths` |
| `git_remote` | – | `RemoteList` | no | `remote -v` |
| `git_fetch` | `remote: str \| None` | `RemoteOperationResult` | no (only `.git`) | `fetch <remote>` |
| `git_pull` | `remote: str \| None`, `branch: str \| None` | `RemoteOperationResult` | yes | `pull --ff-only --no-rebase [remote [branch]]` |
| `git_push` *(registered only when `GIT_ALLOW_PUSH=true`)* | `remote: str \| None`, `set_upstream: bool = false` | `RemoteOperationResult` | yes | `push [--set-upstream] <remote> <current branch>` |

Every Git invocation is prefixed by the provider with
`git --no-pager --literal-pathspecs -c color.ui=never -c core.quotepath=off`, plus
`-c core.hooksPath=/dev/null` when `GIT_ALLOW_HOOKS=false`.

## Error examples (message contract)

| Situation | Message |
|---|---|
| not a repository | `'.' is not inside a Git repository` |
| root outside workspace | `The repository root '/home/me/big-repo' is outside the workspace` |
| secret path | `Access to '.env' is not allowed (protected secret)` |
| bad branch name | `Invalid branch name 'a..b': it may not contain '..'` |
| nothing staged | `Nothing to commit: no staged changes (use git_add first)` |
| conflicts | `Cannot commit: unresolved conflicts in app/x.py, README.md` |
| push disabled | `Push is disabled. Set GIT_ALLOW_PUSH=true to enable it` |
| protected branch | `Pushing 'main' is not allowed (protected branch)` |
| read-only | `Cannot commit: the workspace is read-only` |
| Git failure | `git switch failed: error: Your local changes to the following files would be overwritten…` |
