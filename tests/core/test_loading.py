import json
from pathlib import Path

import pytest

from thomas.core.loading import (
    ThomasFileError,
    load_environment,
    load_scenarios,
    load_variables,
    resolve_apis,
    resolve_environment_path,
)

VALID_SCENARIO = {
    "schema_version": 1,
    "feature": "instant_transfer",
    "scenario_id": "valid_amount_transfer",
    "endpoint": {"method": "POST", "path": "/orders"},
    "payload": {"amount": 150.0},
    "api_checks": [
        {"id": "http_status", "field": "status_code", "operator": "equals", "expected_value": 201}
    ],
}

VALID_ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
}

VALID_VARIABLES = {
    "schema_version": 1,
    "variables": {"valid_bank_account": "12345-6"},
}


def write_json(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document))


def test_load_scenarios_valid_folder(tmp_path):
    write_json(tmp_path / "a.json", VALID_SCENARIO)
    nested = tmp_path / "nested"
    nested.mkdir()
    write_json(nested / "b.json", {**VALID_SCENARIO, "scenario_id": "other"})

    loaded = load_scenarios(tmp_path, project_root=tmp_path)

    assert len(loaded) == 2
    files = sorted(s.scenario_file for s in loaded)
    assert files == ["a.json", str(Path("nested") / "b.json")]


def test_load_scenarios_records_folder_for_grouping(tmp_path):
    nested = tmp_path / "instant_transfer"
    nested.mkdir()
    write_json(nested / "a.json", VALID_SCENARIO)

    loaded = load_scenarios(tmp_path)

    assert loaded[0].folder == "instant_transfer"


def test_load_scenarios_single_file(tmp_path):
    scenario_path = tmp_path / "a.json"
    write_json(scenario_path, VALID_SCENARIO)

    loaded = load_scenarios(scenario_path, project_root=tmp_path)

    assert len(loaded) == 1
    assert loaded[0].scenario_file == "a.json"


def test_load_scenarios_rejects_incompatible_schema_version(tmp_path):
    write_json(tmp_path / "a.json", {**VALID_SCENARIO, "schema_version": 2})

    with pytest.raises(ThomasFileError):
        load_scenarios(tmp_path)


def test_load_scenarios_rejects_missing_required_field(tmp_path):
    broken = dict(VALID_SCENARIO)
    del broken["endpoint"]
    write_json(tmp_path / "a.json", broken)

    with pytest.raises(ThomasFileError):
        load_scenarios(tmp_path)


def test_load_scenarios_reports_all_invalid_files_at_once(tmp_path):
    write_json(tmp_path / "good.json", VALID_SCENARIO)
    write_json(tmp_path / "bad1.json", {**VALID_SCENARIO, "schema_version": 2})
    write_json(tmp_path / "bad2.json", {"schema_version": 1})

    with pytest.raises(ThomasFileError) as exc_info:
        load_scenarios(tmp_path)

    offending_files = {Path(path).name for path, _ in exc_info.value.errors}
    assert offending_files == {"bad1.json", "bad2.json"}


def test_load_scenarios_empty_folder_aborts(tmp_path):
    with pytest.raises(ThomasFileError) as exc_info:
        load_scenarios(tmp_path)

    assert "no scenarios found" in str(exc_info.value)


def test_load_environment_valid(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, VALID_ENVIRONMENT)

    document = load_environment(env_path)

    assert document["environment_name"] == "dev"


def test_load_environment_rejects_invalid(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, {"schema_version": 1})

    with pytest.raises(ThomasFileError):
        load_environment(env_path)


def test_load_scenarios_duplicate_feature_and_scenario_id_both_processed(tmp_path):
    write_json(tmp_path / "a.json", VALID_SCENARIO)
    write_json(tmp_path / "b.json", VALID_SCENARIO)

    loaded = load_scenarios(tmp_path)

    assert len(loaded) == 2
    assert all(s.document["scenario_id"] == VALID_SCENARIO["scenario_id"] for s in loaded)


def test_load_variables_valid(tmp_path):
    vars_path = tmp_path / "variables.json"
    write_json(vars_path, VALID_VARIABLES)

    variables = load_variables(vars_path)

    assert variables == {"valid_bank_account": "12345-6"}


