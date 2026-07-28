"""Core scaffolding logic for Thomas project initialization."""

from dataclasses import dataclass
from pathlib import Path

from .fileops import FileStatusTracker, copy_template, create_directory_safe
from .loader import load_template
from .validator import ensure_destination_exists, validate_destination_path


@dataclass
class ScaffoldResult:
    """Result of a scaffold operation."""

    destination: Path
    created: list
    skipped: list
    overwritten: list
    protected: list

    @property
    def success(self) -> bool:
        return True  # Always success if we get here (exit 0)

    @property
    def total_files(self) -> int:
        return len(self.created) + len(self.skipped) + len(self.overwritten) + len(self.protected)


def scaffold_project(destination: Path = None, force: bool = False) -> ScaffoldResult:
    """
    Create a complete Thomas project scaffold at destination.

    Args:
        destination: Target directory (default: current working directory)
        force: If True, overwrite template files (but never scenarios/)

    Returns:
        ScaffoldResult with status of each file/directory

    Raises:
        ScaffoldError: If validation fails or scaffolding encounters errors
    """
    if destination is None:
        destination = Path.cwd()
    else:
        destination = Path(destination)

    # Validate destination before proceeding
    validate_destination_path(destination)

    # Ensure destination exists (creates if needed)
    destination = ensure_destination_exists(destination)

    # Track file operations
    tracker = FileStatusTracker()

    # List of templates to create
    # Format: (template_path, dest_relative_path, is_executable, is_protected)
    templates = [
        # Directories (empty)
        (None, "scenarios", False, True),  # Protected user directory
        (None, "config", False, False),
        (None, "config/environments", False, False),
        (None, "examples", False, False),
        (None, "examples/config", False, False),
        (None, "examples/config/environments", False, False),
        (None, "examples/scenarios", False, False),
        (None, "examples/scenarios/generic_example", False, False),
        # Template files (root config)
        ("config/environments/example.json.dist", "config/environments/example.json.dist", False, False),
        ("config/variables.example.json", "config/variables.example.json", False, False),
        (".gitignore.dist", ".gitignore", False, False),
        ("README.dist", "README", False, False),
        # Example files
        ("examples/mock_server.py", "examples/mock_server.py", True, False),  # Executable
        ("examples/config/environments/example.json", "examples/config/environments/example.json", False, False),
        ("examples/config/variables.example.json", "examples/config/variables.example.json", False, False),
        ("examples/scenarios/generic_example/billing.json", "examples/scenarios/generic_example/billing.json", False, False),
        ("examples/scenarios/generic_example/valid_transfers.json", "examples/scenarios/generic_example/valid_transfers.json", False, False),
        ("examples/scenarios/generic_example/invalid_transfers.json", "examples/scenarios/generic_example/invalid_transfers.json", False, False),
    ]

    for template_name, dest_rel, executable, protected in templates:
        dest_path = destination / dest_rel

        if template_name is None:
            # This is a directory
            if dest_path.exists():
                if protected:
                    tracker.report_protected(dest_path)
                else:
                    tracker.report_skipped(dest_path)
            else:
                create_directory_safe(dest_path)
                tracker.report_created(dest_path)
        else:
            # This is a file
            if dest_path.exists():
                if protected:
                    tracker.report_protected(dest_path)
                elif force:
                    # Load template and copy
                    template_content = load_template(template_name)
                    copy_template(template_content, dest_path, executable=executable)
                    tracker.report_overwritten(dest_path)
                else:
                    tracker.report_skipped(dest_path)
            else:
                # Load template and copy
                template_content = load_template(template_name)
                copy_template(template_content, dest_path, executable=executable)
                tracker.report_created(dest_path)

    summary = tracker.get_summary()
    return ScaffoldResult(
        destination=destination,
        created=summary["created"],
        skipped=summary["skipped"],
        overwritten=summary["overwritten"],
        protected=summary["protected"],
    )
