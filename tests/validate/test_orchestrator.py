import json

from thomas.connectors.fake import FakeConnector
from thomas.validate.orchestrator import build_validation_round, compute_final_status, run_validate

# --- compute_final_status: FR-010 table ---


def test_final_status_passed_no_validations():
    assert compute_final_status("passed", False, []) == "passed"


def test_final_status_passed_has_validations_no_rounds_yet():
    assert compute_final_status("passed", True, []) == "awaiting_validation"


def test_final_status_passed_has_validations_latest_round_passed():
    rounds = [{"round_result": "failed"}, {"round_result": "passed"}]
    assert compute_final_status("passed", True, rounds) == "passed"


def test_final_status_passed_has_validations_latest_round_failed():
    rounds = [{"round_result": "passed"}, {"round_result": "failed"}]
    assert compute_final_status("passed", True, rounds) == "failed"


def test_final_status_api_result_not_passed_is_always_failed():
    assert compute_final_status("failed", True, [{"round_result": "passed"}]) == "failed"
    assert compute_final_status("failed", False, []) == "failed"


# --- build_validation_round ---


def test_build_validation_round_result_passed_when_all_pass():
    round_entry = build_validation_round(
        "dev", "2026-07-28T10:00:00-03:00",
        [{"passed": True}, {"passed": True}],
    )
    assert round_entry["round_result"] == "passed"
    assert round_entry["environment_used"] == "dev"
    assert round_entry["timestamp"] == "2026-07-28T10:00:00-03:00"


def test_build_validation_round_result_failed_when_any_fails():
    round_entry = build_validation_round(
        "dev", "2026-07-28T10:00:00-03:00",
        [{"passed": True}, {"passed": False}],
    )
    assert round_entry["round_result"] == "failed"


# --- run_validate ---

ENVIRONMENT = {
    "environment_name": "dev",
    "timezone": "America/Sao_Paulo",
    "connectors": {
        "fake_main": {"type": "fake", "values": {"v1": 150.0}, "failures": {}},
    },
}


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
    path = tmp_path / filename
    path.write_text(json.dumps(scenario))
    return filename


def _scenario_result(scenario_file, api_result="passed"):
    return {
        "scenario_file": scenario_file,
        "feature": "transfers",
        "scenario_id": "sc1",
        "folder": "",
        "correlation_id": "corr-1",
        "correlation_error": None,
        "request_timestamp": "2026-07-28T09:00:00-03:00",
        "response_timestamp": "2026-07-28T09:00:01-03:00",
        "request_sent": {"method": "POST", "path": "/orders", "payload": {}},
        "api_response": {"status_code": 201, "body": {}},
        "request_technical_error": None,
        "api_checks_result": [],
        "api_result": api_result,
        "validation_rounds": [],
        "final_status": "awaiting_validation" if api_result == "passed" else "failed",
    }


def test_run_validate_ineligible_scenario_is_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenario_file = _write_scenario(
        tmp_path, "sc1.json",
        [{"id": "v1", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 150.0}],
    )
    execution_record = {"results": [_scenario_result(scenario_file, api_result="failed")]}

    updated = run_validate(execution_record, ENVIRONMENT)

    assert updated["results"][0]["validation_rounds"] == []
    assert updated["results"][0]["final_status"] == "failed"


def test_run_validate_connector_reused_across_scenarios(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    connect_calls = []
    original_connect = FakeConnector.connect
    monkeypatch.setattr(FakeConnector, "connect", lambda self: (connect_calls.append(1), original_connect(self)))

    scenario_file_1 = _write_scenario(
        tmp_path, "sc1.json",
        [{"id": "v1", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 150.0}],
    )
    scenario_file_2 = _write_scenario(
        tmp_path, "sc2.json",
        [{"id": "v1", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 150.0}],
    )
    execution_record = {
        "results": [_scenario_result(scenario_file_1), _scenario_result(scenario_file_2)],
    }

    updated = run_validate(execution_record, ENVIRONMENT)

    assert len(updated["results"][0]["validation_rounds"]) == 1
    assert len(updated["results"][1]["validation_rounds"]) == 1
    assert updated["results"][0]["final_status"] == "passed"
    assert updated["results"][1]["final_status"] == "passed"
    assert len(connect_calls) == 1


# --- technical-error vs. assertion-failure distinction (US3) ---

ENVIRONMENT_WITH_FAILURE = {
    "environment_name": "dev",
    "timezone": "America/Sao_Paulo",
    "connectors": {
        "fake_main": {
            "type": "fake",
            "values": {"v_ok": 999.0},
            "failures": {"v_fail": "connection timed out"},
        },
    },
}


def test_connector_technical_error_captured_without_aborting_scenario(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenario_file = _write_scenario(
        tmp_path, "sc1.json",
        [
            {"id": "v_fail", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 1},
            {"id": "v_ok", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 999.0},
        ],
    )
    execution_record = {"results": [_scenario_result(scenario_file)]}

    updated = run_validate(execution_record, ENVIRONMENT_WITH_FAILURE)

    results = updated["results"][0]["validation_rounds"][0]["results"]
    assert results[0]["technical_error"] == "connection timed out"
    assert results[0]["passed"] is False
    assert results[1]["technical_error"] is None
    assert results[1]["passed"] is True


def test_unexpected_exception_during_run_validation_is_captured_per_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenario_file_1 = _write_scenario(
        tmp_path, "sc1.json",
        [
            {"id": "v_boom", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 1},
            {"id": "v_ok", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 999.0},
        ],
    )
    scenario_file_2 = _write_scenario(
        tmp_path, "sc2.json",
        [{"id": "v_ok", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 999.0}],
    )
    execution_record = {
        "results": [_scenario_result(scenario_file_1), _scenario_result(scenario_file_2)],
    }

    original_run_validation = FakeConnector.run_validation

    def boom_run_validation(self, validation, correlation_id):
        if validation["id"] == "v_boom":
            raise RuntimeError("unexpected failure")
        return original_run_validation(self, validation, correlation_id)

    monkeypatch.setattr(FakeConnector, "run_validation", boom_run_validation)

    updated = run_validate(execution_record, ENVIRONMENT_WITH_FAILURE)

    scenario1_results = updated["results"][0]["validation_rounds"][0]["results"]
    assert scenario1_results[0]["technical_error"] == "unexpected failure"
    assert scenario1_results[0]["passed"] is False
    assert scenario1_results[1]["technical_error"] is None
    assert scenario1_results[1]["passed"] is True

    scenario2_results = updated["results"][1]["validation_rounds"][0]["results"]
    assert scenario2_results[0]["technical_error"] is None
    assert scenario2_results[0]["passed"] is True
