import json
import sys
import types
from unittest.mock import MagicMock

from thomas.cli import BANNER, main

ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
    "connectors": {
        "fake_main": {"type": "fake", "values": {"v1": 150.0}, "failures": {}},
    },
}

ENVIRONMENT_MISSING_CONNECTOR = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
    "connectors": {},
}

SCENARIO = {
    "schema_version": 1,
    "feature": "transfers",
    "scenario_id": "sc1",
    "endpoint": {"method": "POST", "path": "/orders"},
    "correlation": {"source": "api_response", "field": "id"},
    "api_checks": [],
    "validations": [
        {"id": "v1", "connector": "fake_main", "field": "balance", "operator": "equals", "expected_value": 150.0}
    ],
}


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


EXECUTION_RECORD = {
    "schema_version": 1,
    "execution_id": "execution_test",
    "thomas_version": "0.0.0",
    "environment": "dev",
    "start_timestamp": "2026-07-28T09:00:00-03:00",
    "included_scenarios": ["sc1.json"],
    "services_info": [],
    "results": [_scenario_result("sc1.json")],
}


def write_json(path, document) -> None:
    path.write_text(json.dumps(document, indent=2))


def test_validate_happy_path_appends_round(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "sc1.json", SCENARIO)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 0
    record = json.loads(exec_path.read_text())
    rounds = record["results"][0]["validation_rounds"]
    assert len(rounds) == 1
    assert rounds[0]["results"][0]["passed"] is True
    assert rounds[0]["results"][0]["obtained"] == 150.0
    assert record["results"][0]["final_status"] == "passed"


def test_validate_failing_comparison_sets_final_status_failed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scenario = json.loads(json.dumps(SCENARIO))
    scenario["validations"][0]["expected_value"] = 999.0
    write_json(tmp_path / "sc1.json", scenario)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 0
    record = json.loads(exec_path.read_text())
    assert record["results"][0]["validation_rounds"][0]["round_result"] == "failed"
    assert record["results"][0]["final_status"] == "failed"


def test_validate_second_run_appends_second_round(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "sc1.json", SCENARIO)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    args = [
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ]
    main(args)
    record_after_first = json.loads(exec_path.read_text())
    first_round = record_after_first["results"][0]["validation_rounds"][0]

    main(args)
    record_after_second = json.loads(exec_path.read_text())
    rounds = record_after_second["results"][0]["validation_rounds"]

    assert len(rounds) == 2
    assert rounds[0] == first_round
    assert record_after_second["results"][0]["final_status"] == "passed"


def test_validate_prints_banner_before_any_other_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "sc1.json", SCENARIO)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    captured = capsys.readouterr()
    banner_first_line = BANNER.strip().splitlines()[0]
    assert captured.out.startswith(banner_first_line)


def test_validate_help_does_not_print_banner(capsys):
    try:
        main(["validate", "--help"])
    except SystemExit:
        pass

    captured = capsys.readouterr()
    banner_first_line = BANNER.strip().splitlines()[0]
    assert banner_first_line not in captured.out


def test_validate_missing_connector_aborts_without_touching_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "sc1.json", SCENARIO)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ENVIRONMENT_MISSING_CONNECTOR)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)
    before = exec_path.read_bytes()

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 1
    assert exec_path.read_bytes() == before


