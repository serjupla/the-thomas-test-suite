import json
from datetime import datetime, timezone
from importlib import resources

import jsonschema

from thomas import __version__ as THOMAS_VERSION
from thomas.core.execution_record import (
    ScenarioResult,
    build_execution_record,
    write_execution_record,
)


def make_result(**overrides) -> ScenarioResult:
    defaults = {
        "scenario_file": "a.json",
        "feature": "instant_transfer",
        "scenario_id": "valid_amount_transfer",
        "folder": "",
        "correlation_id": "abc-123",
        "correlation_error": None,
        "request_timestamp": "2026-07-25T14:30:02-03:00",
        "response_timestamp": "2026-07-25T14:30:02.340000-03:00",
        "request_sent": {"method": "POST", "path": "/orders", "payload": {}},
        "api_response": {"status_code": 201, "body": {"id": "abc-123"}},
        "request_technical_error": None,
        "api_checks_result": [
            {"id": "http_status", "expected": 201, "obtained": 201, "operator": "equals", "passed": True}
        ],
        "api_result": "passed",
        "final_status": "passed",
    }
    defaults.update(overrides)
    return ScenarioResult(**defaults)


def load_execution_schema() -> dict:
    schema_text = resources.files("thomas.schemas").joinpath("execution_v1.json").read_text()
    return json.loads(schema_text)


def test_execution_record_validates_against_schema(tmp_path):
    record = build_execution_record(
        environment_name="dev",
        timezone_name="America/Sao_Paulo",
        start_time=datetime(2026, 7, 25, 14, 30, tzinfo=timezone.utc),
        included_scenarios=["a.json"],
        services_info=[{"name": "svc", "collected_at": "2026-07-25T14:30:01-03:00", "status_code": 200, "error": None, "data": {"version": "1.0"}}],
        results=[make_result()],
    )

    jsonschema.validate(record, load_execution_schema())

    assert record["results"][0]["validation_rounds"] == []


def test_execution_record_includes_thomas_version(tmp_path):
    record = build_execution_record(
        environment_name="dev",
        timezone_name="America/Sao_Paulo",
        start_time=datetime(2026, 7, 25, 14, 30, tzinfo=timezone.utc),
        included_scenarios=["a.json"],
        services_info=[],
        results=[make_result()],
    )

    assert record["thomas_version"] == THOMAS_VERSION


def test_final_status_passed_no_validations():
    result = make_result(final_status="passed")
    assert result.to_dict()["final_status"] == "passed"


def test_response_timestamp_recorded_alongside_request_timestamp():
    result = make_result()
    as_dict = result.to_dict()
    assert as_dict["request_timestamp"] == "2026-07-25T14:30:02-03:00"
    assert as_dict["response_timestamp"] == "2026-07-25T14:30:02.340000-03:00"


def test_response_timestamp_null_on_request_technical_failure():
    result = make_result(
        response_timestamp=None,
        api_response=None,
        request_technical_error="connection refused",
        api_result="failed",
        final_status="failed",
    )
    assert result.to_dict()["response_timestamp"] is None


def test_final_status_awaiting_validation():
    result = make_result(final_status="awaiting_validation")
    assert result.to_dict()["final_status"] == "awaiting_validation"


def test_final_status_failed():
    result = make_result(
        final_status="failed",
        api_result="failed",
        api_checks_result=[
            {"id": "http_status", "expected": 201, "obtained": 500, "operator": "equals", "passed": False}
        ],
    )
    assert result.to_dict()["final_status"] == "failed"
    assert result.to_dict()["api_checks_result"][0]["passed"] is False


def test_write_execution_record_creates_file(tmp_path):
    record = build_execution_record(
        environment_name="dev",
        timezone_name="America/Sao_Paulo",
        start_time=datetime(2026, 7, 25, 14, 30, tzinfo=timezone.utc),
        included_scenarios=["a.json"],
        services_info=[],
        results=[make_result()],
    )

    output_path = write_execution_record(record, tmp_path)

    assert output_path.exists()
    on_disk = json.loads(output_path.read_text())
    assert on_disk["execution_id"] == record["execution_id"]
