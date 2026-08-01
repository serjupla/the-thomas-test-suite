# Architecture — Data Schemas

Every JSON file handled by The Thomas carries `schema_version` (integer) at
the root level. The Thomas must validate this field and the rest of the
document against the corresponding JSON Schema (draft-07) before any
processing, failing with a clear message on incompatibility.

---

## 1. Scenario Schema (`scenario_v1.json`)

### Full example — success case with validation on two connectors

```json
{
  "schema_version": 1,
  "feature": "instant_transfer",
  "scenario_id": "valid_amount_transfer",
  "description": "An instant transfer with valid data must be settled",
  "endpoint": {
    "method": "POST",
    "path": "/orders"
  },
  "payload": {
    "source_account": "{{valid_bank_account}}",
    "destination_key": "{{valid_payment_key}}",
    "customer_id": "{{fake_customer_id}}",
    "amount": 150.00
  },
  "correlation": {
    "source": "api_response",
    "field": "$.id"
  },
  "api_checks": [
    { "id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201 },
    { "id": "initial_status", "field": "$.status", "operator": "equals", "expected_value": "PENDING" }
  ],
  "validations": [
    {
      "id": "transaction_status_oracle",
      "connector": "oracle_main",
      "query": "SELECT STATUS FROM PAYMENT_TRANSACTIONS WHERE ID = :correlation_id",
      "field": "STATUS",
      "operator": "equals",
      "expected_value": "SETTLED"
    },
    {
      "id": "kafka_confirmation",
      "connector": "kafka_main",
      "topic": "payments.instant_transfer.confirmation",
      "key_filter": "correlationId",
      "field": "status",
      "operator": "equals",
      "expected_value": "CONFIRMED"
    }
  ]
}
```

### Example — expected failure case, checking nothing was persisted

```json
{
  "schema_version": 1,
  "feature": "instant_transfer",
  "scenario_id": "invalid_key_transfer",
  "description": "A non-existent payment key must be rejected without persisting any transaction",
  "endpoint": { "method": "POST", "path": "/orders" },
  "payload": {
    "source_account": "{{valid_bank_account}}",
    "destination_key": "nonexistent-key@example.com",
    "customer_id": "{{fake_customer_id}}",
    "amount": 50.00
  },
  "correlation": { "source": "request_payload", "field": "idempotency_key" },
  "api_checks": [
    { "id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 422 },
    { "id": "error_code", "field": "$.error.code", "operator": "equals", "expected_value": "PAYMENT_KEY_NOT_FOUND" }
  ],
  "validations": [
    {
      "id": "nothing_persisted",
      "connector": "oracle_main",
      "query": "SELECT COUNT(*) as TOTAL FROM PAYMENT_TRANSACTIONS WHERE IDEMPOTENCY_KEY = :correlation_id",
      "field": "TOTAL",
      "operator": "equals",
      "expected_value": 0
    }
  ]
}
```

### Example — dynamic path with variable-based correlation

```json
{
  "schema_version": 1,
  "feature": "user_management",
  "scenario_id": "update_user_profile",
  "description": "Update an existing user profile using a variable for both path and correlation",
  "endpoint": {
    "method": "PUT",
    "path": "/users/{{user_id}}/profile"
  },
  "payload": {
    "name": "{{user_name}}",
    "email": "{{user_email}}"
  },
  "correlation": {
    "source": "variable",
    "field": "request_id"
  },
  "api_checks": [
    { "id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 200 },
    { "id": "response_name", "field": "$.name", "operator": "equals", "expected_value": "{{user_name}}" }
  ]
}
```

Notes on this example:
- `endpoint.path` is `/users/{{user_id}}/profile`, which resolves to `/users/12345/profile` if `user_id = "12345"`.
- `correlation.source` is `"variable"`, so the `correlation_id` is taken directly from the `request_id` variable (not from the response or payload).
- Both `payload` fields and `endpoint.path` can reference variables; they are all resolved before the HTTP request is built.

### Example — custom headers in scenario endpoint (Feature 004)

