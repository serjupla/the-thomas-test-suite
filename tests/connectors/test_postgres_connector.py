import datetime
import decimal
import ipaddress
import json
import logging
import subprocess
import sys
import types
import urllib.parse
import uuid
from unittest.mock import MagicMock

import pytest

from thomas.connectors import ConnectorTechnicalError
from thomas.core.json_encoding import ExecutionRecordEncoder

CONFIG = {
    "type": "postgres",
    "connection_string": "postgresql://uri_user:uri-secret@fictional-pg-host:5432/fictional_db",
    "username": "fictional_user",
    "password": "fictional-secret",
}

READ_ONLY_SQL = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
TIMESTAMP = "2026-07-28T09:00:00-03:00"


def _install_fake_psycopg(monkeypatch, connect_mock):
    """Install a fake psycopg module (plus its psycopg.conninfo submodule) in
    sys.modules, exposing only what PostgresConnector touches."""
    fake_module = types.ModuleType("psycopg")

    class Error(Exception):
        pass

    class OperationalError(Error):
        pass

    fake_module.Error = Error
    fake_module.OperationalError = OperationalError
    fake_module.connect = connect_mock

    conninfo_module = types.ModuleType("psycopg.conninfo")

    def _conninfo_to_dict(conninfo):
        parsed = urllib.parse.urlparse(conninfo)
        result = {}
        if parsed.username:
            result["user"] = parsed.username
        if parsed.password:
            result["password"] = parsed.password
        return result

    conninfo_module.conninfo_to_dict = _conninfo_to_dict
    fake_module.conninfo = conninfo_module
    monkeypatch.setitem(sys.modules, "psycopg", fake_module)
    monkeypatch.setitem(sys.modules, "psycopg.conninfo", conninfo_module)
    return fake_module


class FakeCursor:
    def __init__(self, rows=None, columns=None, raise_on_execute=None):
        self.rows = list(rows) if rows is not None else []
        self.columns = list(columns) if columns is not None else []
        self.raise_on_execute = raise_on_execute
        self.executed = []
        self.fetchmany_sizes = []
        self.closed = False

    @property
    def description(self):
        return [types.SimpleNamespace(name=column) for column in self.columns]

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self.raise_on_execute is not None:
            raise self.raise_on_execute

    def fetchmany(self, size):
        self.fetchmany_sizes.append(size)
        return self.rows[:size]

    def close(self):
        self.closed = True


class FakeConnection:
    """Hands out queued cursors first, then fresh cursors built from the
    default rows/columns. Records every (sql, params) executed on any cursor,
    including the read-only SET issued by connect()."""

    def __init__(self, cursors=None, rows=None, columns=None, close_side_effect=None):
        self.queue = list(cursors) if cursors is not None else []
        self.default_rows = rows
        self.default_columns = columns
        self.close_side_effect = close_side_effect
        self.cursors = []
        self.closed = False
        self.close_calls = 0

    def cursor(self):
        cursor = self.queue.pop(0) if self.queue else FakeCursor(self.default_rows, self.default_columns)
        self.cursors.append(cursor)
        return cursor

    @property
    def executed(self):
        return [call for cursor in self.cursors for call in cursor.executed]

    def close(self):
        self.close_calls += 1
        if self.close_side_effect is not None:
            raise self.close_side_effect
        self.closed = True


def _make_connector(
    monkeypatch, rows=None, columns=None, cursors=None, connect_side_effect=None, config=None, close_side_effect=None
):
    """Returns (connector, connect_mock, fake_connection). When `cursors` is
    given, a plain cursor for the read-only SET is prepended so the queued
    cursors serve the validations in order."""
    queued = [FakeCursor(), *cursors] if cursors is not None else None
    fake_connection = FakeConnection(
        cursors=queued, rows=rows, columns=columns, close_side_effect=close_side_effect
    )
    if connect_side_effect is not None:
        connect_mock = MagicMock(side_effect=connect_side_effect)
    else:
        connect_mock = MagicMock(return_value=fake_connection)
    _install_fake_psycopg(monkeypatch, connect_mock)

    from thomas.connectors.postgres import PostgresConnector

    connector = PostgresConnector(dict(config) if config is not None else dict(CONFIG))
    return connector, connect_mock, fake_connection


