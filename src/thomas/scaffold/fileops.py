"""File operations for scaffold creation."""

from pathlib import Path


def copy_template(src_path: str, dst_path: Path, executable: bool = False) -> None:
    """
    Copy template file to destination, preserving metadata.

    Args:
        src_path: Template file path (loaded from package resources)
        dst_path: Destination path (must be a file path, not directory)
        executable: If True, make destination file executable

    Raises:
        OSError: If copy fails due to permissions or other I/O errors
    """
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    # Write template content to destination
    dst_path.write_text(src_path, encoding="utf-8")

    # Make executable if requested
    if executable:
        dst_path.chmod(0o755)


def create_directory_safe(path: Path) -> None:
    """
    Create directory with idempotent semantics (mkdir -p equivalent).

    Args:
        path: Directory path to create

    Raises:
        OSError: If creation fails due to permissions or other I/O errors
    """
    path.mkdir(parents=True, exist_ok=True)


class FileStatusTracker:
    """Track file/directory creation status for reporting."""

    def __init__(self):
        self.created = []
        self.skipped = []
        self.overwritten = []
        self.protected = []

    def report_created(self, file_path: Path) -> None:
        self.created.append(str(file_path.relative_to(file_path.resolve().parents[-1])))

    def report_skipped(self, file_path: Path) -> None:
        self.skipped.append(str(file_path))

    def report_overwritten(self, file_path: Path) -> None:
        self.overwritten.append(str(file_path))

    def report_protected(self, file_path: Path) -> None:
        self.protected.append(str(file_path))

    def get_summary(self) -> dict:
        return {
            "created": self.created,
            "skipped": self.skipped,
            "overwritten": self.overwritten,
            "protected": self.protected,
        }
