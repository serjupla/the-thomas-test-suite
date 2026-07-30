"""Oracle connector (thin mode, no Oracle Instant Client). See
docs/architecture/05-connectors.md and contracts/oracle-connector.md.
Requires the optional extra `thomas[oracle]`.
"""

from __future__ import annotations

import logging
from typing import Any

from thomas.connectors import BaseConnector, ConnectorTechnicalError

_logger = logging.getLogger("thomas.connectors.oracle")


class OracleConnector(BaseConnector):
    def __init__(self, config: dict):
        super().__init__(config)
        try:
            import oracledb
        except ModuleNotFoundError as exc:
            raise ConnectorTechnicalError(
                "Oracle driver not installed. Run: pip install thomas[oracle]"
            ) from exc
        self._oracledb = oracledb
        self._connection = None

    def connect(self) -> None:
        try:
            self._connection = self._oracledb.connect(
                dsn=self.config.get("dsn"),
                user=self.config.get("username"),
                password=self.config.get("password"),
            )
        except Exception as exc:
            _logger.debug("Oracle connection failed", exc_info=True)
            raise ConnectorTechnicalError(
                "failed to connect to Oracle database — check dsn/username/password"
            ) from exc

    def run_validation(self, validation: dict, correlation_id: str) -> Any:
        cursor = self._connection.cursor()
        try:
            cursor.execute(validation["query"], correlation_id=correlation_id)
            rows = cursor.fetchall()
            columns = [column[0] for column in cursor.description]
        finally:
            cursor.close()

        if len(rows) == 0:
            raise ConnectorTechnicalError("no record found for the given query")
        if len(rows) > 1:
            raise ConnectorTechnicalError(
                "query returned multiple records; refine the query to return a single record"
            )

        row_map = {column.lower(): value for column, value in zip(columns, rows[0])}
        return row_map[validation["field"].lower()]

    def disconnect(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.close()
        except Exception:
            pass
