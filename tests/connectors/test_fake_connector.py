import pytest

from thomas.connectors import ConnectorTechnicalError
from thomas.connectors.fake import FakeConnector


def test_returns_preconfigured_value_for_known_id():
    connector = FakeConnector({"values": {"balance_check": 150.0}, "failures": {}})
    connector.connect()

    assert connector.run_validation({"id": "balance_check"}, "corr-1") == 150.0


def test_raises_technical_error_for_id_in_failures():
    connector = FakeConnector({"values": {}, "failures": {"balance_check": "connection timed out"}})
    connector.connect()

    with pytest.raises(ConnectorTechnicalError, match="connection timed out"):
        connector.run_validation({"id": "balance_check"}, "corr-1")


def test_raises_technical_error_for_id_in_neither_map():
    connector = FakeConnector({"values": {}, "failures": {}})
    connector.connect()

    with pytest.raises(ConnectorTechnicalError, match="balance_check"):
        connector.run_validation({"id": "balance_check"}, "corr-1")


def test_never_show_fields_unchanged_empty():
    connector = FakeConnector({"values": {}, "failures": {}})
    assert connector.NEVER_SHOW_FIELDS == frozenset()


def test_describe_query_returns_lookup_label():
    connector = FakeConnector({"values": {}, "failures": {}})
    assert connector.describe_query({"id": "balance_check"}) == "lookup: balance_check"
