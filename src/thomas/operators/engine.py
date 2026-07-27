"""Single, generic comparison engine shared by `api_checks` and (in a later
feature) `validations`. See docs/architecture/04-validation-engine-operators.md.

F00 ships the minimum operator set needed for `api_checks`: equals,
not_equals, greater_than, less_than, in, is_null, is_not_null. F02 extends
COMPARATORS in place with the full operator table (between, contains,
starts_with, regex, etc.) without changing this module's signature or how
callers invoke it (Constitution Principle III).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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


COMPARATORS: dict[str, Callable[[Any, Any], bool]] = {
    "equals": _equals,
    "not_equals": _not_equals,
    "greater_than": _greater_than,
    "less_than": _less_than,
    "in": _in,
    "is_null": _is_null,
    "is_not_null": _is_not_null,
}


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

    try:
        passed = comparator(obtained_value, expected_value)
    except TypeError as exc:
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
