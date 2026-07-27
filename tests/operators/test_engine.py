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
