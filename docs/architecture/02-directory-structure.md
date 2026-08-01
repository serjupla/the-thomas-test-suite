# Architecture — Directory Structure

## The Thomas repository structure (The Thomas source code)

```
thomas-test-suite/
├── .specify/
│   └── memory/
│       └── constitution.md           # kept in Portuguese (SDD process document)
├── docs/
│   ├── ROADMAP.md                     # kept in Portuguese (SDD process document)
│   └── architecture/                  # product documentation — English
│       ├── 01-overview.md
│       ├── 02-directory-structure.md
│       ├── 03-data-schemas.md
│       ├── 04-validation-engine-operators.md
│       ├── 05-connectors.md
│       ├── 06-html-report.md
│       ├── 07-cli-commands.md
│       └── init-command.md
├── specs/
│   └── prompts/                       # kept in Portuguese (SDD /specify inputs)
│       └── prompt_*.md
├── src/
│   └── thomas/
│       ├── __init__.py                # exposes __version__
│       ├── cli.py                     # CLI entrypoint (init/request/validate/report)
│       ├── schemas/                   # versioned JSON Schemas
│       │   ├── scenario_v1.json
│       │   ├── environment_v1.json
│       │   ├── variables_v1.json
│       │   └── execution_v1.json
│       ├── core/
│       │   ├── loading.py             # recursive scenario loading, schema validation
│       │   ├── variables.py           # {{variable}} resolution
│       │   ├── correlation.py         # correlation_id resolution
│       │   └── execution_record.py    # execution record read/write
│       ├── operators/
│       │   └── engine.py              # generic comparison engine (equals, greater_than, etc.)
│       ├── connectors/
│       │   ├── __init__.py            # BaseConnector abstract class + dispatch by `type`
│       │   ├── oracle.py
│       │   └── fake.py                # deterministic connector used by examples/tests
│       │       # (db2.py, mongo.py, kafka.py: planned, not yet implemented — see ROADMAP.md F06-F08)
│       ├── request/
│       │   └── dispatch.py            # `thomas request` logic
│       ├── validate/
│       │   ├── preflight.py
│       │   └── orchestrator.py        # `thomas validate` logic
│       ├── commands/
│       │   └── init.py                # `thomas init` logic
│       ├── scaffold/                  # templates/logic backing `thomas init`
│       │   ├── scaffolder.py
│       │   ├── loader.py
│       │   ├── validator.py
│       │   ├── fileops.py
│       │   ├── reporter.py
│       │   ├── README.dist
│       │   └── examples/              # packaged example config/scenarios
│       └── report/
│           ├── generator.py           # `thomas report` logic
│           ├── strings.py             # bilingual (EN/PT) UI strings
│           ├── template.html.j2       # main Jinja2 template (bilingual, EN/PT)
│           └── assets/
│               ├── thomas-icon.svg        # light-mode icon (inline SVG)
│               └── thomas-icon-dark.svg   # dark-mode icon (inline SVG)
├── tests/
│   └── ...                            # mirrors the src/thomas structure
├── pyproject.toml
├── README.md
├── LICENSE
├── NOTICE
└── .gitignore
```

## Expected structure in a The Thomas *adopter's* project (not part of this repo)

A team adopting The Thomas organizes its own test repository like this:

```
my-thomas-tests/
├── scenarios/
│   ├── payments_a/
│   │   ├── valid_transfer.json
│   │   └── invalid_key_transfer.json
│   ├── payments_b/
│   │   └── ...
│   └── billing/
│       └── ...
├── config/
│   ├── environments/
│   │   ├── staging.json               # NOT versioned (.gitignore)
│   │   └── example.json.dist          # versioned, no real credentials
│   └── variables.json                 # may or may not be versioned, team's choice
├── executions/
│   └── execution_2026-07-25_1430.json
└── reports/
    └── report_2026-07-25_1430.html
```

The `scenarios/` folder is organized freely by the user — the folder
hierarchy used here is the same one used for grouping in the report.

## Required `.gitignore` (adopter's repository, not The Thomas itself)

```
config/environments/*.json
!config/environments/*.json.dist
executions/
reports/
```

## File naming convention

| Artifact | Convention |
|---|---|
| Scenario | free, inside `scenarios/`, recommended `snake_case.json`, descriptive |
| Environment file | `config/environments/<environment_name>.json` (e.g. `staging.json`, `dev.json`) |
| Execution record | `executions/execution_<YYYY-MM-DD>_<HHmm>.json` |
| Report | `reports/report_<YYYY-MM-DD>_<HHmm>.html` |
