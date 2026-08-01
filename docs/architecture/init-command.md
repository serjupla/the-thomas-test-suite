# Architecture: Thomas Init Command

**Status**: Implemented (Feature 005, examples reworked in Feature 011)  
**Version**: 1.1  
**Last Updated**: 2026-07-31

## Overview

The `thomas init` command bootstraps a new Thomas test project without requiring git clone. It creates a complete, idempotent directory structure with user-owned test scenarios, template configurations, ready-to-run examples against a real public API, and documentation.

## Command Interface

```bash
thomas init [DESTINATION] [--force]
```

**Arguments**:
- `DESTINATION` (optional): Project directory path (default: current directory)
- `--force`: Overwrite template files (except `scenarios/` which is always protected)

**Exit Codes**:
- `0`: Success (files created, skipped, or overwritten)
- `1`: Runtime error (permissions, symlink, mount point, path too long, broken installation)
- `2`: Invalid arguments (invalid path syntax)

## Directory Structure Created

```
<destination>/
├── scenarios/                     (user-owned, protected from overwrite)
├── config/
│   └── environments/
│       └── example.json.dist      (template, no credentials)
├── examples/                      (read-only reference)
│   ├── config/
│   │   ├── environments/
│   │   │   └── example.json       (points to a real public API, jsonplaceholder.typicode.com)
│   │   ├── variables.example.json
│   │   └── company-logo.svg       (placeholder logo, referenced by example.json's company_logo_path)
│   └── scenarios/
│       └── quickstart/
│           ├── 01_read_existing_post.json
│           ├── 02_create_new_post.json
│           └── 03_create_and_confirm_order.json
├── .gitignore                     (template, skip/overwrite based on --force)
└── README                         (quickstart instructions)
```

### File Ownership & Mutability

| Path | Ownership | Behavior |
|------|-----------|----------|
| `scenarios/` | User | Never overwritten, even with `--force` |
| `config/` | Template | Skipped if exists; overwritten with `--force` |
| `examples/` | Template | Skipped if exists; overwritten with `--force` |
| `.gitignore` | Template | Skipped if exists; overwritten with `--force` |
| `README` | Template | Skipped if exists; overwritten with `--force` |

**Rationale**: `scenarios/` contains user-created test data and must be immutable to prevent data loss. Template files can be refreshed without affecting user work.

## Implementation Details

### Template Resolution

Templates are stored in the Python package at `src/thomas/scaffold/` and resolved using `importlib.resources.files()`. This ensures templates are available in both:
- **Wheel installations**: Package is installed; templates are bundled
- **Editable installations**: `pip install -e .` symlinks source; templates resolve from `src/`

**Module**: `thomas.scaffold.loader.load_template(template_name: str) -> str`

### Path Validation

Before scaffolding, the destination path is validated:

**Module**: `thomas.scaffold.validator.validate_destination_path(path: Path) -> None`

**Checks**:
1. Not a symlink (`os.path.islink()`)
2. Not a mount point (`os.path.ismount()`)
3. Path length ≤ 260 characters (Windows compatibility)
4. No null bytes or invalid filesystem characters
5. Directory is writable (test file creation)

**Error Handling**: Raises appropriate `ScaffoldError` subclass with exit code mapping:
- `SymlinkError` → exit 1
- `MountPointError` → exit 1
- `PathTooLongError` → exit 1
- `PermissionError` → exit 1
- `BrokenInstallationError` → exit 1
- `InvalidArgumentError` → exit 2

### File Operations

**Module**: `thomas.scaffold.fileops`

- **copy_template()**: Uses `shutil.copy2()` to preserve file metadata (timestamps, permissions)
- **create_directory_safe()**: Idempotent directory creation with `mkdir(parents=True, exist_ok=True)`
- **FileStatusTracker**: Tracks file operation results (Created, Skipped, Overwritten, Skipped Protected)

### Scaffolding Logic

**Module**: `thomas.scaffold.scaffolder.scaffold_project(destination: Path, force: bool) -> ScaffoldResult`

**Algorithm**:
1. Validate destination path
2. Ensure destination directory exists (create if needed)
3. For each template (file or directory):
   - If directory doesn't exist: create
   - If file doesn't exist: load template and copy
   - If file exists and protected (scenarios/): skip with "Skipped (protected)"
   - If file exists and no --force: skip
   - If file exists and --force: overwrite
4. Track all operations (created, skipped, overwritten, protected)
5. Return `ScaffoldResult` with status summary

