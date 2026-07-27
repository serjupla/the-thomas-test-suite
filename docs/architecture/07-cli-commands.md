# Architecture — CLI Commands

## General conventions

- Single entry point: `thomas`, with subcommands.
- Every command accepts `--log-file <path>` (default: `thomas.log` in the
  current directory) and `--verbose` (raises the console log level,
  without affecting the file log level, which is always DEBUG).
- Real-time console progress via `rich` (progress bar while processing
  scenarios; summary table at the end).
- Exit codes: `0` = all scenarios processed without technical error
  (regardless of whether they passed/failed the test itself); `1` =
  technical error prevented completion (e.g. invalid environment, missing
  connector); `2` = invalid command-line arguments.

## `thomas request`

```
thomas request --environment config/environments/staging.json \
                (--folder scenarios/instant_transfer | --scenario scenarios/instant_transfer/x.json) \
                [--variables config/variables.json] \
                [--output executions/]
```

| Option | Required | Description |
|---|---|---|
| `--environment` | Yes | Path to the environment file. |
| `--folder` | One of the two | Recursively scans the folder for `.json` scenarios. |
| `--scenario` | One of the two | Runs a single scenario file. |
| `--variables` | No (default `config/variables.json` if it exists) | Preparatory variables file. |
| `--output` | No (default `executions/`) | Directory where the execution record is written. |

Behavior: validates environment and variables against their schemas;
resolves variables; scans scenarios; queries `/info`; dispatches
sequentially; writes the execution record; prints summary.

## `thomas validate`

```
thomas validate --execution executions/execution_2026-07-25_1430.json \
                 --environment config/environments/staging.json
```

| Option | Required | Description |
|---|---|---|
| `--execution` | Yes | Path to the execution record to validate. |
| `--environment` | Yes | Environment whose connectors will be used (may differ from the one used in `request`). |

Behavior: validates that every required connector exists in the given
environment (fails early if not); for each scenario with non-empty
`validations`, runs the validations, builds a new round, appends it to
the record; recalculates `final_status`; rewrites the same file; prints a
summary of the current round (not the accumulated history).

Can be called repeatedly against the same `--execution` at any time.

## `thomas report`

```
thomas report --execution executions/execution_2026-07-25_1430.json \
               --environment config/environments/staging.json \
               [--output reports/]
```

| Option | Required | Description |
|---|---|---|
| `--execution` | Yes | Execution record from which the report is generated. |
| `--environment` | Yes | Source of `system_name`, `timezone`, and `report_language`. |
| `--output` | No (default `reports/`) | Output directory for the `.html`. |

Can be run as many times as needed, at any point after the first `thomas
request` run — including before any validation has happened (the report
would show everything as `awaiting_validation`).

## File log vs. console

- Console (via `rich`): progress bar "Processing scenario X/N", and at
  the end a compact table (counts by status). Nothing at DEBUG level.
- Log file: every technical detail — full payload, full response,
  executed query, stack trace of technical errors. Always DEBUG level.
  **Never logs credentials**, even at DEBUG.
