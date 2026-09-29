"""End-to-end CLI runs under simulated Windows conditions (spec 020, FR-010)."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import requests
import responses
from tests.conftest import apply_cp1252_default_encoding, write_utf8

from thomas.cli import main

BAD_TIMEZONE = "America/Sao_Paul"
EXAMPLE_ENV = "examples/config/environments/example.json"
EXAMPLE_API = re.compile(r"https://jsonplaceholder\.typicode\.com/.*")
REPORT_GLYPHS = ("▸", "⚠", "✓", "✕")

ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Sistema de Cobrança",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
    "connectors": {"fake_main": {"type": "fake", "values": {"v1": "inválido"}, "failures": {}}},
}

SCENARIO = {
    "schema_version": 1,
    "feature": "validação",
    "scenario_id": "sc1",
    "endpoint": {"method": "POST", "path": "/orders"},
    "correlation": {"source": "api_response", "field": "id"},
    "api_checks": [
        {"id": "status_text", "field": "$.status", "operator": "equals", "expected_value": "inválido"}
    ],
    "validations": [
        {"id": "v1", "connector": "fake_main", "field": "status", "operator": "equals", "expected_value": "inválido"}
    ],
}

EXECUTION_RECORD = {
    "schema_version": 1,
    "execution_id": "execution_compat",
    "thomas_version": "0.0.0",
    "environment": "dev",
    "start_timestamp": "2026-07-28T09:00:00-03:00",
    "included_scenarios": ["sc1.json"],
    "services_info": [],
    "results": [
        {
            "scenario_file": "sc1.json",
            "feature": "validação",
            "scenario_id": "sc1",
            "folder": "",
            "correlation_id": "corr-1",
            "correlation_error": None,
            "request_timestamp": "2026-07-28T09:00:00-03:00",
            "response_timestamp": "2026-07-28T09:00:01-03:00",
            "request_sent": {"method": "POST", "path": "/orders", "payload": {}},
            "api_response": {"status_code": 201, "body": {"status": "inválido"}},
            "request_technical_error": None,
            "api_checks_result": [],
            "api_result": "passed",
            "validation_rounds": [],
            "final_status": "awaiting_validation",
        }
    ],
}


def _write_json(path: Path, document: dict) -> Path:
    write_utf8(path, json.dumps(document, indent=2, ensure_ascii=False))
    return path


def _squash(text: str) -> str:
    """Drop all whitespace: rich wraps long console lines, sometimes mid-path."""
    return "".join(text.split())


def _latest(directory: Path, pattern: str) -> Path:
    [path] = sorted(directory.glob(pattern))
    return path


def _mock_order_api(status_body: str = "inválido") -> None:
    responses.add(
        responses.POST,
        "https://example.test/api/orders",
        json={"id": "corr-1", "status": status_body},
        status=201,
    )


def _request_args(tmp_path: Path, env_path: Path, scenario: Path) -> list[str]:
    return [
        "request",
        "--environment", str(env_path),
        "--scenario", str(scenario),
        "--output", str(tmp_path / "executions"),
        "--log-file", str(tmp_path / "thomas.log"),
    ]


# --- US1: README quickstart under cp1252 ------------------------------------


@responses.activate
def test_quickstart_init_request_report_under_cp1252(
    tmp_path, monkeypatch, cp1252_default_encoding, cp1252_console
):
    monkeypatch.chdir(tmp_path)
    cp1252_console.install()
    # A technical error on one scenario puts the "⚠" block in the report.
    responses.add(
        responses.GET,
        "https://jsonplaceholder.typicode.com/posts/1",
        body=requests.ConnectionError("serviço indisponível"),
    )
    responses.add(responses.GET, EXAMPLE_API, json={"id": 1, "userId": 1, "title": "Olá"}, status=200)
    responses.add(responses.POST, EXAMPLE_API, json={"id": 101, "userId": 1, "title": "Olá"}, status=201)

    assert main(["init"]) == 0
    assert "Scaffolding Thomas project" in cp1252_console.out()
    assert (tmp_path / EXAMPLE_ENV).is_file()

    assert main([
        "request",
        "--environment", EXAMPLE_ENV,
        "--folder", "examples/scenarios",
        "--variables", "examples/config/variables.example.json",
        "--title", "Thomas Quickstart — validação",
    ]) == 0
    record_path = _latest(tmp_path / "executions", "*.json")
    assert json.loads(record_path.read_bytes())["title"] == "Thomas Quickstart — validação"

    assert main(["report", "--execution", str(record_path), "--environment", EXAMPLE_ENV]) == 0
    report_bytes = _latest(tmp_path / "reports", "*.html").read_bytes()
    html = report_bytes.decode("utf-8")
    assert '<meta charset="utf-8">' in html
    for glyph in REPORT_GLYPHS:
        assert glyph in html
    assert b"\r\n" not in report_bytes
    assert "Traceback" not in cp1252_console.err()


@responses.activate
@pytest.mark.parametrize("command", ["request", "validate", "report"])
def test_invalid_timezone_fails_cleanly_before_any_work(tmp_path, monkeypatch, capsys, command):
    monkeypatch.chdir(tmp_path)
    _mock_order_api()
    env_path = _write_json(tmp_path / "dev.json", {**ENVIRONMENT, "timezone": BAD_TIMEZONE})
    scenario_path = _write_json(tmp_path / "sc1.json", SCENARIO)
    exec_path = _write_json(tmp_path / "execution.json", EXECUTION_RECORD)
    exec_before = exec_path.read_bytes()

    if command == "request":
        args = _request_args(tmp_path, env_path, scenario_path)
    else:
        args = [command, "--execution", str(exec_path), "--environment", str(env_path)]

    assert main(args) == 1

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert _squash(f"Invalid environment file: {env_path}: unknown timezone '{BAD_TIMEZONE}'") in _squash(output)
    assert "Traceback" not in output
    assert len(responses.calls) == 0
    assert not (tmp_path / "executions").exists()
    assert not (tmp_path / "reports").exists()
    assert exec_path.read_bytes() == exec_before


def _run_cli_as_windows_console(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp1252:strict", "LC_ALL": "C"}
    return subprocess.run(
        [sys.executable, "-c", "import sys; from thomas.cli import main; sys.exit(main())", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=False,
    )


def test_subprocess_init_and_report_under_cp1252_console(tmp_path):
    init = _run_cli_as_windows_console(["init"], tmp_path)
    assert init.returncode == 0, init.stderr.decode("cp1252", errors="replace")
    init.stdout.decode("cp1252")
    assert b"Traceback" not in init.stderr

    record = {**EXECUTION_RECORD, "environment": "example-public-api"}
    exec_path = _write_json(tmp_path / "execution.json", record)
    report = _run_cli_as_windows_console(
        ["report", "--execution", str(exec_path), "--environment", EXAMPLE_ENV], tmp_path
    )
    assert report.returncode == 0, report.stderr.decode("cp1252", errors="replace")
    report.stdout.decode("cp1252")
    assert b"Traceback" not in report.stderr

    for generated in [tmp_path / EXAMPLE_ENV, _latest(tmp_path / "reports", "*.html")]:
        generated.read_bytes().decode("utf-8")


# --- US2: accented scenario values -------------------------------------------


@responses.activate
def test_request_matches_accented_expected_value_under_cp1252(
    tmp_path, monkeypatch, cp1252_default_encoding, cp1252_console
):
    monkeypatch.chdir(tmp_path)
    cp1252_console.install()
    _mock_order_api("inválido")
    env_path = _write_json(tmp_path / "dev.json", ENVIRONMENT)
    scenario_path = _write_json(tmp_path / "sc1.json", SCENARIO)

    assert main(_request_args(tmp_path, env_path, scenario_path)) == 0

    record_bytes = _latest(tmp_path / "executions", "*.json").read_bytes()
    assert "inválido".encode() not in record_bytes  # ensure_ascii keeps JSON ASCII-only
    [result] = json.loads(record_bytes)["results"]
    [check] = result["api_checks_result"]
    assert check["passed"] is True
    assert result["api_response"]["body"]["status"] == "inválido"


@responses.activate
def test_request_rejects_cp1252_scenario_naming_the_file(
    tmp_path, monkeypatch, cp1252_default_encoding, cp1252_console
):
    monkeypatch.chdir(tmp_path)
    cp1252_console.install()
    _mock_order_api()
    env_path = _write_json(tmp_path / "dev.json", ENVIRONMENT)
    scenario_path = tmp_path / "sc1.json"
    scenario_path.write_bytes(json.dumps(SCENARIO, indent=2, ensure_ascii=False).encode("cp1252"))

    assert main(_request_args(tmp_path, env_path, scenario_path)) == 1

    output = cp1252_console.out() + cp1252_console.err()
    assert _squash(f"Invalid scenario file(s): {scenario_path}: file is not valid UTF-8") in _squash(output)
    assert "Traceback" not in output
    assert len(responses.calls) == 0
    assert not (tmp_path / "executions").exists()


# --- US3: records portable across encodings ----------------------------------


@responses.activate
def test_record_written_under_cp1252_is_validated_natively(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    _mock_order_api()
    env_path = _write_json(tmp_path / "dev.json", ENVIRONMENT)
    scenario_path = _write_json(tmp_path / "sc1.json", SCENARIO)

    with pytest.MonkeyPatch.context() as windows:
        apply_cp1252_default_encoding(windows, tmp_path)
        assert main(_request_args(tmp_path, env_path, scenario_path)) == 0
    exec_path = _latest(tmp_path / "executions", "*.json")
    request_phase = json.loads(exec_path.read_bytes())["results"][0]

    validate_args = [
        "validate",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--log-file", str(tmp_path / "thomas.log"),
    ]
    assert main(validate_args) == 0
    first_round = json.loads(exec_path.read_bytes())["results"][0]["validation_rounds"][0]
    assert main(validate_args) == 0

    data = exec_path.read_bytes()
    assert b"\r\n" not in data
    [result] = json.loads(data)["results"]
    assert len(result["validation_rounds"]) == 2
    assert json.dumps(result["validation_rounds"][0]) == json.dumps(first_round)
    assert result["validation_rounds"][1]["results"][0]["passed"] is True
    assert result["validation_rounds"][1]["results"][0]["obtained"] == "inválido"
    for key, value in request_phase.items():
        if key not in ("validation_rounds", "final_status"):
            assert result[key] == value
