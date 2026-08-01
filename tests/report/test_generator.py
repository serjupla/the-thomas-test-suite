import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from bs4 import BeautifulSoup

from thomas.core.loading import ThomasFileError
from thomas.report.generator import (
    _build_groups,
    _build_validation_rounds,
    _donut_gradient_stops,
    _duration_display,
    _flatten_kv,
    _is_sensitive_key,
    _percentages,
    _status_counts,
    _worst_of,
    generate_report_html,
    resolve_report_filename,
    write_report,
)

ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api"},
}


def _scenario(
    scenario_id,
    folder,
    feature,
    final_status,
    validation_rounds=None,
    api_checks_result=None,
    request_technical_error=None,
    request_timestamp="2026-07-25T10:00:00-03:00",
    response_timestamp="2026-07-25T10:00:01-03:00",
):
    return {
        "scenario_file": f"{folder}/{scenario_id}.json" if folder else f"{scenario_id}.json",
        "feature": feature,
        "scenario_id": scenario_id,
        "folder": folder,
        "correlation_id": "corr-1",
        "correlation_error": None,
        "request_timestamp": request_timestamp,
        "response_timestamp": None if request_technical_error else response_timestamp,
        "request_sent": {"method": "POST", "path": "/orders", "payload": {"amount": 150.0}, "headers": {}},
        "api_response": None if request_technical_error else {"status_code": 201, "body": {"status": "PENDING"}},
        "request_technical_error": request_technical_error,
        "api_checks_result": api_checks_result or [],
        "api_result": "failed" if request_technical_error else "passed",
        "validation_rounds": validation_rounds or [],
        "final_status": final_status,
    }


def _execution_record(results, **overrides):
    record = {
        "schema_version": 1,
        "execution_id": "execution_test",
        "thomas_version": "0.0.0",
        "environment": "dev",
        "start_timestamp": "2026-07-25T10:00:00-03:00",
        "included_scenarios": [r["scenario_file"] for r in results],
        "services_info": [],
        "results": results,
    }
    record.update(overrides)
    return record


def test_resolve_report_filename_distinct_for_distinct_timestamps():
    a = resolve_report_filename(Path("execution_1.json"), datetime(2026, 7, 29, 10, 0, 0, 1, tzinfo=timezone.utc))
    b = resolve_report_filename(Path("execution_1.json"), datetime(2026, 7, 29, 10, 0, 0, 2, tzinfo=timezone.utc))
    assert a != b
    assert a.startswith("execution_1_") and a.endswith(".html")


def test_write_report_creates_output_dir_and_returns_path(tmp_path):
    output_dir = tmp_path / "reports"
    path = write_report("<html></html>", Path("execution_1.json"), output_dir, datetime(2026, 7, 29, 10, 0, 0, tzinfo=timezone.utc))
    assert path.exists()
    assert path.read_text() == "<html></html>"
    assert path.parent == output_dir


# --- _worst_of / _status_counts (research.md §4) ---


@pytest.mark.parametrize(
    "statuses,expected",
    [
        ([], "aprovado"),
        (["aprovado"], "aprovado"),
        (["aprovado", "aguardando"], "aguardando"),
        (["aprovado", "aguardando", "reprovado"], "reprovado"),
        (["reprovado"], "reprovado"),
    ],
)
def test_worst_of_priority(statuses, expected):
    assert _worst_of(statuses) == expected


def test_status_counts_priority_reprovado_over_aguardando_over_aprovado():
    results = [_scenario("a", "", "f", "passed"), _scenario("b", "", "f", "awaiting_validation")]
    assert _status_counts(results)["status"] == "aguardando"
    results.append(_scenario("c", "", "f", "failed"))
    assert _status_counts(results)["status"] == "reprovado"


# --- percentages / donut (FR-003, Edge Cases) ---


def test_percentages_sum_to_100():
    counts = {"passed_count": 1, "failed_count": 1, "awaiting_count": 1, "total_count": 3}
    pct = _percentages(counts)
    assert sum(pct.values()) == 100


def test_percentages_zero_total_returns_zeros():
    counts = {"passed_count": 0, "failed_count": 0, "awaiting_count": 0, "total_count": 0}
    assert _percentages(counts) == {"passed": 0, "failed": 0, "awaiting": 0}


def test_donut_gradient_stops_zero_scenarios_single_neutral_ring():
    stops = _donut_gradient_stops({"passed": 0, "failed": 0, "awaiting": 0}, 0)
    assert stops == "var(--color-neutral-300) 0% 100%"


def test_donut_gradient_stops_all_passed_full_single_color_ring():
    stops = _donut_gradient_stops({"passed": 100, "failed": 0, "awaiting": 0}, 2)
    assert "var(--color-status-approved) 0% 100%" in stops


