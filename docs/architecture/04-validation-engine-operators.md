# Architecture — Validation Engine and Operators

## Design principle

There is a **single** comparison engine, used both for `api_checks` and
for `validations`. No comparison logic should be duplicated or
specialized by check type — the engine always receives the same input
shape: `(obtained_value, operator, expected_value)` → structured result.

## Engine signature

```python
def evaluate(obtained_value, operator: str, expected_value) -> ValidationResult:
    """
    Returns an object with: passed (bool), obtained_value, expected_value,
    operator, and technical_error (None, unless the comparison itself is
    inapplicable to the data type — e.g. 'greater_than' with non-numeric
    strings).
    """
```

## Operator table (mandatory set for v1)

| Operator | Semantics | Applicable types | Note |
|---|---|---|---|
| `equals` | `obtained_value == expected_value` | any | strict type comparison when possible |
| `not_equals` | `obtained_value != expected_value` | any | |
| `greater_than` | `obtained_value > expected_value` | number, ISO-8601 date/time | technical error if not numeric/date |
| `greater_or_equal` | `obtained_value >= expected_value` | number, date/time | |
| `less_than` | `obtained_value < expected_value` | number, date/time | |
| `less_or_equal` | `obtained_value <= expected_value` | number, date/time | |
| `between` | `expected_value[0] <= obtained_value <= expected_value[1]` | number, date/time | `expected_value` is a `[min, max]` list |
| `contains` | `expected_value in obtained_value` | string, list | substring or list item |
| `not_contains` | negation of `contains` | string, list | |
| `starts_with` | `obtained_value.startswith(expected_value)` | string | |
| `ends_with` | `obtained_value.endswith(expected_value)` | string | |
| `in` | `obtained_value in expected_value` | any | `expected_value` is a list of acceptable values |
| `not_in` | negation of `in` | any | |
| `is_null` | `obtained_value is None` | any | `expected_value` ignored |
| `is_not_null` | `obtained_value is not None` | any | `expected_value` ignored |
| `is_empty` | zero-length string/list/object | string, list, object | |
| `is_not_empty` | negation of `is_empty` | string, list, object | |
| `length_equals` | `len(obtained_value) == expected_value` | string, list | |
| `length_greater_than` | `len(obtained_value) > expected_value` | string, list | |
| `length_less_than` | `len(obtained_value) < expected_value` | string, list | |
| `regex` | `re.match(expected_value, str(obtained_value))` is not None | string | `expected_value` is the regex pattern |

The set is extensible — new features can add operators to the dispatch
dictionary without changing the engine signature or its callers.

## Implementation via dispatch dictionary

```python
COMPARATORS: dict[str, Callable] = {
    "equals": operator.eq,
    "not_equals": operator.ne,
    "greater_than": operator.gt,
    # ...
}
```

No operator should be implemented as `if/elif` — dispatch is always via
dictionary, to keep extensibility without inflating cyclomatic
complexity.

## Resolving `field` for `api_checks`

- `field == "status_code"`: special value, resolves to the HTTP status
  code of the response (integer).
- Any other `field` value: treated as **JSONPath** applied to the response
  body (e.g. `$.error.code`, `$.items[0].status`).
- If the JSONPath doesn't find the field, `obtained_value = None` and the
  check is evaluated normally against that `None` (allows using
  `operator: "is_null"` to check field absence).

## Resolving `field` for `validations` (via connector)

- Each connector returns a single value per validation (see
  `05-connectors.md` for each type's contract).
- `query` (Oracle/DB2/Mongo) or `topic`+`key_filter` (Kafka) plus `field`
  determine which value is extracted from the connector's raw result
  before reaching the comparison engine.

## Technical error vs. assertion failure

It is mandatory that the engine and connectors distinguish:

- **Assertion failure**: the query/call worked normally, but the obtained
  value differs from the expected one according to the operator.
  `technical_error: null`, `passed: false`.
- **Technical error**: the query/call could not be completed (timeout,
  connection failure, invalid SQL query, non-existent topic).
  `technical_error` filled with the message, `passed: false` always.

This distinction is mandatory throughout the whole pipeline (execution
record, report) — this information must never be lost along the flow.
