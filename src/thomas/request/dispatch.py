"""`thomas request` orchestration: /info polling, sequential HTTP dispatch,
api_checks evaluation, and execution record assembly.

See docs/architecture/01-overview.md Step 1 and 07-cli-commands.md.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from jsonpath_ng.ext import parse as parse_jsonpath

from thomas.core.correlation import resolve_correlation
from thomas.core.execution_record import (
    ScenarioResult,
    build_execution_record,
    write_execution_record,
)
from thomas.core.loading import LoadedScenario
from thomas.core.variables import resolve_payload
from thomas.operators import engine

logger = logging.getLogger("thomas")


def poll_services_info(services_info: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sequentially GET every services_info[].info_url, isolating per-service failures (FR-009, FR-010).

    Records the HTTP response regardless of status code. Only connection/timeout errors are recorded
    as technical failures (FR-010). If fields_to_extract is specified, extracts only those fields;
    otherwise records the entire response body.
    """
    results: list[dict[str, Any]] = []
    for service in services_info:
        collected_at = datetime.now(timezone.utc).isoformat()
        entry: dict[str, Any] = {"name": service["name"], "collected_at": collected_at, "error": None, "status_code": None}
        try:
            response = requests.get(service["info_url"], timeout=10)
            entry["status_code"] = response.status_code
            # Record any successful connection, regardless of status code (404, 500, etc. are still valid responses)
            try:
                body = response.json()
                if isinstance(body, dict):
                    fields_to_extract = service.get("fields_to_extract")
                    if fields_to_extract:
                        entry["data"] = {field: body.get(field) for field in fields_to_extract}
                    else:
                        entry["data"] = body
                else:
                    entry["data"] = body
            except ValueError:
                # Body is not JSON; record null data
                entry["data"] = None
            logger.debug("services_info[%s] responded: status=%s", service["name"], response.status_code)
        except requests.RequestException as exc:
            # Only connection/timeout errors are recorded as technical failures
            entry["error"] = str(exc)
            entry["status_code"] = None
            entry["data"] = None
            logger.debug("services_info[%s] failed: %s", service["name"], exc)
        results.append(entry)
    return results


def _resolve_field(field: str, status_code: int, body: Any) -> Any:
    if field == "status_code":
        return status_code
    matches = parse_jsonpath(field).find(body)
    return matches[0].value if matches else None


def _evaluate_api_checks(
    checks: list[dict[str, Any]], status_code: int, body: Any, variables: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    results = []
    for check in checks:
        obtained = _resolve_field(check["field"], status_code, body)
        # Resolve variables in expected_value (e.g., "{{expected_status}}" → 200)
        expected = resolve_payload(check["expected_value"], variables or {})
        outcome = engine.evaluate(obtained, check["operator"], expected)
        results.append(
            {
                "id": check["id"],
                "expected": expected,
                "obtained": outcome.obtained_value,
                "operator": check["operator"],
                "passed": outcome.passed,
            }
        )
    return results


def _compute_final_status(api_result: str, correlation_error: str | None, has_validations: bool) -> str:
    if api_result == "failed" or correlation_error is not None:
        return "failed"
    if has_validations:
        return "awaiting_validation"
    return "passed"


def dispatch_scenario(
    scenario: LoadedScenario,
    *,
    base_url: str,
    timeout_seconds: int,
    variables: dict[str, Any],
) -> ScenarioResult:
    document = scenario.document
    endpoint = document["endpoint"]
    resolved_path = resolve_payload(endpoint["path"], variables)
    resolved_payload = resolve_payload(document.get("payload"), variables)
    url = base_url.rstrip("/") + "/" + resolved_path.lstrip("/")
    request_timestamp = datetime.now(timezone.utc).isoformat()

    logger.debug(
        "Dispatching scenario %s: %s %s payload=%s",
        scenario.scenario_file,
        endpoint["method"],
        url,
        resolved_payload,
    )

    try:
        response = requests.request(
            endpoint["method"],
            url,
            json=resolved_payload,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        logger.debug("Scenario %s request technical failure: %s", scenario.scenario_file, exc)
        return ScenarioResult(
            scenario_file=scenario.scenario_file,
            feature=document["feature"],
            scenario_id=document["scenario_id"],
            folder=scenario.folder,
            correlation_id=None,
            correlation_error=None,
            request_timestamp=request_timestamp,
            response_timestamp=None,
            request_sent={"method": endpoint["method"], "path": resolved_path, "payload": resolved_payload},
            api_response=None,
            request_technical_error=str(exc),
            api_checks_result=[],
            api_result="failed",
            final_status="failed",
        )

    response_timestamp = datetime.now(timezone.utc).isoformat()

    try:
        body = response.json()
    except ValueError:
        body = response.text

    logger.debug(
        "Scenario %s response: status=%s body=%s",
        scenario.scenario_file,
        response.status_code,
        body,
    )

    api_checks_result = _evaluate_api_checks(document["api_checks"], response.status_code, body, variables)
    api_result = "passed" if all(c["passed"] for c in api_checks_result) else "failed"

    correlation = document.get("correlation")
    correlation_result = resolve_correlation(
        correlation,
        response_body=body,
        resolved_payload=resolved_payload,
        variables=variables,
    )

    has_validations = bool(document.get("validations"))
    final_status = _compute_final_status(api_result, correlation_result.correlation_error, has_validations)

    return ScenarioResult(
        scenario_file=scenario.scenario_file,
        feature=document["feature"],
        scenario_id=document["scenario_id"],
        folder=scenario.folder,
        correlation_id=correlation_result.correlation_id,
        correlation_error=correlation_result.correlation_error,
        request_timestamp=request_timestamp,
        response_timestamp=response_timestamp,
        request_sent={"method": endpoint["method"], "path": resolved_path, "payload": resolved_payload},
        api_response={"status_code": response.status_code, "body": body},
        request_technical_error=None,
        api_checks_result=api_checks_result,
        api_result=api_result,
        final_status=final_status,
    )


def run_request(
    *,
    environment: dict[str, Any],
    scenarios: Iterable[LoadedScenario],
    variables: dict[str, Any],
    output_dir: Path,
    progress_callback=None,
) -> Path:
    """Execute the full `thomas request` flow and write the execution record. Returns the written file path."""
    scenarios = list(scenarios)
    start_time = datetime.now(timezone.utc)

    services_info = poll_services_info(environment.get("services_info", []))

    base_url = environment["api"]["base_url"]
    timeout_seconds = environment["api"].get("timeout_seconds", 30)

    results = []
    for scenario in scenarios:
        result = dispatch_scenario(
            scenario,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            variables=variables,
        )
        results.append(result)
        if progress_callback is not None:
            progress_callback(scenario, result)

    record = build_execution_record(
        environment_name=environment["environment_name"],
        timezone_name=environment["timezone"],
        start_time=start_time,
        included_scenarios=[s.scenario_file for s in scenarios],
        services_info=services_info,
        results=results,
    )

    return write_execution_record(record, output_dir)
