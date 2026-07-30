"""Resolve execution-record + environment data into a self-contained HTML report.

See docs/architecture/06-html-report.md and specs/010-report-dashboard-restructure/data-model.md.
All business logic (aggregation, worst-of status, filtering data, sorting)
lives here; template.html.j2 only loops/conditionals over already-resolved data
(FR-026).
"""

from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader

from thomas.core.loading import ThomasFileError
from thomas.report.strings import STRINGS

_STATUS_PRIORITY = {"aprovado": 0, "aguardando": 1, "reprovado": 2}
_FINAL_STATUS_TO_PT = {
    "passed": "aprovado",
    "failed": "reprovado",
    "awaiting_validation": "aguardando",
}
_SENSITIVE_KEY_PATTERN = re.compile(
    r"KEY|TOKEN|SECRET|PASSWORD|SENHA|CREDENTIAL|SECURITY", re.IGNORECASE
)
_MASK_DISPLAY = "•" * 10


def resolve_report_filename(execution_path: Path, generated_at: datetime) -> str:
    """Return "<execution_stem>_<timestamp>.html" per FR-001."""
    timestamp = generated_at.strftime("%Y%m%d_%H%M%S_%f")
    return f"{execution_path.stem}_{timestamp}.html"


def write_report(html: str, execution_path: Path, output_dir: Path, generated_at: datetime) -> Path:
    """Create output_dir if needed, write html to the resolved filename, return the written Path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / resolve_report_filename(execution_path, generated_at)
    output_path.write_text(html)
    return output_path


def _read_package_svg(file_name: str) -> str:
    return resources.files("thomas.report.assets").joinpath(file_name).read_text()


def _validate_svg(text: str, path: Path) -> str:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ThomasFileError([(str(path), f"not a well-formed SVG file: {exc}")]) from exc
    if not root.tag.endswith("svg"):
        raise ThomasFileError([(str(path), "not a well-formed SVG file: root element is not <svg>")])
    return text


def _resolve_company_logo_svg(environment: dict) -> str | None:
    logo_path = environment.get("company_logo_path")
    if not logo_path:
        return None
    path = Path(logo_path)
    try:
        text = path.read_text()
    except OSError as exc:
        raise ThomasFileError([(str(path), f"could not read company_logo_path file: {exc}")]) from exc
    return _validate_svg(text, path)


def _build_header(environment: dict, generated_at: datetime) -> dict:
    tz = ZoneInfo(environment["timezone"])
    return {
        "company_name": environment.get("company_name"),
        "department_name": environment.get("department_name"),
        "system_name": environment["system_name"],
        "environment_name": environment["environment_name"],
        "generated_at": generated_at.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def _format_duration(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "—"
    if total_seconds < 1:
        return f"{int(delta.total_seconds() * 1000)}ms"
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def _worst_of(pt_statuses: list[str]) -> str:
    """Reprovado > Aguardando > Aprovado priority over a list of pt-status strings.

    Vacuously "aprovado" when the list is empty (research.md §4, data-model.md).
    """
    if not pt_statuses:
        return "aprovado"
    return max(pt_statuses, key=lambda s: _STATUS_PRIORITY[s])


def _status_counts(results: list[dict]) -> dict:
    passed_count = sum(1 for r in results if r["final_status"] == "passed")
    failed_count = sum(1 for r in results if r["final_status"] == "failed")
    awaiting_count = sum(1 for r in results if r["final_status"] == "awaiting_validation")
    total_count = len(results)
    if failed_count:
        status = "reprovado"
    elif awaiting_count:
        status = "aguardando"
    else:
        status = "aprovado"
    return {
        "status": status,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "awaiting_count": awaiting_count,
        "total_count": total_count,
    }


def _percentages(counts: dict) -> dict:
    total = counts["total_count"]
    if not total:
        return {"passed": 0, "failed": 0, "awaiting": 0}
    raw = {
        "passed": counts["passed_count"] * 100 / total,
        "failed": counts["failed_count"] * 100 / total,
        "awaiting": counts["awaiting_count"] * 100 / total,
    }
    rounded = {key: int(value) for key, value in raw.items()}
    remainder = 100 - sum(rounded.values())
    if remainder:
        fractional_order = sorted(raw, key=lambda key: raw[key] - rounded[key], reverse=True)
        rounded[fractional_order[0]] += remainder
    return rounded


def _donut_gradient_stops(percentages: dict, total_count: int) -> str:
    if not total_count:
        return "var(--color-neutral-300) 0% 100%"
    stops = []
    cumulative = 0
    for key, color_var in (
        ("passed", "--color-status-approved"),
        ("failed", "--color-status-failed"),
        ("awaiting", "--color-status-awaiting"),
    ):
        start = cumulative
        cumulative += percentages[key]
        stops.append(f"var({color_var}) {start}% {cumulative}%")
    return ", ".join(stops)


def _build_groups(rows: list[dict], key_fn) -> list[dict]:
    """Group already-built scenario rows (or raw results) by key_fn(row).

    Each row must carry `scenario_id` and `final_status`. Used for both the
    Dashboard mini-cards/scenario-list grouping (rows = scenario_rows) and
    any raw-result grouping needs (research.md §3).
    """
    order: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        key = key_fn(row)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(row)

    groups = []
    for key in order:
        scenarios = grouped[key]
        counts = _status_counts(scenarios)
        groups.append({
            "name": key,
            "status": counts["status"],
            "passed_count": counts["passed_count"],
            "failed_count": counts["failed_count"],
            "awaiting_count": counts["awaiting_count"],
            "total_count": counts["total_count"],
            "scenario_ids": [r["scenario_id"] for r in scenarios],
            "scenarios": scenarios,
        })
    return groups


def _is_sensitive_key(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def _flatten_kv(value, prefix: str = "") -> list[dict]:
    """Recursively flatten a JSON value into display rows with dotted-path keys.

    Each row: {"key", "value", "is_sensitive", "value_masked"}. A key is
    sensitive if any path segment case-insensitively contains KEY/TOKEN/
    SECRET/PASSWORD (research.md §8).
    """
    rows: list[dict] = []
    if isinstance(value, dict):
        for key, sub_value in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(sub_value, (dict, list)) and sub_value:
                rows.extend(_flatten_kv(sub_value, child_prefix))
            else:
                rows.append(_leaf_row(child_prefix, sub_value))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            if isinstance(item, (dict, list)) and item:
                rows.extend(_flatten_kv(item, child_prefix))
            else:
                rows.append(_leaf_row(child_prefix, item))
    else:
        rows.append(_leaf_row(prefix, value))
    return rows


def _leaf_row(key: str, value) -> dict:
    is_sensitive = _is_sensitive_key(key)
    return {
        "key": key,
        "value": value,
        "is_sensitive": is_sensitive,
        "value_masked": _MASK_DISPLAY if is_sensitive else value,
    }


def _format_time_short(timestamp: str, tz: ZoneInfo) -> str:
    return datetime.fromisoformat(timestamp).astimezone(tz).strftime("%H:%M:%S")


def _format_time_full(timestamp: str, tz: ZoneInfo) -> str:
    return datetime.fromisoformat(timestamp).astimezone(tz).strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_datetime_br(timestamp: str, tz: ZoneInfo) -> str:
    return datetime.fromisoformat(timestamp).astimezone(tz).strftime("%d/%m/%Y %H:%M:%S")


def _format_log_timestamp(timestamp: str, tz: ZoneInfo) -> str:
    return datetime.fromisoformat(timestamp).astimezone(tz).strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]


def _gantt_ruler_format(min_ts: datetime, max_ts: datetime, tz: ZoneInfo) -> str:
    min_local, max_local = min_ts.astimezone(tz), max_ts.astimezone(tz)
    if min_local.date() != max_local.date():
        return "%d/%m %H:%M:%S"
    if min_local.replace(microsecond=0) == max_local.replace(microsecond=0):
        return "%H:%M:%S.%f"
    return "%H:%M:%S"


def _format_gantt_tick(ts: datetime, tz: ZoneInfo, fmt: str) -> str:
    label = ts.astimezone(tz).strftime(fmt)
    return label[:-3] if fmt.endswith("%f") else label


def _build_check_rows(checks: list[dict]) -> dict:
    status = "reprovado" if any(not c["passed"] for c in checks) else "aprovado"
    rows = [
        {
            "id": c["id"],
            "expected": c["expected"],
            "obtained": c["obtained"],
            "operator": c["operator"],
            "passed": c["passed"],
            "outcome": "passed" if c["passed"] else "failed",
        }
        for c in checks
    ]
    return {"status": status, "checks": rows}


def _resolve_validation_outcome(validation: dict) -> str:
    if validation.get("technical_error") is not None:
        return "technical_error"
    if validation.get("passed") is True:
        return "passed"
    return "failed"


def _build_validation_rounds(validation_rounds: list[dict]) -> list[dict]:
    rounds = []
    for round_entry in validation_rounds:
        outcomes = [_resolve_validation_outcome(v) for v in round_entry["results"]]
        round_status = "reprovado" if any(o != "passed" for o in outcomes) else "aprovado"
        checks = [
            {
                "id": v["id"],
                "connector": v["connector"],
                "operator": v["operator"],
                "expected": v["expected"],
                "obtained": v["obtained"],
                "outcome": _resolve_validation_outcome(v),
                "technical_error": v.get("technical_error"),
            }
            for v in round_entry["results"]
        ]
        rounds.append({
            "timestamp": round_entry["timestamp"],
            "environment_used": round_entry["environment_used"],
            "status": round_status,
            "checks": checks,
        })
    return rounds


def _status_code_class(status_code: int | None) -> str | None:
    if status_code is None:
        return None
    return f"{status_code // 100}xx"


def _build_scenario_detail(result: dict) -> dict:
    request_sent = result["request_sent"]
    requisicao = {
        "method": request_sent.get("method"),
        "path": request_sent.get("path"),
        "correlation_id": result.get("correlation_id"),
        "headers": request_sent.get("headers") or {},
        "payload": request_sent.get("payload"),
    }

    if result.get("request_technical_error") is not None:
        resposta = {"technical_error": result["request_technical_error"]}
    else:
        api_response = result.get("api_response") or {}
        resposta = {
            "status_code": api_response.get("status_code"),
            "status_code_class": _status_code_class(api_response.get("status_code")),
            "body": api_response.get("body"),
        }

    verificacoes = _build_check_rows(result.get("api_checks_result") or [])

    validation_rounds = result.get("validation_rounds") or []
    if validation_rounds:
        rounds = _build_validation_rounds(validation_rounds)
        validacao = {
            "state": "occurred",
            "status": _worst_of([r["status"] for r in rounds]),
            "rounds": rounds,
        }
    elif result["final_status"] == "awaiting_validation":
        validacao = {"state": "pending"}
    else:
        validacao = None

    return {
        "requisicao": requisicao,
        "resposta": resposta,
        "verificacoes": verificacoes,
        "validacao": validacao,
    }


def _duration_display(result: dict) -> str:
    validation_rounds = result.get("validation_rounds") or []
    request_ts = datetime.fromisoformat(result["request_timestamp"])

    if validation_rounds:
        last_round_ts = datetime.fromisoformat(validation_rounds[-1]["timestamp"])
        return _format_duration(last_round_ts - request_ts)
    if result["final_status"] == "awaiting_validation":
        return "—"
    response_timestamp = result.get("response_timestamp")
    if not response_timestamp:
        return "—"
    response_ts = datetime.fromisoformat(response_timestamp)
    return _format_duration(response_ts - request_ts)


def _build_dashboard(results: list[dict], tz: ZoneInfo) -> dict:
    counts = _status_counts(results)
    percentages = _percentages(counts)

    scenario_rows = []
    for result in results:
        scenario_rows.append({
            "scenario_id": result["scenario_id"],
            "folder": result["folder"],
            "feature": result["feature"],
            "final_status": result["final_status"],
            "status_pt": _FINAL_STATUS_TO_PT[result["final_status"]],
            "time_short": _format_time_short(result["request_timestamp"], tz),
            "time_full": _format_time_full(result["request_timestamp"], tz),
            "duration_display": _duration_display(result),
            "detail": _build_scenario_detail(result),
        })

    return {
        "overall_status": {
            "status": counts["status"],
            "passed_count": counts["passed_count"],
            "failed_count": counts["failed_count"],
            "awaiting_count": counts["awaiting_count"],
            "total_count": counts["total_count"],
            "percentages": percentages,
        },
        "donut": {"gradient_stops": _donut_gradient_stops(percentages, counts["total_count"])},
        "groups": {
            "by_folder": _build_groups(scenario_rows, lambda r: r["folder"]),
            "by_feature": _build_groups(scenario_rows, lambda r: r["feature"]),
        },
        "default_grouping": "feature",
        "scenario_rows": scenario_rows,
    }


def _build_services_info_view(execution_record: dict, tz: ZoneInfo) -> list[dict] | None:
    services_info = execution_record.get("services_info") or []
    if not services_info:
        return None
    view = []
    for service in services_info:
        error = service.get("error")
        entry = {
            "name": service["name"],
            "status": "error" if error else "ok",
            "collected_at": _format_datetime_br(service["collected_at"], tz),
            "status_code": service.get("status_code"),
            "error": error,
        }
        if not error:
            data = service.get("data") or {}
            entry["fields"] = _flatten_kv(data) if isinstance(data, (dict, list)) else [_leaf_row("data", data)]
        view.append(entry)
    return view


def _build_connectors_view(environment: dict) -> list[dict] | None:
    connectors = environment.get("connectors") or {}
    if not connectors:
        return None
    view = []
    for name, connector in connectors.items():
        config = {k: v for k, v in connector.items() if k != "type"}
        view.append({
            "name": name,
            "type": connector.get("type"),
            "config_masked": _flatten_kv(config),
        })
    return view


def _build_prepared_variables_view(execution_record: dict) -> list[dict] | None:
    prepared_variables = execution_record.get("prepared_variables") or {}
    if not prepared_variables:
        return None
    return _flatten_kv(prepared_variables)


def _build_environment_view(
    execution_record: dict, environment: dict, execution_signature: dict, tz: ZoneInfo
) -> dict:
    api = environment.get("api", {})
    headers = api.get("headers") or {}

    return {
        "identificacao": {
            "environment_name": environment["environment_name"],
            "timezone": environment["timezone"],
            "report_language": environment.get("report_language", "en"),
            "execution_id": execution_record["execution_id"],
            "thomas_version": execution_record["thomas_version"],
            "start_timestamp": _format_datetime_br(execution_record["start_timestamp"], tz),
        },
        "api_under_test": {
            "base_url": api.get("base_url"),
            "timeout_seconds": api.get("timeout_seconds", 30),
            "ssl_verify": api.get("ssl_verify", True),
            "headers": [{"key": k, "value": v} for k, v in headers.items()],
        },
        "services_info": _build_services_info_view(execution_record, tz),
        "connectors": _build_connectors_view(environment),
        "prepared_variables": _build_prepared_variables_view(execution_record),
        "signature": execution_signature,
    }


def _build_timeline_events(execution_record: dict, tz: ZoneInfo) -> list[dict]:
    results = execution_record["results"]
    events = []
    for result in results:
        events.append({
            "kind": "request",
            "timestamp": result["request_timestamp"],
            "timestamp_label": _format_log_timestamp(result["request_timestamp"], tz),
            "scenario_id": result["scenario_id"],
            "folder": result["folder"],
            "feature": result["feature"],
        })
        if result.get("response_timestamp"):
            events.append({
                "kind": "response",
                "timestamp": result["response_timestamp"],
                "timestamp_label": _format_log_timestamp(result["response_timestamp"], tz),
                "scenario_id": result["scenario_id"],
                "folder": result["folder"],
                "feature": result["feature"],
            })
        for round_index, round_entry in enumerate(result.get("validation_rounds") or []):
            round_status = "reprovado" if any(
                _resolve_validation_outcome(v) != "passed" for v in round_entry["results"]
            ) else "aprovado"
            events.append({
                "kind": "validation_round",
                "timestamp": round_entry["timestamp"],
                "timestamp_label": _format_log_timestamp(round_entry["timestamp"], tz),
                "scenario_id": result["scenario_id"],
                "folder": result["folder"],
                "feature": result["feature"],
                "round_index": round_index,
                "outcome": round_status,
            })
    for service in execution_record.get("services_info") or []:
        events.append({
            "kind": "service_collected",
            "timestamp": service["collected_at"],
            "timestamp_label": _format_log_timestamp(service["collected_at"], tz),
            "service_name": service["name"],
            "outcome": "reprovado" if service.get("error") else "aprovado",
        })
    events.sort(key=lambda e: datetime.fromisoformat(e["timestamp"]))
    return events


def _build_gantt(results: list[dict], events: list[dict], tz: ZoneInfo) -> dict:
    timestamps = [datetime.fromisoformat(e["timestamp"]) for e in events]
    if not timestamps:
        return {"rows": [], "ticks": []}
    min_ts, max_ts = min(timestamps), max(timestamps)
    span = (max_ts - min_ts).total_seconds()

    def _position(ts: str) -> float:
        if span <= 0:
            return 50.0
        return (datetime.fromisoformat(ts) - min_ts).total_seconds() / span * 100

    def _label(ts: str) -> str:
        return _format_time_short(ts, tz)

    rows = []
    for result in results:
        markers = [{
            "type": "request",
            "position": _position(result["request_timestamp"]),
            "timestamp_label": _label(result["request_timestamp"]),
        }]
        if result.get("response_timestamp"):
            markers.append({
                "type": "response",
                "position": _position(result["response_timestamp"]),
                "timestamp_label": _label(result["response_timestamp"]),
            })
        for round_index, round_entry in enumerate(result.get("validation_rounds") or []):
            outcome = "reprovado" if any(
                _resolve_validation_outcome(v) != "passed" for v in round_entry["results"]
            ) else "aprovado"
            markers.append({
                "type": "validation",
                "position": _position(round_entry["timestamp"]),
                "timestamp_label": _label(round_entry["timestamp"]),
                "round_index": round_index,
                "outcome": outcome,
            })
        rows.append({
            "scenario_id": result["scenario_id"],
            "markers": markers,
            "final_status": result["final_status"],
            "status_pt": _FINAL_STATUS_TO_PT[result["final_status"]],
        })

    n_ticks = 5
    ruler_fmt = _gantt_ruler_format(min_ts, max_ts, tz)
    ticks = []
    for i in range(n_ticks):
        frac = i / (n_ticks - 1)
        tick_ts = min_ts if span <= 0 else min_ts + timedelta(seconds=frac * span)
        ticks.append({"position": frac * 100, "label": _format_gantt_tick(tick_ts, tz, ruler_fmt)})

    return {"rows": rows, "ticks": ticks}


_SERIES_COLOR_VARS = [
    "--color-accent",
    "--color-status-awaiting",
    "--color-status-approved",
    "--color-status-failed",
    "--color-accent-2",
    "--color-neutral-600",
]


def _build_latency(results: list[dict], tz: ZoneInfo) -> dict:
    points = []
    for result in results:
        if result.get("request_technical_error") is not None:
            continue
        response_timestamp = result.get("response_timestamp")
        if not response_timestamp:
            continue
        request_ts = datetime.fromisoformat(result["request_timestamp"])
        response_ts = datetime.fromisoformat(response_timestamp)
        latency_ms = (response_ts - request_ts).total_seconds() * 1000
        points.append({
            "request_timestamp": result["request_timestamp"],
            "latency_ms": latency_ms,
            "path": result["request_sent"].get("path"),
        })

    if not points:
        return {"stats": None, "points": [], "legend": [], "x_ticks": [], "y_ticks": []}

    latencies = sorted(p["latency_ms"] for p in points)
    n = len(latencies)
    p95_index = min(n - 1, max(0, round(0.95 * (n - 1))))
    stats = {
        "average_ms": sum(latencies) / n,
        "p95_ms": latencies[p95_index],
        "max_ms": max(latencies),
    }

    paths = sorted({p["path"] for p in points if p["path"]})
    color_by_path = {path: _SERIES_COLOR_VARS[i % len(_SERIES_COLOR_VARS)] for i, path in enumerate(paths)}
    legend = [{"path": path, "color_var": color_by_path[path]} for path in paths]

    request_timestamps = [datetime.fromisoformat(p["request_timestamp"]) for p in points]
    min_ts, max_ts = min(request_timestamps), max(request_timestamps)
    x_span = (max_ts - min_ts).total_seconds()
    y_max = max(stats["max_ms"], 1.0)

    for point in points:
        ts = datetime.fromisoformat(point["request_timestamp"])
        point["x_percent"] = 50.0 if x_span <= 0 else (ts - min_ts).total_seconds() / x_span * 100
        point["y_percent"] = 100 - (point["latency_ms"] / y_max * 100)
        point["color_var"] = color_by_path.get(point["path"], _SERIES_COLOR_VARS[0])

    n_x_ticks = 5
    ruler_fmt = _gantt_ruler_format(min_ts, max_ts, tz)
    x_ticks = []
    for i in range(n_x_ticks):
        frac = i / (n_x_ticks - 1)
        tick_ts = min_ts if x_span <= 0 else min_ts + timedelta(seconds=frac * x_span)
        x_ticks.append({"position": frac * 100, "label": _format_gantt_tick(tick_ts, tz, ruler_fmt)})

    n_y_ticks = 4
    y_values = [(i / (n_y_ticks - 1)) * y_max for i in range(n_y_ticks)]
    for decimals in range(3):
        y_labels = [f"{value:.{decimals}f}ms" for value in y_values]
        if len(set(y_labels)) == len(y_labels):
            break
    seen_labels: set[str] = set()
    for i, label in enumerate(y_labels):
        if label in seen_labels:
            y_labels[i] = ""
        else:
            seen_labels.add(label)
    y_ticks = [
        {"position": 100 - (i / (n_y_ticks - 1)) * 100, "label": y_labels[i]}
        for i in range(n_y_ticks)
    ]

    return {"stats": stats, "points": points, "legend": legend, "x_ticks": x_ticks, "y_ticks": y_ticks}


def _build_timeline_view(execution_record: dict, tz: ZoneInfo) -> dict:
    results = execution_record["results"]
    events = _build_timeline_events(execution_record, tz)
    return {
        "events": events,
        "gantt": _build_gantt(results, events, tz),
        "latency": _build_latency(results, tz),
    }


def generate_report_html(execution_record: dict, environment: dict, execution_file_bytes: bytes) -> str:
    """Return the fully-rendered, self-contained HTML document as a string."""
    generated_at = datetime.now().astimezone()
    strings = STRINGS.get(environment.get("report_language", "en"), STRINGS["en"])
    results = execution_record["results"]
    tz = ZoneInfo(environment["timezone"])

    execution_signature = {
        "algorithm": "SHA-256",
        "hex_digest": hashlib.sha256(execution_file_bytes).hexdigest(),
    }

    context = {
        "strings": strings,
        "active_tab_default": "dashboard",
        "thomas_logo_svg": _read_package_svg("thomas-logo.svg"),
        "thomas_logo_dark_svg": _read_package_svg("thomas-logo-dark.svg"),
        "company_logo_svg": _resolve_company_logo_svg(environment),
        "header": _build_header(environment, generated_at),
        "dashboard": _build_dashboard(results, tz),
        "environment_view": _build_environment_view(execution_record, environment, execution_signature, tz),
        "timeline_view": _build_timeline_view(execution_record, tz),
    }

    jinja_env = Environment(
        loader=PackageLoader("thomas.report", package_path="."),
        autoescape=True,
    )
    template = jinja_env.get_template("template.html.j2")
    return template.render(**context)
