"""`thomas validate` orchestration: connects to declared connectors, runs each
eligible scenario's validations, appends a validation round, and recalculates
`final_status`. See docs/architecture/05-connectors.md, data-model.md §2-3.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from thomas.connectors import BaseConnector, resolve_connector_type
from thomas.core.loading import load_and_validate
from thomas.operators import engine


def is_eligible(scenario_result: dict, validations: list[dict]) -> bool:
    return scenario_result["api_result"] == "passed" and len(validations) > 0


def load_scenario_validations(scenario_file: str, base_dir: Path) -> list[dict]:
    from thomas.core.loading import _find_project_root

    project_root = _find_project_root()
    scenario_path = project_root / scenario_file
    document = load_and_validate(scenario_path, "scenario_v1.json")
    return document.get("validations", [])


def build_validation_round(environment_name: str, timestamp: str, validation_results: list[dict]) -> dict:
    round_result = "passed" if all(result["passed"] for result in validation_results) else "failed"
    return {
        "timestamp": timestamp,
        "environment_used": environment_name,
        "results": validation_results,
        "round_result": round_result,
    }


def compute_final_status(api_result: str, has_validations: bool, validation_rounds: list[dict]) -> str:
    if api_result != "passed":
        return "failed"
    if not has_validations:
        return "passed"
    if not validation_rounds:
        return "awaiting_validation"
    return validation_rounds[-1]["round_result"]


def _run_single_validation(connector: BaseConnector, validation: dict, correlation_id: str) -> dict:
    try:
        obtained = connector.run_validation(validation, correlation_id)
    except Exception as exc:  # ConnectorTechnicalError or any other unexpected exception
        return {
            "id": validation["id"],
            "connector": validation["connector"],
            "expected": validation["expected_value"],
            "obtained": None,
            "operator": validation["operator"],
            "passed": False,
            "technical_error": str(exc),
        }

    result = engine.evaluate(obtained, validation["operator"], validation["expected_value"])
    return {
        "id": validation["id"],
        "connector": validation["connector"],
        "expected": validation["expected_value"],
        "obtained": obtained,
        "operator": validation["operator"],
        "passed": result.passed,
        "technical_error": result.technical_error,
    }


def run_validate(execution_record: dict, environment: dict) -> dict:
    base_dir = Path.cwd()
    tz = ZoneInfo(environment["timezone"])
    environment_name = environment["environment_name"]

    scenario_validations: dict[int, list[dict]] = {}
    connector_names: set[str] = set()
    for index, scenario_result in enumerate(execution_record["results"]):
        validations = load_scenario_validations(scenario_result["scenario_file"], base_dir)
        scenario_validations[index] = validations
        if is_eligible(scenario_result, validations):
            connector_names.update(validation["connector"] for validation in validations)

    connectors: dict[str, BaseConnector] = {}
    for name in connector_names:
        connector_config = environment["connectors"][name]
        connector_type = resolve_connector_type(connector_config["type"])
        connector = connector_type(connector_config)
        connector.connect()
        connectors[name] = connector

    try:
        for index, scenario_result in enumerate(execution_record["results"]):
            validations = scenario_validations[index]
            if not is_eligible(scenario_result, validations):
                continue

            correlation_id = scenario_result.get("correlation_id") or ""
            validation_results = [
                _run_single_validation(connectors[validation["connector"]], validation, correlation_id)
                for validation in validations
            ]

            timestamp = datetime.now(tz).isoformat()
            round_entry = build_validation_round(environment_name, timestamp, validation_results)
            scenario_result["validation_rounds"].append(round_entry)
            scenario_result["final_status"] = compute_final_status(
                scenario_result["api_result"], len(validations) > 0, scenario_result["validation_rounds"]
            )
    finally:
        for connector in connectors.values():
            connector.disconnect()

    return execution_record
