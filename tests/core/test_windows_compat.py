"""Windows-condition simulation tests for loading and writing files (spec 020, FR-010)."""

import json
import zoneinfo
from pathlib import Path

import pytest

from tests.conftest import write_utf8
from thomas.core import loading
from thomas.core.execution_record import write_execution_record
from thomas.core.json_encoding import ExecutionRecordEncoder
from thomas.core.loading import (
    ThomasFileError,
    load_and_validate,
    load_environment,
    load_scenarios,
    load_variables,
)
from thomas.core.variables import save_variables

TZ_HINT = "not a valid IANA time zone name (on Windows, make sure the 'tzdata' package is installed)"

ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Sistema de Cobrança",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
}

SCENARIO = {
    "schema_version": 1,
    "feature": "validação",
    "scenario_id": "rejects_invalid_value",
    "endpoint": {"method": "POST", "path": "/orders"},
    "api_checks": [
        {"id": "status_text", "field": "$.status", "operator": "equals", "expected_value": "inválido"}
    ],
}

VARIABLES = {"schema_version": 1, "variables": {"customer_name": "João Ninguém", "city": "São Paulo"}}


def _json_text(document: dict) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False)


def _write_environment(path: Path, **overrides) -> Path:
    write_utf8(path, _json_text({**ENVIRONMENT, **overrides}))
    return path


# --- Time zone validation (US1, contracts/cli-console-and-tz.md) -------------


@pytest.mark.parametrize("timezone_value", ["America/Sao_Paul", "../x", "America/"])
def test_load_environment_rejects_unknown_timezone(tmp_path, timezone_value):
    env_path = _write_environment(tmp_path / "dev.json", timezone=timezone_value)

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    assert exc_info.value.errors == [
        (str(env_path), f"unknown timezone '{timezone_value}': {TZ_HINT}")
    ]


def test_load_environment_reports_missing_tz_database_like_windows_without_tzdata(tmp_path, monkeypatch):
    def _no_tz_database(key):
        raise zoneinfo.ZoneInfoNotFoundError(f"No time zone found with key {key}")

    monkeypatch.setattr(loading, "ZoneInfo", _no_tz_database)
    env_path = _write_environment(tmp_path / "dev.json", timezone="UTC")

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    assert exc_info.value.errors == [(str(env_path), f"unknown timezone 'UTC': {TZ_HINT}")]


def test_load_environment_empty_timezone_is_rejected_by_the_schema_first(tmp_path):
    env_path = _write_environment(tmp_path / "dev.json", timezone="")

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    [(_, message)] = exc_info.value.errors
    assert message.startswith("invalid field 'timezone'")


@pytest.mark.parametrize("timezone_value", ["UTC", "America/Sao_Paulo"])
def test_load_environment_accepts_valid_timezone(tmp_path, timezone_value):
    env_path = _write_environment(tmp_path / "dev.json", timezone=timezone_value)

    assert load_environment(env_path)["timezone"] == timezone_value


def test_load_environment_reports_schema_error_before_bad_timezone(tmp_path):
    document = {**ENVIRONMENT, "timezone": "America/Sao_Paul"}
    del document["system_name"]
    env_path = tmp_path / "dev.json"
    write_utf8(env_path, _json_text(document))

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    [(path, message)] = exc_info.value.errors
    assert path == str(env_path)
    assert message.startswith("invalid field")
    assert "timezone" not in message


# --- read_user_text contract (US2, contracts/file-encoding.md) ---------------


def test_read_user_text_returns_exact_utf8_text(tmp_path):
    path = tmp_path / "s.json"
    write_utf8(path, '{"v": "inválido ✓"}')

    assert loading.read_user_text(path) == '{"v": "inválido ✓"}'


def test_read_user_text_strips_utf8_bom(tmp_path):
    path = tmp_path / "s.json"
    write_utf8(path, '{"v": "inválido"}', bom=True)

    text = loading.read_user_text(path)

    assert text == '{"v": "inválido"}'
    assert "﻿" not in text


def test_read_user_text_rejects_cp1252_bytes_naming_file_byte_and_offset(tmp_path):
    path = tmp_path / "s.json"
    content = '{"v": "inválido"}'
    path.write_bytes(content.encode("cp1252"))
    offset = content.encode("cp1252").index(b"\xe1")

    with pytest.raises(ThomasFileError) as exc_info:
        loading.read_user_text(path)

    assert exc_info.value.errors == [
        (
            str(path),
            f"file is not valid UTF-8 (invalid byte 0xE1 at offset {offset}); save it with UTF-8 encoding",
        )
    ]


