"""Errors of the filesystem capability. Messages are written to be shown to the LLM."""


class FilesystemError(Exception):
    """Base class. Any filesystem failure the caller should see."""


class InvalidPath(FilesystemError):
    """The path is malformed (empty segment, NUL byte, ...)."""


class AccessDenied(FilesystemError):
    """The path is outside the workspace, protected, secret, or the operation is not allowed."""


class FileNotFound(FilesystemError):
    pass


class DirectoryNotFound(FilesystemError):
    pass


class FileAlreadyExists(FilesystemError):
    pass


class NotAFile(FilesystemError):
    pass


class NotADirectory(FilesystemError):
    pass


class FileTooLarge(FilesystemError):
    pass


class UnsupportedFile(FilesystemError):
    """The file cannot be handled as text (binary, unknown encoding)."""