# Feature 003: SSL Verification & Metadata tests

def test_load_environment_with_company_name_and_department_name(tmp_path):
    env_path = tmp_path / "prod.json"
    env_data = {
        **VALID_ENVIRONMENT,
        "company_name": "Example Corp",
        "department_name": "Payments QA"
    }
    write_json(env_path, env_data)

    document = load_environment(env_path)

    assert document["company_name"] == "Example Corp"
    assert document["department_name"] == "Payments QA"


def test_load_environment_with_api_ssl_verify_false(tmp_path):
    env_path = tmp_path / "staging.json"
    env_data = {
        **VALID_ENVIRONMENT,
        "api": {**VALID_ENVIRONMENT["api"], "ssl_verify": False}
    }
    write_json(env_path, env_data)

    document = load_environment(env_path)

    assert document["api"]["ssl_verify"] is False


def test_load_environment_with_services_info_ssl_verify(tmp_path):
    env_path = tmp_path / "test.json"
    env_data = {
        **VALID_ENVIRONMENT,
        "services_info": [
            {
                "name": "payment_service",
                "info_url": "https://payment.test/info",
                "ssl_verify": False
            },
            {
                "name": "identity_service",
                "info_url": "https://identity.test/info",
                "ssl_verify": True
            }
        ]
    }
    write_json(env_path, env_data)

    document = load_environment(env_path)

    assert document["services_info"][0]["ssl_verify"] is False
    assert document["services_info"][1]["ssl_verify"] is True


def test_load_environment_without_new_fields_retrocompatibility(tmp_path):
    """Old environment files without new fields (company_name, department_name, ssl_verify) should still validate."""
    env_path = tmp_path / "legacy.json"
    # VALID_ENVIRONMENT already has no new fields, so this should pass
    write_json(env_path, VALID_ENVIRONMENT)

    document = load_environment(env_path)

    assert document["environment_name"] == "dev"
    assert "company_name" not in document
    assert "department_name" not in document
    assert "ssl_verify" not in document.get("api", {})


def test_load_environment_rejects_ssl_verify_string_not_boolean(tmp_path):
    """Malformed ssl_verify as string 'false' instead of boolean should be rejected."""
    env_path = tmp_path / "bad.json"
    env_data = {
        **VALID_ENVIRONMENT,
        "api": {**VALID_ENVIRONMENT["api"], "ssl_verify": "false"}  # string, not boolean
    }
    write_json(env_path, env_data)

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    assert "ssl_verify" in str(exc_info.value) or "boolean" in str(exc_info.value).lower()


def test_load_environment_rejects_empty_company_name(tmp_path):
    """Empty company_name string should be rejected (minLength: 1)."""
    env_path = tmp_path / "bad.json"
    env_data = {
        **VALID_ENVIRONMENT,
        "company_name": ""  # empty string violates minLength: 1
    }
    write_json(env_path, env_data)

    with pytest.raises(ThomasFileError):
        load_environment(env_path)


def test_resolve_environment_path_returns_single_match(tmp_path):
    environments_dir = tmp_path / "config" / "environments"
    environments_dir.mkdir(parents=True)
    write_json(environments_dir / "dev.json", {**VALID_ENVIRONMENT, "environment_name": "internet-tests"})
    write_json(environments_dir / "staging.json", {**VALID_ENVIRONMENT, "environment_name": "staging"})

    resolved = resolve_environment_path("internet-tests", tmp_path)

    assert resolved == environments_dir / "dev.json"


def test_resolve_environment_path_raises_on_zero_matches(tmp_path):
    environments_dir = tmp_path / "config" / "environments"
    environments_dir.mkdir(parents=True)
    write_json(environments_dir / "staging.json", {**VALID_ENVIRONMENT, "environment_name": "staging"})

    with pytest.raises(ThomasFileError):
        resolve_environment_path("internet-tests", tmp_path)


def test_resolve_environment_path_raises_on_multiple_matches(tmp_path):
    environments_dir = tmp_path / "config" / "environments"
    environments_dir.mkdir(parents=True)
    write_json(environments_dir / "a.json", {**VALID_ENVIRONMENT, "environment_name": "internet-tests"})
    write_json(environments_dir / "b.json", {**VALID_ENVIRONMENT, "environment_name": "internet-tests"})

    with pytest.raises(ThomasFileError):
        resolve_environment_path("internet-tests", tmp_path)


