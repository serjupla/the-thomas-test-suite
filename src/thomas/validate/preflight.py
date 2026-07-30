"""Missing-connector pre-flight check (FR-005), run before any connector work."""

from __future__ import annotations

from pathlib import Path

from thomas.validate.orchestrator import is_eligible, load_scenario_validations


def check_missing_connectors(execution_record: dict, environment: dict) -> list[tuple[str, str]]:
    """Return (connector_name, scenario_id) pairs referenced by an eligible
    scenario but absent from environment["connectors"]. Connectors referenced
    only by ineligible scenarios are never considered missing."""
    base_dir = Path.cwd()
    available = environment.get("connectors", {}).keys()

    missing: list[tuple[str, str]] = []
    for scenario_result in execution_record["results"]:
        validations = load_scenario_validations(scenario_result["scenario_file"], base_dir)
        if not is_eligible(scenario_result, validations):
            continue

        referenced = {validation["connector"] for validation in validations}
        for connector_name in referenced:
            if connector_name not in available:
                missing.append((connector_name, scenario_result["scenario_id"]))

    return missing