def _validation(query="SELECT status FROM fictional_orders WHERE order_id = :correlation_id", field="status"):
    return {"id": "v1", "connector": "pg_main", "query": query, "field": field}


def _validation_sql_and_params(fake_connection):
    # executed[0] is the read-only SET; the validation query follows.
    return fake_connection.executed[-1]


# --- US1: bind, escape, extraction ---------------------------------------


def test_run_validation_binds_correlation_id_instead_of_concatenating(monkeypatch):
    connector, _, fake_connection = _make_connector(monkeypatch, rows=[("SETTLED",)], columns=["status"])
    connector.connect()

    connector.run_validation(
        _validation("SELECT status FROM t WHERE id = :correlation_id OR parent_id = :correlation_id"),
        "ABC-1",
        TIMESTAMP,
    )

    sql, params = _validation_sql_and_params(fake_connection)
    assert sql == "SELECT status FROM t WHERE id = %(correlation_id)s OR parent_id = %(correlation_id)s"
    assert "ABC-1" not in sql
    assert params == {"correlation_id": "ABC-1"}


def test_run_validation_escapes_percent_and_preserves_double_colon_casts(monkeypatch):
    connector, _, fake_connection = _make_connector(monkeypatch, rows=[("SETTLED",)], columns=["status"])
    connector.connect()

    connector.run_validation(
        _validation(
            "SELECT status FROM t WHERE id = :correlation_id::bigint AND d LIKE 'order-%' "
            "AND created_at::date = current_date"
        ),
        "42",
        TIMESTAMP,
    )

    sql, _ = _validation_sql_and_params(fake_connection)
    assert sql == (
        "SELECT status FROM t WHERE id = %(correlation_id)s::bigint AND d LIKE 'order-%%' "
        "AND created_at::date = current_date"
    )


def test_run_validation_without_placeholder_still_escapes_percent_and_passes_params(monkeypatch):
    connector, _, fake_connection = _make_connector(monkeypatch, rows=[("SETTLED",)], columns=["status"])
    connector.connect()

    connector.run_validation(_validation("SELECT status FROM t WHERE d LIKE 'x%'"), "ABC-1", TIMESTAMP)

    sql, params = _validation_sql_and_params(fake_connection)
    assert sql == "SELECT status FROM t WHERE d LIKE 'x%%'"
    assert params == {"correlation_id": "ABC-1"}


def test_run_validation_does_not_match_longer_identifier(monkeypatch):
    connector, _, fake_connection = _make_connector(monkeypatch, rows=[("SETTLED",)], columns=["status"])
    connector.connect()

    connector.run_validation(_validation("SELECT status FROM t WHERE id = :correlation_id_2"), "ABC-1", TIMESTAMP)

    sql, _ = _validation_sql_and_params(fake_connection)
    assert sql == "SELECT status FROM t WHERE id = :correlation_id_2"


def test_run_validation_single_row_returns_field_value_and_ignores_timestamp(monkeypatch):
    connector, _, fake_connection = _make_connector(
        monkeypatch, rows=[("SETTLED", decimal.Decimal("150.00"))], columns=["status", "amount"]
    )
    connector.connect()
    query = "SELECT status, amount FROM fictional_orders WHERE order_id = :correlation_id"

    status = connector.run_validation(_validation(query, "status"), "corr-1", TIMESTAMP)
    amount = connector.run_validation(_validation(query, "amount"), "corr-1", "not-a-timestamp")

    assert status == "SETTLED"
    assert amount == 150
    assert isinstance(amount, int)
    assert connector.describe_query(_validation(query)) == query
    assert all(cursor.closed for cursor in fake_connection.cursors)


