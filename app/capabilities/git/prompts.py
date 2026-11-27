"""Instructions telling the agent how to use the Git tools.

Added to the agent's system prompt once tools are bound to the LLM (agent tool loop).
"""

GIT_PROMPT = """\
You can inspect and change the project's Git repository with git tools (never with terminal \
commands).

How to work:
- Start with git_status to see the branch and which files are staged, modified, untracked or in \
conflict. Use git_diff and git_log to understand changes before acting.
- For a task, create a branch with git_checkout (create=true) unless the user asked otherwise.
- Stage only the files that belong to the change (git_add with paths), check with git_diff \
(staged=true), then git_commit with a clear message: a short summary line, then details if useful.
- Secret files (.env, keys) are never staged, committed or shown. Do not try to work around this.
- git_restore with staged=false DISCARDS uncommitted changes: only use it on files you changed \
yourself or when the user asked.
- Resolve conflicts by editing the files with the filesystem tools, then git_add and git_commit.
- git_pull only fast-forwards; if the histories diverged, explain the situation to the user.
- There is no reset, rebase, force push or branch deletion: these are not available on purpose.
- If a git tool returns an error, read it and adjust; do not repeat the same call unchanged.
"""
