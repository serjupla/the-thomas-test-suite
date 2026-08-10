"""DB2 connector (native ibm_db CLI/ODBC driver, no JVM required). See
docs/architecture/05-connectors.md and contracts/db2-connector.md.
Requires the optional extra `thomas[db2]`.
"""

from __future__ import annotations

import logging
from typing import Any

from thomas.connectors import BaseConnector, ConnectorTechnicalError

_logger = logging.getLogger("thomas.connectors.db2")

_REQUIRED_CONFIG_FIELDS = ("connection_string", "username", "password")


class DB2Connector(BaseConnector):
    NEVER_SHOW_FIELDS = frozenset({"connection_string", "username", "password"})

    def __init__(self, config: dict):
        super().__init__(config)
        try:
            import ibm_db
        except ModuleNotFoundError as exc:
            raise ConnectorTechnicalError("DB2 driver not installed. Run: pip install thomas[db2]") from exc

        for field in _REQUIRED_CONFIG_FIELDS:
            if not config.get(field):
                raise ConnectorTechnicalError(f"DB2 connector config is missing required field: {field}")

        self._ibm_db = ibm_db
        self._connection = None

    def connect(self) -> None:
        try:
            self._connection = self._ibm_db.connect(
                self.config["connection_string"], self.config["username"], self.config["password"]
            )
        except Exception as exc:
            _logger.debug("DB2 connection failed", exc_info=True)
            raise ConnectorTechnicalError(
                "failed to connect to DB2 database — check connection_string/username/password"
            ) from exc

    def run_validation(self, validation: dict, correlation_id: str, request_timestamp: str) -> Any:
        query = validation["query"].replace(":correlation_id", "?")
        stmt = self._ibm_db.prepare(self._connection, query)
        self._ibm_db.execute(stmt, (correlation_id,))

        rows = []
        row = self._ibm_db.fetch_assoc(stmt)
        while row is not False:
            rows.append(row)
            row = self._ibm_db.fetch_assoc(stmt)

        if len(rows) == 0:
            raise ConnectorTechnicalError("no record found for the given query")
        if len(rows) > 1:
            raise ConnectorTechnicalError(
                "query returned multiple records; refine the query to return a single record"
            )

        row_map = {column.lower(): value for column, value in rows[0].items()}
        return row_map[validation["field"].lower()]

    def describe_query(self, validation: dict) -> str:
        return validation["query"]

    def disconnect(self) -> None:
        if self._connection is None:
            return
        try:
            self._ibm_db.close(self._connection)
        except Exception:
            pass
