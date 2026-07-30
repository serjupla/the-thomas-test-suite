"""Self-contained in-memory connector for automated tests only. See
docs/architecture/05-connectors.md and contracts/base-connector.md. Not a
user-selectable production connector type.
"""

from __future__ import annotations

from typing import Any

from thomas.connectors import BaseConnector, ConnectorTechnicalError


class FakeConnector(BaseConnector):
    """config = {"values": {id: raw_value, ...}, "failures": {id: error_message, ...}}"""

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def run_validation(self, validation: dict, correlation_id: str) -> Any:
        validation_id = validation["id"]
        failures = self.config.get("failures", {})
        if validation_id in failures:
            raise ConnectorTechnicalError(failures[validation_id])

        values = self.config.get("values", {})
        if validation_id in values:
            return values[validation_id]

        raise ConnectorTechnicalError(f"no value configured for validation id: {validation_id}")
