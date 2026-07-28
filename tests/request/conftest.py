"""Pytest fixtures for request/dispatch tests, including headers test data."""

import pytest

from thomas.core.loading import LoadedScenario


@pytest.fixture
def sample_environment_with_api_headers() -> dict:
    """Sample environment with api-level headers (shared across all scenarios)."""
    return {
        "schema_version": 1,
        "environment_name": "test_env",
        "system_name": "test_api",
        "timezone": "UTC",
        "api": {
            "base_url": "https://example.test/api",
            "timeout_seconds": 30,
            "headers": {
                "X-API-Key": "env-key-12345",
                "X-Tenant": "tenant-a",
            },
        },
        "services_info": [],
        "connectors": {},
    }


@pytest.fixture
def sample_environment_with_service_headers() -> dict:
    """Sample environment with service-level headers (for polling)."""
    return {
        "schema_version": 1,
        "environment_name": "test_env",
        "system_name": "test_api",
        "timezone": "UTC",
        "api": {
            "base_url": "https://example.test/api",
            "timeout_seconds": 30,
        },
        "services_info": [
            {
                "name": "user-service",
                "info_url": "http://localhost:8080/health",
                "headers": {
                    "Authorization": "Bearer service-token-xyz",
                },
            },
        ],
        "connectors": {},
    }


@pytest.fixture
def sample_scenario_with_headers() -> LoadedScenario:
    """Sample scenario with endpoint-level headers (scenario-specific)."""
    document = {
        "schema_version": 1,
        "feature": "headers_feature",
        "scenario_id": "test_scenario_with_headers",
        "endpoint": {
            "method": "POST",
            "path": "/orders",
            "headers": {
                "X-Test-Id": "test-123",
                "Authorization": "Bearer scenario-token",
            },
        },
        "payload": {"amount": 100.0},
        "correlation": {"source": "api_response", "field": "$.id"},
        "api_checks": [
            {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201},
        ],
        "validations": [],
    }
    return LoadedScenario(document=document, scenario_file="scenario_with_headers.json", folder="")


@pytest.fixture
def sample_scenario_with_variable_headers() -> LoadedScenario:
    """Sample scenario with variable placeholders in headers (e.g., {{auth_token}})."""
    document = {
        "schema_version": 1,
        "feature": "headers_feature",
        "scenario_id": "test_scenario_with_variable_headers",
        "endpoint": {
            "method": "POST",
            "path": "/orders",
            "headers": {
                "Authorization": "Bearer {{auth_token}}",
                "X-Request-Id": "{{request_id}}",
            },
        },
        "payload": {"amount": 100.0},
        "correlation": {"source": "api_response", "field": "$.id"},
        "api_checks": [
            {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201},
        ],
        "validations": [],
    }
    return LoadedScenario(document=document, scenario_file="scenario_with_variable_headers.json", folder="")


@pytest.fixture
def sample_scenario_without_headers() -> LoadedScenario:
    """Sample scenario without headers (backward compatibility test)."""
    document = {
        "schema_version": 1,
        "feature": "headers_feature",
        "scenario_id": "test_scenario_without_headers",
        "endpoint": {
            "method": "POST",
            "path": "/orders",
        },
        "payload": {"amount": 100.0},
        "correlation": {"source": "api_response", "field": "$.id"},
        "api_checks": [
            {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201},
        ],
        "validations": [],
    }
    return LoadedScenario(document=document, scenario_file="scenario_without_headers.json", folder="")


@pytest.fixture
def sample_environment_with_multiple_services_headers() -> dict:
    """Sample environment with multiple services, each with different headers."""
    return {
        "schema_version": 1,
        "environment_name": "test_env",
        "system_name": "test_api",
        "timezone": "UTC",
        "api": {
            "base_url": "https://example.test/api",
            "timeout_seconds": 30,
        },
        "services_info": [
            {
                "name": "user-service",
                "info_url": "http://localhost:8080/user-health",
                "headers": {
                    "Authorization": "Bearer user-service-token",
                },
            },
            {
                "name": "payment-service",
                "info_url": "http://localhost:8080/payment-health",
                "headers": {
                    "Authorization": "Bearer payment-service-token",
                    "X-Service-Key": "payment-123",
                },
            },
        ],
        "connectors": {},
    }


@pytest.fixture
def sample_variables_for_headers() -> dict:
    """Sample variables used to resolve headers with {{variable}} syntax."""
    return {
        "auth_token": "resolved-auth-token-abc123",
        "request_id": "req-001",
    }