def test_postgres_and_postgresql_types_resolve_to_postgres_connector(monkeypatch):
    _install_fake_psycopg(monkeypatch, MagicMock())
    from thomas.connectors import resolve_connector_type
    from thomas.connectors.postgres import PostgresConnector

    assert resolve_connector_type("postgresql") is resolve_connector_type("postgres") is PostgresConnector


_UUID = uuid.UUID("12345678-ABCD-4ABC-8DEF-1234567890AB")
_AWARE_DATETIME = datetime.datetime(2026, 7, 28, 9, 0, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=-3)))

NORMALIZE_CASES = [
    pytest.param(decimal.Decimal(42), 42, id="numeric-integral"),
    pytest.param(decimal.Decimal("12.50"), 12.5, id="numeric-fractional"),
    pytest.param(_UUID, "12345678-abcd-4abc-8def-1234567890ab", id="uuid"),
    pytest.param(True, True, id="bool"),
    pytest.param(7, 7, id="int"),
    pytest.param(1.5, 1.5, id="float"),
    pytest.param("text", "text", id="str"),
    pytest.param(datetime.date(2026, 7, 28), datetime.date(2026, 7, 28), id="date"),
    pytest.param(_AWARE_DATETIME, _AWARE_DATETIME, id="timestamptz"),
    pytest.param(
        {"items": [decimal.Decimal(1), decimal.Decimal("2.5")], "id": _UUID, "ok": True},
        {"items": [1, 2.5], "id": "12345678-abcd-4abc-8def-1234567890ab", "ok": True},
        id="jsonb-dict",
    ),
    pytest.param([decimal.Decimal(3), [_UUID]], [3, ["12345678-abcd-4abc-8def-1234567890ab"]], id="array"),
    pytest.param((decimal.Decimal(3), "a"), [3, "a"], id="tuple"),
    pytest.param(None, None, id="null"),
    pytest.param(memoryview(b"\x01\xff"), "\\x01ff", id="bytea-memoryview"),
    pytest.param(b"\x01\xff", "\\x01ff", id="bytea-bytes"),
    pytest.param(datetime.timedelta(hours=1, minutes=30), "1:30:00", id="interval"),
    pytest.param(ipaddress.IPv4Address("192.0.2.10"), "192.0.2.10", id="inet"),
    pytest.param(datetime.time(9, 30), "09:30:00", id="time"),
]


@pytest.mark.parametrize(("value", "expected"), NORMALIZE_CASES)
def test_normalize_maps_postgres_values_to_json_natives(value, expected):
    from thomas.connectors.postgres import _normalize

    result = _normalize(value)

    assert result == expected
    assert type(result) is type(expected)


def test_normalize_non_finite_numeric_becomes_float():
    from thomas.connectors.postgres import _normalize

    result = _normalize(decimal.Decimal("Infinity"))

    assert result == float("inf")


@pytest.mark.parametrize(("value", "expected"), NORMALIZE_CASES)
def test_normalized_values_serialize_with_execution_record_encoder(value, expected):
    from thomas.connectors.postgres import _normalize

    json.dumps({"obtained": _normalize(value)}, cls=ExecutionRecordEncoder)


def test_normalized_dates_serialize_identically_to_f016():
    from thomas.connectors.postgres import _normalize

    encoded = json.dumps(
        {"d": _normalize(datetime.date(2026, 7, 28)), "ts": _normalize(_AWARE_DATETIME)},
        cls=ExecutionRecordEncoder,
    )

    assert json.loads(encoded) == {"d": "2026-07-28", "ts": "2026-07-28T09:00:00-03:00"}


# --- US2: legible technical errors ----------------------------------------


