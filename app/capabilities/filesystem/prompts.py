"""Instructions telling the agent how to use the filesystem tools.

Added to the agent's system prompt once tools are bound to the LLM (agent tool loop).
"""

FILESYSTEM_PROMPT = """\
You can inspect and edit the project with filesystem tools. Paths are relative to the project root.

How to work:
- Inspect before acting: start with list_files (recursive=true for an overview), then read the \
files that matter (README, pyproject.toml, package.json, configuration).
- Never guess file contents. If you need to know what a file says, read it with read_file.
- Always read a file before editing it, then send its complete new content with write_file. \
Keep everything you did not mean to change.
- Use create_file for new files, so you never overwrite an existing one by mistake.
- Delete files only when the user asked for it or it is clearly part of the task.
- If a tool returns an error (not found, access denied, too large), explain it or adjust; do \
not retry the same call unchanged.
- Secrets such as .env files are not accessible, and .git cannot be modified. Do not try to \
work around these rules.
"""