```json
{
  "schema_version": 1,
  "feature": "api_authentication",
  "scenario_id": "create_order_with_auth",
  "description": "Create an order with custom authentication headers",
  "endpoint": {
    "method": "POST",
    "path": "/orders",
    "headers": {
      "Authorization": "Bearer {{auth_token}}",
      "X-Request-Id": "{{request_id}}",
      "X-Tenant": "tenant-staging"
    }
  },
  "payload": {
    "amount": 100.00,
    "customer_id": "{{customer_id}}"
  },
  "correlation": {
    "source": "api_response",
    "field": "$.id"
  },
  "api_checks": [
    { "id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201 }
  ]
}
```

Notes on this example:
- `endpoint.headers` is an optional object (new in Feature 004) with custom HTTP headers to send.
- Header values support variable substitution (e.g., `"Bearer {{auth_token}}"`), resolved the same way as `payload` and `path`.
- Headers from the environment (if defined) are merged with these scenario headers, with scenario values taking precedence on key collision.
- This example sends `Authorization`, `X-Request-Id`, and `X-Tenant` headers; the first two are resolved from variables, the third is literal.

### Field dictionary

| Field | Required | Description |
|---|---|---|
| `schema_version` | Yes | Scenario schema version. |
| `feature` | Yes | Business feature identifier (e.g. "instant_transfer"). Used for grouping/filtering in the report. |
| `scenario_id` | Yes | Unique identifier within the `feature`. |
| `description` | No | Free text, shown in the report. |
| `endpoint.method` | Yes | `GET`, `POST`, `PUT`, `DELETE`, `PATCH`. |
| `endpoint.path` | Yes | Relative path, concatenated with the environment's `base_url`; supports `{{variable}}` (e.g., `/users/{{user_id}}`). |
| `endpoint.headers` | No | Custom HTTP headers for this scenario. Object with string keys and values (e.g., `{"Authorization": "Bearer {{auth_token}}"}`). Values support `{{variable}}`. Merges with environment `api.headers` with scenario values taking precedence. (Feature 004) |
| `payload` | No | Free-form object; supports `{{variable}}`. Omitted for bodyless methods. |
| `correlation.source` | Yes (if there are `validations`) | `api_response`, `request_payload`, or `variable`. |
| `correlation.field` | Yes (if there are `validations`) | JSONPath (if source = `api_response`), field name in the payload (if source = `request_payload`), or variable name (if source = `variable`). |
| `api_checks` | Yes (list, can be empty — not recommended) | List of checks on the HTTP response, using the operator engine. |
| `validations` | No (list, may be omitted or empty) | List of connector-based validations, using the operator engine. |

In `api_checks`, the field value `"status_code"` is a special value
recognized by the engine (refers to the HTTP status code of the
response); any other `field` value is treated as a JSONPath over the
response body.

In `validations`, the placeholder `:correlation_id` inside `query` is
automatically substituted with the resolved value of `correlation` before
execution. For Kafka, `key_filter` indicates which field of the message
must match `correlation_id`.

---

## 2. Environment Schema (`environment_v1.json`)

```json
{
  "schema_version": 1,
  "environment_name": "staging",
  "company_name": "Example Corp",
  "department_name": "Payments QA",
  "system_name": "Example System",
  "timezone": "America/Sao_Paulo",
  "report_language": "en",
  "api": {
    "base_url": "https://staging.example.com/api",
    "timeout_seconds": 30,
    "ssl_verify": false,
    "headers": {
      "X-API-Key": "{{staging_api_key}}",
      "X-Tenant": "example-staging"
    }
  },
  "services_info": [
    {
      "name": "instant-transfer-service",
      "info_url": "https://staging.example.com/instant-transfer/info",
      "fields_to_extract": ["version", "status"],
      "ssl_verify": true,
      "headers": {
        "Authorization": "Bearer {{service_token}}"
      }
    },
    {
      "name": "billing-service",
      "info_url": "https://staging.example.com/billing/info",
      "ssl_verify": false
    }
  ],
  "connectors": {
    "oracle_main": {
      "type": "oracle",
      "dsn": "staging-oracle.example.com:1521/STAGINGPDB",
      "username": "test_user",
      "password": "***"
    },
    "db2_legacy": {
      "type": "db2",
      "connection_string": "DATABASE=STAGINGDB;HOSTNAME=staging-db2.example.com;PORT=50000;PROTOCOL=TCPIP",
      "username": "test_user",
      "password": "***"
    },
    "mongo_main": {
      "type": "mongo",
      "uri": "mongodb://staging-mongo.example.com:27017",
      "database": "payment_hub",
      "username": "test_user",
      "password": "***"
    },
    "kafka_main": {
      "type": "kafka",
      "brokers": ["broker1.example.com:9092", "broker2.example.com:9092"],
      "username": "test_user",
      "password": "***"
    }
  }
}
```

