from thomas.core.extraction import resolve_extract_variables


def test_single_successful_extraction_mutates_variables_and_returns_success():
    extract_variables = [{"json_path": "$.id", "as_variable": "order_id"}]
    variables = {"order_id": None}

    results = resolve_extract_variables(
        extract_variables,
        response_body={"id": "abc-123"},
        variables=variables,
    )

    assert variables["order_id"] == "abc-123"
    assert results == [
        {"json_path": "$.id", "as_variable": "order_id", "success": True, "error": None}
    ]


def test_no_match_returns_failure_and_does_not_mutate():
    extract_variables = [{"json_path": "$.nonexistent", "as_variable": "order_id"}]
    variables = {"order_id": None}

    results = resolve_extract_variables(
        extract_variables,
        response_body={"id": "abc-123"},
        variables=variables,
    )

    assert variables["order_id"] is None
    assert results == [
        {
            "json_path": "$.nonexistent",
            "as_variable": "order_id",
            "success": False,
            "error": "json_path '$.nonexistent' did not resolve in the response body",
        }
    ]


def test_earlier_success_preserved_when_later_item_fails_no_rollback():
    extract_variables = [
        {"json_path": "$.id", "as_variable": "order_id"},
        {"json_path": "$.nonexistent", "as_variable": "status_id"},
        {"json_path": "$.name", "as_variable": "name_var"},
    ]
    variables = {"order_id": None, "status_id": None, "name_var": None}

    results = resolve_extract_variables(
        extract_variables,
        response_body={"id": "abc-123", "name": "widget"},
        variables=variables,
    )

    assert variables["order_id"] == "abc-123"
    assert variables["status_id"] is None
    assert variables["name_var"] is None
    assert len(results) == 2
    assert results[0]["success"] is True
    assert results[1]["success"] is False


def test_multiple_matches_uses_first_match_value():
    extract_variables = [{"json_path": "$.items[*].id", "as_variable": "first_id"}]
    variables = {"first_id": None}

    results = resolve_extract_variables(
        extract_variables,
        response_body={"items": [{"id": "first"}, {"id": "second"}]},
        variables=variables,
    )

    assert variables["first_id"] == "first"
    assert results[0]["success"] is True


def test_duplicate_as_variable_later_item_wins_and_warns(caplog):
    extract_variables = [
        {"json_path": "$.a", "as_variable": "dup"},
        {"json_path": "$.b", "as_variable": "dup"},
    ]
    variables = {"dup": None}

    with caplog.at_level("WARNING", logger="thomas"):
        results = resolve_extract_variables(
            extract_variables,
            response_body={"a": "value_a", "b": "value_b"},
            variables=variables,
            scenario_file="scenarios/example.json",
        )

    assert variables["dup"] == "value_b"
    assert len(results) == 2
    assert all(r["success"] for r in results)
    assert any("duplicate" in message.lower() for message in caplog.messages)


def test_none_extract_variables_returns_empty_list():
    variables = {}
    results = resolve_extract_variables(None, response_body={}, variables=variables)
    assert results == []
