import re
from importlib import metadata
from pathlib import Path

_DIST_NAME = "the-thomas-test-suite"


def _source_tree_version() -> str | None:
    """Version from the project's own pyproject.toml when running from a source
    checkout (editable install). Installed-package metadata is only refreshed on
    reinstall, so in a checkout it goes stale after every version bump."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    project_table = re.search(r"^\[project\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
    if project_table is None or f'name = "{_DIST_NAME}"' not in project_table.group(1):
        return None
    version = re.search(r'^version\s*=\s*"([^"]+)"', project_table.group(1), re.MULTILINE)
    return version.group(1) if version else None


def _resolve_version() -> str:
    source_version = _source_tree_version()
    if source_version:
        return source_version
    try:
        return metadata.version(_DIST_NAME)
    except metadata.PackageNotFoundError:
        return "unknown"


__version__ = _resolve_version()
