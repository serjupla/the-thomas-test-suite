# Architecture — Connectors

## Common abstract interface

Every connector implements the same minimal interface, regardless of the
data source type:

```python
class BaseConnector(ABC):
    def __init__(self, config: dict):
        """config comes directly from the environment's `connectors.<name>` block."""

    @abstractmethod
    def connect(self) -> None:
        """Establishes the connection. Raises ConnectorTechnicalError on failure."""

    @abstractmethod
    def run_validation(self, validation: dict, correlation_id: str) -> Any:
        """
        Executes the query described in the validation (query, topic+filter,
        etc.) and returns the raw value of the requested field
        (`validation["field"]`). Raises ConnectorTechnicalError on
        infrastructure failure — must never silently swallow the error by
        returning None.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Releases the connection."""
```

The `validation/validation_runner.py` module is the only place that
instantiates connectors, using a dispatch dictionary by `type` (similar to
the operator engine) — never an `if/elif` per connector type.

## Connection lifecycle

- One connection per named connector is opened **once per `thomas
  validate` run**, reused for every validation referencing it, and closed
  at the end (or on fatal error). Do not open/close a connection per
  individual validation — that would be expensive for hundreds of
  scenarios.
- If a connector required by some validation doesn't exist in the given
  environment, the command must fail **before starting any dispatch/
  validation**, with a clear message listing the missing connectors.

## Packaging extras (`pyproject.toml`)

```toml
[project.optional-dependencies]
oracle = ["oracledb"]
db2 = ["ibm-db"]
mongo = ["pymongo"]
kafka = ["confluent-kafka"]
```

The Thomas base package depends on no database/messaging driver. If a
user tries to use a connector whose driver isn't installed, The Thomas must
detect this and guide the user to exactly which extra to install (e.g.
`pip install thomas[oracle]`), never just propagate a raw `ImportError`.

---

## Oracle Connector

```json
"oracle_main": {
  "type": "oracle",
  "dsn": "host:port/service_name",
  "username": "...",
  "password": "..."
}
```

- Driver: `oracledb`, thin mode (does not require Instant Client
  installed).
- `run_validation`: executes `validation["query"]`, substituting
  `:correlation_id` with the resolved value; expects exactly one result
  row; extracts `validation["field"]` (column name, case-insensitive)
  from that row.
- Query with zero rows → `technical_error = "no record found for the
  given query"`.
- Query with more than one row → `technical_error = "query returned
  multiple records; refine the query to return a single record"`.

## DB2 Connector (via JDBC)

```json
"db2_legacy": {
  "type": "db2",
  "connection_string": "DATABASE=...;HOSTNAME=...;PORT=...;PROTOCOL=TCPIP",
  "username": "...",
  "password": "..."
}
```

- Driver: `ibm-db` (native CLI/ODBC access) — preferred, as it does not
  require a JVM. If unviable in the target environment, the alternative
  via `jaydebeapi` (JDBC, requires a JVM) should be evaluated and
  documented as an additional prerequisite in that case.
- Same behavior contract as the Oracle connector (single expected row,
  same technical error rules).

## MongoDB Connector

```json
"mongo_main": {
  "type": "mongo",
  "uri": "mongodb://host:port",
  "database": "database_name",
  "username": "...",
  "password": "..."
}
```

- Driver: `pymongo`.
- In the scenario, the validation replaces `query` (SQL) with a
  **Mongo-style filter query**:

```json
{
  "id": "document_status",
  "connector": "mongo_main",
  "collection": "instant_transfer_transactions",
  "filter": { "correlationId": ":correlation_id" },
  "field": "status",
  "operator": "equals",
  "expected_value": "SETTLED"
}
```

- `:correlation_id` inside any `filter` value is substituted the same way
  as in the SQL query.
- `field` supports dot-path notation for nested fields (e.g.
  `"details.settlement_status"`).
- Same "zero documents" / "multiple documents" rules as Oracle/DB2.

## Kafka Connector

```json
"kafka_main": {
  "type": "kafka",
  "brokers": ["broker1:9092", "broker2:9092"],
  "username": "...",
  "password": "..."
}
```

- Driver: `confluent-kafka`.
- Consumption strategy: an **ephemeral consumer group, exclusive to each
  `thomas validate` run**, configured to read from the
  `request_timestamp` of the scenario being validated (offset-by-time,
  not from the beginning of the topic) up to the present moment, with a
  configurable timeout (default 30s per validation) — avoids
  reprocessing the entire topic history on every round.
- Filters messages whose field indicated by `key_filter` matches the
  scenario's `correlation_id`.
- If no matching message is found within the timeout:
  `technical_error = "no matching message found on the topic within the
  time limit"`.
- If more than one message matches, uses the **most recent** one by
  default (explicitly documented behavior, since reprocessing can
  legitimately generate duplicates).

## Fake Connector

```json
"fake_ledger": {
  "type": "fake",
  "values": { "order_confirmed": "confirmed" },
  "failures": {}
}
```

- No driver, no I/O, no packaging extra — `values`/`failures` are fixed,
  in-memory maps declared directly in the environment file and returned
  as-is by `validation["id"]`.
- Two uses: (a) the automated test suite for `thomas validate`
  (`tests/connectors/test_fake_connector.py`), and (b) as of Feature 011,
  the packaged quickstart example generated by `thomas init`
  (`examples/scenarios/quickstart/03_create_and_confirm_order.json`), to
  demonstrate a request → validate flow with an immediate, deterministic
  confirmation, without depending on real infrastructure or a second
  network call during `validate` (see
  `specs/011-init-quickstart-real-apis/research.md`, decision R2).
- It is **not** a production connector type: it does not connect to any
  real, external data source, so it is not suitable for validating a real
  system's side effects. Do not use it outside of tests and the packaged
  quickstart example.

## Adding a new connector type (guide for future features)

1. Create `src/thomas/connectors/<new_type>.py`, implementing
   `BaseConnector`.
2. Register it in the connector dispatch dictionary.
3. Add the corresponding extra in `pyproject.toml`.
4. Document the `validation` format specific to this type in this file.
5. Add a fictional example under `examples/scenarios/`.
