import sys
import types
from unittest.mock import MagicMock

import pytest

from thomas.connectors import ConnectorTechnicalError

CONFIG = {"type": "oracle", "dsn": "host:1521/xe", "username": "user1", "password": "secret-pass"}


class FakeCursor:
    def __init__(self, description, rows):
        self.description = description
        self._rows = rows
        self.execute_calls = []
        self.closed = False

    def execute(self, query, **binds):
        self.execute_calls.append((query, binds))

    def fetchall(self):
        return self._rows

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
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


def _make_connector(monkeypatch, cursor: FakeCursor | None = None, connect_side_effect=None):
    connection = FakeConnection(cursor) if cursor is not None else None
    connect_mock = MagicMock(side_effect=connect_side_effect) if connect_side_effect else MagicMock(return_value=connection)
    _install_fake_oracledb(monkeypatch, connect_mock)

    from thomas.connectors.oracle import OracleConnector

    connector = OracleConnector(dict(CONFIG))
    return connector, connect_mock, connection


def test_connect_opens_connection_using_config_and_stores_it(monkeypatch):
    connector, connect_mock, connection = _make_connector(monkeypatch, cursor=FakeCursor([], []))

    connector.connect()

    connect_mock.assert_called_once_with(dsn="host:1521/xe", user="user1", password="secret-pass")
    assert connector._connection is connection


def test_run_validation_uses_bind_variable_and_returns_single_row_value(monkeypatch):
    cursor = FakeCursor(description=[("STATUS",), ("AMOUNT",)], rows=[("SETTLED", 150.0)])
    connector, _, _ = _make_connector(monkeypatch, cursor=cursor)
    connector.connect()

    result = connector.run_validation(
        {"query": "SELECT status, amount FROM t WHERE id = :correlation_id", "field": "status"}, "corr-1"
    )

    assert result == "SETTLED"
    query, binds = cursor.execute_calls[0]
    assert binds == {"correlation_id": "corr-1"}
    assert "corr-1" not in query


def test_never_show_fields_includes_password():
    from thomas.connectors.oracle import OracleConnector

    assert OracleConnector.NEVER_SHOW_FIELDS == frozenset({"password"})


def test_describe_query_returns_literal_sql_text(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, cursor=FakeCursor([], []))

    query = connector.describe_query({"query": "SELECT status FROM t WHERE id = :correlation_id", "field": "status"})

    assert query == "SELECT status FROM t WHERE id = :correlation_id"


def test_resolve_connector_type_returns_oracle_connector(monkeypatch):
    _install_fake_oracledb(monkeypatch, MagicMock())
    from thomas.connectors import resolve_connector_type
    from thomas.connectors.oracle import OracleConnector

    assert resolve_connector_type("oracle") is OracleConnector


def test_run_validation_zero_rows_raises_technical_error(monkeypatch):
    cursor = FakeCursor(description=[("STATUS",)], rows=[])
    connector, _, _ = _make_connector(monkeypatch, cursor=cursor)
    connector.connect()

    with pytest.raises(ConnectorTechnicalError, match="no record found for the given query"):
        connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1")


def test_run_validation_multiple_rows_raises_technical_error(monkeypatch):
    cursor = FakeCursor(description=[("STATUS",)], rows=[("SETTLED",), ("PENDING",)])
    connector, _, _ = _make_connector(monkeypatch, cursor=cursor)
    connector.connect()

    with pytest.raises(
        ConnectorTechnicalError, match="query returned multiple records; refine the query to return a single record"
    ):
        connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1")


def test_connect_failure_raises_curated_error_and_logs_raw_exception_at_debug(monkeypatch, caplog):
    connector, _, _ = _make_connector(
        monkeypatch, connect_side_effect=Exception("ORA-12541: TNS:no listener, secret-pass exposed")
    )

    with (
        caplog.at_level("DEBUG", logger="thomas.connectors.oracle"),
        pytest.raises(ConnectorTechnicalError) as exc_info,
    ):
        connector.connect()

    assert "secret-pass" not in str(exc_info.value)
    assert "ORA-12541" not in str(exc_info.value)
    assert "ORA-12541" in caplog.text


def test_run_validation_field_lookup_is_case_insensitive(monkeypatch):
    cursor = FakeCursor(description=[("STATUS",)], rows=[("SETTLED",)])
    connector, _, _ = _make_connector(monkeypatch, cursor=cursor)
    connector.connect()

    result = connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1")

    assert result == "SETTLED"


def test_instantiation_raises_clear_error_when_oracledb_not_installed(monkeypatch):
    # oracledb genuinely isn't installed in this dev environment (thomas[oracle]
    # is an optional extra), so no import mocking is needed — this exercises the
    # real ModuleNotFoundError path.
    monkeypatch.delitem(sys.modules, "oracledb", raising=False)

    from thomas.connectors.oracle import OracleConnector

    with pytest.raises(
        ConnectorTechnicalError, match=r"^Oracle driver not installed\. Run: pip install thomas\[oracle\]$"
    ):
        OracleConnector(dict(CONFIG))


def test_run_validation_does_not_reconnect_across_multiple_calls(monkeypatch):
    cursor = FakeCursor(description=[("STATUS",)], rows=[("SETTLED",)])
    connector, connect_mock, _ = _make_connector(monkeypatch, cursor=cursor)
    connector.connect()

    connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1")
    connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-2")

    connect_mock.assert_called_once()


def test_disconnect_is_safe_when_connect_never_called(monkeypatch):
    _install_fake_oracledb(monkeypatch, MagicMock())
    from thomas.connectors.oracle import OracleConnector

    connector = OracleConnector(dict(CONFIG))
    connector.disconnect()


def test_disconnect_is_safe_when_connect_failed_partway(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, connect_side_effect=Exception("boom"))

    with pytest.raises(ConnectorTechnicalError):
        connector.connect()

    connector.disconnect()
