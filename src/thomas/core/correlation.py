"""correlation_id resolution: from the API response body, request payload, or a variable.

See docs/architecture/03-data-schemas.md §1 ("correlation") and the F00
clarification: when correlation.source == "api_response" and the JSONPath
doesn't resolve, this is a distinct technical failure (correlation_error),
not a null pass-through — the scenario's final_status is forced to "failed".
"""

from __future__ import annotations

from dataclasses import dataclass

from jsonpath_ng.ext import parse as parse_jsonpath


@dataclass
class CorrelationResult:
    correlation_id: str | None
    correlation_error: str | None


def resolve_correlation(
    correlation: dict | None,
    *,
    response_body: object,
    resolved_payload: dict | None,
    variables: dict | None = None,
) -> CorrelationResult:
    """Resolve correlation_id per the scenario's declared correlation.source.

    Returns a CorrelationResult with correlation_id=None and no error when
    the scenario declares no correlation block at all (no validations).
    Supports three sources:
    - "api_response": extract from response body via JSONPath
    - "request_payload": extract from resolved payload
    - "variable": extract from variables dict
    """
    if correlation is None:
        return CorrelationResult(correlation_id=None, correlation_error=None)

    source = correlation["source"]
    field = correlation["field"]

    if source == "api_response":
        matches = parse_jsonpath(field).find(response_body)
        if not matches:
            return CorrelationResult(
                correlation_id=None,
                correlation_error=f"correlation.field '{field}' did not resolve in the response body",
            )
        return CorrelationResult(correlation_id=str(matches[0].value), correlation_error=None)

    if source == "request_payload":
        value = (resolved_payload or {}).get(field)
        if value is None:
            return CorrelationResult(
                correlation_id=None,
                correlation_error=f"correlation.field '{field}' not found in the request payload",
            )
        return CorrelationResult(correlation_id=str(value), correlation_error=None)

    if source == "variable":
        value = (variables or {}).get(field)
        if value is None:
            return CorrelationResult(
                correlation_id=None,
                correlation_error=f"correlation.field '{field}' not found in variables",
            )
        return CorrelationResult(correlation_id=str(value), correlation_error=None)

    return CorrelationResult(
        correlation_id=None,
        correlation_error=f"unknown correlation.source: {source}",
    )