**Idempotency**: Running `thomas init` multiple times on the same destination:
- First run: Creates all files (exit 0)
- Second run: Skips all existing files (exit 0)
- With --force: Refreshes templates, protects scenarios/ (exit 0)

### Output Formatting

**Module**: `thomas.scaffold.reporter.print_scaffold_result(result, banner)`

Output structure:
1. **BANNER**: Reuses existing BANNER from `thomas.cli`
2. **Destination info**: "Scaffolding Thomas project at: /path/to/destination"
3. **Status table**: Rich table with columns (File/Directory | Status)
   - Created, Skipped, Skipped (protected), Overwritten
4. **Summary**: Count of each status
5. **Next steps**: Copy-paste-ready quickstart commands

### CLI Integration

**Module**: `thomas.commands.init`

- Integrated into `src/thomas/cli.py` as subcommand
- Argparse configuration: `_build_init_parser()`
- Command dispatch in `main()`: `if args.command == "init": run_init_command(args)`
- Exception handling: Converts `ScaffoldError` exceptions to appropriate exit codes

## Example Scenarios

As of Feature 011, the bundled examples run against a real public API
(`https://jsonplaceholder.typicode.com`) instead of a local mock server — no
process to start, no port to open, no second terminal. This removed the
previous `examples/mock_server.py` and the burden of standing up local
infrastructure just to try the tool (see `specs/011-init-quickstart-real-apis/`).

Located in `examples/scenarios/quickstart/`:

1. **01_read_existing_post.json**: `GET /posts/1` — reads data from a public API.
2. **02_create_new_post.json**: `POST /posts` — sends data to a public API and checks it was accepted and echoed back.
3. **03_create_and_confirm_order.json**: `POST /posts`, then a separate `validations` step confirming the result via the `fake` connector (`connectors.fake_ledger` in `examples/config/environments/example.json`) — demonstrates the request/validate split with an immediate, deterministic confirmation (no wait or retry). See `docs/architecture/05-connectors.md` for why the `fake` connector is used here.

Each scenario uses variable substitution (`{{post_title}}`, `{{post_body}}`, `{{user_id}}`) from `examples/config/variables.example.json`. Each scenario's `description` field states which capability it demonstrates.

## Error Handling

All error paths result in:
1. Clear error message printed to stderr
2. Appropriate exit code (1 or 2)
3. No partial scaffolding (either all succeeds or nothing is created)

**Example errors**:

```
Permission denied: cannot write to /root/project. Check directory permissions.
(exit 1)

Symlink not supported as destination: /tmp/link. Use a regular directory.
(exit 1)

Destination path exceeds 260 characters (Windows compatibility limit).
(exit 1)

Scaffold templates not found. Reinstall: pip install --force-reinstall the-thomas-test-suite
(exit 1)
```

## Testing Strategy

**Unit Tests**: Verify individual components
- `test_init_basic.py`: Core scaffolding logic
- `test_init_destination.py`: Destination path handling
- `test_init_examples.py`: Example files validation
- `test_init_gitignore.py`: .gitignore handling

**Integration Tests**: Verify end-to-end behavior
- `test_init_e2e.py`: Complete workflow (create, idempotency, force refresh)
- `test_init_edge_cases.py`: Error conditions (symlinks, permissions, path limits)

**Manual Smoke Tests** (recommended):
```bash
# Create project
thomas init /tmp/test-project

# Verify structure
ls -la /tmp/test-project/

# Run the bundled examples end-to-end (real network call, no local server)
cd /tmp/test-project
thomas request --environment examples/config/environments/example.json \
                --folder examples/scenarios \
                --variables examples/config/variables.example.json \
                --title "Thomas Quickstart"

# Test idempotency
thomas init /tmp/test-project  # Should succeed, all skipped
thomas init /tmp/test-project --force  # Should succeed, templates overwritten
```

## Configuration

**pyproject.toml**:
```toml
[project]
include-package-data = true

[tool.setuptools.package-data]
thomas = [
    "schemas/*.json",
    "scaffold/**/*",
]
```

This ensures scaffold templates are included in wheel distributions and resolved correctly at runtime.

## Future Enhancements

Potential future work (out of scope for v1):
- Interactive mode (`thomas init --interactive`) to customize settings
- Template selection (`thomas init --template=minimal`)
- Additional example connectors (database queries, Kafka, etc.)
- Configuration wizard for environment setup

## References

- **Specification**: `specs/005-thomas-init/spec.md`
- **Data Model**: `specs/005-thomas-init/data-model.md`
- **CLI Contract**: `specs/005-thomas-init/contracts/cli-command.md`
- **Quickstart**: `specs/005-thomas-init/quickstart.md`
