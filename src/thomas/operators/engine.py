"""Single, generic comparison engine shared by `api_checks` and (in a later
feature) `validations`. See docs/architecture/04-validation-engine-operators.md.

F00 ships the minimum operator set needed for `api_checks`: equals,
not_equals, greater_than, less_than, in, is_null, is_not_null. F02 extends
COMPARATORS in place with the full operator table (between, contains,
starts_with, regex, etc.) without changing this module's signature or how
callers invoke it (Constitution Principle III).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class ValidationResult:
    passed: bool
    obtained_value: Any
    expected_value: Any
    operator: str
    technical_error: str | None = None


def _equals(obtained: Any, expected: Any) -> bool:
    return obtained == expected


def _not_equals(obtained: Any, expected: Any) -> bool:
    return obtained != expected


def _greater_than(obtained: Any, expected: Any) -> bool:
    return obtained > expected


def _less_than(obtained: Any, expected: Any) -> bool:
    return obtained < expected


def _in(obtained: Any, expected: Any) -> bool:
    return obtained in expected


def _is_null(obtained: Any, expected: Any) -> bool:
    return obtained is None


def _is_not_null(obtained: Any, expected: Any) -> bool:
    return obtained is not None


def _normalize_for_ordering(value: Any) -> Any:
    """Coerce a str operand to int/float/datetime for ordering comparisons.

    Non-str values (already int/float/datetime) pass through unchanged.
    Raises ValueError if a str can be normalized to neither a number nor an
    ISO-8601 datetime (FR-002).
    """
    if not isinstance(value, str):
        return value
    try:
        return float(value)
    except ValueError:
        pass
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _greater_or_equal(obtained: Any, expected: Any) -> bool:
    return obtained >= expected


def _less_or_equal(obtained: Any, expected: Any) -> bool:
    return obtained <= expected


def _between(obtained: Any, expected: Any) -> bool:
    low, high = expected
    return low <= obtained <= high


def _contains(obtained: Any, expected: Any) -> bool:
    if not isinstance(obtained, (str, list)):
        raise TypeError(f"'contains' requires a string or list obtained_value, got {type(obtained).__name__}")
    return expected in obtained


def _not_contains(obtained: Any, expected: Any) -> bool:
    return not _contains(obtained, expected)


def _starts_with(obtained: Any, expected: Any) -> bool:
    if not isinstance(obtained, str):
        raise TypeError(f"'starts_with' requires a string obtained_value, got {type(obtained).__name__}")
    return obtained.startswith(expected)


def _ends_with(obtained: Any, expected: Any) -> bool:
    if not isinstance(obtained, str):
        raise TypeError(f"'ends_with' requires a string obtained_value, got {type(obtained).__name__}")
    return obtained.endswith(expected)


def _not_in(obtained: Any, expected: Any) -> bool:
    return obtained not in expected


def _is_empty(obtained: Any, expected: Any) -> bool:
    return len(obtained) == 0


def _is_not_empty(obtained: Any, expected: Any) -> bool:
    return len(obtained) != 0


def _length_equals(obtained: Any, expected: Any) -> bool:
    return len(obtained) == expected


def _length_greater_than(obtained: Any, expected: Any) -> bool:
    return len(obtained) > expected


def _length_less_than(obtained: Any, expected: Any) -> bool:
    return len(obtained) < expected


def _regex(obtained: Any, expected: Any) -> bool:
    if not isinstance(obtained, str):
        raise TypeError(f"'regex' requires a string obtained_value, got {type(obtained).__name__}")
    return re.search(expected, obtained) is not None


COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "equals": _equals,
    "not_equals": _not_equals,
    "greater_than": _greater_than,
    "greater_or_equal": _greater_or_equal,
    "less_than": _less_than,
    "less_or_equal": _less_or_equal,
    "between": _between,
    "contains": _contains,
    "not_contains": _not_contains,
    "starts_with": _starts_with,
    "ends_with": _ends_with,
    "in": _in,
    "not_in": _not_in,
    "is_null": _is_null,
    "is_not_null": _is_not_null,
    "is_empty": _is_empty,
    "is_not_empty": _is_not_empty,
    "length_equals": _length_equals,
    "length_greater_than": _length_greater_than,
    "length_less_than": _length_less_than,
    "regex": _regex,
}

_ORDERING_OPERATORS = {"greater_than", "greater_or_equal", "less_than", "less_or_equal", "between"}


def evaluate(obtained_value: Any, operator: str, expected_value: Any) -> ValidationResult:
    """Compare obtained_value to expected_value using the named operator.

    Returns a ValidationResult with technical_error set (and passed=False)
    when the operator is unknown or inapplicable to the given data types
    (e.g. greater_than on non-comparable values).
    """
    comparator = COMPARATORS.get(operator)
    if comparator is None:
        return ValidationResult(
            passed=False,
            obtained_value=obtained_value,
            expected_value=expected_value,
            operator=operator,
            technical_error=f"unknown operator: {operator}",
        )

    compare_obtained = obtained_value
    compare_expected = expected_value
    if operator in _ORDERING_OPERATORS:
        try:
            compare_obtained = _normalize_for_ordering(obtained_value)
            if operator == "between":
                low, high = expected_value
                compare_expected = [_normalize_for_ordering(low), _normalize_for_ordering(high)]
            else:
                compare_expected = _normalize_for_ordering(expected_value)
        except (ValueError, TypeError) as exc:
            return ValidationResult(
                passed=False,
                obtained_value=obtained_value,
                expected_value=expected_value,
                operator=operator,
                technical_error=f"operator '{operator}' not applicable: {exc}",
            )

    try:
        passed = comparator(compare_obtained, compare_expected)
    except (TypeError, re.error) as exc:
        return ValidationResult(
            passed=False,
            obtained_value=obtained_value,
            expected_value=expected_value,
            operator=operator,
            technical_error=f"operator '{operator}' not applicable: {exc}",
        )

    return ValidationResult(
        passed=passed,
        obtained_value=obtained_value,
        expected_value=expected_value,
        operator=operator,
    )
