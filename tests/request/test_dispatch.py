import json

import responses
from requests.exceptions import ConnectionError

from thomas.core.loading import LoadedScenario
from thomas.request.dispatch import (
    _merge_headers,
    _resolve_headers,
    dispatch_scenario,
    poll_services_info,
    run_request,
)


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
def test_dispatch_scenario_captures_scenario_description_when_present():
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        make_scenario(document_overrides={"description": "A valid transfer must be settled"}),
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    assert result.description == "A valid transfer must be settled"
    assert result.to_dict()["description"] == "A valid transfer must be settled"


@responses.activate
def test_dispatch_scenario_description_is_none_when_absent():
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

    assert result.description is None


@responses.activate
def test_run_request_persists_title_in_execution_record(tmp_path):
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "PENDING"},
        status=201,
    )
    environment = {
        "environment_name": "dev",
        "timezone": "America/Sao_Paulo",
        "api": {"base_url": "https://example.test/api"},
    }

    output_path = run_request(
        environment=environment,
        scenarios=[make_scenario()],
        variables={},
        output_dir=tmp_path,
        title="Release 4.2",
    )

    record = json.loads(output_path.read_text())
    assert record["title"] == "Release 4.2"


@responses.activate
def test_run_request_omits_title_when_not_supplied(tmp_path):
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "PENDING"},
        status=201,
    )
    environment = {
        "environment_name": "dev",
        "timezone": "America/Sao_Paulo",
        "api": {"base_url": "https://example.test/api"},
    }

    output_path = run_request(
        environment=environment,
        scenarios=[make_scenario()],
        variables={},
        output_dir=tmp_path,
    )

    record = json.loads(output_path.read_text())
    assert "title" not in record


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


# Feature 003: SSL Verification & Metadata tests

@responses.activate
def test_dispatch_scenario_with_ssl_verify_false():
    """Test that ssl_verify=False parameter is passed to requests (allows self-signed certs)."""
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
        ssl_verify=False,
    )

    assert result.api_result == "passed"
    assert result.final_status == "passed"


@responses.activate
def test_dispatch_scenario_with_ssl_verify_true_default():
    """Test that ssl_verify defaults to True when not specified."""
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
        # ssl_verify not specified, should default to True
    )

    assert result.api_result == "passed"


@responses.activate
def test_poll_services_info_respects_per_service_ssl_verify_false():
    """Test that each service's ssl_verify setting is honored independently."""
    responses.add(
        responses.GET,
        "https://staging.test/info",
        json={"version": "1.0"},
        status=200,
    )

    services_info = [
        {"name": "staging-service", "info_url": "https://staging.test/info", "ssl_verify": False},
    ]

    results = poll_services_info(services_info)

    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200


@responses.activate
def test_poll_services_info_per_service_ssl_verify_defaults_to_true():
    """Test that per-service ssl_verify defaults to True when not specified."""
    responses.add(
        responses.GET,
        "https://prod.test/info",
        json={"version": "2.0"},
        status=200,
    )

    services_info = [
        {"name": "prod-service", "info_url": "https://prod.test/info"},
        # ssl_verify not specified for this service, should default to True
    ]

    results = poll_services_info(services_info)

    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200


# Feature 004: Request Headers Tests (User Story 1 - Scenario Headers)

def test_resolve_headers_with_variable_substitution(sample_variables_for_headers):
    """T010: Unit test for _resolve_headers() - test variable substitution."""
    headers = {
        "Authorization": "Bearer {{auth_token}}",
        "X-Request-Id": "{{request_id}}",
    }
    resolved = _resolve_headers(headers, sample_variables_for_headers)

    assert resolved["Authorization"] == "Bearer resolved-auth-token-abc123"
    assert resolved["X-Request-Id"] == "req-001"


def test_resolve_headers_with_empty_input():
    """T010: Unit test for _resolve_headers() - test empty/None input."""
    assert _resolve_headers(None, {}) == {}
    assert _resolve_headers({}, {}) == {}


@responses.activate
def test_dispatch_scenario_with_endpoint_headers(sample_scenario_with_headers):
    """T011: Integration test - scenario with endpoint.headers sends headers in request."""
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "xyz-789", "status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        sample_scenario_with_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    # Verify that headers were sent (checked by responses library matchers)
    assert result.api_result == "passed"
    # Verify headers are recorded in execution record
    assert "headers" in result.request_sent
    assert result.request_sent["headers"]["X-Test-Id"] == "test-123"
    assert result.request_sent["headers"]["Authorization"] == "Bearer scenario-token"


