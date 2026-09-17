"""extract_variables resolution: pull values out of a scenario's own API response
and write them into the shared, mutable `variables` dict so later scenarios in the
same `thomas request` run can consume them via {{variable}} placeholders.

See docs/architecture/03-data-schemas.md §1 ("extract_variables") and
specs/017-extract-variables-chaining/research.md §2 (success gate) and §4
(halt-on-failure, no rollback).
"""

from __future__ import annotations

import logging
from typing import Any

from jsonpath_ng.ext import parse as parse_jsonpath

logger = logging.getLogger("thomas")


def resolve_extract_variables(
    extract_variables: list[dict[str, Any]] | None,
    *,
    response_body: object,
    variables: dict[str, Any],
    scenario_file: str | None = None,
) -> list[dict[str, Any]]:
    """Resolve each declared extraction in order, mutating `variables` in place.

    Stops processing (no rollback of prior successes) at the first item whose
    json_path does not resolve. Duplicate as_variable names across items are
    allowed; the later successful item wins and a warning is logged.
    """
    if not extract_variables:
        return []

    seen_as_variable: set[str] = set()
    results: list[dict[str, Any]] = []

    for item in extract_variables:
        json_path = item["json_path"]
        as_variable = item["as_variable"]

        if as_variable in seen_as_variable:
            logger.warning(
                "Scenario %s: duplicate extract_variables.as_variable '%s' — later item wins",
                scenario_file,
                as_variable,
            )
        seen_as_variable.add(as_variable)

        matches = parse_jsonpath(json_path).find(response_body)
        if not matches:
            results.append(
                {
                    "json_path": json_path,
                    "as_variable": as_variable,
                    "success": False,
                    "error": f"json_path '{json_path}' did not resolve in the response body",
                }
            )
            break

        variables[as_variable] = matches[0].value
        results.append(
            {
                "json_path": json_path,
                "as_variable": as_variable,
                "success": True,
                "error": None,
            }
        )

    return results
