"""Live PostgreSQL checks (research R8). Skipped unless THOMAS_TEST_POSTGRES_DSN
points at a disposable database and psycopg is installed (`thomas[postgres]`)."""

import datetime
import json
import os

import pytest

from thomas.connectors import ConnectorTechnicalError
from thomas.core.json_encoding import ExecutionRecordEncoder

DSN = os.environ.get("THOMAS_TEST_POSTGRES_DSN")

pytestmark = pytest.mark.skipif(not DSN, reason="THOMAS_TEST_POSTGRES_DSN not set")

TABLE = "thomas_pg_live_types"
CORRELATION_ID = "live-corr-1"
TIMESTAMP = "2026-07-28T09:00:00-03:00"


@pytest.fixture(scope="module")
def live_table():
    psycopg = pytest.importorskip("psycopg")
    # A regular (not TEMP) table: temp tables are session-local, and the
    # connector opens its own session. Setup uses a separate writable session.
    with psycopg.connect(DSN, autocommit=True) as setup:
        setup.execute(f"DROP TABLE IF EXISTS {TABLE}")
        setup.execute(
            f"""CREATE TABLE {TABLE} (
                correlation_id text PRIMARY KEY,
                c_integer integer, c_bigint bigint, c_numeric_int numeric, c_numeric_frac numeric(10,2),
                c_real real, c_bool boolean, c_text text, c_uuid uuid, c_date date,
                c_timestamptz timestamptz, c_jsonb jsonb, c_array integer[], c_null text,
                c_bytea bytea, c_interval interval, c_inet inet, c_time time
            )"""
        )
        setup.execute(
            f"""INSERT INTO {TABLE} VALUES (
                %s, 7, 9000000000, 42, 12.50, 1.5, true, 'SETTLED',
                '12345678-abcd-4abc-8def-1234567890ab', '2026-07-28', '2026-07-28 12:00:00+00',
                '{{"items": [1, 2.5], "status": "SETTLED"}}', ARRAY[1, 2, 3], NULL,
                '\\x01ff'::bytea, '1 hour 30 minutes', '192.0.2.10', '09:30:00'
            )""",
            (CORRELATION_ID,),
        )
    yield
    with psycopg.connect(DSN, autocommit=True) as teardown:
        teardown.execute(f"DROP TABLE IF EXISTS {TABLE}")


@pytest.fixture
def connector(live_table):
    from thomas.connectors.postgres import PostgresConnector

    instance = PostgresConnector({"type": "postgres", "connection_string": DSN})
    instance.connect()
    yield instance
    instance.disconnect()


def _run(connector, field, query=None):
    query = query or f"SELECT * FROM {TABLE} WHERE correlation_id = :correlation_id"
    return connector.run_validation({"query": query, "field": field}, CORRELATION_ID, TIMESTAMP)


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("c_integer", 7),
        ("c_bigint", 9000000000),
        ("c_numeric_int", 42),
        ("c_numeric_frac", 12.5),
        ("c_real", 1.5),
        ("c_bool", True),
        ("c_text", "SETTLED"),
        ("c_uuid", "12345678-abcd-4abc-8def-1234567890ab"),
        ("c_jsonb", {"items": [1, 2.5], "status": "SETTLED"}),
        ("c_array", [1, 2, 3]),
        ("c_null", None),
        ("c_bytea", "\\x01ff"),
        ("c_interval", "1:30:00"),
        ("c_inet", "192.0.2.10"),
        ("c_time", "09:30:00"),
    ],
)
def test_live_values_are_normalized(connector, field, expected):
    value = _run(connector, field)

    assert value == expected
    assert type(value) is type(expected)
    json.dumps({"obtained": value}, cls=ExecutionRecordEncoder)


def test_live_dates_serialize_as_iso_8601(connector):
    date_value = _run(connector, "c_date")
    timestamp_value = _run(connector, "c_timestamptz")

    assert date_value == datetime.date(2026, 7, 28)
    assert timestamp_value == datetime.datetime(2026, 7, 28, 12, 0, tzinfo=datetime.timezone.utc)
    json.dumps({"d": date_value, "ts": timestamp_value}, cls=ExecutionRecordEncoder)


def test_live_percent_and_casts_are_preserved(connector):
    query = (
        f"SELECT c_text FROM {TABLE} WHERE correlation_id = :correlation_id::text "
        "AND c_text LIKE 'SETT%' AND c_date::text = '2026-07-28'"
    )

    assert _run(connector, "c_text", query) == "SETTLED"


def test_live_write_is_rejected_and_connection_recovers(connector):
    with pytest.raises(ConnectorTechnicalError, match="^query failed:"):
        _run(connector, "c_text", f"INSERT INTO {TABLE} (correlation_id) VALUES (:correlation_id) RETURNING c_text")

    assert _run(connector, "c_text") == "SETTLED"
