"""Filesystem capability: safe inspection and editing of the workspace.

tool.py ─► service.py ─► validator.py (rules) ─► providers/filesystem (OS)
"""

from app.capabilities.filesystem.capability import build_filesystem_capability, build_filesystem_service
from app.capabilities.filesystem.service import FilesystemService
from app.capabilities.filesystem.validator import FilesystemPolicy, Operation, PathValidator

__all__ = [
    "FilesystemPolicy",
    "FilesystemService",
    "Operation",
    "PathValidator",
    "build_filesystem_capability",
    "build_filesystem_service",
]