### Field dictionary

| Field | Required | Type | Default | Description |
|---|---|---|---|---|
| `environment_name` | Yes | string | — | Environment identifier (e.g. "staging"), should match the file name. |
| `company_name` | No | string | — | Organization context for audit trail; appears in execution record if present. |
| `department_name` | No | string | — | Department/team context for audit trail; appears in execution record if present. |
| `system_name` | Yes | string | — | Name of the system under test, shown in the report header. |
| `timezone` | Yes | string | — | IANA name (e.g. `America/Sao_Paulo`); used to format every timestamp in the report. |
| `report_language` | No | enum | `"en"` | `"en"` or `"pt"` — language used to render `thomas report` output. |
| `api.base_url` | Yes | string | — | Base URL concatenated with each scenario's `endpoint.path`. |
| `api.timeout_seconds` | No | integer | 30 | HTTP request timeout in seconds. |
| `api.ssl_verify` | No | boolean | `true` | SSL certificate verification for API requests; set to `false` for self-signed certs in staging. |
| `api.headers` | No | object | — | Custom HTTP headers applied to all scenario requests. Object with string keys and values; values support `{{variable}}` for dynamic substitution. Scenario headers override these for the same key. (Feature 004) |
| `services_info[].name` | Yes | string | — | Service identifier (e.g., `"payment-gateway"`). |
| `services_info[].info_url` | Yes | string | — | HTTP endpoint to query for service information. |
| `services_info[].fields_to_extract` | No | array | — | Array of field names to extract from the JSON response. If omitted, the entire response body is recorded. |
| `services_info[].ssl_verify` | No | boolean | `true` | SSL certificate verification for this service's polling; independent of `api.ssl_verify`. |
| `services_info[].headers` | No | object | — | Custom HTTP headers for this service's polling requests. Object with string keys and values; values support `{{variable}}`. (Feature 004) |
| `connectors.<name>.type` | Yes | string | — | `oracle`, `db2`, `mongo`, or `kafka` — determines which driver/module is used. |
| `connectors.<name>.*` | Yes (varies by type) | — | — | Remaining connection fields, specific per type (see `05-connectors.md`). |

A single environment may have **multiple connectors of the same type**
(e.g. `oracle_main` and `oracle_secondary`), each with its own name.

---

## 3. Preparatory Variables Schema (`variables_v1.json`)

```json
{
  "schema_version": 1,
  "variables": {
    "valid_bank_account": "12345-6",
    "valid_payment_key": "fake-key@example.com",
    "fake_customer_id": "999999"
  }
}
```

In v1, all variables are static values, read once before the dispatch
phase (`thomas request`) starts. Any scenario can reference any variable
defined here via `{{variable_name}}` anywhere in the `payload`. Future
roadmap item (out of current scope): support `"source": "api"` or
`"source": "database"` per variable, with dynamic resolution during the
preparation step.

---

## 4. Execution Record Schema (`execution_v1.json`)

