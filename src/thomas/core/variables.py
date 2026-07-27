"""Preparatory variable resolution: {{variable_name}} substitution in scenario payloads."""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


class UndefinedVariableError(Exception):
    """Raised when one or more scenarios reference variables absent from the variables file."""

    def __init__(self, missing: list[tuple[str, str]]):
        self.missing = missing
        joined = "; ".join(f"{scenario}: undefined variable '{name}'" for scenario, name in missing)
        super().__init__(joined)


def _substitute(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        match = _PLACEHOLDER_RE.fullmatch(value)
        if match:
            # Whole-string placeholder: preserve the variable's original type.
            return variables.get(match.group(1), value)

        def replace(m: re.Match) -> str:
            return str(variables.get(m.group(1), m.group(0)))

        return _PLACEHOLDER_RE.sub(replace, value)
    if isinstance(value, dict):
        return {key: _substitute(val, variables) for key, val in value.items()}
    if isinstance(value, list):
        return [_substitute(item, variables) for item in value]
    return value


def resolve_payload(payload: dict[str, Any] | None, variables: dict[str, Any]) -> dict[str, Any] | None:
    """Replace every {{variable_name}} occurrence in payload with its resolved value."""
    if payload is None:
        return None
    return _substitute(payload, variables)


def find_undefined_references(payload: dict[str, Any] | None, variables: dict[str, Any]) -> set[str]:
    """Return the set of variable names referenced in payload but absent from variables."""
    if payload is None:
        return set()

    referenced: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, str):
            referenced.update(_PLACEHOLDER_RE.findall(value))
        elif isinstance(value, dict):
            for val in value.values():
                walk(val)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    return referenced - set(variables.keys())
