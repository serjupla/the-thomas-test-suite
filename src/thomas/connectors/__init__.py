"""Abstract connector contract + type registry. See docs/architecture/05-connectors.md.

`BaseConnector` is the isolation boundary every connector type (present and
future) implements. Only `FakeConnector` (test-only) is registered by this
feature; real drivers (Oracle, DB2, Mongo, Kafka) register here in their own
future features without touching `thomas.validate` orchestration logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ConnectorTechnicalError(Exception):
    """Raised by a BaseConnector implementation to signal an infrastructure-level
    failure (connection, timeout, invalid query/topic) — never a normal non-match."""


class BaseConnector(ABC):
    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def connect(self) -> None:
        """Raises ConnectorTechnicalError on failure."""

    @abstractmethod
    def run_validation(self, validation: dict, correlation_id: str) -> Any:
        """Returns the raw obtained value for validation["field"]; raises
        ConnectorTechnicalError on infrastructure failure — never returns None
        to silently signal a failure."""

    @abstractmethod
    def disconnect(self) -> None:
        """Releases the connection."""


CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {}


def resolve_connector_type(type_name: str) -> type[BaseConnector]:
    """Look up a connector class by its environment `connectors.<name>.type` value.

    Raises ConnectorTechnicalError (never a bare KeyError) naming the unknown
    type if it isn't registered.
    """
    connector_type = CONNECTOR_TYPES.get(type_name)
    if connector_type is None:
        raise ConnectorTechnicalError(f"unregistered connector type: {type_name}")
    return connector_type


def _register_builtin_types() -> None:
    from thomas.connectors.fake import FakeConnector
    from thomas.connectors.oracle import OracleConnector

    CONNECTOR_TYPES["fake"] = FakeConnector
    CONNECTOR_TYPES["oracle"] = OracleConnector


_register_builtin_types()