```json
{
  "schema_version": 1,
  "execution_id": "execution_2026-07-25_1430",
  "thomas_version": "0.1.0",
  "environment": "staging",
  "title": "Release 4.2 — Regression Pass",
  "start_timestamp": "2026-07-25T14:30:00-03:00",
  "included_scenarios": [
    "scenarios/instant_transfer/valid_amount_transfer.json",
    "scenarios/instant_transfer/invalid_key_transfer.json"
  ],
  "services_info": [
    {
      "name": "instant-transfer-service",
      "collected_at": "2026-07-25T14:30:01-03:00",
      "status_code": 200,
      "error": null,
      "data": { "version": "2.4.1", "status": "online" }
    }
  ],
  "results": [
    {
      "scenario_file": "scenarios/instant_transfer/valid_amount_transfer.json",
      "feature": "instant_transfer",
      "scenario_id": "valid_amount_transfer",
      "folder": "instant_transfer",
      "description": "An instant transfer with valid data must be settled",
      "correlation_id": "abc-123-def",
      "correlation_error": null,
      "request_timestamp": "2026-07-25T14:30:02-03:00",
      "response_timestamp": "2026-07-25T14:30:02.340000-03:00",
      "request_sent": { "method": "POST", "path": "/orders", "payload": { "...": "..." }, "headers": { "Authorization": "Bearer abc123", "X-Tenant": "example-staging" } },
      "api_response": { "status_code": 201, "body": { "id": "abc-123-def", "status": "PENDING" } },
      "request_technical_error": null,
      "api_checks_result": [
        { "id": "http_status", "expected": 201, "obtained": 201, "operator": "equals", "passed": true },
        { "id": "initial_status", "expected": "PENDING", "obtained": "PENDING", "operator": "equals", "passed": true }
      ],
      "api_result": "passed",
      "validation_rounds": [
        {
          "timestamp": "2026-07-25T16:00:00-03:00",
          "environment_used": "staging",
          "results": [
            { "id": "transaction_status_oracle", "connector": "oracle_main", "field": "status", "expected": "SETTLED", "obtained": "PROCESSING", "operator": "equals", "query": "SELECT status FROM transactions WHERE correlation_id = :correlation_id", "passed": false, "technical_error": null },
            { "id": "kafka_confirmation", "connector": "kafka_main", "field": "status", "expected": "CONFIRMED", "obtained": null, "operator": "equals", "query": "topic=confirmations filter=correlationId", "passed": false, "technical_error": "timeout waiting for message on topic" }
          ],
          "round_result": "failed"
        },
        {
          "timestamp": "2026-07-25T18:30:00-03:00",
          "environment_used": "staging",
          "results": [
            { "id": "transaction_status_oracle", "connector": "oracle_main", "field": "status", "expected": "SETTLED", "obtained": "SETTLED", "operator": "equals", "query": "SELECT status FROM transactions WHERE correlation_id = :correlation_id", "passed": true, "technical_error": null },
            { "id": "kafka_confirmation", "connector": "kafka_main", "field": "status", "expected": "CONFIRMED", "obtained": "CONFIRMED", "operator": "equals", "query": "topic=confirmations filter=correlationId", "passed": true, "technical_error": null }
          ],
          "round_result": "passed"
        }
      ],
      "final_status": "passed"
    }
  ]
}
```

### Write/update rules

- `thomas request` creates the whole file, with `validation_rounds: []`
  for every scenario, and `final_status` computed as `awaiting_validation`
  (if there are `validations`) or inherited from `api_result` (if not).