# --- _build_groups / dual grouping (FR-004/FR-005, research.md §3) ---


def test_build_groups_sums_to_total_and_preserves_first_seen_order():
    rows = [
        {"scenario_id": "a", "final_status": "passed", "folder": "billing"},
        {"scenario_id": "b", "final_status": "failed", "folder": "onboarding"},
        {"scenario_id": "c", "final_status": "awaiting_validation", "folder": "billing"},
    ]
    groups = _build_groups(rows, lambda r: r["folder"])
    assert [g["name"] for g in groups] == ["billing", "onboarding"]
    assert sum(g["total_count"] for g in groups) == 3
    billing = groups[0]
    assert billing["passed_count"] == 1
    assert billing["awaiting_count"] == 1
    assert billing["status"] == "aguardando"


# --- masking / flatten (FR-019/FR-020, research.md §8) ---


@pytest.mark.parametrize(
    "key,expected",
    [
        ("api_token", True),
        ("API_KEY", True),
        ("password", True),
        ("secret_value", True),
        ("username", True),
        ("user", True),
        ("usuário", True),
        ("USUÁRIO", True),
        ("usuario", True),
        ("host", False),
    ],
)
def test_is_sensitive_key(key, expected):
    assert _is_sensitive_key(key) == expected


def test_flatten_kv_masks_nested_sensitive_fields_at_any_depth():
    config = {"host": "db.internal", "auth": {"password": "s3cr3t", "nested": {"api_token": "tok-1"}}}
    rows = {row["key"]: row for row in _flatten_kv(config)}
    assert rows["host"]["is_sensitive"] is False
    assert rows["host"]["value_masked"] == "db.internal"
    assert rows["auth.password"]["is_sensitive"] is True
    assert rows["auth.password"]["value_masked"] == "•" * 10
    assert rows["auth.nested.api_token"]["is_sensitive"] is True


def test_flatten_kv_handles_lists():
    config = {"scopes": ["read", "write"]}
    rows = {row["key"]: row for row in _flatten_kv(config)}
    assert rows["scopes[0]"]["value"] == "read"
    assert rows["scopes[1]"]["value"] == "write"


def test_flatten_kv_never_show_field_never_carries_real_value():
    config = {"dsn": "host:1521/xe", "password": "s3cr3t"}
    rows = {row["key"]: row for row in _flatten_kv(config, never_show_fields=frozenset({"password"}))}
    assert rows["password"]["is_never_show"] is True
    assert rows["password"]["value"] is None
    assert rows["password"]["value_masked"] is None
    assert rows["dsn"]["is_never_show"] is False
    assert rows["dsn"]["value"] == "host:1521/xe"


def test_flatten_kv_never_show_takes_precedence_over_sensitive_match():
    config = {"password": "s3cr3t"}
    rows = {row["key"]: row for row in _flatten_kv(config, never_show_fields=frozenset({"password"}))}
    assert rows["password"]["is_sensitive"] is True
    assert rows["password"]["is_never_show"] is True
    assert rows["password"]["value"] is None


# --- validation rounds: field/query columns + tz timestamp (FR-001/FR-002/FR-003/FR-006a) ---

CONNECTORS = {
    "oracle_main": {"type": "oracle", "dsn": "host:1521/xe", "username": "svc", "password": "s3cr3t"},
    "fake_main": {"type": "fake", "values": {}, "failures": {}},
}


def _validation_round(timestamp, results):
    return {"timestamp": timestamp, "environment_used": "dev", "results": results}


def test_build_validation_rounds_visible_field_carries_query_and_tz_timestamp():
    rounds = _build_validation_rounds(
        [_validation_round(
            "2026-07-25T13:00:00+00:00",
            [{"id": "v1", "connector": "oracle_main", "field": "status", "expected": "SETTLED",
              "obtained": "SETTLED", "operator": "equals", "query": "SELECT status FROM t", "passed": True}],
        )],
        CONNECTORS,
        ZoneInfo("America/Sao_Paulo"),
    )
    check = rounds[0]["checks"][0]
    assert check["field"] == "status"
    assert check["query_display"] == "SELECT status FROM t"
    assert check["query_visibility"] == "visible"
    assert "10:00:00" in rounds[0]["timestamp_label"]


def test_build_validation_rounds_never_show_field_suppresses_query_visibility():
    rounds = _build_validation_rounds(
        [_validation_round(
            "2026-07-25T13:00:00+00:00",
            [{"id": "v1", "connector": "oracle_main", "field": "password", "expected": "x",
              "obtained": "x", "operator": "equals", "query": "SELECT password FROM t", "passed": True}],
        )],
        CONNECTORS,
        ZoneInfo("America/Sao_Paulo"),
    )
    assert rounds[0]["checks"][0]["query_visibility"] == "never_show"


