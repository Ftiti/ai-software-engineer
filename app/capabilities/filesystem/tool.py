"""Filesystem tools: thin wrappers exposing :class:`FilesystemService` to the tool system.

Each tool maps its input model to one service call. :class:`FilesystemTool` holds the shared
plumbing: run the blocking service in a worker thread, turn capability errors into
``ToolExecutionError`` (so the manager reports them to the LLM) and serialise the response.
"""

import asyncio
from abc import abstractmethod
from typing import Any, TypeVar

from pydantic import BaseModel

from app.capabilities.filesystem.exceptions import FilesystemError
from app.capabilities.filesystem.schemas import (
    CreateFileRequest,
    DeleteFileRequest,
    ListDirectoryRequest,
    ReadFileRequest,
    WriteFileRequest,
)
from app.capabilities.filesystem.service import FilesystemService
from app.tools import BaseTool, ToolExecutionError

InputT = TypeVar("InputT", bound=BaseModel)


class FilesystemTool(BaseTool[InputT]):
    def __init__(self, service: FilesystemService) -> None:
        self._service = service

    async def execute(self, params: InputT) -> dict[str, Any]:
        try:
            response = await asyncio.to_thread(self._run, params)
        except FilesystemError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return response.model_dump()

    @abstractmethod
    def _run(self, params: InputT) -> BaseModel: ...


class ListFilesTool(FilesystemTool[ListDirectoryRequest]):
    name = "list_files"
    description = (
        "List files and directories in the project. Use '.' for the project root and "
        "recursive=true to see the whole tree."
    )
    input_model = ListDirectoryRequest

    def _run(self, params: ListDirectoryRequest) -> BaseModel:
        return self._service.list_directory(params.path, recursive=params.recursive)


class ReadFileTool(FilesystemTool[ReadFileRequest]):
    name = "read_file"
    description = "Read a UTF-8 text file of the project and return its full content."
    input_model = ReadFileRequest

    def _run(self, params: ReadFileRequest) -> BaseModel:
        return self._service.read_file(params.path)


class WriteFileTool(FilesystemTool[WriteFileRequest]):
    name = "write_file"
    description = (
        "Replace the whole content of a text file, creating it (and its folders) if needed. "
        "Read the file first when it already exists."
    )
    input_model = WriteFileRequest

    def _run(self, params: WriteFileRequest) -> BaseModel:
        return self._service.write_file(params.path, params.content)


class CreateFileTool(FilesystemTool[CreateFileRequest]):
    name = "create_file"
    description = "Create a new text file. Fails if the file already exists."
    input_model = CreateFileRequest

    def _run(self, params: CreateFileRequest) -> BaseModel:
        return self._service.create_file(params.path, params.content)


class DeleteFileTool(FilesystemTool[DeleteFileRequest]):
    name = "delete_file"
    description = "Delete a file of the project. Directories cannot be deleted."
    input_model = DeleteFileRequest

    def _run(self, params: DeleteFileRequest) -> BaseModel:
        return self._service.delete_file(params.path)


TOOL_CLASSES: tuple[type[FilesystemTool[Any]], ...] = (
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
    CreateFileTool,
    DeleteFileTool,
)


def filesystem_tools(service: FilesystemService) -> list[BaseTool[Any]]:
    """One instance of every filesystem tool, sharing ``service``."""
    return [tool_class(service) for tool_class in TOOL_CLASSES]