def test_resolve_environment_path_raises_when_directory_missing(tmp_path):
    with pytest.raises(ThomasFileError):
        resolve_environment_path("internet-tests", tmp_path)


# Feature 018: Multiple APIs per environment

MULTI_API_ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "apis": {
        "identity_service": {
            "base_url": "https://identity.test/api",
            "default": True,
        },
        "business_api": {
            "base_url": "https://business.test/api",
            "headers": {"X-Api-Key": "secret"},
        },
    },
}


def test_load_environment_multi_api_valid(tmp_path):
    env_path = tmp_path / "dev.json"
    write_json(env_path, MULTI_API_ENVIRONMENT)

    document = load_environment(env_path)

    assert set(document["apis"].keys()) == {"identity_service", "business_api"}


def test_load_environment_rejects_api_and_apis_both_present(tmp_path):
    env_path = tmp_path / "dev.json"
    env_data = {**MULTI_API_ENVIRONMENT, "api": VALID_ENVIRONMENT["api"]}
    write_json(env_path, env_data)

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    message = str(exc_info.value)
    assert "api" in message and "apis" in message


def test_load_environment_rejects_apis_with_no_default(tmp_path):
    env_path = tmp_path / "dev.json"
    env_data = {
        **MULTI_API_ENVIRONMENT,
        "apis": {
            name: {k: v for k, v in config.items() if k != "default"}
            for name, config in MULTI_API_ENVIRONMENT["apis"].items()
        },
    }
    write_json(env_path, env_data)

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    assert "default" in str(exc_info.value).lower()


def test_load_environment_rejects_apis_with_multiple_defaults(tmp_path):
    env_path = tmp_path / "dev.json"
    env_data = {
        **MULTI_API_ENVIRONMENT,
        "apis": {
            name: {**config, "default": True}
            for name, config in MULTI_API_ENVIRONMENT["apis"].items()
        },
    }
    write_json(env_path, env_data)

    with pytest.raises(ThomasFileError) as exc_info:
        load_environment(env_path)

    assert "default" in str(exc_info.value).lower()


def test_load_environment_accepts_single_apis_entry_without_default_flag(tmp_path):
    env_path = tmp_path / "dev.json"
    env_data = {
        **VALID_ENVIRONMENT,
        "apis": {"only_api": {"base_url": "https://only.test/api"}},
    }
    del env_data["api"]
    write_json(env_path, env_data)

    document = load_environment(env_path)
    resolved_apis, default_api_name = resolve_apis(document)

    assert default_api_name == "only_api"
    assert resolved_apis == {"only_api": {"base_url": "https://only.test/api"}}


def test_resolve_apis_legacy_single_api_normalizes_to_default(tmp_path):
    resolved_apis, default_api_name = resolve_apis(VALID_ENVIRONMENT)

    assert default_api_name == "default"
    assert resolved_apis == {"default": VALID_ENVIRONMENT["api"]}


def test_load_environment_legacy_single_api_full_pipeline_unaffected(tmp_path):
    """Regression (FR-008/FR-009, SC-004): a legacy single-`api` environment,
    with no `apis` field at all, must load, validate, and normalize exactly
    as it did before this feature — no observable behavior change."""
    env_path = tmp_path / "legacy.json"
    write_json(env_path, VALID_ENVIRONMENT)

    document = load_environment(env_path)
    resolved_apis, default_api_name = resolve_apis(document)

    assert "apis" not in document
    assert document["api"] == VALID_ENVIRONMENT["api"]
    assert default_api_name == "default"
    assert resolved_apis == {"default": VALID_ENVIRONMENT["api"]}


def test_resolve_apis_multi_api_normalizes_and_strips_default_flag():
    resolved_apis, default_api_name = resolve_apis(MULTI_API_ENVIRONMENT)

    assert default_api_name == "identity_service"
    assert resolved_apis["identity_service"] == {"base_url": "https://identity.test/api"}
    assert resolved_apis["business_api"] == {
        "base_url": "https://business.test/api",
        "headers": {"X-Api-Key": "secret"},
    }
    assert "default" not in resolved_apis["identity_service"]
