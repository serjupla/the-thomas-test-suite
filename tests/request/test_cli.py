import json

import pytest
import responses

from thomas.cli import BANNER, main

VALID_ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
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
def test_request_command_exit_zero_on_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    responses.add(responses.POST, "https://example.test/api/orders", json={}, status=201)

    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    write_json(scenarios_dir / "a.json", VALID_SCENARIO)

    exit_code = main([
        "request",
        "--environment", str(env_path),
        "--folder", str(scenarios_dir),
        "--output", str(tmp_path / "executions"),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 0
    assert list((tmp_path / "executions").glob("*.json"))


@responses.activate
def test_request_command_prints_banner_before_progress(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    responses.add(responses.POST, "https://example.test/api/orders", json={}, status=201)

    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    write_json(scenarios_dir / "a.json", VALID_SCENARIO)

    main([
        "request",
        "--environment", str(env_path),
        "--folder", str(scenarios_dir),
        "--output", str(tmp_path / "executions"),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    captured = capsys.readouterr()
    banner_first_line = BANNER.strip().splitlines()[0]
    assert banner_first_line in captured.out
    assert captured.out.index(banner_first_line) < captured.out.index("Dispatching")


def test_request_command_exit_one_on_invalid_environment(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, {"schema_version": 1})
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    write_json(scenarios_dir / "a.json", VALID_SCENARIO)

    exit_code = main([
        "request",
        "--environment", str(env_path),
        "--folder", str(scenarios_dir),
        "--output", str(tmp_path / "executions"),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 1


def test_request_command_exit_two_on_missing_folder_and_scenario(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)

    with pytest.raises(SystemExit) as exc_info:
        main(["request", "--environment", str(env_path)])

    assert exc_info.value.code == 2


def test_request_command_aborts_on_undefined_variable_before_any_request(tmp_path, capsys):
    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    write_json(
        scenarios_dir / "a.json",
        {**VALID_SCENARIO, "payload": {"amount": "{{unknown_variable}}"}},
    )
    variables_path = tmp_path / "variables.json"
    write_json(variables_path, {"schema_version": 1, "variables": {}})
    output_dir = tmp_path / "executions"

    exit_code = main([
        "request",
        "--environment", str(env_path),
        "--folder", str(scenarios_dir),
        "--variables", str(variables_path),
        "--output", str(output_dir),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "a.json" in captured.out
    assert "unknown_variable" in captured.out
    assert not output_dir.exists()


def test_request_command_aborts_on_undefined_variable_in_path(tmp_path, capsys):
    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    write_json(
        scenarios_dir / "a.json",
        {**VALID_SCENARIO, "endpoint": {"method": "GET", "path": "/users/{{user_id}}"}},
    )
    variables_path = tmp_path / "variables.json"
    write_json(variables_path, {"schema_version": 1, "variables": {}})
    output_dir = tmp_path / "executions"

    exit_code = main([
        "request",
        "--environment", str(env_path),
        "--folder", str(scenarios_dir),
        "--variables", str(variables_path),
        "--output", str(output_dir),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "a.json" in captured.out
    assert "user_id" in captured.out
    assert not output_dir.exists()


@responses.activate
def test_request_command_prints_console_summary_with_correct_counts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    responses.add(
        responses.POST,
        "https://example.test/api/passing",
        json={}, status=201,
    )
    responses.add(
        responses.POST,
        "https://example.test/api/failing",
        json={}, status=500,
    )

    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    write_json(scenarios_dir / "passing.json", {**VALID_SCENARIO, "scenario_id": "passing", "endpoint": {"method": "POST", "path": "/passing"}})
    write_json(scenarios_dir / "failing.json", {**VALID_SCENARIO, "scenario_id": "failing", "endpoint": {"method": "POST", "path": "/failing"}})

    exit_code = main([
        "request",
        "--environment", str(env_path),
        "--folder", str(scenarios_dir),
        "--output", str(tmp_path / "executions"),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 0
    output_file = next((tmp_path / "executions").glob("*.json"))
    record = json.loads(output_file.read_text())
    statuses = [r["final_status"] for r in record["results"]]
    assert statuses.count("passed") == 1
    assert statuses.count("failed") == 1

    captured = capsys.readouterr()
    assert "summary" in captured.out.lower()


def test_request_command_exit_two_on_both_folder_and_scenario(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        main([
            "request",
            "--environment", str(env_path),
            "--folder", str(scenarios_dir),
            "--scenario", str(scenarios_dir / "a.json"),
        ])

    assert exc_info.value.code == 2
