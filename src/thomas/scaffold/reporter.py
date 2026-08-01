"""Output formatting for scaffold initialization."""

from rich.console import Console
from rich.table import Table

from .scaffolder import ScaffoldResult


def print_scaffold_result(result: ScaffoldResult, banner: str = "") -> None:
    """
    Print formatted scaffold result with BANNER, status table, and next steps.

    Args:
        result: ScaffoldResult from scaffold_project()
        banner: Banner text to print (from thomas.cli.BANNER)
    """
    console = Console()

    # Print banner if provided
    if banner:
        console.print(banner)

    # Print destination info
    console.print(f"\nScaffolding Thomas project at: {result.destination.resolve()}\n")

    # Build and print status table
    table = Table(title="Scaffold Status", show_header=True, header_style="bold")
    table.add_column("File/Directory", style="cyan")
    table.add_column("Status", style="magenta")

    # Add all files to table
    for file_path in result.created:
        table.add_row(file_path, "[green]Created[/green]")

    for file_path in result.skipped:
        table.add_row(file_path, "[yellow]Skipped[/yellow]")

    for file_path in result.overwritten:
        table.add_row(file_path, "[cyan]Overwritten[/cyan]")

    for file_path in result.protected:
        table.add_row(file_path, "[red]Skipped (protected)[/red]")

    console.print(table)

    # Print summary
    console.print(
        f"\n[bold]Summary:[/bold] Created: {len(result.created)} | "
        f"Skipped: {len(result.skipped)} | "
        f"Overwritten: {len(result.overwritten)} | "
        f"Protected: {len(result.protected)}\n"
    )

    # Print next steps
    console.print("[bold]Next steps:[/bold]")
    console.print(
        "  1. thomas request --environment examples/config/environments/example.json \\"
    )
    console.print(
        "                    --folder examples/scenarios \\"
    )
    console.print(
        "                    --variables examples/config/variables.example.json \\"
    )
    console.print(
        '                    --title "Thomas Quickstart"'
    )
    console.print(
        "     (uses a real public API, no local server needed — "
        "note the execution record path it prints)"
    )
    console.print(
        "  2. thomas validate --execution executions/<execution-record-from-step-1>.json \\"
    )
    console.print(
        "                     --environment examples/config/environments/example.json"
    )
    console.print(
        "  3. thomas report --execution executions/<execution-record-from-step-1>.json \\"
    )
    console.print(
        "                   --environment examples/config/environments/example.json"
    )
    console.print()