- `thomas_version` records the installed version of The Thomas that
  produced the execution record (the package's own version, not
  `schema_version`, which tracks the JSON document's shape). It is written
  once by `thomas request` and never modified afterward — useful for
  reproducing or auditing a run against a specific release, especially
  when validation happens much later, potentially after an upgrade.
- `thomas validate` only **appends** a new object to each processed
  scenario's `validation_rounds` array, and recalculates `final_status`.
  It never removes or edits previous rounds.
- `environment_used` inside each round records which environment file was
  used for that particular validation run (relevant when validation is
  run against a different environment than the one used for dispatch, or
  across different environments between rounds).
- `technical_error` field: `null` when the validation executed
  successfully (regardless of the assertion result); contains the error
  message when there was an infrastructure failure (connection, timeout,
  invalid query). A validation with `technical_error` set is always
  `"passed": false`.

### Scenario result technical-failure fields (`thomas request`)

Two fields on each `results[]` entry distinguish technical failures at
dispatch time from a regular failed `api_check`, mirroring the same
technical-error-vs-assertion-failure distinction used for `validations`:

- `correlation_error`: `null` when `correlation_id` was resolved
  successfully (or when the scenario has no `validations` and no
  `correlation` block at all); otherwise contains a message explaining why
  resolution failed (e.g. the `correlation.field` JSONPath did not match
  anything in the response body). When set, `correlation_id` is `null` and
  the scenario's `final_status` is forced to `"failed"`, regardless of the
  `api_checks` outcome.
- `request_technical_error`: `null` when the HTTP request completed
  (regardless of status code or `api_checks` outcome); contains the error
  message when the request itself could not be completed (connection
  error, timeout). When set, `api_response` is `null` and `api_result` is
  `"failed"`.

### Report title, scenario description, and per-check field/query (additive, no `schema_version` bump)

- `title` (top-level, optional string): set only when `thomas request --title
  "<text>"` was supplied with non-blank content; absent otherwise. Rendered
  as a dedicated section below the report header, escaped as literal text.
- `results[].description` (optional string, `null` when absent): copied
  verbatim from the source scenario's own `description` field at `thomas
  request` time. Shown in the report's scenario detail view when present.
- `results[].validation_rounds[].results[].field` and `.query`: `field` is
  copied from `validation["field"]`; `query` is produced by
  `connector.describe_query(validation)` (the literal SQL text for Oracle,
  `lookup: <validation_id>` for the Fake connector). Both are subject to the
  same sensitive-keyword masking and connector `NEVER_SHOW_FIELDS` denylist
  as any other field in the report (see docs/architecture/05-connectors.md).
  Execution records written before this feature simply lack these keys; the
  report falls back to a neutral placeholder ("—") for `query` in that case.

### Response timestamp (`thomas request`)

Alongside `request_timestamp` (captured immediately before the HTTP call is
made), each `results[]` entry also carries `response_timestamp`: the moment
the response was received (or, for a streaming/chunked response, once the
body has been fully read). `response_timestamp` is `null` whenever
`request_technical_error` is set, since no response was ever received. The
difference between the two timestamps is the scenario's response time —
recorded here so a later feature (the HTML report) can display it without
`thomas request` needing to compute or format a duration itself.

### Request headers in execution record (`request_sent.headers`) (Feature 004)

The `request_sent` object now includes a `headers` field containing all HTTP headers sent with the request.
This includes:
- Headers defined in `endpoint.headers` (scenario-level)
- Headers defined in `environment.api.headers` (environment-level)
- Merged result with scenario headers taking precedence over environment headers for the same key

All variable substitutions (e.g., `{{auth_token}}`) are resolved before recording, so the `headers` field
shows the actual values sent. This ensures full traceability and auditability of requests for compliance
and debugging purposes.

Example:
```json
"request_sent": {
  "method": "POST",
  "path": "/orders",
  "payload": { "amount": 100.00, "customer_id": "12345" },
  "headers": {
    "Authorization": "Bearer eyJhbGc...",
    "X-Request-Id": "req-2026-07-25-001",
    "X-Tenant": "tenant-staging",
    "X-API-Key": "staging-key-abc123"
  }
}
```

### Variable substitution in `endpoint.path`

The `endpoint.path` field supports the same `{{variable_name}}` substitution
syntax as `payload`. This allows dynamic path construction (e.g., `/users/{{user_id}}/orders/{{order_id}}`).
Variables are resolved before the URL is built, using the same dictionary
as payload substitution. If a variable referenced in the path is not defined,
the command aborts with a clear error message before any HTTP request is sent
(precondition validation, same as for `payload` variables).

### Correlation source: `variable`

In addition to `source: "api_response"` and `source: "request_payload"`,
`correlation.source` now supports `source: "variable"`. When set:
- `correlation.field` is interpreted as a variable name (not a JSONPath or payload field name).
- The `correlation_id` is resolved directly from the variables dictionary.
- If the variable is not defined, a `correlation_error` is recorded (distinct
  technical failure), and `final_status` is set to `"failed"`.

Example:
```json
"correlation": {
  "source": "variable",
  "field": "request_id"
}
```
With `variables: {"request_id": "req-12345"}`, the correlation_id becomes `"req-12345"`.
