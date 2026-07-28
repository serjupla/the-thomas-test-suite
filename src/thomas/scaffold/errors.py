"""Custom exceptions for scaffold operations."""


class ScaffoldError(Exception):
    """Base exception for scaffold-related errors."""

    exit_code = 1

    def __str__(self):
        return super().__str__()


class PermissionError(ScaffoldError):
    """Raised when destination lacks write permissions."""

    exit_code = 1


class SymlinkError(ScaffoldError):
    """Raised when destination is a symlink."""

    exit_code = 1


class MountPointError(ScaffoldError):
    """Raised when destination is a mount point or network path."""

    exit_code = 1


class PathTooLongError(ScaffoldError):
    """Raised when destination path exceeds Windows compatibility limit."""

    exit_code = 1


class BrokenInstallationError(ScaffoldError):
    """Raised when scaffold templates cannot be resolved."""

    exit_code = 1


class InvalidArgumentError(ScaffoldError):
    """Raised for invalid command-line arguments."""

    exit_code = 2