def test_read_user_text_reports_unreadable_file(tmp_path):
    path = tmp_path / "missing.json"

    with pytest.raises(ThomasFileError) as exc_info:
        loading.read_user_text(path)

    [(error_path, message)] = exc_info.value.errors
    assert error_path == str(path)
    assert message.startswith("could not read file: ")


# --- Loaders under a cp1252 default encoding (US2) ---------------------------


def test_scenario_with_accented_expected_value_loads_exactly(tmp_path, cp1252_default_encoding):
    path = tmp_path / "s.json"
    write_utf8(path, _json_text(SCENARIO))

    document = load_and_validate(path, "scenario_v1.json")

    assert document["api_checks"][0]["expected_value"] == "inválido"
    assert document["feature"] == "validação"


def test_scenario_with_bom_loads(tmp_path, cp1252_default_encoding):
    path = tmp_path / "s.json"
    write_utf8(path, _json_text(SCENARIO), bom=True)

    document = load_and_validate(path, "scenario_v1.json")

    assert document["api_checks"][0]["expected_value"] == "inválido"


def test_environment_and_variables_with_accents_load_exactly(tmp_path, cp1252_default_encoding):
    env_path = _write_environment(tmp_path / "dev.json")
    variables_path = tmp_path / "variables.json"
    write_utf8(variables_path, _json_text(VARIABLES))

    assert load_environment(env_path)["system_name"] == "Sistema de Cobrança"
    assert load_variables(variables_path) == VARIABLES["variables"]


def test_load_scenarios_reports_cp1252_and_schema_errors_together(tmp_path, cp1252_default_encoding):
    write_utf8(tmp_path / "a_valid.json", _json_text(SCENARIO))
    cp1252_path = tmp_path / "b_cp1252.json"
    cp1252_path.write_bytes(_json_text(SCENARIO).encode("cp1252"))
    invalid_path = tmp_path / "c_invalid.json"
    write_utf8(invalid_path, _json_text({k: v for k, v in SCENARIO.items() if k != "endpoint"}))

    with pytest.raises(ThomasFileError) as exc_info:
        load_scenarios(tmp_path, project_root=tmp_path)

    errors = exc_info.value.errors
    assert [path for path, _ in errors] == [str(cp1252_path), str(invalid_path)]
    assert errors[0][1].startswith("file is not valid UTF-8")
    assert errors[1][1].startswith("invalid field")


# --- Generated artifacts round-trip across encodings (US3) -------------------

RECORD = {
    "schema_version": 1,
    "execution_id": "execution_compat",
    "environment": "homologação",
    "results": [{"scenario_id": "sc1", "api_response": {"body": {"status": "inválido ✓"}}}],
}


def test_execution_record_written_under_cp1252_reads_back_identically(tmp_path, request):
    request.getfixturevalue("cp1252_default_encoding")
    output_path = write_execution_record(RECORD, tmp_path)

    data = output_path.read_bytes()
    assert data == json.dumps(RECORD, indent=2, cls=ExecutionRecordEncoder).encode("ascii")
    assert b"\r\n" not in data
    assert json.loads(loading.read_user_text(output_path)) == RECORD


def test_execution_record_written_natively_reads_back_under_cp1252(tmp_path, request):
    output_path = write_execution_record(RECORD, tmp_path)

    request.getfixturevalue("cp1252_default_encoding")

    assert json.loads(loading.read_user_text(output_path)) == RECORD


def test_variables_written_under_cp1252_reads_back_identically(tmp_path, request):
    request.getfixturevalue("cp1252_default_encoding")
    path = tmp_path / "variables.json"
    save_variables(path, VARIABLES["variables"])

    data = path.read_bytes()
    assert data == json.dumps(VARIABLES, indent=2).encode("ascii")
    assert b"\r\n" not in data
    assert load_variables(path) == VARIABLES["variables"]


def test_variables_written_natively_reads_back_under_cp1252(tmp_path, request):
    path = tmp_path / "variables.json"
    save_variables(path, VARIABLES["variables"])

    request.getfixturevalue("cp1252_default_encoding")

    assert load_variables(path) == VARIABLES["variables"]
