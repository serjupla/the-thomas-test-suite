import json
from datetime import datetime, timezone

from thomas.connectors.fake import FakeConnector
from thomas.validate.orchestrator import (
    _run_single_validation,
    build_validation_round,
    compute_final_status,
    run_validate,
)

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


def test_field_and_query_are_persisted_for_both_success_and_technical_error_checks(tmp_path, monkeypatch):
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
    assert results[0]["field"] == "balance"
    assert results[0]["query"] == "lookup: v_fail"
    assert results[1]["field"] == "balance"
    assert results[1]["query"] == "lookup: v_ok"


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

    def boom_run_validation(self, validation, correlation_id, request_timestamp):
        if validation["id"] == "v_boom":
            raise RuntimeError("unexpected failure")
        return original_run_validation(self, validation, correlation_id, request_timestamp)

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


# --- Feature 016: FR-008 — comparison uses the original datetime, unaffected by serialization ---


def test_datetime_obtained_comparison_uses_original_datetime_not_a_string():
    obtained_value = datetime(2026, 9, 16, 14, 30, tzinfo=timezone.utc)
    connector = FakeConnector({"values": {"v1": obtained_value}, "failures": {}})
    validation = {
        "id": "v1",
        "connector": "fake_main",
        "field": "obtained_at",
        "operator": "equals",
        "expected_value": obtained_value,
    }

    result = _run_single_validation(connector, validation, "corr-1", "2026-09-16T14:30:00+00:00")

    assert result["obtained"] == obtained_value
    assert isinstance(result["obtained"], datetime)
    assert result["passed"] is True

    mismatched = _run_single_validation(
        connector,
        {**validation, "expected_value": obtained_value.isoformat()},
        "corr-1",
        "2026-09-16T14:30:00+00:00",
    )
    assert mismatched["passed"] is False
