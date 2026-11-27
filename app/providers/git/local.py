"""Git provider running the local git executable through the :class:`TerminalProvider`.

It starts no process itself: the terminal provider does (no shell, own process group, timeout,
cancellation, bounded output). This module only knows how to talk to git:

- global flags making every call script-friendly and literal:
  ``--no-pager --literal-pathspecs -c color.ui=never -c core.quotepath=off``
  (``*`` or ``:(glob)`` in a path are plain characters, file names are printed unescaped);
- an environment that never waits for input (editor, pager, credentials) and contains only the
  allowed host variables, so the agent's own secrets never reach git;
- optionally, hooks disabled with ``-c core.hooksPath=/dev/null``.
"""

from collections.abc import Iterable, Mapping

from app.providers.git.base import GitInvocation, GitOutput, GitProvider
from app.providers.terminal import ProcessRequest, TerminalProvider, process_environment

GLOBAL_FLAGS: tuple[str, ...] = (
    "--no-pager",
    "--literal-pathspecs",
    "-c",
    "color.ui=never",
    "-c",
    "core.quotepath=off",
)
NO_HOOKS: tuple[str, ...] = ("-c", "core.hooksPath=/dev/null")
GIT_ENV: Mapping[str, str] = {
    "GIT_EDITOR": "true",  # never open an editor (commit messages are always given)
    "GIT_SEQUENCE_EDITOR": "true",
    "GIT_MERGE_AUTOEDIT": "no",
    "GIT_OPTIONAL_LOCKS": "0",  # read-only commands do not take locks the user's tools may need
}


class LocalGitProvider(GitProvider):
    def __init__(
        self,
        terminal: TerminalProvider,
        *,
        executable: str = "git",
        inherited_env: Iterable[str] = (),
        hooks: bool = True,
    ) -> None:
        self._terminal = terminal
        self._executable = executable
        self._inherited_env = tuple(inherited_env)
        self._flags = GLOBAL_FLAGS if hooks else GLOBAL_FLAGS + NO_HOOKS

    async def run(self, invocation: GitInvocation) -> GitOutput:
        request = ProcessRequest(
            argv=(self._executable, *self._flags, *invocation.args),
            cwd=invocation.repository,
            env=process_environment(self._terminal.environment(), self._inherited_env, GIT_ENV),
            timeout=invocation.timeout,
            max_output_bytes=invocation.max_output_bytes,
        )
        result = await self._terminal.run(request)
        return GitOutput(
            exit_code=result.exit_code,
            stdout=result.stdout.text(),
            stderr=result.stderr.text(),
            timed_out=result.timed_out,
            truncated=result.stdout.truncated or result.stderr.truncated,
        )
