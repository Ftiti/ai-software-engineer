"""Git tools: thin wrappers exposing :class:`GitService` to the tool system.

Each tool maps its input model to one service call. Error translation and serialisation come
from :class:`AsyncCapabilityTool`; the call runs on the event loop, so a cancelled tool call
stops git (through the terminal provider).
"""

from typing import Any, TypeVar

from pydantic import BaseModel

from app.capabilities.base import AsyncCapabilityTool
from app.capabilities.git.exceptions import GitError
from app.capabilities.git.schemas import (
    GitAddRequest,
    GitBranchRequest,
    GitCheckoutRequest,
    GitCommitRequest,
    GitDiffRequest,
    GitFetchRequest,
    GitLogRequest,
    GitPullRequest,
    GitPushRequest,
    GitRemoteRequest,
    GitRestoreRequest,
    GitShowRequest,
    GitStatusRequest,
)
from app.capabilities.git.service import GitService
from app.tools import BaseTool

InputT = TypeVar("InputT", bound=BaseModel)


class GitTool(AsyncCapabilityTool[InputT]):
    errors = (GitError,)

    def __init__(self, service: GitService) -> None:
        self._service = service


class GitStatusTool(GitTool[GitStatusRequest]):
    name = "git_status"
    description = (
        "Repository state: current branch, upstream, ahead/behind, and staged, modified, untracked and "
        "conflicted files. Start here before any other git tool."
    )
    input_model = GitStatusRequest

    async def _arun(self, params: GitStatusRequest) -> BaseModel:
        return await self._service.status(params.repository)


class GitDiffTool(GitTool[GitDiffRequest]):
    name = "git_diff"
    description = (
        "Show changes: of the working copy (default), of staged files (staged=true), against a "
        "commit/branch (ref) or between two (ref + target)."
    )
    input_model = GitDiffRequest

    async def _arun(self, params: GitDiffRequest) -> BaseModel:
        return await self._service.diff(
            params.repository,
            staged=params.staged,
            ref=params.ref,
            target=params.target,
            paths=params.paths,
            stat_only=params.stat_only,
        )


class GitLogTool(GitTool[GitLogRequest]):
    name = "git_log"
    description = "List recent commits (hash, author, date, subject), most recent first."
    input_model = GitLogRequest

    async def _arun(self, params: GitLogRequest) -> BaseModel:
        return await self._service.log(
            params.repository, limit=params.limit, ref=params.ref, paths=params.paths
        )


class GitShowTool(GitTool[GitShowRequest]):
    name = "git_show"
    description = "Show a commit (metadata and changes), or a file's content at that commit (path)."
    input_model = GitShowRequest

    async def _arun(self, params: GitShowRequest) -> BaseModel:
        return await self._service.show(params.repository, ref=params.ref, path=params.path)


class GitBranchTool(GitTool[GitBranchRequest]):
    name = "git_branch"
    description = "List branches (current one marked), or create a branch without switching (create)."
    input_model = GitBranchRequest

    async def _arun(self, params: GitBranchRequest) -> BaseModel:
        if params.create:
            return await self._service.create_branch(
                params.repository, name=params.create, start_point=params.start_point
            )
        return await self._service.branches(params.repository, include_remote=params.include_remote)


class GitCheckoutTool(GitTool[GitCheckoutRequest]):
    name = "git_checkout"
    description = (
        "Switch to a branch, or create and switch (create=true). Refused if it would overwrite "
        "uncommitted changes."
    )
    input_model = GitCheckoutRequest

    async def _arun(self, params: GitCheckoutRequest) -> BaseModel:
        return await self._service.checkout(
            params.repository, branch=params.branch, create=params.create, start_point=params.start_point
        )


class GitAddTool(GitTool[GitAddRequest]):
    name = "git_add"
    description = (
        "Stage changed files (paths, or all=true) for the next commit. Secret files are never staged."
    )
    input_model = GitAddRequest

    async def _arun(self, params: GitAddRequest) -> BaseModel:
        return await self._service.add(params.repository, paths=params.paths, all=params.all)


class GitCommitTool(GitTool[GitCommitRequest]):
    name = "git_commit"
    description = (
        "Commit the staged changes with a message. Refused if nothing is staged or conflicts remain."
    )
    input_model = GitCommitRequest

    async def _arun(self, params: GitCommitRequest) -> BaseModel:
        return await self._service.commit(params.repository, message=params.message)


class GitRestoreTool(GitTool[GitRestoreRequest]):
    name = "git_restore"
    description = (
        "Unstage files (staged=true, changes kept), or DISCARD the uncommitted changes of the named "
        "files (staged=false). Files must be named one by one."
    )
    input_model = GitRestoreRequest

    async def _arun(self, params: GitRestoreRequest) -> BaseModel:
        return await self._service.restore(params.repository, paths=params.paths, staged=params.staged)


class GitRemoteTool(GitTool[GitRemoteRequest]):
    name = "git_remote"
    description = "List the remotes and their URLs (credentials masked)."
    input_model = GitRemoteRequest

    async def _arun(self, params: GitRemoteRequest) -> BaseModel:
        return await self._service.remotes(params.repository)


class GitFetchTool(GitTool[GitFetchRequest]):
    name = "git_fetch"
    description = "Download new commits and branches from a remote (does not change your files)."
    input_model = GitFetchRequest

    async def _arun(self, params: GitFetchRequest) -> BaseModel:
        return await self._service.fetch(params.repository, remote=params.remote)


class GitPullTool(GitTool[GitPullRequest]):
    name = "git_pull"
    description = "Fast-forward the current branch from its remote. Refused if the histories diverged."
    input_model = GitPullRequest

    async def _arun(self, params: GitPullRequest) -> BaseModel:
        return await self._service.pull(params.repository, remote=params.remote, branch=params.branch)


class GitPushTool(GitTool[GitPushRequest]):
    name = "git_push"
    description = "Push the current branch to a remote (never forced)."
    input_model = GitPushRequest

    async def _arun(self, params: GitPushRequest) -> BaseModel:
        return await self._service.push(
            params.repository, remote=params.remote, set_upstream=params.set_upstream
        )


GIT_TOOLS: tuple[type[GitTool[Any]], ...] = (
    GitStatusTool,
    GitDiffTool,
    GitLogTool,
    GitShowTool,
    GitBranchTool,
    GitCheckoutTool,
    GitAddTool,
    GitCommitTool,
    GitRestoreTool,
    GitRemoteTool,
    GitFetchTool,
    GitPullTool,
)


def git_tools(service: GitService, *, allow_push: bool = False) -> list[BaseTool[Any]]:
    """The Git tools; ``git_push`` only when push is enabled (a tool that can only fail is noise)."""
    tools: tuple[type[GitTool[Any]], ...] = (*GIT_TOOLS, GitPushTool) if allow_push else GIT_TOOLS
    return [tool(service) for tool in tools]
