# Architecture — HTML Report

## Visual reference

Inspired by the Karate framework's report (top dashboard with statistic
cards, circular percentage gauge, overall status badge), adapted to
The Thomas-specific concepts: multiple validation rounds over time, grouping
by folder, and the `awaiting_validation` state.

## Non-negotiable requirement: single self-contained file

- All CSS and JS embedded inline in the `.html` (no external files).
- The Thomas logo embedded as **inline SVG** (not `<img>` with base64, per
  project decision — allows CSS styling, including color changes in dark
  mode).
- No network calls at viewing time (no external CDN).

## Bilingual support (English / Portuguese)

- The report language is controlled by the environment file's
  `report_language` field (`"en"` or `"pt"`, default `"en"`).
- All static UI strings (labels, headers, badge text, filter names,
  column headers, section titles) must exist in **two string tables**
  (`en` and `pt`) inside the report generation module (e.g.
  `src/thomas/report/strings.py` or an equivalent structure), never
  hardcoded in the Jinja2 template.
- The template renders using whichever string table matches
  `report_language`; there is no runtime language switcher in the
  generated HTML — the language is fixed at generation time, based on the
  environment configuration used for that `thomas report` run.
- Data values themselves (scenario IDs, feature names, connector names,
  obtained/expected values, error messages coming from drivers) are never
  translated — only the report's own UI chrome is bilingual.
- Adding a third language in the future should only require adding a new
  string table, without changing the template structure — the template
  must reference string keys (e.g. `strings.passed_label`), never
  literal English or Portuguese text directly.

## Header structure

- The Thomas logo (inline SVG) + report title (translated: "The Thomas Test
  Report" / "Relatório de Teste The Thomas").
- System under test name (`system_name` from the environment).
- Environment name used (`environment_name`).
- Report generation timestamp, formatted in the environment's `timezone`.
- "Timeline" tab/link: chronological view of every recorded event (each
  scenario's dispatch + each scenario's validation round), ordered by
  timestamp — useful for audit purposes, given that days may pass between
  rounds.
- Dark mode toggle (client-side, no server dependency).

## Overall status block

- **Badge**: combinable, not binary —
  - `ALL PASSED` (green) if there is no `failed` nor `awaiting_validation`.
  - `X FAILED` (red) if there is at least one `failed`.
  - `Y AWAITING VALIDATION` (amber) if there is no `failed`, but there is
    pending `awaiting_validation`.
  - Can combine `X FAILED · Y AWAITING VALIDATION` simultaneously.
- **Circular percentage gauge**:
  `passed / (passed + failed) * 100`. Scenarios in `awaiting_validation`
  are **excluded** from the denominator (they are neither a pass nor a
  fail yet).

## Statistic cards

| Card | Calculation |
|---|---|
| Features | count of distinct `feature` values among the report's scenarios |
| Scenarios | total scenarios in the execution record |
| Passed | count of `final_status == "passed"` |
| Failed | count of `final_status == "failed"` |
| Awaiting validation | count of `final_status == "awaiting_validation"` |
| Validation rounds | sum of `len(validation_rounds)` across all scenarios (indicates reprocessing volume) |
| Duration | time between `start_timestamp` and the most recent timestamp among all recorded rounds |

## Filters

- Filter chips by **folder** (derived from the relative path of
  `scenario_file`).
- Filter chips by **feature**.
- Combinable filters, applied client-side via plain JS (no framework).

## Summary table (level 1)

Grouped by folder, mirroring the `scenarios/` hierarchy. Each group is a
collapsible section, with a header showing how many
passed/failed/awaiting in that folder. Each row: `scenario_id`,
`feature`, `final_status`, request timestamp, timestamp of the latest
validation round (if any).

## Per-scenario detail (level 2)

When expanding a row:

- Request payload sent and response received.
- Result of each `api_check` (expected/obtained/operator/passed).
- **Timeline of validation rounds**: chronological list with each round's
  timestamp and that round's specific result, visually highlighting the
  most recent round as the one determining `final_status`.

## Per-round detail (level 3)

Within each round, a table with each individual validation: `id`,
connector used, operator, expected value, obtained value, result
(passed/failed/technical error — visually distinct: assertion failure in
red, technical error in orange/gray showing the error text).

## Technical generation

- Template engine: **Jinja2**.
- A single `template.html.j2` file in the package
  (`src/thomas/report/`), read, rendered with the aggregated data from
  the execution record + environment data + the selected language string
  table, and written to `reports/report_<timestamp>.html`.
- No data is fetched at render time — all content must already be
  resolved from the execution record and environment file before calling
  the template.
