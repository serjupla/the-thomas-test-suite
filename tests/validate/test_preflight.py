import json

from thomas.validate.preflight import check_missing_connectors


def _write_scenario(tmp_path, filename, validations):
    scenario = {
        "schema_version": 1,
        "feature": "transfers",
        "scenario_id": "sc1",
        "endpoint": {"method": "POST", "path": "/orders"},
        "correlation": {"source": "api_response", "field": "id"},
        "api_checks": [],
        "validations": validations,
    }
    (tmp_path / filename).write_text(json.dumps(scenario))
    return filename


def _scenario_result(scenario_file, scenario_id="sc1", api_result="passed"):
    return {
        "scenario_file": scenario_file,
        "scenario_id": scenario_id,
        "api_result": api_result,
    }


def test_single_missing_connector_is_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenario_file = _write_scenario(
        tmp_path, "sc1.json",
        [{"id": "v1", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 1}],
    )
    execution_record = {"results": [_scenario_result(scenario_file)]}
    environment = {"connectors": {}}

    missing = check_missing_connectors(execution_record, environment)

    assert missing == [("fake_main", "sc1")]


def test_multiple_missing_connectors_across_scenarios_all_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenario_file_1 = _write_scenario(
        tmp_path, "sc1.json",
        [{"id": "v1", "connector": "conn_a", "field": "balance", "operator": "equals", "expected_value": 1}],
    )
    scenario_file_2 = _write_scenario(
        tmp_path, "sc2.json",
        [{"id": "v1", "connector": "conn_b", "field": "balance", "operator": "equals", "expected_value": 1}],
    )
    execution_record = {
        "results": [
            _scenario_result(scenario_file_1, scenario_id="sc1"),
            _scenario_result(scenario_file_2, scenario_id="sc2"),
        ]
    }
    environment = {"connectors": {}}

    missing = check_missing_connectors(execution_record, environment)

    assert set(missing) == {("conn_a", "sc1"), ("conn_b", "sc2")}


def test_connector_referenced_only_by_ineligible_scenario_not_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenario_file = _write_scenario(
        tmp_path, "sc1.json",
        [{"id": "v1", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 1}],
    )
    execution_record = {"results": [_scenario_result(scenario_file, api_result="failed")]}
    environment = {"connectors": {}}

    missing = check_missing_connectors(execution_record, environment)

    assert missing == []
