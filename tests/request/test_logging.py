import json

import responses

from thomas.cli import main

VALID_ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
    "connectors": {
        "oracle_main": {
            "type": "oracle",
            "dsn": "host:1521/service",
            "username": "test_user",
            "password": "super-secret-value",
        }
    },
}

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


def write_json(path, document) -> None:
    path.write_text(json.dumps(document))


@responses.activate
def test_log_file_has_full_detail_and_no_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "abc-123", "status": "PENDING"},
        status=201,
    )

    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    write_json(scenarios_dir / "a.json", VALID_SCENARIO)
    log_path = tmp_path / "thomas.log"

    exit_code = main([
        "request",
        "--environment", str(env_path),
        "--folder", str(scenarios_dir),
        "--output", str(tmp_path / "executions"),
        "--log-file", str(log_path),
    ])

    assert exit_code == 0
    log_content = log_path.read_text()
    assert "amount" in log_content
    assert "PENDING" in log_content
    assert "super-secret-value" not in log_content
