"""Assembles the filesystem capability: provider -> validator -> service -> tools."""

from app.capabilities.base import Capability
from app.capabilities.filesystem.prompts import FILESYSTEM_PROMPT
from app.capabilities.filesystem.service import FilesystemService
from app.capabilities.filesystem.tool import filesystem_tools
from app.capabilities.filesystem.validator import FilesystemPolicy, PathValidator
from app.config import Settings
from app.providers.filesystem import FilesystemProvider, LocalFilesystemProvider


def build_filesystem_service(
    settings: Settings, provider: FilesystemProvider | None = None
) -> FilesystemService:
    provider = provider or LocalFilesystemProvider()
    validator = PathValidator(provider, FilesystemPolicy.from_settings(settings))
    return FilesystemService(provider, validator)


def build_filesystem_capability(service: FilesystemService) -> Capability:
    """The filesystem tools around ``service`` (shared with capabilities that read the project)."""
    return Capability(name="filesystem", tools=filesystem_tools(service), prompt=FILESYSTEM_PROMPT)
