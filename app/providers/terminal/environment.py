"""Environment of the processes started for capabilities (terminal commands, git).

Only an allow-list of host variables is passed on: API keys and tokens in the agent's own
environment never reach a command.
"""

from collections.abc import Iterable, Mapping

# Set for every process: no colours, pagers or interactive prompts (stdin is empty anyway).
NON_INTERACTIVE_ENV: Mapping[str, str] = {
    "NO_COLOR": "1",
    "PAGER": "cat",
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
    "PYTHONUNBUFFERED": "1",
}


def process_environment(
    host: Mapping[str, str], inherited: Iterable[str], *overlays: Mapping[str, str]
) -> dict[str, str]:
    """The ``inherited`` host variables, then :data:`NON_INTERACTIVE_ENV`, then each overlay."""
    environment = {name: host[name] for name in inherited if name in host}
    environment.update(NON_INTERACTIVE_ENV)
    for overlay in overlays:
        environment.update(overlay)
    return environment
