"""thomas CLI entry point. See docs/architecture/07-cli-commands.md."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from thomas import __version__
from thomas.core.loading import ThomasFileError, load_environment, load_scenarios, load_variables
from thomas.core.variables import find_undefined_references
from thomas.request.dispatch import run_request

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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thomas")
    subparsers = parser.add_subparsers(dest="command", required=True)
    _build_init_parser(subparsers)
    _build_request_parser(subparsers)
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return run_init_command(args)
    elif args.command == "request":
        return run_request_command(args)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
