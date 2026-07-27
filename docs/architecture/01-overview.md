# Architecture — Overview

## End-to-end flow

```
┌────────────────────┐     ┌───────────────────┐     ┌───────────────────┐
│  1. thomas request  │────▶│  2. thomas validate │────▶│  3. thomas report  │
│                     │     │  (0..N runs)        │     │                   │
└────────────────────┘     └───────────────────┘     └───────────────────┘
         │                            │                          │
         ▼                            ▼                          ▼
  executions/execution_   executions/execution_XXX.json   reports/report_XXX.html
  XXX.json (created)        (updated, round appended)        (generated/regenerated)
```

The three commands are independent and can run on different processes,
machines, and moments — the only coupling between them is the execution
record JSON file.

## Step 1 — `thomas request`

1. Reads the environment file (`--environment`) and validates its schema.
2. Reads the preparatory variables file and resolves the values (static
   resolution in v1 — see `03-data-schemas.md`).
3. Recursively scans the given scenarios path (`--folder` or `--scenario`),
   collecting all valid `.json` files.
4. Queries the `info_url` endpoint of each service listed in the environment,
   extracting specified fields (or the entire response if no fields are specified),
   along with the HTTP status code.
5. For each scenario, in the order it was found (sequential in v1):
   - Resolves `{{variables}}` in the payload.
   - Fires the HTTP request as described in `endpoint`.
   - Resolves `correlation_id` (from the response or from the payload,
     per `correlation.source`).
   - Evaluates `api_checks` using the operator engine.
   - Records everything in the scenario's result object.
6. Writes `executions/execution_<timestamp>.json`.
7. Prints a console summary (via `rich`): total scenarios, how many
   passed/failed the API check, how many are awaiting validation.

## Step 2 — `thomas validate`

1. Receives the execution record path (`--execution`).
2. Reads the given environment file (may differ from the one used in
   `request`, as long as the required connectors are present).
3. For each scenario in the record that has non-empty `validations`:
   - For each validation, resolves the connector by name, executes the
     query (query/topic depending on type), extracts the field, and
     compares it using the operator engine.
   - Separately captures **assertion failure** (obtained value differs
     from expected) from **technical error** (connection exception,
     timeout, invalid query) — both result in a non-approved validation,
     but are recorded distinguishably.
4. Groups the results of the run into a **new round**, with its own
   timestamp, and **appends** it to the scenario's `validation_rounds`
   list — never replacing previous rounds.
5. Recalculates the scenario's `final_status` based on the latest round.
6. Writes the updated execution record (same path).
7. Console: summary of the current round (how many passed/failed in this
   round specifically).

Can be run as many times as needed against the same file.

## Step 3 — `thomas report`

1. Receives the execution record path.
2. Reads the environment file (for system name, timezone, report
   language, logo).
3. Renders the Jinja2 template with all aggregated data: overall
   statistics, grouping by folder, per-scenario detail, timeline of
   rounds — in the language configured by `report_language`.
4. Writes `reports/report_<timestamp>.html`, self-contained.

Can be run at any time after at least one `request` step, regardless of
whether validation has happened yet.

## Possible scenario states (`final_status`)

| State | Condition |
|---|---|
| `passed` | All `api_checks` passed **and** (there are no `validations` **or** the latest validation round had all validations approved). |
| `failed` | Some `api_check` failed, **or** there are `validations` with at least one round executed and the latest round had some validation rejected/with a technical error. |
| `awaiting_validation` | All `api_checks` passed, `validations` are defined, but no validation round has been executed yet. |

## Actors and usage modes

- **Development team**: integrates `thomas request` and `thomas validate`
  into a CI/CD pipeline, or runs locally during development.
- **Product/QA team**: edits scenario and variable files (plain JSON), runs
  the three commands locally via CLI, opens the HTML report in a browser.

## Project timeline note

Publication of this project (public repository, license, trademark
notice) happens right after Feature F00 (Core) is delivered — see
`docs/ROADMAP.md`. From that point on, every subsequent feature is
developed directly in the public repository, so the hygiene rules in the
constitution (no real third-party data, no real domain names) apply to
every commit from day one, not just at a final "publication" milestone.
