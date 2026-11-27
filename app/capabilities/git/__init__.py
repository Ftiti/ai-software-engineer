"""Git capability: safe inspection and modification of Git repositories in the workspace.

tool.py ─► service.py ─► validator.py (rules) ─► providers/git ─► providers/terminal (process)
"""

from app.capabilities.git.capability import build_git_capability, build_git_service
from app.capabilities.git.service import GitService
from app.capabilities.git.validator import GitOperation, GitPolicy, GitValidator

__all__ = [
    "GitOperation",
    "GitPolicy",
    "GitService",
    "GitValidator",
    "build_git_capability",
    "build_git_service",
]
