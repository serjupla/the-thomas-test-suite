"""Recursive scenario discovery and schema-validated loading of user-supplied JSON files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema

SUPPORTED_SCHEMA_VERSION = 1


class ThomasFileError(Exception):
    """Raised when a user-supplied file fails to parse or validate.

    Carries a list of (file_path, message) pairs so callers can report every
    offending file in a batch at once, instead of aborting on the first one.
    """

    def __init__(self, errors: list[tuple[str, str]]):
        self.errors = errors
        joined = "; ".join(f"{path}: {msg}" for path, msg in errors)
        super().__init__(joined)


def _load_schema(schema_name: str) -> dict:
    schema_text = resources.files("thomas.schemas").joinpath(schema_name).read_text()
    return json.loads(schema_text)


def load_and_validate(file_path: Path, schema_name: str) -> dict:
    """Load a single JSON file and validate it against the given schema.

    Raises ThomasFileError (with a single entry) naming the file and the
    specific invalid field on any parse or validation failure, including an
    incompatible schema_version.
    """
    try:
        raw_text = file_path.read_text()
    except OSError as exc:
        raise ThomasFileError([(str(file_path), f"could not read file: {exc}")]) from exc

    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ThomasFileError([(str(file_path), f"invalid JSON: {exc}")]) from exc

    schema = _load_schema(schema_name)

    found_version = document.get("schema_version") if isinstance(document, dict) else None
    if found_version != SUPPORTED_SCHEMA_VERSION:
        raise ThomasFileError([
            (
                str(file_path),
                f"unsupported schema_version: expected {SUPPORTED_SCHEMA_VERSION}, found {found_version!r}",
            )
        ])

    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        field = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ThomasFileError([(str(file_path), f"invalid field '{field}': {exc.message}")]) from exc

    return document


@dataclass
class LoadedScenario:
    document: dict
    scenario_file: str
    folder: str


def discover_scenario_files(path: Path) -> list[Path]:
    """Return every .json file under `path` (recursively) if it's a directory, or [path] if it's a file."""
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*.json") if p.is_file())


def load_scenarios(path: Path) -> list[LoadedScenario]:
    """Discover and validate every scenario under `path`, failing all-at-once.

    If `path` is a folder, every discovered .json file is treated as a scenario
    (FR-003). All discovered files are validated before any is accepted; if one
    or more are invalid, a single ThomasFileError is raised listing every
    offending file (FR-001 clarification). If no scenario file is discoverable,
    a ThomasFileError is raised as well (FR-003 clarification).
    """
    root = path if path.is_dir() else path.parent
    files = discover_scenario_files(path)

    if not files:
        raise ThomasFileError([(str(path), "no scenarios found")])

    errors: list[tuple[str, str]] = []
    loaded: list[LoadedScenario] = []
    for file_path in files:
        try:
            document = load_and_validate(file_path, "scenario_v1.json")
        except ThomasFileError as exc:
            errors.extend(exc.errors)
            continue

        relative = file_path.relative_to(root) if path.is_dir() else Path(file_path.name)
        loaded.append(
            LoadedScenario(
                document=document,
                scenario_file=str(relative),
                folder=str(relative.parent) if str(relative.parent) != "." else "",
            )
        )

    if errors:
        raise ThomasFileError(errors)

    return loaded


def load_environment(file_path: Path) -> dict:
    return load_and_validate(file_path, "environment_v1.json")


def load_variables(file_path: Path) -> dict[str, Any]:
    document = load_and_validate(file_path, "variables_v1.json")
    return document["variables"]