def test_run_validation_zero_rows_raises_technical_error(monkeypatch):
    connector, _, fake_connection = _make_connector(monkeypatch, rows=[], columns=["status"])
    connector.connect()

    with pytest.raises(ConnectorTechnicalError, match="^no record found for the given query$"):
        connector.run_validation(_validation(), "corr-1", TIMESTAMP)

    assert fake_connection.cursors[-1].fetchmany_sizes == [2]


def test_run_validation_multiple_rows_raises_technical_error(monkeypatch):
    connector, _, fake_connection = _make_connector(
        monkeypatch, rows=[("SETTLED",), ("PENDING",), ("FAILED",)], columns=["status"]
    )
    connector.connect()

    with pytest.raises(
        ConnectorTechnicalError,
        match="^query returned multiple records; refine the query to return a single record$",
    ):
        connector.run_validation(_validation(), "corr-1", TIMESTAMP)

    assert fake_connection.cursors[-1].fetchmany_sizes == [2]


@pytest.mark.parametrize("field", ["STATUS", "Status", "status"])
def test_run_validation_field_lookup_is_case_insensitive(monkeypatch, field):
    connector, _, _ = _make_connector(monkeypatch, rows=[("SETTLED",)], columns=["status"])
    connector.connect()

    assert connector.run_validation(_validation(field=field), "corr-1", TIMESTAMP) == "SETTLED"


def test_run_validation_missing_field_raises_technical_error(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, rows=[("SETTLED",)], columns=["status"])
    connector.connect()

    with pytest.raises(ConnectorTechnicalError, match="^field not found in query result: missing_col$"):
        connector.run_validation(_validation(field="missing_col"), "corr-1", TIMESTAMP)


def test_query_error_is_legible_and_connection_stays_usable(monkeypatch):
    connect_mock = MagicMock()
    fake_module = _install_fake_psycopg(monkeypatch, connect_mock)
    failing = FakeCursor(raise_on_execute=fake_module.Error('syntax error at or near "SELEC"\nLINE 1: SELEC status'))
    succeeding = FakeCursor(rows=[("SETTLED",)], columns=["status"])
    fake_connection = FakeConnection(cursors=[FakeCursor(), failing, succeeding])
    connect_mock.return_value = fake_connection

    from thomas.connectors.postgres import PostgresConnector

    connector = PostgresConnector(dict(CONFIG))
    connector.connect()

    with pytest.raises(ConnectorTechnicalError) as exc_info:
        connector.run_validation(_validation("SELEC status FROM t"), "corr-1", TIMESTAMP)

    assert str(exc_info.value) == 'query failed: syntax error at or near "SELEC"'
    assert failing.closed
    assert connector.run_validation(_validation(), "corr-2", TIMESTAMP) == "SETTLED"
    assert connect_mock.call_count == 1


def test_query_error_with_empty_message_uses_exception_class_name(monkeypatch):
    connect_mock = MagicMock()
    fake_module = _install_fake_psycopg(monkeypatch, connect_mock)
    connect_mock.return_value = FakeConnection(cursors=[FakeCursor(), FakeCursor(raise_on_execute=fake_module.Error(""))])

    from thomas.connectors.postgres import PostgresConnector

    connector = PostgresConnector(dict(CONFIG))
    connector.connect()

    with pytest.raises(ConnectorTechnicalError, match="^query failed: Error$"):
        connector.run_validation(_validation(), "corr-1", TIMESTAMP)


def test_query_error_message_and_log_are_redacted(monkeypatch, caplog):
    connect_mock = MagicMock()
    fake_module = _install_fake_psycopg(monkeypatch, connect_mock)
    error = fake_module.Error('permission denied for user "fictional_user"')
    connect_mock.return_value = FakeConnection(cursors=[FakeCursor(), FakeCursor(raise_on_execute=error)])

    from thomas.connectors.postgres import PostgresConnector

    connector = PostgresConnector(dict(CONFIG))
    connector.connect()

    with (
        caplog.at_level(logging.DEBUG, logger="thomas.connectors.postgres"),
        pytest.raises(ConnectorTechnicalError) as exc_info,
    ):
        connector.run_validation(_validation(), "corr-1", TIMESTAMP)

    assert "fictional_user" not in str(exc_info.value)
    assert "fictional_user" not in caplog.text
    assert "permission denied" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


