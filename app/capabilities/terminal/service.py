"""Business logic of the terminal capability: which command to run for a request.

Every operation follows the same shape: build an argument vector, validate it with the
:class:`CommandValidator`, run it with the :class:`CommandExecutor`. The service never starts
processes nor touches the OS itself.
"""

from collections.abc import Sequence

from app.capabilities.terminal.exceptions import InvalidCommand
from app.capabilities.terminal.executor import CommandExecutor
from app.capabilities.terminal.schemas import CommandOptions, CommandResult, TestRunner
from app.capabilities.terminal.validator import CommandValidator

DEFAULT_OPTIONS = CommandOptions()

# run_tests(runner="auto"): first runner whose marker file exists in the working directory.
TEST_RUNNER_MARKERS: tuple[tuple[TestRunner, tuple[str, ...]], ...] = (
    ("pytest", ("pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", "conftest.py")),
    ("npm", ("package.json",)),
    ("composer", ("composer.json",)),
    ("make", ("Makefile", "makefile", "GNUmakefile")),
)


class TerminalService:
    def __init__(
        self, validator: CommandValidator, executor: CommandExecutor, *, python: str = "python3"
    ) -> None:
        self._validator = validator
        self._executor = executor
        self._python = python

    async def execute_command(self, command: str, options: CommandOptions = DEFAULT_OPTIONS) -> CommandResult:
        """Run one command line (split with POSIX quoting, never through a shell)."""
        return await self.run(self._validator.parse(command), options)

    async def run(self, argv: Sequence[str], options: CommandOptions = DEFAULT_OPTIONS) -> CommandResult:
        command = self._validator.validate(
            argv, working_directory=options.working_directory, timeout=options.timeout, env=options.env
        )
        return await self._executor.execute(command)

    # -- Program shortcuts -------------------------------------------------------------------

    async def run_python(
        self, args: Sequence[str], options: CommandOptions = DEFAULT_OPTIONS
    ) -> CommandResult:
        return await self.run([self._python, *args], options)

    async def run_pytest(
        self, args: Sequence[str], options: CommandOptions = DEFAULT_OPTIONS
    ) -> CommandResult:
        # As a module: uses the project's interpreter and puts the working directory on sys.path.
        return await self.run([self._python, "-m", "pytest", *args], options)

    async def run_make(
        self, target: str | None, args: Sequence[str], options: CommandOptions = DEFAULT_OPTIONS
    ) -> CommandResult:
        return await self.run(["make", *([target] if target else []), *args], options)

    async def run_npm(self, args: Sequence[str], options: CommandOptions = DEFAULT_OPTIONS) -> CommandResult:
        return await self.run(["npm", *args], options)

    async def run_composer(
        self, args: Sequence[str], options: CommandOptions = DEFAULT_OPTIONS
    ) -> CommandResult:
        return await self.run(["composer", *args], options)

    async def run_tests(
        self, runner: TestRunner = "auto", args: Sequence[str] = (), options: CommandOptions = DEFAULT_OPTIONS
    ) -> CommandResult:
        """Run the project's test suite with the given runner, or the detected one."""
        chosen = self.detect_test_runner(options.working_directory) if runner == "auto" else runner
        extra = ["--", *args] if args else []
        if chosen == "pytest":
            return await self.run_pytest(args, options)
        if chosen == "npm":
            return await self.run_npm(["test", *extra], options)
        if chosen == "composer":
            return await self.run_composer(["test", *extra], options)
        return await self.run_make("test", args, options)

    def detect_test_runner(self, working_directory: str = ".") -> TestRunner:
        directory = self._validator.working_directory(working_directory)
        for runner, markers in TEST_RUNNER_MARKERS:
            if any(self._validator.has_file(directory, marker) for marker in markers):
                return runner
        raise InvalidCommand(
            f"No test runner detected in {directory.relative!r} (no pyproject.toml, package.json, "
            "composer.json or Makefile). Choose one with the 'runner' argument."
        )
