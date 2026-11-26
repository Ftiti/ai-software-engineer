"""Typed requests and responses of the filesystem capability.

Requests double as tool input models: their field descriptions end up in the JSON Schema the
LLM reads. All paths are relative to the workspace root and use ``/`` as separator.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PathField = Field(description="Path relative to the workspace root, e.g. 'src/app.py'.")


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# -- Requests -------------------------------------------------------------------------------


class ListDirectoryRequest(_Model):
    path: str = Field(default=".", description="Directory relative to the workspace root. '.' is the root.")
    recursive: bool = Field(
        default=False, description="Also list subdirectories (skips .git, .venv, node_modules, caches)."
    )


class ReadFileRequest(_Model):
    path: str = PathField


class WriteFileRequest(_Model):
    path: str = PathField
    content: str = Field(description="Full new content of the file (UTF-8 text).")


class CreateFileRequest(_Model):
    path: str = PathField
    content: str = Field(default="", description="Initial content (UTF-8 text).")


class DeleteFileRequest(_Model):
    path: str = PathField


class CreateDirectoryRequest(_Model):
    path: str = PathField


class MoveFileRequest(_Model):
    source: str = PathField
    destination: str = PathField
    overwrite: bool = False


class CopyFileRequest(_Model):
    source: str = PathField
    destination: str = PathField
    overwrite: bool = False


# -- Responses ------------------------------------------------------------------------------


class DirectoryEntry(_Model):
    path: str
    type: Literal["file", "directory", "symlink"]
    size: int | None = None


class ListDirectoryResponse(_Model):
    path: str
    entries: list[DirectoryEntry]
    truncated: bool = Field(default=False, description="True when the entry limit was reached.")


class ReadFileResponse(_Model):
    path: str
    content: str
    size: int


class WriteFileResponse(_Model):
    path: str
    bytes_written: int
    created: bool


class FileOperationResponse(_Model):
    path: str
    detail: str