def test_connect_passes_credentials_autocommit_and_default_timeout(monkeypatch):
    connector, connect_mock, fake_connection = _make_connector(monkeypatch)

    connector.connect()

    connect_mock.assert_called_once_with(
        CONFIG["connection_string"],
        autocommit=True,
        connect_timeout=10,
        user="fictional_user",
        password="fictional-secret",
    )
    assert fake_connection.executed[0][0] == READ_ONLY_SQL


@pytest.mark.parametrize("blank", [None, ""])
def test_connect_omits_user_and_password_when_not_configured(monkeypatch, blank):
    config = {"type": "postgres", "connection_string": CONFIG["connection_string"]}
    if blank is not None:
        config.update(username=blank, password=blank)
    connector, connect_mock, _ = _make_connector(monkeypatch, config=config)

    connector.connect()

    connect_mock.assert_called_once_with(CONFIG["connection_string"], autocommit=True, connect_timeout=10)


def test_connect_forwards_custom_connect_timeout(monkeypatch):
    connector, connect_mock, _ = _make_connector(monkeypatch, config=dict(CONFIG, connect_timeout=3))

    connector.connect()

    assert connect_mock.call_args.kwargs["connect_timeout"] == 3


CONNECT_FAILURE_MESSAGE = "failed to connect to PostgreSQL database — check connection_string/username/password"
SECRETS = ["fictional_user", "fictional-secret", "uri_user", "uri-secret", CONFIG["connection_string"]]


def test_connect_failure_raises_fixed_message_and_logs_no_credentials(monkeypatch, caplog):
    connect_mock = MagicMock()
    fake_module = _install_fake_psycopg(monkeypatch, connect_mock)
    connect_mock.side_effect = fake_module.OperationalError(
        'connection to server failed: password authentication failed for user "fictional_user" '
        f"(uri_user, fictional-secret, uri-secret, {CONFIG['connection_string']})"
    )

    from thomas.connectors.postgres import PostgresConnector

    connector = PostgresConnector(dict(CONFIG))

    with (
        caplog.at_level(logging.DEBUG, logger="thomas.connectors.postgres"),
        pytest.raises(ConnectorTechnicalError) as exc_info,
    ):
        connector.connect()

    assert str(exc_info.value) == CONNECT_FAILURE_MESSAGE
    assert "OperationalError" in caplog.text
    assert "password authentication failed" in caplog.text
    for secret in SECRETS:
        assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert connector._connection is None


def test_read_only_set_failure_is_a_connect_failure_and_closes_connection(monkeypatch, caplog):
    connect_mock = MagicMock()
    fake_module = _install_fake_psycopg(monkeypatch, connect_mock)
    fake_connection = FakeConnection(
        cursors=[FakeCursor(raise_on_execute=fake_module.Error('role "fictional_user" cannot SET'))]
    )
    connect_mock.return_value = fake_connection

    from thomas.connectors.postgres import PostgresConnector

    connector = PostgresConnector(dict(CONFIG))

    with (
        caplog.at_level(logging.DEBUG, logger="thomas.connectors.postgres"),
        pytest.raises(ConnectorTechnicalError) as exc_info,
    ):
        connector.connect()

    assert str(exc_info.value) == CONNECT_FAILURE_MESSAGE
    assert fake_connection.closed
    assert connector._connection is None
    for secret in SECRETS:
        assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("value", [None, ""])
