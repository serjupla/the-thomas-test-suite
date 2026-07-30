"""Path validation for scaffold destination."""

import os
from pathlib import Path

from .errors import (
    InvalidArgumentError,
    MountPointError,
    PathTooLongError,
    PermissionError,
    SymlinkError,
)

WINDOWS_PATH_LIMIT = 260


def validate_destination_path(path: Path) -> None:
    """
    Validate that destination path is safe for scaffolding.

    Args:
        path: Destination path to validate

    Raises:
        SymlinkError: If path is a symlink
        MountPointError: If path is a mount point or network path
        PathTooLongError: If path exceeds Windows compatibility limit
        InvalidArgumentError: If path is an existing file, not a directory
        PermissionError: If path is not writable
    """
    # Check for invalid characters (null bytes) first — any OS-facing call
    # below (is_symlink, resolve, ...) raises a raw ValueError on a null byte
    # instead of failing cleanly, so this must run before them.
    if "\x00" in str(path):
        raise PathTooLongError(
            "Destination path contains invalid characters (null byte)."
        )

    # Check path length (Windows compatibility) before any filesystem-facing
    # call below — on Linux/macOS, a single path component longer than the
    # filesystem's NAME_MAX makes is_symlink()/ismount()/resolve() raise a
    # raw OSError ("File name too long") instead of failing cleanly, so the
    # cheap string-length check must run first.
    if len(str(path)) > WINDOWS_PATH_LIMIT:
        raise PathTooLongError(
            f"Destination path exceeds {WINDOWS_PATH_LIMIT} characters (Windows compatibility limit)."
        )

    try:
        # Check if symlink
        if path.is_symlink():
            raise SymlinkError(
                f"Symlink not supported as destination: {path}. Use a regular directory."
            )

        # Check if mount point
        if os.path.ismount(path):
            raise MountPointError(
                f"Mount point or network path not supported: {path}. Use a local directory."
            )

        # Check path length again using the resolved absolute path, in case
        # resolving a relative path (e.g. "..") pushes it over the limit.
        resolved_path = str(path.resolve())
    except OSError as e:
        raise PathTooLongError(
            f"Destination path exceeds {WINDOWS_PATH_LIMIT} characters (Windows compatibility limit)."
        ) from e

    if len(resolved_path) > WINDOWS_PATH_LIMIT:
        raise PathTooLongError(
            f"Destination path exceeds {WINDOWS_PATH_LIMIT} characters (Windows compatibility limit)."
        )

    # Reject an existing file destination before probing it as a directory
    if path.exists() and path.is_file():
        raise InvalidArgumentError(
            f"Destination is a file, not a directory: {path}"
        )

    # Try to check if we can write to destination
    # Create a test file in parent directory (or destination if it exists)
    test_dir = path if path.exists() else path.parent
    if test_dir.exists():
        try:
            test_file = test_dir / ".thomas_init_test"
            test_file.touch()
            test_file.unlink()
        except OSError as e:
            raise PermissionError(
                f"Permission denied: cannot write to {test_dir}. Check directory permissions."
            ) from e


def ensure_destination_exists(path: Path) -> Path:
    """
    Ensure destination directory exists and is valid.

    Args:
        path: Directory path to ensure

    Returns:
        Resolved absolute path

    Raises:
        InvalidArgumentError: If path is a file (not directory)
        OSError: If directory creation fails
    """
    # If path exists and is a file, reject
    if path.exists() and path.is_file():
        raise InvalidArgumentError(
            f"Destination is a file, not a directory: {path}"
        )

    # Create directory if it doesn't exist
    path.mkdir(parents=True, exist_ok=True)

    return path.resolve()
