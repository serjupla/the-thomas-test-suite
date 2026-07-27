import json
from pathlib import Path

import pytest

from thomas.core.loading import ThomasFileError, load_environment, load_scenarios, load_variables

VALID_SCENARIO = {
    "schema_version": 1,
    "feature": "instant_transfer",
    "scenario_id": "valid_amount_transfer",
    "endpoint": {"method": "POST", "path": "/orders"},
    "payload": {"amount": 150.0},
    "api_checks": [
        {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201}
    ],
}

VALID_ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
}

VALID_VARIABLES = {
    "schema_version": 1,
    "variables": {"valid_bank_account": "12345-6"},
}


def write_json(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document))


def test_load_scenarios_valid_folder(tmp_path):
    write_json(tmp_path / "a.json", VALID_SCENARIO)
    nested = tmp_path / "nested"
    nested.mkdir()
    write_json(nested / "b.json", {**VALID_SCENARIO, "scenario_id": "other"})

    loaded = load_scenarios(tmp_path)

    assert len(loaded) == 2
    files = sorted(s.scenario_file for s in loaded)
    assert files == ["a.json", str(Path("nested") / "b.json")]


def test_load_scenarios_records_folder_for_grouping(tmp_path):
    nested = tmp_path / "instant_transfer"
    nested.mkdir()
    write_json(nested / "a.json", VALID_SCENARIO)

    loaded = load_scenarios(tmp_path)

    assert loaded[0].folder == "instant_transfer"


def test_load_scenarios_single_file(tmp_path):
    scenario_path = tmp_path / "a.json"
    write_json(scenario_path, VALID_SCENARIO)

    loaded = load_scenarios(scenario_path)

    assert len(loaded) == 1
    assert loaded[0].scenario_file == "a.json"


def test_load_scenarios_rejects_incompatible_schema_version(tmp_path):
    write_json(tmp_path / "a.json", {**VALID_SCENARIO, "schema_version": 2})

    with pytest.raises(ThomasFileError):
        load_scenarios(tmp_path)


def test_load_scenarios_rejects_missing_required_field(tmp_path):
    broken = dict(VALID_SCENARIO)
    del broken["endpoint"]
    write_json(tmp_path / "a.json", broken)

    with pytest.raises(ThomasFileError):
        load_scenarios(tmp_path)


def test_load_scenarios_reports_all_invalid_files_at_once(tmp_path):
    write_json(tmp_path / "good.json", VALID_SCENARIO)
    write_json(tmp_path / "bad1.json", {**VALID_SCENARIO, "schema_version": 2})
    write_json(tmp_path / "bad2.json", {"schema_version": 1})

    with pytest.raises(ThomasFileError) as exc_info:
        load_scenarios(tmp_path)

    offending_files = {Path(path).name for path, _ in exc_info.value.errors}
    assert offending_files == {"bad1.json", "bad2.json"}


def test_load_scenarios_empty_folder_aborts(tmp_path):
    with pytest.raises(ThomasFileError) as exc_info:
        load_scenarios(tmp_path)

    assert "no scenarios found" in str(exc_info.value)


def test_load_environment_valid(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)

    document = load_environment(env_path)

    assert document["environment_name"] == "dev"


def test_load_environment_rejects_invalid(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, {"schema_version": 1})

    with pytest.raises(ThomasFileError):
        load_environment(env_path)


def test_load_scenarios_duplicate_feature_and_scenario_id_both_processed(tmp_path):
    write_json(tmp_path / "a.json", VALID_SCENARIO)
    write_json(tmp_path / "b.json", VALID_SCENARIO)

    loaded = load_scenarios(tmp_path)

    assert len(loaded) == 2
    assert all(s.document["scenario_id"] == VALID_SCENARIO["scenario_id"] for s in loaded)


def test_load_variables_valid(tmp_path):
    vars_path = tmp_path / "variables.json"
    write_json(vars_path, VALID_VARIABLES)

    variables = load_variables(vars_path)

    assert variables == {"valid_bank_account": "12345-6"}