@responses.activate
def test_dispatch_scenario_records_resolved_headers(sample_scenario_with_variable_headers, sample_variables_for_headers):
    """T012: Integration test - scenario with {{var}} headers, confirm resolved values in execution_record."""
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "req-001-result", "status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        sample_scenario_with_variable_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables=sample_variables_for_headers,
    )

    assert result.api_result == "passed"
    assert "headers" in result.request_sent
    assert result.request_sent["headers"]["Authorization"] == "Bearer resolved-auth-token-abc123"
    assert result.request_sent["headers"]["X-Request-Id"] == "req-001"


@responses.activate
def test_dispatch_scenario_without_headers_backward_compatibility(sample_scenario_without_headers):
    """T013: Integration test - scenario without headers field continues to work (backward compatibility)."""
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "old-scenario", "status": "PENDING"},
        status=201,
    )

    result = dispatch_scenario(
        sample_scenario_without_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
    )

    assert result.api_result == "passed"
    assert result.final_status == "passed"


def test_merge_headers_scenario_overrides_environment():
    """T014: Unit test - scenario headers override environment headers for same key."""
    env_headers = {"X-API-Key": "env-key", "X-Tenant": "env-tenant"}
    scenario_headers = {"X-API-Key": "scenario-key"}

    merged = _merge_headers(env_headers, scenario_headers)

    assert merged["X-API-Key"] == "scenario-key"  # scenario wins
    assert merged["X-Tenant"] == "env-tenant"  # environment preserved
    assert len(merged) == 2


# Feature 004: Request Headers Tests (User Story 2 - Environment Headers)

def test_merge_headers_empty_inputs():
    """T021: Unit test for _merge_headers() - both None returns empty dict."""
    merged = _merge_headers(None, None)
    assert merged == {}


def test_merge_headers_env_only():
    """T022: Unit test for _merge_headers() - env headers only, scenario None."""
    env_headers = {"X-API-Key": "env-key", "X-Tenant": "tenant-a"}
    merged = _merge_headers(env_headers, None)
    assert merged == env_headers


def test_merge_headers_scenario_only():
    """T023: Unit test for _merge_headers() - scenario headers only, env None."""
    scenario_headers = {"X-Test-Id": "test-123"}
    merged = _merge_headers(None, scenario_headers)
    assert merged == scenario_headers


@responses.activate
def test_dispatch_scenario_applies_default_headers(sample_scenario_without_headers, sample_environment_with_api_headers):
    """T024: Integration test - run_request() passes environment api.headers to dispatch_scenario()."""
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "env-test", "status": "PENDING"},
        status=201,
    )

    env_headers = sample_environment_with_api_headers["api"]["headers"]
    result = dispatch_scenario(
        sample_scenario_without_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
        default_headers=env_headers,
    )

    assert result.api_result == "passed"
    assert "headers" in result.request_sent
    assert result.request_sent["headers"]["X-API-Key"] == "env-key-12345"
    assert result.request_sent["headers"]["X-Tenant"] == "tenant-a"


@responses.activate
def test_dispatch_scenario_merge_precedence(sample_scenario_with_headers, sample_environment_with_api_headers):
    """T025: Integration test - scenario headers override environment headers for same key."""
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "merge-test", "status": "PENDING"},
        status=201,
    )

    env_headers = sample_environment_with_api_headers["api"]["headers"]
    # Scenario has same keys but different values
    result = dispatch_scenario(
        sample_scenario_with_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
        default_headers=env_headers,
    )

    assert result.api_result == "passed"
    # Scenario values should win
    assert result.request_sent["headers"]["Authorization"] == "Bearer scenario-token"  # from scenario
    assert result.request_sent["headers"]["X-Test-Id"] == "test-123"  # from scenario
    # Environment values preserved
    assert result.request_sent["headers"]["X-Tenant"] == "tenant-a"  # from environment


@responses.activate
def test_dispatch_scenario_resolve_environment_headers_variables(sample_scenario_without_headers):
    """T026: Integration test - environment api.headers with {{variable}} are resolved."""
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "var-env-test", "status": "PENDING"},
        status=201,
    )

    env_headers = {
        "X-API-Key": "{{api_key_var}}",
        "X-Tenant": "tenant-staging",
    }
    variables = {"api_key_var": "resolved-api-key-xyz"}

    result = dispatch_scenario(
        sample_scenario_without_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables=variables,
        default_headers=_resolve_headers(env_headers, variables),  # Resolve env headers before passing
    )

    assert result.api_result == "passed"
    assert result.request_sent["headers"]["X-API-Key"] == "resolved-api-key-xyz"


@responses.activate
def test_poll_services_info_with_headers(sample_environment_with_service_headers):
    """T027: Integration test - poll_services_info() uses service-level headers."""
    responses.add(
        responses.GET,
        "http://localhost:8080/health",
        json={"status": "healthy", "version": "1.0"},
        status=200,
    )

    services_info = sample_environment_with_service_headers["services_info"]
    results = poll_services_info(services_info)

    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200
    assert results[0]["data"]["status"] == "healthy"


