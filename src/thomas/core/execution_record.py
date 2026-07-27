"""Build and write the execution record produced by `thomas request`.

See docs/architecture/03-data-schemas.md §4. `thomas request` always writes
`validation_rounds: []` per scenario; only a later, separate command
(`thomas validate`, F02) ever appends to that list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from thomas import __version__ as THOMAS_VERSION


def build_execution_id(now: datetime) -> str:
    return f"execution_{now.strftime('%Y-%m-%d_%H%M')}"


@dataclass
class ScenarioResult:
    scenario_file: str
    feature: str
    scenario_id: str
    folder: str
    correlation_id: str | None
    correlation_error: str | None
    request_timestamp: str
    response_timestamp: str | None
    request_sent: dict[str, Any]
    api_response: dict[str, Any] | None
    request_technical_error: str | None
    api_checks_result: list[dict[str, Any]]
    api_result: str
    final_status: str
    validation_rounds: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_file": self.scenario_file,
            "feature": self.feature,
            "scenario_id": self.scenario_id,
            "folder": self.folder,
            "correlation_id": self.correlation_id,
            "correlation_error": self.correlation_error,
            "request_timestamp": self.request_timestamp,
            "response_timestamp": self.response_timestamp,
            "request_sent": self.request_sent,
            "api_response": self.api_response,
            "request_technical_error": self.request_technical_error,
            "api_checks_result": self.api_checks_result,
            "api_result": self.api_result,
            "validation_rounds": self.validation_rounds,
            "final_status": self.final_status,
        }


def build_execution_record(
    *,
    environment_name: str,
    timezone_name: str,
    start_time: datetime,
    included_scenarios: list[str],
    services_info: list[dict[str, Any]],
    results: list[ScenarioResult],
) -> dict[str, Any]:
    tz = ZoneInfo(timezone_name)
    start_time = start_time.astimezone(tz)
    return {
        "schema_version": 1,
        "execution_id": build_execution_id(start_time),
        "thomas_version": THOMAS_VERSION,
        "environment": environment_name,
        "start_timestamp": start_time.isoformat(),
        "included_scenarios": included_scenarios,
        "services_info": services_info,
        "results": [result.to_dict() for result in results],
    }


def write_execution_record(record: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{record['execution_id']}.json"
    output_path.write_text(json.dumps(record, indent=2))
    return output_path
