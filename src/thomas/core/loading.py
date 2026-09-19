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


def _check_schema_version(document: Any, file_path: Path) -> None:
    found_version = document.get("schema_version") if isinstance(document, dict) else None
    if found_version != SUPPORTED_SCHEMA_VERSION:
        raise ThomasFileError([
            (
                str(file_path),
                f"unsupported schema_version: expected {SUPPORTED_SCHEMA_VERSION}, found {found_version!r}",
            )
        ])


def _validate_against_schema(document: Any, file_path: Path, schema_name: str) -> None:
    schema = _load_schema(schema_name)
    try:
        jsonschema.validate(document, schema)
    except jsonschema.ValidationError as exc:
        field = "/".join(str(part) for part in exc.absolute_path) or "<root>"
        raise ThomasFileError([(str(file_path), f"invalid field '{field}': {exc.message}")]) from exc


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

    _check_schema_version(document, file_path)
    _validate_against_schema(document, file_path, schema_name)

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


def _find_project_root() -> Path:
    """Find project root by looking for .git or pyproject.toml, starting from cwd."""
    current = Path.cwd()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return current


def load_scenarios(path: Path, project_root: Path | None = None) -> list[LoadedScenario]:
    """Discover and validate every scenario under `path`, failing all-at-once.

    If `path` is a folder, every discovered .json file is treated as a scenario
    (FR-003). All discovered files are validated before any is accepted; if one
    or more are invalid, a single ThomasFileError is raised listing every
    offending file (FR-001 clarification). If no scenario file is discoverable,
    a ThomasFileError is raised as well (FR-003 clarification).

    Scenario file paths are recorded relative to project_root if provided and the
    file is within the project; otherwise recorded relative to the discovery root.
    """
    root = path if path.is_dir() else path.parent
    files = discover_scenario_files(path)
    if project_root is None:
        project_root = _find_project_root()

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
        resolved_path = file_path.resolve()
        try:
            scenario_file = str(resolved_path.relative_to(project_root))
        except ValueError:
            scenario_file = str(resolved_path)
        loaded.append(
            LoadedScenario(
                document=document,
                scenario_file=scenario_file,
                folder=str(relative.parent) if str(relative.parent) != "." else "",
            )
        )

    if errors:
        raise ThomasFileError(errors)

    return loaded


def load_environment(file_path: Path) -> dict:
    """Load and validate an environment file, including multi-API imperative checks.

    Beyond the standard parse/version/schema-validate pipeline, this enforces
    rules not expressible in JSON Schema alone (data-model.md "Environment"
    validation rules): `api`/`apis` mutual exclusion (FR-019), duplicate API
    names within `apis` (FR-018, detected via a duplicate-key-aware JSON parse
    since a plain `json.loads` silently collapses duplicate keys), and — when
    `apis` has 2+ entries — exactly one `default: true` entry (FR-006).
    """
    try:
        raw_text = file_path.read_text()
    except OSError as exc:
        raise ThomasFileError([(str(file_path), f"could not read file: {exc}")]) from exc

    duplicate_keys: list[str] = []

    def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict:
        seen: set[str] = set()
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                duplicate_keys.append(key)
            seen.add(key)
            result[key] = value
        return result

    try:
        document = json.loads(raw_text, object_pairs_hook=_pairs_hook)
    except json.JSONDecodeError as exc:
        raise ThomasFileError([(str(file_path), f"invalid JSON: {exc}")]) from exc

    _check_schema_version(document, file_path)

    has_api = isinstance(document, dict) and "api" in document
    has_apis = isinstance(document, dict) and "apis" in document
    if has_api and has_apis:
        raise ThomasFileError([
            (str(file_path), "environment declares both 'api' and 'apis'; only one is allowed")
        ])

    if duplicate_keys:
        raise ThomasFileError([
            (str(file_path), f"duplicate key(s) in JSON object: {', '.join(sorted(set(duplicate_keys)))}")
        ])

    _validate_against_schema(document, file_path, "environment_v1.json")

    if has_apis:
        apis = document["apis"]
        if len(apis) >= 2:
            default_names = [name for name, config in apis.items() if config.get("default") is True]
            if not default_names:
                raise ThomasFileError([
                    (
                        str(file_path),
                        'ambiguous environment: no default API declared (exactly one entry in \'apis\' must have "default": true)',
                    )
                ])
            if len(default_names) > 1:
                raise ThomasFileError([
                    (
                        str(file_path),
                        f"ambiguous environment: multiple default APIs declared: {', '.join(default_names)}",
                    )
                ])

    return document


def resolve_apis(environment: dict) -> tuple[dict, str]:
    """Normalize an environment's `api`/`apis` config into one uniform shape.

    Assumes the environment already passed `load_environment`'s validation
    (mutual exclusion, no duplicate names, exactly one default when 2+ APIs
    are declared). Returns `(resolved_apis, default_api_name)` per
    data-model.md:

    - Legacy `api` present -> `{"default": {...api}}`, default name `"default"`.
    - `apis` with exactly 1 entry -> that entry is the default regardless of
      its own `default` flag.
    - `apis` with 2+ entries -> the entry marked `default: true` is the default.

    Each entry's `default` key is stripped from the returned config (it is a
    selection flag, not part of the API's request configuration).
    """
    apis = environment.get("apis")
    if apis is None:
        api = environment["api"]
        return {"default": dict(api)}, "default"

    def _strip_default_flag(config: dict) -> dict:
        return {key: value for key, value in config.items() if key != "default"}

    if len(apis) == 1:
        [(name, config)] = apis.items()
        return {name: _strip_default_flag(config)}, name

    default_name = next(name for name, config in apis.items() if config.get("default") is True)
    normalized = {name: _strip_default_flag(config) for name, config in apis.items()}
    return normalized, default_name


def resolve_environment_path(environment_name: str, project_root: Path) -> Path:
    """Find the single `config/environments/*.json` file whose `environment_name` matches.

    Used to auto-resolve `--environment` from an execution record's recorded
    environment name when the flag is omitted on `validate`/`report`. Raises
    ThomasFileError if zero or more than one file matches.
    """
    environments_dir = project_root / "config" / "environments"
    candidates = sorted(environments_dir.glob("*.json")) if environments_dir.is_dir() else []

    matches: list[Path] = []
    for candidate in candidates:
        try:
            document = load_and_validate(candidate, "environment_v1.json")
        except ThomasFileError:
            continue
        if document.get("environment_name") == environment_name:
            matches.append(candidate)

    if len(matches) == 1:
        return matches[0]

    message = (
        f"could not auto-resolve environment {environment_name!r} from "
        f"{environments_dir} ({len(matches)} matching file(s) found); "
        "pass --environment explicitly"
    )
    raise ThomasFileError([(environment_name, message)])


def load_variables(file_path: Path) -> dict[str, Any]:
    document = load_and_validate(file_path, "variables_v1.json")
    return document["variables"]
