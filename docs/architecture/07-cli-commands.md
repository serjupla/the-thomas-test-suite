# Architecture — CLI Commands

## General conventions

- Single entry point: `thomas`, with subcommands.
- `thomas --version` / `thomas -v`: prints the installed package version
  (read live from installed distribution metadata, never hardcoded) and
  exits, printing nothing else. Short-circuits before any subcommand
  runs, even when combined with one (e.g. `thomas init --version` still
  just prints the version).
- Every command accepts `--log-file <path>` (default: `thomas.log` in the
  current directory) and `--verbose` (raises the console log level,
  without affecting the file log level, which is always DEBUG).
- Real-time console progress via `rich` (progress bar while processing
  scenarios; summary table at the end).
- Exit codes: `0` = all scenarios processed without technical error
  (regardless of whether they passed/failed the test itself); `1` =
  technical error prevented completion (e.g. invalid environment, missing
  connector); `2` = invalid command-line arguments.
- The four process commands (`init`, `request`, `validate`, `report`)
  print an ASCII-art banner — including the live installed version — as
  the first line of output. Standard CLI-convention commands/flags
  (`help`, `--version`/`-v`), whether invoked at the top level or on a
  subcommand (e.g. `thomas validate --help`), never print the banner.

## `thomas request`

```
thomas request --environment config/environments/staging.json \
                (--folder scenarios/instant_transfer | --scenario scenarios/instant_transfer/x.json) \
                [--variables config/variables.json] \
                [--output executions/] \
                [--title "Release 4.2 — Regression Pass"]
```

| Option | Required | Description |
|---|---|---|
| `--environment` | Yes | Path to the environment file. |
| `--folder` | One of the two | Recursively scans the folder for `.json` scenarios. |
| `--scenario` | One of the two | Runs a single scenario file. |
| `--variables` | No (default `config/variables.json` if it exists) | Preparatory variables file. |
| `--output` | No (default `executions/`) | Directory where the execution record is written. |
| `--title` | No (default: none) | Optional short label for this execution, persisted in the execution record's `title` field and rendered in a dedicated section below the report header. Blank/whitespace-only input is treated as if the flag were omitted (no `title` is persisted). |

Behavior: validates environment and variables against their schemas;
resolves variables; scans scenarios; queries `/info`; dispatches
sequentially; writes the execution record; prints summary.

## `thomas validate`

```
thomas validate --execution executions/execution_2026-07-25_1430.json \
                 [--environment config/environments/staging.json]
```

| Option | Required | Description |
|---|---|---|
| `--execution` | Yes | Path to the execution record to validate. |
| `--environment` | No | Environment whose connectors will be used (may differ from the one used in `request`). If omitted, auto-resolved from the execution record's recorded environment name (see below). |

Behavior: validates that every required connector exists in the given
environment (fails early if not); for each scenario with non-empty
`validations`, runs the validations, builds a new round, appends it to
the record; recalculates `final_status`; rewrites the same file; prints a
summary of the current round (not the accumulated history).

Can be called repeatedly against the same `--execution` at any time.

## `thomas report`

```
thomas report --execution executions/execution_2026-07-25_1430.json \
               [--environment config/environments/staging.json] \
               [--output reports/]
```

| Option | Required | Description |
|---|---|---|
| `--execution` | Yes | Execution record from which the report is generated. |
| `--environment` | No | Source of `system_name`, `timezone`, and `report_language`. If omitted, auto-resolved from the execution record's recorded environment name (see below). |
| `--output` | No (default `reports/`) | Output directory for the `.html`. |

Can be run as many times as needed, at any point after the first `thomas
request` run — including before any validation has happened (the report
would show everything as `awaiting_validation`).

On success, `thomas report` has an independent ~40% chance of also
printing a one-line GitHub-star invitation after the "Report written to
..." line. This is stateless — no file, counter, or run history is
created or read to produce it — and it is never shown on a failed run.

## Auto-resolving `--environment` on `validate`/`report`

When `--environment` is omitted on `validate` or `report`, Thomas reads
the `environment` name already recorded in the `--execution` file and
scans `config/environments/*.json` for the one file whose
`environment_name` matches:

- **Exactly one match**: prints `Using environment '<name>' (auto-detected
  from execution file)` and proceeds using that file.
- **Zero or multiple matches**: fails (exit `1`) with a message explaining
  the environment could not be resolved and suggesting `--environment` be
  passed explicitly.

When `--environment` **is** supplied and its `environment_name` differs
from the one recorded in the execution file, Thomas always prints a short
note about the mismatch before proceeding — the explicit value still wins.

## File log vs. console

- Console (via `rich`): progress bar "Processing scenario X/N", and at
  the end a compact table (counts by status). Nothing at DEBUG level.
- Log file: every technical detail — full payload, full response,
  executed query, stack trace of technical errors. Always DEBUG level.
  **Never logs credentials**, even at DEBUG.
