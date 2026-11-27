"""Application settings loaded from environment variables and an optional ``.env`` file."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["ollama", "openai", "gemini", "groq"]
Temperature = Annotated[float, Field(ge=0.0, le=2.0)]


class Settings(BaseSettings):
    """Typed runtime configuration. Every field maps to an upper-case environment variable."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Active LLM provider and defaults shared by every provider
    llm_provider: LLMProviderName = "ollama"
    llm_temperature: Temperature = 0.0
    llm_timeout: float | None = Field(default=None, gt=0)  # seconds; None = no limit

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_temperature: Temperature | None = None  # None = use LLM_TEMPERATURE

    # OpenAI
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_temperature: Temperature | None = None

    # Google Gemini
    google_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_temperature: Temperature | None = None

    # Groq
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_temperature: Temperature | None = None

    # Tools
    tool_timeout: float | None = Field(default=60.0, gt=0)  # seconds per tool call; None = no limit

    # Filesystem capability. Patterns are matched against each path component (fnmatch).
    fs_workspace_root: Path = Path(".")  # the only directory tools may touch
    fs_read_only: bool = False
    fs_max_read_bytes: int = Field(default=1_048_576, gt=0)
    fs_max_write_bytes: int = Field(default=1_048_576, gt=0)
    fs_max_list_entries: int = Field(default=1000, gt=0)
    # No access at all (secrets).
    fs_denied_patterns: list[str] = [
        ".env",
        ".env.local",
        ".env.*.local",
        "*.pem",
        "*.key",
        "id_rsa*",
        "id_ed25519*",
    ]
    # Readable but never modified.
    fs_protected_patterns: list[str] = [".git"]
    # Skipped by recursive listings (still listable explicitly).
    fs_ignored_patterns: list[str] = [
        ".git",
        ".venv",
        ".venv-*",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    ]

    # Code intelligence
    code_max_results: int = Field(default=50, gt=0)  # cap on symbols/imports/references per query

    # Terminal capability. Commands run without a shell, in the filesystem workspace.
    terminal_enabled: bool = True
    # Whitelist of program names; "*" allows every program that is not denied.
    terminal_allowed_commands: list[str] = [
        "python",
        "python3",
        "pytest",
        "ruff",
        "mypy",
        "make",
        "npm",
        "node",
        "composer",
        "php",
        "ls",
        "pwd",
        "echo",
    ]
    # Blacklist: always refused, even with "*". Shells and wrappers would bypass the other rules;
    # git goes through the Git capability only.
    terminal_denied_commands: list[str] = [
        "git",
        "rm",
        "rmdir",
        "sudo",
        "su",
        "doas",
        "dd",
        "mkfs",
        "fdisk",
        "shutdown",
        "reboot",
        "halt",
        "poweroff",
        "kill",
        "killall",
        "pkill",
        "chmod",
        "chown",
        "chgrp",
        "curl",
        "wget",
        "ssh",
        "scp",
        "rsync",
        "nc",
        "netcat",
        "telnet",
        "sh",
        "bash",
        "zsh",
        "dash",
        "fish",
        "env",
        "xargs",
        "nohup",
        "eval",
        "exec",
        "npx",
        "crontab",
        "mount",
        "umount",
        "systemctl",
    ]
    # For these programs the first argument must be one of the listed subcommands.
    terminal_allowed_subcommands: dict[str, list[str]] = {
        "npm": ["install", "ci", "test", "run", "run-script", "ls", "list", "outdated"],
        "composer": [
            "install",
            "update",
            "require",
            "dump-autoload",
            "validate",
            "show",
            "outdated",
            "test",
            "run-script",
        ],
    }
    # Arguments refused for every program (fnmatch); they can run arbitrary programs or write files.
    terminal_denied_arguments: list[str] = [
        "--exec*",
        "--upload-pack*",
        "--receive-pack*",
        "--ext-diff",
        "--output*",
        "--config-env*",
    ]
    # Environment variables a command may not set (fnmatch): they change what actually runs.
    terminal_denied_env: list[str] = [
        "PATH",
        "LD_*",
        "DYLD_*",
        "GIT_*",
        "PYTHONSTARTUP",
        "PYTHONPATH",
        "NODE_OPTIONS",
        "BASH_ENV",
        "ENV",
        "IFS",
        "PERL5OPT",
    ]
    # Host variables passed on to commands. Everything else (API keys, tokens) is not.
    terminal_inherited_env: list[str] = [
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "TMPDIR",
        "TZ",
        "VIRTUAL_ENV",
    ]
    terminal_default_timeout: float = Field(default=30.0, gt=0)  # seconds
    terminal_max_timeout: float = Field(default=50.0, gt=0)  # must stay below TOOL_TIMEOUT
    terminal_max_output_bytes: int = Field(default=64_000, gt=0)  # per stream (stdout, stderr)
    terminal_python: str = "python3"  # interpreter used by run_python, run_pytest and run_tests

    # Git capability. Git runs through the terminal provider (no shell), in repositories whose root is
    # inside FS_WORKSPACE_ROOT; FS_READ_ONLY also refuses every modifying git operation.
    git_enabled: bool = True
    git_executable: str = "git"
    git_allow_push: bool = False  # git_push is registered only when true; never forced
    git_protected_branches: list[str] = []  # branches git_push refuses, e.g. ["main", "master"]
    git_allow_hooks: bool = True  # repository hooks run like the project's Makefile; false disables them
    git_timeout: float = Field(default=30.0, gt=0)  # seconds, local operations
    git_network_timeout: float = Field(default=50.0, gt=0)  # seconds, fetch / pull / push
    git_max_output_bytes: int = Field(default=64_000, gt=0)  # diff / show text returned to the agent
    git_max_log_entries: int = Field(default=100, gt=0)
    # Host variables passed to git in addition to TERMINAL_INHERITED_ENV (ssh agent, config location).
    git_extra_inherited_env: list[str] = ["SSH_AUTH_SOCK", "XDG_CONFIG_HOME"]

    # MCP
    mcp_config_path: Path = Path("mcp_servers.json")

    @model_validator(mode="after")
    def _check_timeouts(self) -> "Settings":
        if self.terminal_default_timeout > self.terminal_max_timeout:
            raise ValueError("TERMINAL_DEFAULT_TIMEOUT must not exceed TERMINAL_MAX_TIMEOUT")
        if self.tool_timeout is not None and self.terminal_max_timeout >= self.tool_timeout:
            # Otherwise the tool manager would cancel the call before the command's own timeout,
            # and the agent would lose the partial output.
            raise ValueError("TERMINAL_MAX_TIMEOUT must be lower than TOOL_TIMEOUT")
        if (
            self.tool_timeout is not None
            and max(self.git_timeout, self.git_network_timeout) >= self.tool_timeout
        ):
            raise ValueError("GIT_TIMEOUT and GIT_NETWORK_TIMEOUT must be lower than TOOL_TIMEOUT")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