def test_build_validation_rounds_sensitive_field_masks_query_visibility():
    rounds = _build_validation_rounds(
        [_validation_round(
            "2026-07-25T13:00:00+00:00",
            [{"id": "v1", "connector": "oracle_main", "field": "username", "expected": "x",
              "obtained": "x", "operator": "equals", "query": "SELECT username FROM t", "passed": True}],
        )],
        CONNECTORS,
        ZoneInfo("America/Sao_Paulo"),
    )
    assert rounds[0]["checks"][0]["query_visibility"] == "sensitive"


def test_build_validation_rounds_fake_connector_lookup_label_is_visible():
    rounds = _build_validation_rounds(
        [_validation_round(
            "2026-07-25T13:00:00+00:00",
            [{"id": "v1", "connector": "fake_main", "field": "balance", "expected": 1,
              "obtained": 1, "operator": "equals", "query": "lookup: v1", "passed": True}],
        )],
        CONNECTORS,
        ZoneInfo("America/Sao_Paulo"),
    )
    check = rounds[0]["checks"][0]
    assert check["query_display"] == "lookup: v1"
    assert check["query_visibility"] == "visible"


def test_build_validation_rounds_missing_query_on_older_records_is_none():
    rounds = _build_validation_rounds(
        [_validation_round(
            "2026-07-25T13:00:00+00:00",
            [{"id": "v1", "connector": "fake_main", "expected": 1, "obtained": 1, "operator": "equals", "passed": True}],
        )],
        CONNECTORS,
        ZoneInfo("America/Sao_Paulo"),
    )
    assert rounds[0]["checks"][0]["query_display"] is None
    assert rounds[0]["checks"][0]["field"] == ""


def test_rendered_html_never_shows_oracle_password_in_query_column():
    validation_rounds = [_validation_round(
        "2026-07-25T13:00:00+00:00",
        [{"id": "v1", "connector": "oracle_main", "field": "password", "expected": "s3cr3t",
          "obtained": "s3cr3t", "operator": "equals", "query": "SELECT password FROM t WHERE id = 's3cr3t'", "passed": True}],
    )]
    result = _scenario("sc1", "", "feat", "passed", validation_rounds=validation_rounds)
    record = _execution_record([result])
    environment = dict(ENVIRONMENT, connectors=CONNECTORS)
    html = generate_report_html(record, environment, b"{}")
    assert "SELECT password FROM t" not in html
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".query-cell .not-displayed-badge") is not None


def test_rendered_html_shows_scenario_description_when_present():
    result = dict(_scenario("sc1", "", "feat", "passed"), description="A valid transfer must be settled")
    record = _execution_record([result])
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    assert "A valid transfer must be settled" in html


def test_rendered_html_omits_description_block_when_absent():
    result = _scenario("sc1", "", "feat", "passed")
    record = _execution_record([result])
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".scenario-description") is None


# --- duration display (FR-010) ---


def test_duration_display_no_validation_uses_response_minus_request():
    result = _scenario("a", "", "f", "passed")
    assert _duration_display(result) == "1s"


def test_duration_display_pending_validation_shows_placeholder():
    result = _scenario("a", "", "f", "awaiting_validation")
    assert _duration_display(result) == "—"


def test_duration_display_occurred_validation_uses_last_round_timestamp():
    result = _scenario(
        "a", "", "f", "passed",
        validation_rounds=[
            {"timestamp": "2026-07-25T10:05:00-03:00", "environment_used": "dev", "round_result": "passed", "results": []}
        ],
    )
    assert _duration_display(result) == "5m"


def test_duration_display_technical_error_no_response_shows_placeholder():
    result = _scenario("a", "", "f", "failed", request_technical_error="connection refused")
    assert _duration_display(result) == "—"


# --- generate_report_html smoke + structure ---


@pytest.mark.parametrize(
    "statuses,expected_status",
    [
        (["passed", "passed"], "aprovado"),
        (["passed", "failed"], "reprovado"),
        (["passed", "awaiting_validation"], "aguardando"),
        (["failed", "awaiting_validation"], "reprovado"),
    ],
)
def test_overall_status_combinations_render_without_crash(statuses, expected_status):
    results = [_scenario(f"sc{i}", "", "feat", status) for i, status in enumerate(statuses)]
    record = _execution_record(results)
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    badge = soup.select_one(".overall-status-badge")
    assert f"status-{expected_status}" in badge["class"]


def test_sha256_signature_matches_raw_bytes_independent_of_parsed_dict():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    execution_file_bytes = json.dumps(record).encode() + b"   trailing whitespace differs from dict"
    html = generate_report_html(record, ENVIRONMENT, execution_file_bytes)
    expected_digest = hashlib.sha256(execution_file_bytes).hexdigest()
    assert expected_digest in html