def test_missing_connection_string_is_rejected_before_connect(monkeypatch, value):
    connect_mock = MagicMock()
    _install_fake_psycopg(monkeypatch, connect_mock)
    config = dict(CONFIG)
    if value is None:
        del config["connection_string"]
    else:
        config["connection_string"] = value

    from thomas.connectors.postgres import PostgresConnector

    with pytest.raises(
        ConnectorTechnicalError,
        match="^PostgreSQL connector config is missing required field: connection_string$",
    ):
        PostgresConnector(config)

    connect_mock.assert_not_called()


@pytest.mark.parametrize("value", [0, -1, "10", True, 1.5])
def test_invalid_connect_timeout_is_rejected(monkeypatch, value):
    _install_fake_psycopg(monkeypatch, MagicMock())

    from thomas.connectors.postgres import PostgresConnector

    with pytest.raises(ConnectorTechnicalError) as exc_info:
        PostgresConnector(dict(CONFIG, connect_timeout=value))

    assert str(exc_info.value) == (
        "PostgreSQL connector config field connect_timeout must be a positive integer (seconds)"
    )


# --- US3: optional dependency ---------------------------------------------

DRIVER_MISSING_PATTERN = r"^PostgreSQL driver not installed\. Run: pip install thomas\[postgres\]$"


def test_instantiation_raises_install_guidance_when_psycopg_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)

    from thomas.connectors.postgres import PostgresConnector

    with pytest.raises(ConnectorTechnicalError, match=DRIVER_MISSING_PATTERN):
        PostgresConnector(dict(CONFIG))


def test_missing_driver_is_reported_before_config_validation(monkeypatch):
    monkeypatch.setitem(sys.modules, "psycopg", None)

    from thomas.connectors.postgres import PostgresConnector

    with pytest.raises(ConnectorTechnicalError, match=DRIVER_MISSING_PATTERN):
        PostgresConnector({})


def test_registry_import_does_not_require_psycopg():
    # A fresh interpreter, so the registry import really runs with psycopg blocked.
    script = (
        "import sys; sys.modules['psycopg'] = None\n"
        "from thomas.connectors import resolve_connector_type\n"
        "assert resolve_connector_type('postgres').__name__ == 'PostgresConnector'\n"
        "assert resolve_connector_type('postgresql') is resolve_connector_type('postgres')\n"
    )

    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False, encoding="utf-8")

    assert completed.returncode == 0, completed.stderr


# --- US4: report hiding ---------------------------------------------------


def test_never_show_fields_includes_connection_string_username_and_password():
    from thomas.connectors.postgres import PostgresConnector

    assert PostgresConnector.NEVER_SHOW_FIELDS == frozenset({"connection_string", "username", "password"})


# --- US5: connection reuse ------------------------------------------------


def test_one_connect_and_one_close_across_multiple_validations(monkeypatch):
    connector, connect_mock, fake_connection = _make_connector(monkeypatch, rows=[("SETTLED",)], columns=["status"])

    connector.connect()
    for correlation_id in ("corr-1", "corr-2", "corr-3"):
        connector.run_validation(_validation(), correlation_id, TIMESTAMP)
    connector.disconnect()

    assert connect_mock.call_count == 1
    assert fake_connection.close_calls == 1
    assert connector._connection is None


def test_disconnect_is_safe_when_connect_never_called(monkeypatch):
    connector, _, fake_connection = _make_connector(monkeypatch)

    connector.disconnect()

    assert fake_connection.close_calls == 0


def test_disconnect_is_safe_when_connect_failed(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, connect_side_effect=Exception("boom"))

    with pytest.raises(ConnectorTechnicalError):
        connector.connect()

    connector.disconnect()


def test_disconnect_swallows_close_errors(monkeypatch):
    connector, _, fake_connection = _make_connector(monkeypatch, close_side_effect=Exception("already closed"))
    connector.connect()

    connector.disconnect()

    assert fake_connection.close_calls == 1
    assert connector._connection is None
