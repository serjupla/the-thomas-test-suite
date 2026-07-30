import json

from bs4 import BeautifulSoup

from thomas.cli import main

ENVIRONMENT = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {
        "base_url": "https://example.test/api",
        "timeout_seconds": 30,
        "ssl_verify": True,
        "headers": {"X-Api-Key": "abc123"},
    },
    "connectors": {
        "ledger_db": {"type": "oracle", "password": "s3cr3t-conn", "host": "db.internal"},
    },
    "services_info": [
        {"name": "billing-service", "info_url": "https://svc.test/info", "fields_to_extract": ["status"]},
    ],
}

ENVIRONMENT_PT = dict(ENVIRONMENT, report_language="pt")

ENVIRONMENT_MINIMAL = {
    "schema_version": 1,
    "environment_name": "dev",
    "system_name": "Example System",
    "timezone": "America/Sao_Paulo",
    "api": {"base_url": "https://example.test/api", "timeout_seconds": 30},
}


def _scenario_result(
    scenario_id,
    folder,
    feature,
    final_status,
    validation_rounds=None,
    api_checks_result=None,
    request_technical_error=None,
    request_timestamp="2026-07-25T10:00:00-03:00",
):
    return {
        "scenario_file": f"{folder}/{scenario_id}.json" if folder else f"{scenario_id}.json",
        "feature": feature,
        "scenario_id": scenario_id,
        "folder": folder,
        "correlation_id": "corr-1",
        "correlation_error": None,
        "request_timestamp": request_timestamp,
        "response_timestamp": None if request_technical_error else "2026-07-25T10:00:01-03:00",
        "request_sent": {"method": "POST", "path": "/orders", "payload": {"amount": 150.0}, "headers": {}},
        "api_response": None if request_technical_error else {"status_code": 201, "body": {"status": "PENDING"}},
        "request_technical_error": request_technical_error,
        "api_checks_result": api_checks_result or [],
        "api_result": "failed" if request_technical_error else "passed",
        "validation_rounds": validation_rounds or [],
        "final_status": final_status,
    }


def _round(timestamp, results, round_result):
    return {"timestamp": timestamp, "environment_used": "dev", "results": results, "round_result": round_result}


def _validation(id_, passed=True, technical_error=None, expected="SETTLED", obtained="SETTLED"):
    return {
        "id": id_,
        "connector": "oracle_main",
        "expected": expected,
        "obtained": obtained,
        "operator": "equals",
        "passed": passed,
        "technical_error": technical_error,
    }


def _build_execution_record(prepared_variables=None, services_info=None):
    results = [
        _scenario_result(
            "oracle_settlement_confirmation",
            "billing",
            "instant_transfer",
            "passed",
            api_checks_result=[
                {"id": "http_status", "expected": 201, "obtained": 201, "operator": "equals", "passed": True}
            ],
        ),
        _scenario_result("valid_amount_transfer", "billing", "instant_transfer", "failed"),
        _scenario_result(
            "kyc_document_check",
            "onboarding",
            "kyc",
            "passed",
            validation_rounds=[
                _round(
                    "2026-07-25T12:00:00-03:00",
                    [
                        _validation("v1", passed=False, obtained="PROCESSING"),
                        _validation("v2", passed=False, technical_error="timeout waiting for message"),
                    ],
                    "failed",
                ),
                _round(
                    "2026-07-25T14:00:00-03:00",
                    [_validation("v1", passed=True), _validation("v2", passed=True)],
                    "passed",
                ),
            ],
        ),
        _scenario_result("kyc_awaiting", "onboarding", "kyc", "awaiting_validation"),
        _scenario_result(
            "gateway_timeout",
            "billing",
            "instant_transfer",
            "failed",
            request_technical_error="connection refused",
        ),
    ]
    record = {
        "schema_version": 1,
        "execution_id": "execution_test",
        "thomas_version": "0.0.0",
        "environment": "dev",
        "start_timestamp": "2026-07-25T10:00:00-03:00",
        "included_scenarios": [r["scenario_file"] for r in results],
        "services_info": services_info if services_info is not None else [
            {
                "name": "billing-service",
                "collected_at": "2026-07-25T09:59:00-03:00",
                "status_code": 200,
                "error": None,
                "data": {"status": "UP"},
            }
        ],
        "results": results,
    }
    if prepared_variables:
        record["prepared_variables"] = prepared_variables
    return record


