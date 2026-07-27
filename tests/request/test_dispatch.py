
import responses
from requests.exceptions import ConnectionError

from thomas.core.loading import LoadedScenario
from thomas.request.dispatch import dispatch_scenario, poll_services_info


def make_scenario(**overrides) -> LoadedScenario:
    document = {
        "schema_version": 1,
        "feature": "instant_transfer",
        "scenario_id": "valid_amount_transfer",
        "endpoint": {"method": "POST", "path": "/orders"},
        "payload": {"amount": 150.0},
        "correlation": {"source": "api_response", "field": "$.id"},
        "api_checks": [
            {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201},
            {"id": "status", "field": "$.status", "operator": "equals", "expected_value": "PENDING"},
        ],
        "validations": [],
    }
    document.update(overrides.pop("document_overrides", {}))
    return LoadedScenario(document=document, scenario_file="a.json", folder="")


@responses.activate
def test_dispatch_scenario_happy_path():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        make_scenario(),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    assert result.api_result == "passed"
    assert result.final_status == "passed"
    assert result.correlation_id == "abc-123"
    assert result.request_technical_error is None
    assert result.response_timestamp is not None
    assert result.response_timestamp >= result.request_timestamp


@responses.activate
def test_dispatch_scenario_failing_api_check():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "REJECTED"},
        status=201,
    )

    result = dispatch_scenario(
        make_scenario(),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    assert result.api_result == "failed"
    assert result.final_status == "failed"
    failing_checks = [c for c in result.api_checks_result if not c["passed"]]
    assert len(failing_checks) == 1
    assert failing_checks[0]["id"] == "status"


@responses.activate
def test_dispatch_scenario_awaiting_validation():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        make_scenario(document_overrides={"validations": [{"id": "x"}]}),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    assert result.final_status == "awaiting_validation"


@responses.activate
def test_dispatch_scenario_network_technical_failure():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        body=ConnectionError("connection refused"),
    )

    result = dispatch_scenario(
        make_scenario(),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    assert result.request_technical_error is not None
    assert result.api_response is None
    assert result.api_result == "failed"
    assert result.final_status == "failed"
    assert result.response_timestamp is None


@responses.activate
def test_dispatch_scenario_correlation_failure_forces_failed_status():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"status": "PENDING"},  # no "id" field — correlation.field "$.id" won't resolve
        status=201,
    )

    result = dispatch_scenario(
        make_scenario(document_overrides={
            "api_checks": [
                {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201}
            ],
        }),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    assert result.api_result == "passed"
    assert result.correlation_id is None
    assert result.correlation_error is not None
    assert result.final_status == "failed"


@responses.activate
def test_dispatch_scenario_correlation_from_variable():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        make_scenario(
            document_overrides={
                "correlation": {"source": "variable", "field": "request_id"},
            }
        ),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={"request_id": "req-abc-123"},
    )

    assert result.correlation_id == "req-abc-123"
    assert result.correlation_error is None
    assert result.api_result == "passed"


@responses.activate
def test_dispatch_scenario_resolves_variables_in_path():
    responses.add(
        responses.GET,
        "https://example.test/api/users/12345",
        json={"id": "12345", "name": "Alice"},
        status=200,
    )

    result = dispatch_scenario(
        make_scenario(
            document_overrides={
                "endpoint": {"method": "GET", "path": "/users/{{user_id}}"},
                "payload": None,
                "api_checks": [
                    {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 200}
                ],
            }
        ),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={"user_id": "12345"},
    )

    assert result.api_result == "passed"
    assert result.final_status == "passed"


@responses.activate
def test_dispatch_scenario_resolves_variables_in_api_checks():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        make_scenario(
            document_overrides={
                "api_checks": [
                    {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": "{{expected_status}}"}
                ],
            }
        ),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={"expected_status": 201},
    )

    assert result.api_result == "passed"
    assert result.api_checks_result[0]["expected"] == 201
    assert result.api_checks_result[0]["passed"] is True


@responses.activate
def test_poll_services_info_isolates_failures():
    responses.add(responses.GET, "https://good.test/info", json={"version": "1.0", "status": "online"}, status=200)
    responses.add(responses.GET, "https://bad.test/info", body=ConnectionError("down"))

    services_info = [
        {"name": "good-service", "info_url": "https://good.test/info", "fields_to_extract": ["version"]},
        {"name": "bad-service", "info_url": "https://bad.test/info"},
    ]

    results = poll_services_info(services_info)

    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200
    assert results[0]["data"] == {"version": "1.0"}
    assert results[1]["error"] is not None
    assert results[1]["status_code"] is None
    assert results[1]["data"] is None


@responses.activate
def test_poll_services_info_records_entire_body_when_no_fields_specified():
    responses.add(responses.GET, "https://svc.test/health", json={"version": "2.0", "status": "healthy", "uptime_ms": 500000}, status=200)

    services_info = [
        {"name": "service", "info_url": "https://svc.test/health"},
    ]

    results = poll_services_info(services_info)

    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200
    assert results[0]["data"] == {"version": "2.0", "status": "healthy", "uptime_ms": 500000}


@responses.activate
def test_poll_services_info_extracts_specific_fields():
    responses.add(responses.GET, "https://db.test/info", json={"version": "14.5", "connections": 42, "replication_lag_ms": 0}, status=200)

    services_info = [
        {"name": "database", "info_url": "https://db.test/info", "fields_to_extract": ["version", "connections"]},
    ]

    results = poll_services_info(services_info)

    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200
    assert results[0]["data"] == {"version": "14.5", "connections": 42}


@responses.activate
def test_poll_services_info_handles_non_json_response():
    responses.add(responses.GET, "https://html.test/info", body="<html>Not JSON</html>", status=200, content_type="text/html")

    services_info = [
        {"name": "service", "info_url": "https://html.test/info"},
    ]

    results = poll_services_info(services_info)

    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200
    assert results[0]["data"] is None
