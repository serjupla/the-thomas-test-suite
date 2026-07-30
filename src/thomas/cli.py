"""thomas CLI entry point. See docs/architecture/07-cli-commands.md."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.markup import escape
from rich.progress import Progress
from rich.table import Table

from thomas import __version__
from thomas.connectors import ConnectorTechnicalError
from thomas.core.loading import (
    ThomasFileError,
    load_and_validate,
    load_environment,
    load_scenarios,
    load_variables,
)
from thomas.core.variables import find_undefined_references
from thomas.request.dispatch import run_request
from thomas.validate.orchestrator import run_validate
from thomas.validate.preflight import check_missing_connectors

console = Console()

_BANNER_ART_LINES = [
    "//",
    "// ▀▛▘▌      ▀▛▘▌                ▀▛▘     ▐   ▞▀▖   ▗▐     ",
    "//  ▌ ▛▀▖▞▀▖  ▌ ▛▀▖▞▀▖▛▚▀▖▝▀▖▞▀▘  ▌▞▀▖▞▀▘▜▀  ▚▄ ▌ ▌▄▜▀ ▞▀▖",
    "//  ▌ ▌ ▌▛▀   ▌ ▌ ▌▌ ▌▌▐ ▌▞▀▌▝▀▖  ▌▛▀ ▝▀▖▐ ▖ ▖ ▌▌ ▌▐▐ ▖▛▀ ",
    # Bottom row where version is appended
    "//  ▘ ▘ ▘▝▀▘  ▘ ▘ ▘▝▀ ▘▝ ▘▝▀▘▀▀   ▘▝▀▘▀▀  ▀  ▝▀ ▝▀▘▀▘▀ ▝▀▘",
    "//",
]
_BANNER_ART_LINES[-2] += f" v.{__version__}"
BANNER = "\n".join(_BANNER_ART_LINES)

_CREDENTIAL_KEYS = {"password", "username"}


class _CredentialRedactingFilter(logging.Filter):
    """Best-effort guard: never let a configured connector credential value reach the log (FR-025)."""

    def __init__(self, secrets: list[str]):
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            if secret in message:
                record.msg = record.getMessage().replace(secret, "***REDACTED***")
                record.args = ()
        return True


def _collect_credential_values(environment: dict) -> list[str]:
    secrets: list[str] = []
    for connector in environment.get("connectors", {}).values():
        for key in _CREDENTIAL_KEYS:
            value = connector.get(key)
            if value:
                secrets.append(str(value))
    return secrets


def _configure_logging(log_file: Path, secrets: list[str]) -> None:
    logger = logging.getLogger("thomas")
    logger.setLevel(logging.DEBUG)
    handler = logging.FileHandler(log_file)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(_CredentialRedactingFilter(secrets))
    logger.addHandler(handler)


def _build_init_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("init", help="Bootstrap a new Thomas test project.")
    parser.add_argument(
        "destination",
        nargs="?",
        default=None,
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing template files (scenarios/ is always protected)",
    )


def _build_request_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("request", help="Dispatch scenario requests and record results.")
    parser.add_argument("--environment", required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--folder", type=Path)
    group.add_argument("--scenario", type=Path)
    parser.add_argument("--variables", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("executions"))
    parser.add_argument("--log-file", type=Path, default=Path("thomas.log"))
    parser.add_argument("--verbose", action="store_true")


def _build_validate_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("validate", help="Run declared validations against an execution record.")
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--log-file", type=Path, default=Path("thomas.log"))
    parser.add_argument("--verbose", action="store_true")


def _build_report_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("report", help="Generate a self-contained HTML report from an execution record.")
    parser.add_argument("--execution", required=True, type=Path)
    parser.add_argument("--environment", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thomas")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_init_parser(subparsers)
    _build_request_parser(subparsers)
    _build_validate_parser(subparsers)
    _build_report_parser(subparsers)
    return parser


def run_init_command(args: argparse.Namespace) -> int:
    from thomas.commands.init import init_command

    return init_command(args, banner=BANNER)


def _print_summary(results: list[dict]) -> None:
    table = Table(title="thomas request summary")
    table.add_column("Total")
    table.add_column("Passed")
    table.add_column("Failed")
    table.add_column("Awaiting validation")

    total = len(results)
    passed = sum(1 for r in results if r["final_status"] == "passed")
    failed = sum(1 for r in results if r["final_status"] == "failed")
    awaiting = sum(1 for r in results if r["final_status"] == "awaiting_validation")

    table.add_row(str(total), str(passed), str(failed), str(awaiting))
    console.print(table)


def run_request_command(args: argparse.Namespace) -> int:
    # Printed via plain print(), not console.print(): rich word-wraps text to the
    # detected console width, which breaks this fixed-width ASCII art mid-line.
    print(BANNER)

    try:
        environment = load_environment(args.environment)
    except ThomasFileError as exc:
        console.print(f"[red]Invalid environment file:[/red] {exc}")
        return 1

    variables: dict = {}
    variables_path = args.variables or (Path("config/variables.json") if Path("config/variables.json").exists() else None)
    if variables_path is not None:
        try:
            variables = load_variables(variables_path)
        except ThomasFileError as exc:
            console.print(f"[red]Invalid variables file:[/red] {exc}")
            return 1

    scenarios_path = args.folder or args.scenario
    try:
        scenarios = load_scenarios(scenarios_path)
    except ThomasFileError as exc:
        console.print(f"[red]Invalid scenario file(s):[/red] {exc}")
        return 1

    undefined: list[tuple[str, str]] = []
    for scenario in scenarios:
        for name in find_undefined_references(scenario.document.get("payload"), variables):
            undefined.append((scenario.scenario_file, name))
        for name in find_undefined_references(scenario.document.get("endpoint", {}).get("path"), variables):
            undefined.append((scenario.scenario_file, name))
    if undefined:
        details = "; ".join(f"{scenario}: undefined variable '{name}'" for scenario, name in undefined)
        console.print(f"[red]Undefined variable reference(s):[/red] {details}")
        return 1

    secrets = _collect_credential_values(environment)
    _configure_logging(args.log_file, secrets)

    with Progress(console=console) as progress:
        task = progress.add_task("Dispatching scenarios...", total=len(scenarios))

        def on_progress(scenario, result):
            progress.advance(task)

        output_path = run_request(
            environment=environment,
            scenarios=scenarios,
            variables=variables,
            output_dir=args.output,
            progress_callback=on_progress,
        )

    import json

    record = json.loads(output_path.read_text())
    _print_summary(record["results"])
    console.print(f"Execution record written to [bold]{output_path}[/bold]")
    return 0


def _print_validate_summary(new_rounds: list[dict]) -> None:
    table = Table(title="thomas validate summary")
    table.add_column("Validations passed")
    table.add_column("Validations failed")
    table.add_column("Technical errors")

    passed = 0
    failed = 0
    technical_errors = 0
    for round_entry in new_rounds:
        for result in round_entry["results"]:
            if result["technical_error"] is not None:
                technical_errors += 1
            elif result["passed"]:
                passed += 1
            else:
                failed += 1

    table.add_row(str(passed), str(failed), str(technical_errors))
    console.print(table)


def _validate_scenario_files_exist(execution_record: dict) -> tuple[bool, str | None]:
    """Check if all scenarios referenced in the execution record exist.

    Returns (success: bool, error_message: str | None).
    """
    from thomas.core.loading import _find_project_root

    project_root = _find_project_root()
    for scenario_result in execution_record["results"]:
        scenario_file_str = scenario_result["scenario_file"]
        scenario_path = project_root / scenario_file_str
        if not scenario_path.exists():
            error_msg = f"Scenario file not found: [bold]{scenario_file_str}[/bold]"
            return False, error_msg
    return True, None


def run_validate_command(args: argparse.Namespace) -> int:
    import json

    try:
        execution_record = load_and_validate(args.execution, "execution_v1.json")
    except ThomasFileError as exc:
        console.print(f"[red]Invalid execution record file:[/red] {exc}")
        return 1

    try:
        environment = load_environment(args.environment)
    except ThomasFileError as exc:
        console.print(f"[red]Invalid environment file:[/red] {exc}")
        return 1

    scenarios_ok, scenario_error = _validate_scenario_files_exist(execution_record)
    if not scenarios_ok:
        console.print(f"[red]{scenario_error}[/red]")
        return 1

    missing_connectors = check_missing_connectors(execution_record, environment)
    if missing_connectors:
        details = "; ".join(f"{connector}: required by scenario '{scenario_id}'" for connector, scenario_id in missing_connectors)
        console.print(f"[red]Missing connector(s):[/red] {details}")
        return 1

    secrets = _collect_credential_values(environment)
    _configure_logging(args.log_file, secrets)

    prior_round_counts = [len(result["validation_rounds"]) for result in execution_record["results"]]

    try:
        updated_record = run_validate(execution_record, environment)
    except ConnectorTechnicalError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        return 1

    args.execution.write_text(json.dumps(updated_record, indent=2))

    new_rounds = [
        result["validation_rounds"][-1]
        for result, prior_count in zip(updated_record["results"], prior_round_counts)
        if len(result["validation_rounds"]) > prior_count
    ]
    _print_validate_summary(new_rounds)
    console.print(f"Execution record updated at [bold]{args.execution}[/bold]")
    return 0


def run_report_command(args: argparse.Namespace) -> int:
    from thomas.report.generator import generate_report_html, write_report

    try:
        execution_record = load_and_validate(args.execution, "execution_v1.json")
    except ThomasFileError as exc:
        console.print(f"[red]Invalid execution record file:[/red] {exc}")
        return 1

    try:
        environment = load_environment(args.environment)
    except ThomasFileError as exc:
        console.print(f"[red]Invalid environment file:[/red] {exc}")
        return 1

    if environment.get("company_logo_path"):
        logo_path = Path(environment["company_logo_path"])
        if not logo_path.is_absolute():
            environment = dict(environment)
            environment["company_logo_path"] = str(args.environment.parent / logo_path)

    execution_file_bytes = args.execution.read_bytes()

    try:
        html = generate_report_html(execution_record, environment, execution_file_bytes)
    except ThomasFileError as exc:
        console.print(f"[red]Invalid company_logo_path:[/red] {exc}")
        return 1

    output_path = write_report(html, args.execution, args.output, datetime.now().astimezone())
    console.print(f"Report written to [bold]{output_path}[/bold]")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return run_init_command(args)
    elif args.command == "request":
        return run_request_command(args)
    elif args.command == "validate":
        return run_validate_command(args)
    elif args.command == "report":
        return run_report_command(args)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