def test_logo_resolution_thomas_always_inlined_company_none_when_absent():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    assert "<svg" in html
    assert 'class="company-logo"' not in html


def test_logo_resolution_raises_thomas_file_error_when_company_logo_missing(tmp_path):
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    environment = dict(ENVIRONMENT, company_logo_path=str(tmp_path / "missing.svg"))
    with pytest.raises(ThomasFileError):
        generate_report_html(record, environment, b"{}")


def test_logo_resolution_raises_thomas_file_error_when_not_well_formed_svg(tmp_path):
    bad_svg = tmp_path / "logo.svg"
    bad_svg.write_text("not xml at all <<<")
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    environment = dict(ENVIRONMENT, company_logo_path=str(bad_svg))
    with pytest.raises(ThomasFileError):
        generate_report_html(record, environment, b"{}")


def test_logo_resolution_reads_valid_company_logo(tmp_path):
    good_svg = tmp_path / "logo.svg"
    good_svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>')
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    environment = dict(ENVIRONMENT, company_logo_path=str(good_svg))
    html = generate_report_html(record, environment, b"{}")
    assert "<rect" in html


def test_environment_without_report_language_defaults_to_english():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    environment = dict(ENVIRONMENT)
    environment.pop("report_language", None)
    html = generate_report_html(record, environment, b"{}")
    assert "Test Report" in html


def test_report_title_section_rendered_when_present():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results, title="Release 4.2 — Regression Pass")
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    section = soup.select_one(".report-title-section")
    assert section is not None
    assert "Release 4.2" in section.get_text()


def test_report_title_section_omitted_when_absent():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".report-title-section") is None


def test_header_uses_new_icon_assets_and_generated_wording():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".topbar-brand-icon-light") is not None
    assert soup.select_one(".topbar-brand-icon-dark") is not None
    assert "Generated on" in html

    environment_pt = dict(ENVIRONMENT, report_language="pt")
    html_pt = generate_report_html(record, environment_pt, b"{}")
    assert "Gerado em" in html_pt


def test_edge_case_zero_scenarios_no_donut_division_by_zero_no_crash():
    record = _execution_record([])
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    assert "NaN" not in html
    assert "undefined" not in html
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".empty-state") is not None
    assert soup.select(".mini-card") == []


def test_edge_case_request_technical_error_distinct_from_assertion_failure():
    result = _scenario("sc1", "", "feat", "failed", request_technical_error="connection refused")
    record = _execution_record([result])
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".technical-error-block") is not None
    assert "connection refused" in html


def test_oracle_connector_password_never_appears_in_rendered_html():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    environment = dict(
        ENVIRONMENT,
        connectors={
            "oracle_main": {
                "type": "oracle",
                "dsn": "host:1521/xe",
                "username": "svc_user",
                "password": "s3cr3t-value",
            }
        },
    )
    html = generate_report_html(record, environment, b"{}")
    assert "s3cr3t-value" not in html
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".not-displayed-badge") is not None
    # username is sensitive (FR-016) but still maskable/revealable, not never-show
    assert 'data-real-value="svc_user"' in html


def test_gantt_services_row_renders_one_marker_per_collection_event():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(
        results,
        services_info=[
            {"name": "billing-service", "collected_at": "2026-07-25T10:00:00-03:00", "status_code": 200, "error": None, "data": {}},
            {"name": "fraud-service", "collected_at": "2026-07-25T10:00:05-03:00", "status_code": 200, "error": None, "data": {}},
        ],
    )
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    service_markers = soup.select(".gantt-marker-service")
    assert len(service_markers) == 2
    # distinct from the per-scenario request/response/validation markers
    assert soup.select_one(".gantt-marker-request") is not None


def test_gantt_omits_services_row_when_no_services_info():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".gantt-marker-service") is None


def test_latency_points_render_as_non_circular_markers():
    results = [_scenario("sc1", "", "feat", "passed")]
    record = _execution_record(results)
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one("circle.latency-point") is None
    assert soup.select_one("span.latency-point") is not None


def test_edge_case_single_timestamp_gantt_markers_render_without_divide_by_zero():
    ts = "2026-07-25T10:00:00-03:00"
    results = [_scenario("a", "", "f", "passed", request_timestamp=ts, response_timestamp=ts)]
    record = _execution_record(results)
    html = generate_report_html(record, ENVIRONMENT, b"{}")
    assert "NaN" not in html
    soup = BeautifulSoup(html, "html.parser")
    marker = soup.select_one(".gantt-marker")
    assert marker is not None
    assert "* 0.5)" in marker["style"]
