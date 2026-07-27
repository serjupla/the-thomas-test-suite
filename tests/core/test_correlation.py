from thomas.core.correlation import resolve_correlation


def test_correlation_from_api_response():
    correlation = {"source": "api_response", "field": "$.id"}

    result = resolve_correlation(
        correlation,
        response_body={"id": "abc-123", "status": "PENDING"},
        resolved_payload=None,
    )

    assert result.correlation_id == "abc-123"
    assert result.correlation_error is None


def test_correlation_from_request_payload():
    correlation = {"source": "request_payload", "field": "idempotency_key"}

    result = resolve_correlation(
        correlation,
        response_body={},
        resolved_payload={"idempotency_key": "xyz-789"},
    )

    assert result.correlation_id == "xyz-789"
    assert result.correlation_error is None


def test_correlation_api_response_field_not_found_is_technical_failure():
    correlation = {"source": "api_response", "field": "$.nonexistent"}

    result = resolve_correlation(
        correlation,
        response_body={"id": "abc-123"},
        resolved_payload=None,
    )

    assert result.correlation_id is None
    assert result.correlation_error is not None


def test_correlation_from_variable():
    correlation = {"source": "variable", "field": "request_id"}

    result = resolve_correlation(
        correlation,
        response_body={},
        resolved_payload=None,
        variables={"request_id": "req-12345-abc"},
    )

    assert result.correlation_id == "req-12345-abc"
    assert result.correlation_error is None


def test_correlation_variable_field_not_found_is_technical_failure():
    correlation = {"source": "variable", "field": "request_id"}

    result = resolve_correlation(
        correlation,
        response_body={},
        resolved_payload=None,
        variables={},
    )

    assert result.correlation_id is None
    assert result.correlation_error is not None


def test_correlation_none_when_no_correlation_block():
    result = resolve_correlation(None, response_body={}, resolved_payload=None)

    assert result.correlation_id is None
    assert result.correlation_error is None
