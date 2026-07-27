from thomas.core.variables import find_undefined_references, resolve_payload


def test_resolve_payload_substitutes_defined_variable():
    payload = {"source_account": "{{valid_bank_account}}", "amount": 150.0}
    variables = {"valid_bank_account": "12345-6"}

    resolved = resolve_payload(payload, variables)

    assert resolved["source_account"] == "12345-6"
    assert resolved["amount"] == 150.0


def test_resolve_payload_substitutes_inside_string_with_other_text():
    payload = {"description": "Transfer to {{valid_bank_account}} now"}
    variables = {"valid_bank_account": "12345-6"}

    resolved = resolve_payload(payload, variables)

    assert resolved["description"] == "Transfer to 12345-6 now"


def test_resolve_payload_handles_nested_structures():
    payload = {"nested": {"key": "{{valid_bank_account}}"}, "list": ["{{valid_bank_account}}"]}
    variables = {"valid_bank_account": "12345-6"}

    resolved = resolve_payload(payload, variables)

    assert resolved["nested"]["key"] == "12345-6"
    assert resolved["list"] == ["12345-6"]


def test_resolve_payload_none_returns_none():
    assert resolve_payload(None, {"a": "b"}) is None


def test_find_undefined_references_detects_missing_variable():
    payload = {"source_account": "{{valid_bank_account}}", "destination": "{{unknown_variable}}"}
    variables = {"valid_bank_account": "12345-6"}

    missing = find_undefined_references(payload, variables)

    assert missing == {"unknown_variable"}


def test_find_undefined_references_empty_when_all_defined():
    payload = {"source_account": "{{valid_bank_account}}"}
    variables = {"valid_bank_account": "12345-6"}

    missing = find_undefined_references(payload, variables)

    assert missing == set()


def test_find_undefined_references_none_payload():
    assert find_undefined_references(None, {}) == set()
