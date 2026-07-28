"""Implementation of thomas init command."""

import sys
from pathlib import Path

from thomas.scaffold.errors import InvalidArgumentError, ScaffoldError
from thomas.scaffold.reporter import print_scaffold_result
from thomas.scaffold.scaffolder import scaffold_project


def init_command(args, banner: str = "") -> int:
    """
    Execute thomas init command.

    Args:
        args: Parsed arguments (args.destination, args.force)
        banner: Optional banner text to print

    Returns:
        Exit code (0 on success, 1 on error, 2 on invalid arguments)
    """
    try:
        # Parse destination
        destination = None
        if hasattr(args, "destination") and args.destination:
            destination = Path(args.destination)

        # Get force flag
        force = getattr(args, "force", False)

        # Scaffold the project
        result = scaffold_project(destination=destination, force=force)

        # Print results
        print_scaffold_result(result, banner=banner)

        return 0

    except InvalidArgumentError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2
    except ScaffoldError as e:
        print(f"Error: {e}", file=sys.stderr)
        return e.exit_code
    except OSError as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return 1