def test_validate_auto_resolves_environment_from_execution_record(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "sc1.json", SCENARIO)
    environments_dir = tmp_path / "config" / "environments"
    environments_dir.mkdir(parents=True)
    write_json(environments_dir / "dev.json", ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Using environment 'dev' (auto-detected from execution file)" in captured.out
    record = json.loads(exec_path.read_text())
    assert record["results"][0]["final_status"] == "passed"


def test_validate_auto_resolve_failure_suggests_explicit_environment(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "sc1.json", SCENARIO)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "--environment" in captured.out


def test_validate_explicit_environment_differing_from_record_prints_mismatch_note(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "sc1.json", SCENARIO)
    other_env_path = tmp_path / "other.json"
    write_json(other_env_path, {**ENVIRONMENT, "environment_name": "other"})
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(other_env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "differs from the environment recorded" in captured.out


ORACLE_ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
    "connectors": {
        "oracle_main": {"type": "oracle", "dsn": "host:1521/xe", "username": "user1", "password": "secret"},
    },
}

ORACLE_SCENARIO = {
    "schema_version": 1,
    "feature": "transfers",
    "scenario_id": "sc1",
    "endpoint": {"method": "POST", "path": "/orders"},
    "correlation": {"source": "api_response", "field": "id"},
    "api_checks": [],
    "validations": [
        {
            "id": "v1",
            "connector": "oracle_main",
            "query": "SELECT status FROM t WHERE id = :correlation_id",
            "field": "status",
            "operator": "equals",
            "expected_value": "SETTLED",
        }
    ],
}


class _FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.execute_calls = []

    def execute(self, query, **binds):
        self.execute_calls.append((query, binds))

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def _install_fake_oracledb(monkeypatch, connect_mock):
    fake_module = types.ModuleType("oracledb")
    fake_module.connect = connect_mock
    fake_module.Error = Exception
    monkeypatch.setitem(sys.modules, "oracledb", fake_module)
    return fake_module


def test_validate_oracle_single_row_match_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cursor = _FakeCursor(description=[("STATUS",)], rows=[("SETTLED",)])
    connection = _FakeConnection(cursor)
    _install_fake_oracledb(monkeypatch, MagicMock(return_value=connection))

    write_json(tmp_path / "sc1.json", ORACLE_SCENARIO)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ORACLE_ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 0
    record = json.loads(exec_path.read_text())
    rounds = record["results"][0]["validation_rounds"]
    assert rounds[0]["results"][0]["passed"] is True
    assert rounds[0]["results"][0]["technical_error"] is None


def test_validate_oracle_connect_failure_prints_readable_error_no_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _install_fake_oracledb(monkeypatch, MagicMock(side_effect=Exception("ORA-12541: TNS:no listener")))

    write_json(tmp_path / "sc1.json", ORACLE_SCENARIO)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ORACLE_ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err
    assert "ORA-12541" not in captured.out


def test_validate_oracle_driver_not_installed_prints_exact_guidance_message(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delitem(sys.modules, "oracledb", raising=False)

    write_json(tmp_path / "sc1.json", ORACLE_SCENARIO)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ORACLE_ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    write_json(exec_path, EXECUTION_RECORD)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Oracle driver not installed. Run: pip install thomas[oracle]" in captured.out
    assert "Traceback" not in captured.out
    assert "Traceback" not in captured.err


def test_validate_oracle_reuses_one_connection_across_multiple_scenarios(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cursor = _FakeCursor(description=[("STATUS",)], rows=[("SETTLED",)])
    connection = _FakeConnection(cursor)
    connect_mock = MagicMock(return_value=connection)
    _install_fake_oracledb(monkeypatch, connect_mock)

    scenario_2 = json.loads(json.dumps(ORACLE_SCENARIO))
    scenario_2["scenario_id"] = "sc2"
    scenario_2["validations"][0]["id"] = "v2"
    write_json(tmp_path / "sc1.json", ORACLE_SCENARIO)
    write_json(tmp_path / "sc2.json", scenario_2)
    env_path = tmp_path / "dev.json"
    write_json(env_path, ORACLE_ENVIRONMENT)
    exec_path = tmp_path / "execution.json"
    execution_record = json.loads(json.dumps(EXECUTION_RECORD))
    execution_record["included_scenarios"] = ["sc1.json", "sc2.json"]
    execution_record["results"] = [_scenario_result("sc1.json"), _scenario_result("sc2.json")]
    write_json(exec_path, execution_record)

    exit_code = main([
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ])

    assert exit_code == 0
    connect_mock.assert_called_once()
    assert connection.closed is True
