import sys
import types
from unittest.mock import MagicMock

import pytest

from thomas.connectors import ConnectorTechnicalError

CONFIG = {
    "type": "db2",
    "connection_string": "DATABASE=x;HOSTNAME=y;PORT=50000;PROTOCOL=TCPIP;",
    "username": "user1",
    "password": "secret-pass",
}


def _install_fake_ibm_db(monkeypatch, connect_mock, rows=None):
    """Install a fake ibm_db module. `rows` (a list of column-name -> value
    dicts) is re-queued into fetch_assoc on every execute() call, mirroring a
    fresh result set per prepared-statement execution."""
    fake_module = types.ModuleType("ibm_db")
    fake_module.connect = connect_mock
    template_rows = list(rows) if rows is not None else []
    state = {"queue": []}

    def _prepare(connection, sql):
        return {"connection": connection, "sql": sql}

    def _execute(stmt, params=()):
        stmt["params"] = params
        state["queue"] = list(template_rows)
        return True

    def _fetch_assoc(stmt):
        if state["queue"]:
            return state["queue"].pop(0)
        return False

    fake_module.prepare = MagicMock(side_effect=_prepare)
    fake_module.execute = MagicMock(side_effect=_execute)
    fake_module.fetch_assoc = MagicMock(side_effect=_fetch_assoc)
    fake_module.close = MagicMock()
    monkeypatch.setitem(sys.modules, "ibm_db", fake_module)
    return fake_module


def _make_connector(monkeypatch, rows=None, connect_side_effect=None, config=None):
    connect_mock = MagicMock(side_effect=connect_side_effect) if connect_side_effect else MagicMock(return_value="CONN")
    fake_module = _install_fake_ibm_db(monkeypatch, connect_mock, rows=rows)

    from thomas.connectors.db2 import DB2Connector

    connector = DB2Connector(dict(config) if config is not None else dict(CONFIG))
    return connector, connect_mock, fake_module


def test_connect_opens_connection_using_config_and_stores_it(monkeypatch):
    connector, connect_mock, _ = _make_connector(monkeypatch, rows=[])

    connector.connect()

    connect_mock.assert_called_once_with(CONFIG["connection_string"], CONFIG["username"], CONFIG["password"])
    assert connector._connection == "CONN"


def test_run_validation_uses_bind_variable_and_returns_single_row_value(monkeypatch):
    connector, _, fake_module = _make_connector(monkeypatch, rows=[{"STATUS": "SETTLED", "AMOUNT": 150.0}])
    connector.connect()

    result = connector.run_validation(
        {"query": "SELECT status, amount FROM t WHERE id = :correlation_id", "field": "status"},
        "corr-1",
        "2026-07-28T09:00:00-03:00",
    )

    assert result == "SETTLED"
    prepare_query = fake_module.prepare.call_args[0][1]
    assert "?" in prepare_query
    assert "corr-1" not in prepare_query
    _execute_stmt, execute_params = fake_module.execute.call_args[0]
    assert execute_params == ("corr-1",)


def test_resolve_connector_type_returns_db2_connector(monkeypatch):
    _install_fake_ibm_db(monkeypatch, MagicMock())
    from thomas.connectors import resolve_connector_type
    from thomas.connectors.db2 import DB2Connector

    assert resolve_connector_type("db2") is DB2Connector


def test_run_validation_zero_rows_raises_technical_error(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, rows=[])
    connector.connect()

    with pytest.raises(ConnectorTechnicalError, match="no record found for the given query"):
        connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1", "2026-07-28T09:00:00-03:00")


def test_run_validation_multiple_rows_raises_technical_error(monkeypatch):
    connector, _, _ = _make_connector(
        monkeypatch, rows=[{"STATUS": "SETTLED"}, {"STATUS": "PENDING"}]
    )
    connector.connect()

    with pytest.raises(
        ConnectorTechnicalError, match="query returned multiple records; refine the query to return a single record"
    ):
        connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1", "2026-07-28T09:00:00-03:00")


def test_connect_failure_raises_curated_error_and_logs_raw_exception_at_debug(monkeypatch, caplog):
    connector, _, _ = _make_connector(
        monkeypatch, connect_side_effect=Exception("SQL30081N connection failure, secret-pass exposed")
    )

    with (
        caplog.at_level("DEBUG", logger="thomas.connectors.db2"),
        pytest.raises(ConnectorTechnicalError) as exc_info,
    ):
        connector.connect()

    assert "secret-pass" not in str(exc_info.value)
    assert "SQL30081N" not in str(exc_info.value)
    assert "SQL30081N" in caplog.text


def test_run_validation_field_lookup_is_case_insensitive(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, rows=[{"STATUS": "SETTLED"}])
    connector.connect()

    result = connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1", "2026-07-28T09:00:00-03:00")

    assert result == "SETTLED"


@pytest.mark.parametrize("missing_field", ["connection_string", "username", "password"])
def test_connect_raises_clear_error_when_config_field_missing(monkeypatch, missing_field):
    bad_config = dict(CONFIG)
    bad_config[missing_field] = ""
    connect_mock = MagicMock(return_value="CONN")
    _install_fake_ibm_db(monkeypatch, connect_mock)

    from thomas.connectors.db2 import DB2Connector

    with pytest.raises(ConnectorTechnicalError, match=missing_field):
        DB2Connector(bad_config)

    connect_mock.assert_not_called()


def test_instantiation_raises_clear_error_when_ibm_db_not_installed(monkeypatch):
    # ibm_db genuinely isn't installed in this dev environment (thomas[db2]
    # is an optional extra), so no import mocking is needed — this exercises
    # the real ModuleNotFoundError path.
    monkeypatch.delitem(sys.modules, "ibm_db", raising=False)

    from thomas.connectors.db2 import DB2Connector

    with pytest.raises(ConnectorTechnicalError, match=r"^DB2 driver not installed\. Run: pip install thomas\[db2\]$"):
        DB2Connector(dict(CONFIG))


def test_run_validation_does_not_reconnect_across_multiple_calls(monkeypatch):
    connector, connect_mock, _ = _make_connector(monkeypatch, rows=[{"STATUS": "SETTLED"}])
    connector.connect()

    connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-1", "2026-07-28T09:00:00-03:00")
    connector.run_validation({"query": "SELECT status FROM t", "field": "status"}, "corr-2", "2026-07-28T09:00:00-03:00")

    connect_mock.assert_called_once()


def test_disconnect_is_safe_when_connect_never_called(monkeypatch):
    _install_fake_ibm_db(monkeypatch, MagicMock())
    from thomas.connectors.db2 import DB2Connector

    connector = DB2Connector(dict(CONFIG))
    connector.disconnect()


def test_disconnect_is_safe_when_connect_failed_partway(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, connect_side_effect=Exception("boom"))

    with pytest.raises(ConnectorTechnicalError):
        connector.connect()

    connector.disconnect()


def test_never_show_fields_includes_connection_string_username_and_password():
    from thomas.connectors.db2 import DB2Connector

    assert DB2Connector.NEVER_SHOW_FIELDS == frozenset({"connection_string", "username", "password"})


def test_describe_query_returns_literal_sql_text(monkeypatch):
    connector, _, _ = _make_connector(monkeypatch, rows=[])

    query = connector.describe_query({"query": "SELECT status FROM t WHERE id = :correlation_id", "field": "status"})

    assert query == "SELECT status FROM t WHERE id = :correlation_id"
