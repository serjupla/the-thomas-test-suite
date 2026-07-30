import pytest

from thomas.connectors import BaseConnector, ConnectorTechnicalError, resolve_connector_type
from thomas.connectors.fake import FakeConnector


def test_base_connector_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BaseConnector({})


def test_connector_technical_error_is_a_plain_exception():
    assert issubclass(ConnectorTechnicalError, Exception)


def test_resolve_connector_type_returns_registered_class():
    assert resolve_connector_type("fake") is FakeConnector


def test_resolve_connector_type_returns_oracle_connector():
    from thomas.connectors.oracle import OracleConnector

    assert resolve_connector_type("oracle") is OracleConnector


def test_resolve_connector_type_raises_clear_error_for_unregistered_type():
    with pytest.raises(Exception) as exc_info:
        resolve_connector_type("does_not_exist")

    assert not isinstance(exc_info.value, KeyError)
    assert "does_not_exist" in str(exc_info.value)
