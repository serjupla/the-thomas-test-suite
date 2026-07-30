import pytest

from thomas.operators.engine import evaluate

CASES = [
    ("equals", 201, 201, True),
    ("equals", 201, 202, False),
    ("not_equals", 201, 202, True),
    ("not_equals", 201, 201, False),
    ("greater_than", 10, 5, True),
    ("greater_than", 5, 10, False),
    ("less_than", 5, 10, True),
    ("less_than", 10, 5, False),
    ("in", "PENDING", ["PENDING", "SETTLED"], True),
    ("in", "REJECTED", ["PENDING", "SETTLED"], False),
    ("is_null", None, None, True),
    ("is_null", "value", None, False),
    ("is_not_null", "value", None, True),
    ("is_not_null", None, None, False),
]


@pytest.mark.parametrize("operator,obtained,expected,should_pass", CASES)
def test_operators(operator, obtained, expected, should_pass):
    result = evaluate(obtained, operator, expected)

    assert result.passed is should_pass
    assert result.technical_error is None


def test_missing_field_is_null_compared_normally():
    result = evaluate(None, "is_null", None)
    assert result.passed is True

    result = evaluate(None, "equals", "PENDING")
    assert result.passed is False
    assert result.technical_error is None


def test_unknown_operator_is_technical_error():
    result = evaluate(1, "does_not_exist", 1)

    assert result.passed is False
    assert result.technical_error is not None


def test_inapplicable_operator_is_technical_error():
    result = evaluate("abc", "greater_than", 5)

    assert result.passed is False
    assert result.technical_error is not None


EXTENDED_CASES = [
    ("greater_or_equal", 10, 10, True),
    ("greater_or_equal", 5, 10, False),
    ("less_or_equal", 10, 10, True),
    ("less_or_equal", 10, 5, False),
    ("between", 5, [1, 10], True),
    ("between", 15, [1, 10], False),
    ("contains", "hello world", "world", True),
    ("contains", "hello world", "xyz", False),
    ("contains", [1, 2, 3], 2, True),
    ("not_contains", "hello world", "xyz", True),
    ("not_contains", "hello world", "world", False),
    ("starts_with", "hello world", "hello", True),
    ("starts_with", "hello world", "world", False),
    ("ends_with", "hello world", "world", True),
    ("ends_with", "hello world", "hello", False),
    ("not_in", "REJECTED", ["PENDING", "SETTLED"], True),
    ("not_in", "PENDING", ["PENDING", "SETTLED"], False),
    ("is_empty", [], None, True),
    ("is_empty", [1], None, False),
    ("is_empty", "", None, True),
    ("is_not_empty", [1], None, True),
    ("is_not_empty", [], None, False),
    ("length_equals", [1, 2, 3], 3, True),
    ("length_equals", [1, 2], 3, False),
    ("length_greater_than", [1, 2, 3], 2, True),
    ("length_greater_than", [1, 2], 2, False),
    ("length_less_than", [1, 2], 3, True),
    ("length_less_than", [1, 2, 3], 3, False),
    ("regex", "order-1234", r"^order-\d+$", True),
    ("regex", "order-abcd", r"^order-\d+$", False),
    # numeric/date values presented as strings
    ("greater_than", "10", "5", True),
    ("less_than", "5", "10", True),
    ("greater_or_equal", "10", 10, True),
    ("between", "5", ["1", "10"], True),
    ("greater_than", "2024-01-02T00:00:00", "2024-01-01T00:00:00", True),
    ("less_than", "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", True),
]


@pytest.mark.parametrize("operator,obtained,expected,should_pass", EXTENDED_CASES)
def test_extended_operators(operator, obtained, expected, should_pass):
    result = evaluate(obtained, operator, expected)

    assert result.passed is should_pass
    assert result.technical_error is None


def test_greater_than_non_normalizable_string_is_technical_error():
    result = evaluate("not-a-number", "greater_than", 5)

    assert result.passed is False
    assert result.technical_error is not None


def test_greater_than_mismatched_normalized_types_is_technical_error():
    result = evaluate("5", "greater_than", "2024-01-01T00:00:00")

    assert result.passed is False
    assert result.technical_error is not None


def test_contains_inapplicable_type_is_technical_error():
    result = evaluate(42, "contains", 4)

    assert result.passed is False
    assert result.technical_error is not None


def test_length_equals_inapplicable_type_is_technical_error():
    result = evaluate(42, "length_equals", 2)

    assert result.passed is False
    assert result.technical_error is not None


def test_regex_invalid_pattern_is_technical_error():
    result = evaluate("abc", "regex", "[")

    assert result.passed is False
    assert result.technical_error is not None
