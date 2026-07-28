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
        InvalidArgumentError: If path is a file (not directory)
        SymlinkError: If path is a symlink
        MountPointError: If path is a mount point or network path
        PathTooLongError: If path exceeds Windows compatibility limit
        PermissionError: If path is not writable
    """
    # Check if path is a file
    if path.exists() and path.is_file():
        raise InvalidArgumentError(
            f"Destination is a file, not a directory: {path}"
        )

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

    # Check path length (Windows compatibility)
    resolved_path = str(path.resolve())
    if len(resolved_path) > WINDOWS_PATH_LIMIT:
        raise PathTooLongError(
            f"Destination path exceeds {WINDOWS_PATH_LIMIT} characters (Windows compatibility limit)."
        )

    # Check for invalid characters (null bytes)
    if "\x00" in str(path):
        raise PathTooLongError(
            "Destination path contains invalid characters (null byte)."
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
