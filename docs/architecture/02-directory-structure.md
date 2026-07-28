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
│       └── 07-cli-commands.md
├── specs/
│   └── prompts/                       # kept in Portuguese (SDD /specify inputs)
│       └── prompt_*.md
├── src/
│   └── thomas/
│       ├── __init__.py
│       ├── cli.py                     # CLI entrypoint (request/validate/report)
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
│       │   ├── base.py                # abstract connector interface
│       │   ├── oracle.py
│       │   ├── db2.py
│       │   ├── mongo.py
│       │   └── kafka.py
│       ├── request/
│       │   └── dispatch.py            # `thomas request` logic
│       ├── validation/
│       │   └── validation_runner.py   # `thomas validate` logic
│       └── report/
│           ├── generation.py          # `thomas report` logic
│           ├── template.html.j2       # main Jinja2 template (bilingual, EN/PT)
│           └── assets/
│               └── logo.svg           # The Thomas logo (provided by the maintainer)
├── tests/
│   └── ...                            # mirrors the src/thomas structure
├── examples/
│   ├── scenarios/
│   │   └── generic_example/           # fictional demo scenarios
│   └── config/
│       ├── environments/
│       │   └── example.json.dist
│       └── variables.example.json
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
