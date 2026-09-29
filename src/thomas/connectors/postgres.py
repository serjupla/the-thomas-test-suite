"""PostgreSQL connector (psycopg 3 with bundled libpq, no OS client required).
See docs/architecture/05-connectors.md and contracts/postgres-connector.md.
Requires the optional extra `thomas[postgres]`.
"""

from __future__ import annotations

import datetime
import decimal
import logging
import re
import uuid
from typing import Any

from thomas.connectors import BaseConnector, ConnectorTechnicalError

_logger = logging.getLogger("thomas.connectors.postgres")

_DEFAULT_CONNECT_TIMEOUT = 10

# A single leading colon only: `created_at::date` casts are never touched, while
# `:correlation_id::uuid` still matches (the trailing cast is outside the match).
_PLACEHOLDER = re.compile(r"(?<!:):correlation_id\b")

_READ_ONLY_SESSION_SQL = "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"


def _normalize(value: Any) -> Any:
    """Map a psycopg-returned value to a JSON-serializable native (spec RF-010).
    date/datetime pass through: ExecutionRecordEncoder renders them as ISO-8601."""
    if value is None or isinstance(value, (bool, int, float, str, datetime.date)):
        return value
    if isinstance(value, decimal.Decimal):
        if value.is_finite() and value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "\\x" + bytes(value).hex()
    return str(value)


def _redact(text: str, secrets: list[str]) -> str:
    """Replace every non-empty secret with `***`, longest first so a secret that
    contains another (e.g. the full connection_string) is removed whole."""
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


class PostgresConnector(BaseConnector):
    NEVER_SHOW_FIELDS = frozenset({"connection_string", "username", "password"})

    def __init__(self, config: dict):
        super().__init__(config)
        try:
            import psycopg
        except ModuleNotFoundError as exc:
            raise ConnectorTechnicalError("PostgreSQL driver not installed. Run: pip install thomas[postgres]") from exc

        if not config.get("connection_string"):
            raise ConnectorTechnicalError("PostgreSQL connector config is missing required field: connection_string")

        connect_timeout = config.get("connect_timeout", _DEFAULT_CONNECT_TIMEOUT)
        if isinstance(connect_timeout, bool) or not isinstance(connect_timeout, int) or connect_timeout <= 0:
            raise ConnectorTechnicalError(
                "PostgreSQL connector config field connect_timeout must be a positive integer (seconds)"
            )

        self._psycopg = psycopg
        self._connect_timeout = connect_timeout
        self._connection = None

    def _secret_values(self) -> list[str]:
        secrets = [self.config.get(field) for field in ("connection_string", "username", "password")]
        try:
            parsed = self._psycopg.conninfo.conninfo_to_dict(self.config["connection_string"])
            secrets.extend([parsed.get("user"), parsed.get("password")])
        except Exception:  # noqa: BLE001, S110 -- a malformed conninfo must never break error handling
            pass
        return [str(s) for s in secrets if s]

    def connect(self) -> None:
        kwargs: dict[str, Any] = {"autocommit": True, "connect_timeout": self._connect_timeout}
        if self.config.get("username"):
            kwargs["user"] = self.config["username"]
        if self.config.get("password"):
            kwargs["password"] = self.config["password"]

        connection = None
        try:
            connection = self._psycopg.connect(self.config["connection_string"], **kwargs)
            cursor = connection.cursor()
            try:
                cursor.execute(_READ_ONLY_SESSION_SQL)
            finally:
                cursor.close()
        except Exception as exc:  # noqa: BLE001 -- any driver/libpq failure maps to the fixed connect message
            # Never exc_info: a traceback re-renders the raw driver message, which
            # can carry the username or conninfo fragments (RF-018).
            _logger.debug(
                "PostgreSQL connection failed — %s: %s",
                type(exc).__name__,
                _redact(str(exc), self._secret_values()),
            )
            if connection is not None:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001, S110 -- best-effort cleanup of a half-open connection
                    pass
            self._connection = None
            raise ConnectorTechnicalError(
                "failed to connect to PostgreSQL database — check connection_string/username/password"
            ) from None
        self._connection = connection

    def run_validation(self, validation: dict, correlation_id: str, request_timestamp: str) -> Any:
        # Escape literal `%` first so the introduced placeholder is not double-escaped.
        sql = _PLACEHOLDER.sub("%(correlation_id)s", validation["query"].replace("%", "%%"))

        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, {"correlation_id": correlation_id})
            rows = cursor.fetchmany(2)
            columns = [getattr(col, "name", None) or col[0] for col in (cursor.description or [])]
        except self._psycopg.Error as exc:
            redacted = _redact(str(exc), self._secret_values())
            _logger.debug("PostgreSQL query failed — %s: %s", type(exc).__name__, redacted)
            raise ConnectorTechnicalError(
                f"query failed: {_first_line(redacted) or type(exc).__name__}"
            ) from None
        finally:
            cursor.close()

        if len(rows) == 0:
            raise ConnectorTechnicalError("no record found for the given query")
        if len(rows) > 1:
            raise ConnectorTechnicalError(
                "query returned multiple records; refine the query to return a single record"
            )

        row_map = {column.lower(): value for column, value in zip(columns, rows[0])}
        field = validation["field"]
        if field.lower() not in row_map:
            raise ConnectorTechnicalError(f"field not found in query result: {field}")
        return _normalize(row_map[field.lower()])

    def describe_query(self, validation: dict) -> str:
        return validation["query"]

    def disconnect(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.close()
        except Exception:  # noqa: BLE001, S110 -- best-effort cleanup, close() failures are not actionable
            pass
        self._connection = None