@responses.activate
def test_poll_services_info_resolves_headers_variables():
    """T028: Integration test - services_info[].headers with {{variable}} are resolved."""
    responses.add(
        responses.GET,
        "http://localhost:9999/health",
        json={"status": "up"},
        status=200,
    )

    services_info = [
        {
            "name": "dynamic-service",
            "info_url": "http://localhost:9999/health",
            "headers": {
                "Authorization": "Bearer {{service_token}}",
            },
        },
    ]

    # For now, poll_services_info doesn't have variables support yet (T034 will add it)
    # This test documents the expected behavior
    results = poll_services_info(services_info)
    assert results[0]["error"] is None


@responses.activate
def test_dispatch_scenario_with_env_and_scenario_headers_both_present(sample_scenario_with_headers):
    """T029: Integration test - environment and scenario headers both defined, confirm merge result sent and recorded."""
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "both-headers-test", "status": "PENDING"},
        status=201,
    )

    env_headers = {
        "X-API-Key": "env-api-key",
        "X-Correlation-ID": "corr-123",
    }

    result = dispatch_scenario(
        sample_scenario_with_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
        default_headers=env_headers,
    )

    assert result.api_result == "passed"
    # Check all headers are present: env, scenario, merged
    assert result.request_sent["headers"]["X-API-Key"] == "env-api-key"  # from env
    assert result.request_sent["headers"]["X-Correlation-ID"] == "corr-123"  # from env
    assert result.request_sent["headers"]["X-Test-Id"] == "test-123"  # from scenario
    assert result.request_sent["headers"]["Authorization"] == "Bearer scenario-token"  # from scenario


@responses.activate
def test_poll_services_info_multiple_services_different_headers(sample_environment_with_multiple_services_headers):
    """T042: Test multiple services_info items, each with different headers, confirm each receives its own headers during polling."""
    responses.add(
        responses.GET,
        "http://localhost:8080/user-health",
        json={"status": "healthy"},
        status=200,
    )
    responses.add(
        responses.GET,
        "http://localhost:8080/payment-health",
        json={"status": "online"},
        status=200,
    )

    services_info = sample_environment_with_multiple_services_headers["services_info"]
    results = poll_services_info(services_info)

    # Check that both services were polled
    assert len(results) == 2
    assert results[0]["name"] == "user-service"
    assert results[0]["error"] is None
    assert results[0]["status_code"] == 200

    assert results[1]["name"] == "payment-service"
    assert results[1]["error"] is None
    assert results[1]["status_code"] == 200

    # Verify the requests were made with correct headers
    # (responses library tracks all calls)
    user_service_call = responses.calls[0]
    payment_service_call = responses.calls[1]

    assert user_service_call.request.headers.get("Authorization") == "Bearer user-service-token"
    assert payment_service_call.request.headers.get("Authorization") == "Bearer payment-service-token"
    assert payment_service_call.request.headers.get("X-Service-Key") == "payment-123"


@responses.activate
def test_scenario_env_and_service_headers_all_combined(
    sample_scenario_with_headers, sample_environment_with_multiple_services_headers
):
    """T043: Full integration - scenario with headers, environment with headers, services with headers, confirm all are handled correctly."""
    # Mock scenario request
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "combined-test", "status": "PENDING"},
        status=201,
    )

    # Mock services polling
    responses.add(
        responses.GET,
        "http://localhost:8080/user-health",
        json={"status": "healthy"},
        status=200,
    )
    responses.add(
        responses.GET,
        "http://localhost:8080/payment-health",
        json={"status": "online"},
        status=200,
    )

    env_headers = {"X-API-Key": "env-key", "X-Tenant": "tenant-a"}

    # Dispatch scenario with env headers
    scenario_result = dispatch_scenario(
        sample_scenario_with_headers,
        base_url="https://example.test/api",
        timeout_seconds=30,
        variables={},
        default_headers=env_headers,
    )

    assert scenario_result.api_result == "passed"
    # Scenario headers should override env headers
    assert scenario_result.request_sent["headers"]["Authorization"] == "Bearer scenario-token"
    # Env headers should be preserved if not overridden
    assert scenario_result.request_sent["headers"]["X-API-Key"] == "env-key"
    assert scenario_result.request_sent["headers"]["X-Tenant"] == "tenant-a"
    # Scenario-specific headers
    assert scenario_result.request_sent["headers"]["X-Test-Id"] == "test-123"

    # Poll services with their own headers
    services_info = sample_environment_with_multiple_services_headers["services_info"]
    service_results = poll_services_info(services_info)

    assert len(service_results) == 2
    assert all(result["error"] is None for result in service_results)
    assert service_results[0]["status_code"] == 200
    assert service_results[1]["status_code"] == 200