EXECUTION_RECORD = _build_execution_record(
    prepared_variables={"customer_id": "999999", "api_token": "sk-secret-xyz"}
)


def write_json(path, document) -> None:
    path.write_text(json.dumps(document, indent=2))


def _run_report(tmp_path, environment, subdir="", execution_record=None):
    workdir = tmp_path / subdir if subdir else tmp_path
    workdir.mkdir(parents=True, exist_ok=True)
    env_path = workdir / "dev.json"
    write_json(env_path, environment)
    exec_path = workdir / "execution.json"
    write_json(exec_path, execution_record if execution_record is not None else EXECUTION_RECORD)
    output_dir = workdir / "reports"

    exit_code = main([
        "report",
        "--execution", str(exec_path),
        "--environment", str(env_path),
        "--output", str(output_dir),
    ])
    assert exit_code == 0
    html_files = list(output_dir.glob("*.html"))
    assert len(html_files) == 1
    return html_files[0].read_text()


# --- US1: Dashboard ---


def test_dashboard_overall_status_stat_cards_and_totals_consistent(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us1_overall")
    soup = BeautifulSoup(html, "html.parser")

    badge = soup.select_one(".overall-status-badge")
    assert "status-reprovado" in badge["class"]

    total_count = int(soup.select_one(".stat-card--total .stat-card-value").contents[0].strip())
    assert total_count == 5

    stat_counts = [
        int(soup.select_one(f".stat-card--{cls} .stat-card-value").contents[0].strip())
        for cls in ("passed", "failed", "awaiting")
    ]
    assert sum(stat_counts) == total_count


def test_dashboard_mini_card_totals_sum_to_total_in_both_groupings(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us1_minicards")
    soup = BeautifulSoup(html, "html.parser")

    feature_cards = soup.select('.mini-card-scroll[data-grouping-view="feature"] .mini-card')
    folder_cards = soup.select('.mini-card-scroll[data-grouping-view="folder"] .mini-card')
    assert len(feature_cards) == 2  # instant_transfer, kyc
    assert len(folder_cards) == 2  # billing, onboarding

    def total_of(cards):
        return sum(int(c.select_one(".mini-card-counts").get_text(strip=True).split("/")[1]) for c in cards)

    assert total_of(feature_cards) == 5
    assert total_of(folder_cards) == 5


def test_dashboard_scenario_row_opposite_axis_tag_and_grouping_default(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us1_tags")
    soup = BeautifulSoup(html, "html.parser")

    # default grouping is feature -> feature view visible, tags show folder
    feature_view = soup.select_one('.scenario-list-view[data-grouping-view="feature"]')
    assert "hidden" not in feature_view.get("class", [])
    folder_view = soup.select_one('.scenario-list-view[data-grouping-view="folder"]')
    assert "hidden" in folder_view.get("class", [])

    row = feature_view.select_one('.scenario-row[data-scenario-id="oracle_settlement_confirmation"]')
    tag_text = row.select_one(".scenario-tag").get_text(strip=True)
    assert tag_text == "billing"


def test_dashboard_scenario_detail_four_sections_and_validation_states(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us1_detail")
    soup = BeautifulSoup(html, "html.parser")

    kyc_row = soup.select_one('.scenario-row[data-scenario-id="kyc_document_check"]')
    sections = kyc_row.select(".scenario-detail-panel > details.detail-section")
    assert len(sections) == 4  # Requisicao, Resposta, Verificacoes, Validacao
    round_rows = kyc_row.select("details.round-row")
    assert len(round_rows) == 2
    assert round_rows[0].get("open") is None
    assert round_rows[1].has_attr("open")

    # no validation configured -> section omitted entirely
    no_validation_row = soup.select_one('.scenario-row[data-scenario-id="oracle_settlement_confirmation"]')
    assert len(no_validation_row.select(".scenario-detail-panel > details.detail-section")) == 3

    # pending validation -> placeholder shown
    pending_row = soup.select_one('.scenario-row[data-scenario-id="kyc_awaiting"]')
    assert pending_row.select_one(".pending-placeholder") is not None


def test_dashboard_technical_error_resposta_indicator_requisicao_still_renders(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us1_technical_error")
    soup = BeautifulSoup(html, "html.parser")

    row = soup.select_one('.scenario-row[data-scenario-id="gateway_timeout"]')
    assert row.select_one(".technical-error-block") is not None
    assert "connection refused" in row.select_one(".technical-error-block").get_text()
    requisicao_meta = row.select(".detail-section-meta")[0]
    assert "POST /orders" in requisicao_meta.get_text()


def test_dashboard_zero_scenario_empty_state(tmp_path):
    empty_record = _build_execution_record()
    empty_record["results"] = []
    empty_record["included_scenarios"] = []
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us1_empty", execution_record=empty_record)
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one("#tab-dashboard .empty-state") is not None
    assert soup.select(".mini-card") == []
    assert "NaN" not in html
    assert "undefined" not in html


# --- US2: Ambiente de execução ---


def test_environment_tab_replaces_dashboard_and_back(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us2_tabs")
    soup = BeautifulSoup(html, "html.parser")
    panels = {p["id"]: p for p in soup.select(".tab-panel")}
    assert set(panels) == {"tab-dashboard", "tab-environment", "tab-timeline"}
    assert "active" in panels["tab-dashboard"]["class"]
    assert "active" not in panels["tab-environment"]["class"]
    assert "active" not in panels["tab-timeline"]["class"]


def test_environment_identificacao_block_fields(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us2_identificacao")
    soup = BeautifulSoup(html, "html.parser")
    env_block = soup.select("#tab-environment .env-block")[0]
    text = env_block.get_text()
    assert "dev" in text
    assert "America/Sao_Paulo" in text
    assert "execution_test" in text
    assert "0.0.0" in text


def test_environment_api_block_headers_collapsed_by_default(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us2_api")
    soup = BeautifulSoup(html, "html.parser")
    api_block = soup.select("#tab-environment .env-block")[1]
    assert "https://example.test/api" in api_block.get_text()
    headers_details = api_block.select_one("details.sub-collapsible")
    assert headers_details is not None
    assert headers_details.get("open") is None


def test_environment_services_info_block_present_when_configured_absent_when_not(tmp_path):
    html_with = _run_report(tmp_path, ENVIRONMENT, subdir="us2_services_with")
    assert "billing-service" in html_with

    record_without = _build_execution_record(services_info=[])
    html_without = _run_report(tmp_path, ENVIRONMENT, subdir="us2_services_without", execution_record=record_without)
    soup = BeautifulSoup(html_without, "html.parser")
    headers = [h3.get_text() for h3 in soup.select("#tab-environment h3")]
    assert not any("Informa" in h or "service" in h.lower() for h in headers)


def test_environment_connectors_masked_by_default_and_block_omitted_when_absent(tmp_path):
    html_with = _run_report(tmp_path, ENVIRONMENT, subdir="us2_connectors_with")
    soup = BeautifulSoup(html_with, "html.parser")
    mask_span = soup.select_one(".mask-value")
    assert mask_span is not None
    assert mask_span.get_text(strip=True) == "•" * 10
    assert mask_span["data-real-value"] == "s3cr3t-conn"

    html_without = _run_report(tmp_path, ENVIRONMENT_MINIMAL, subdir="us2_connectors_without")
    soup_without = BeautifulSoup(html_without, "html.parser")
    assert soup_without.select_one(".connector-details") is None


def test_environment_prepared_variables_masked_and_block_omitted_when_absent(tmp_path):
    html_with = _run_report(tmp_path, ENVIRONMENT, subdir="us2_vars_with")
    soup = BeautifulSoup(html_with, "html.parser")
    var_heading = next(h3 for h3 in soup.select("#tab-environment h3") if "ariáve" in h3.get_text() or "ariable" in h3.get_text())
    var_table = var_heading.find_parent(class_="env-block").select_one("table.kv-table")
    text = var_table.get_text()
    assert "999999" in text  # non-sensitive value shown plainly
    mask_spans = var_table.select(".mask-value")
    assert any(span.get_text(strip=True) == "•" * 10 for span in mask_spans)

    record_without = _build_execution_record(prepared_variables=None)
    html_without = _run_report(tmp_path, ENVIRONMENT, subdir="us2_vars_without", execution_record=record_without)
    soup_without = BeautifulSoup(html_without, "html.parser")
    headers = [h3.get_text() for h3 in soup_without.select("#tab-environment h3")]
    assert not any("ariáve" in h or "ariable" in h for h in headers)


def test_environment_signature_block_present_with_copy_action(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us2_signature")
    soup = BeautifulSoup(html, "html.parser")
    signature_block = soup.select_one(".env-signature-block")
    assert signature_block is not None
    assert signature_block.select_one("code") is not None
    assert signature_block.select_one('[data-copy-target="report-signature"]') is not None


# --- US3: Timeline ---


def test_timeline_gantt_default_visualization_markers_and_badges(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us3_gantt")
    soup = BeautifulSoup(html, "html.parser")
    gantt_view = soup.select_one('.gantt-view[data-viz-view="gantt"]')
    assert "hidden" not in gantt_view.get("class", [])
    log_view = soup.select_one('.log-view[data-viz-view="log"]')
    assert "hidden" in log_view.get("class", [])

    rows = gantt_view.select(".gantt-row")
    assert len(rows) == 5
    kyc_row = None
    for row in rows:
        if row.select_one(".gantt-row-label").get_text(strip=True) == "kyc_document_check":
            kyc_row = row
            break
    assert kyc_row is not None
    markers = kyc_row.select(".gantt-marker")
    assert len(markers) == 4  # request, response, 2 validation rounds
    assert kyc_row.select_one(".gantt-badge.status-aprovado") is not None


def test_timeline_log_visualization_interleaves_all_event_kinds(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us3_log")
    soup = BeautifulSoup(html, "html.parser")
    log_entries = soup.select('.log-view[data-viz-view="log"] .log-entry')
    assert len(log_entries) > 0
    joined_text = " ".join(entry.get_text() for entry in log_entries)
    assert "billing-service" in joined_text  # service_collected kind present


def test_timeline_local_event_log_expandable_per_scenario(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us3_local_log")
    soup = BeautifulSoup(html, "html.parser")
    local_log = soup.select_one("#local-log-kyc_document_check")
    assert local_log is not None
    assert "hidden" in local_log.get("class", [])
    assert len(local_log.select(".log-entry")) >= 4  # request, response, 2 rounds


def test_timeline_latency_stats_and_scatter_plot_with_legend(tmp_path):
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us3_latency")
    soup = BeautifulSoup(html, "html.parser")
    stats = soup.select_one(".latency-stats")
    assert stats is not None
    assert "ms" in stats.get_text()
    points = soup.select(".latency-chart circle")
    assert len(points) == 4  # excludes the technical-error scenario
    legend_items = soup.select(".latency-legend .legend-item")
    assert len(legend_items) >= 1


def test_timeline_edge_case_single_timestamp_no_divide_by_zero(tmp_path):
    same_ts = "2026-07-25T10:00:00-03:00"
    record = _build_execution_record()
    for result in record["results"]:
        result["request_timestamp"] = same_ts
        if result.get("response_timestamp"):
            result["response_timestamp"] = same_ts
    html = _run_report(tmp_path, ENVIRONMENT, subdir="us3_same_instant", execution_record=record)
    assert "NaN" not in html


# --- Bilingual labels (Principle X) ---


def test_bilingual_labels_translate_data_stays_identical(tmp_path):
    html_en = _run_report(tmp_path, ENVIRONMENT, subdir="lang_en")
    html_pt = _run_report(tmp_path, ENVIRONMENT_PT, subdir="lang_pt")

    assert "Test Report" in html_en
    assert "Relatório de Testes" in html_pt
    assert "Relatório de Testes" not in html_en

    soup_en = BeautifulSoup(html_en, "html.parser")
    soup_pt = BeautifulSoup(html_pt, "html.parser")

    ids_en = sorted(row["data-scenario-id"] for row in soup_en.select('.scenario-list-view[data-grouping-view="feature"] .scenario-row'))
    ids_pt = sorted(row["data-scenario-id"] for row in soup_pt.select('.scenario-list-view[data-grouping-view="feature"] .scenario-row'))
    assert ids_en == ids_pt

    digest_en = soup_en.select_one(".env-signature-block code").get_text(strip=True)
    digest_pt = soup_pt.select_one(".env-signature-block code").get_text(strip=True)
    assert digest_en == digest_pt
