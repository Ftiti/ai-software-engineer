"""Instructions telling the agent how to use the terminal tools.

Added to the agent's system prompt once tools are bound to the LLM (agent tool loop).
"""

TERMINAL_PROMPT = """\
You can run commands in the project with terminal tools. They run in the project root unless \
you give a working_directory (relative to the root).

How to work:
- Prefer the dedicated tools: run_tests to check your changes, run_pytest / run_npm / \
run_composer / run_make / run_python for one tool, run_git_command to inspect history. Use \
execute_command for other allowed programs (linters, formatters, type checkers).
- Read files with the filesystem tools, not with commands.
- Commands run without a shell: one program per call, no pipes, redirections, '&&', globs \
or $VARIABLES. Pass variables with the env argument.
- Commands are not interactive: there is no input, so use non-interactive flags (e.g. -y).
- A non-zero exit code is a result, not a tool error: read stderr and stdout, fix the cause, \
then run the command again. Do not repeat a failing command unchanged.
- If a command times out, run a smaller part (one test file, -x) instead of raising the timeout.
- A refused command (not allowed, outside the workspace, secret) is a security rule. Do not \
try to work around it with another program or an interpreter; explain what you need instead.
- Never run destructive commands, and only install dependencies when the task requires it.
"""
