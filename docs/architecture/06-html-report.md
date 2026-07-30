# Architecture — HTML Report

## Visual reference

Three-view dashboard structure (Dashboard / Ambiente de execução / Timeline),
per `design_system/thomas-relatorio-wireframe-v1.md` and the visual direction
in `design_system/design-intent/project/`. Spec 008 established the data
pipeline and a single-page structure; spec 009 layered design tokens on top
of it; spec 010 restructured the markup into three mutually-exclusive tab
views while reusing spec 008's execution-record parsing/aggregation and
spec 009's CSS custom properties as-is.

## Non-negotiable requirement: single self-contained file

- All CSS and JS embedded inline in the `.html` (no external files).
- The Thomas logo embedded as **inline SVG** (not `<img>` with base64, per
  project decision — allows CSS styling, including color changes in dark
  mode).
- No network calls at viewing time (no external CDN, no charting library —
  the donut chart, mini-cards, Gantt timeline, and latency scatter plot are
  all inline CSS/SVG, computed in Python and handed to the template as
  already-resolved values).

## Bilingual support (English / Portuguese)

- The report language is controlled by the environment file's
  `report_language` field (`"en"` or `"pt"`, default `"en"`).
- All static UI strings (labels, headers, badge text, filter names,
  column headers, section titles) exist in **two string tables** (`en` and
  `pt`) in `src/thomas/report/strings.py`, never hardcoded in the Jinja2
  template. `tests/report/test_strings.py` asserts both tables define the
  exact same key set.
- The template renders using whichever string table matches
  `report_language`; there is no runtime language switcher in the
  generated HTML — the language is fixed at generation time, based on the
  environment configuration used for that `thomas report` run.
- Data values themselves (scenario IDs, feature names, connector names,
  obtained/expected values, error messages coming from drivers) are never
  translated — only the report's own UI chrome is bilingual.

## Three top-level views

The report has **three mutually-exclusive views**, switchable via tabs in
the header banner: **Dashboard** (default), **Ambiente de execução**, and
**Timeline**. Switching tabs is a pure client-side DOM show/hide (each
view is a `.tab-panel`, only one has the `.active` class at a time) — no
server round-trip, no page reload, no stacking of the previous view's
content.

### Header (common to all three views)

- **Top bar**: The Thomas icon + product name + dark-mode toggle.
- **Banner**: company logo (inline SVG, from `environment.company_logo_path`,
  omitted entirely when absent), company name, department name, system
  name, and the report generation timestamp (formatted in the environment's
  `timezone`), followed by the tab navigation.
- The execution file's SHA-256 signature, previously shown directly under
  the header (spec 008), now lives inside the **Ambiente de execução**
  view only (see below).

## Dashboard view (default)

- **Overall status**: `reprovado` (any `failed`) > `aguardando` (any
  `awaiting_validation`, none failed) > `aprovado` (otherwise) — the same
  three-way priority is reused for mini-card status, each scenario detail
  section's own status, and validation-round status, via one shared
  `_worst_of` helper in `generator.py`.
- **Donut chart**: a CSS `conic-gradient` circle (no SVG/library) built
  from pre-computed passed/failed/awaiting percentages, with a legend
  listing each category's count and percentage. A zero-scenario execution
  record renders a single neutral full ring rather than dividing by zero.
- **Mini-cards**: one card per group, grouped by folder ("Pasta") or by
  feature ("Funcionalidade") via a client-side toggle defaulting to
  Funcionalidade. Both groupings are computed eagerly in Python
  (`_build_groups`) so the toggle is a pure show/hide of two parallel,
  fully-rendered card rows and scenario-list trees — never a client-side
  re-grouping from raw data. Every scenario belongs to exactly one folder
  and one feature, so both groupings' totals always sum to the report's
  total scenario count. Clicking a card filters the scenario list to that
  group, scrolls to it, and shows a clearable active-filter indicator.
- **Filters**: status chips (Aprovados/Falhas/Aguardando, multi-select OR
  logic) plus a free-text search box (matches scenario name); chip
  selection, search text, and an active mini-card filter combine with AND
  across filter types.
- **Scenario list**: grouped into collapsible sections by the active
  grouping mode. Each row shows a status icon, the scenario name, a tag
  for the grouping property *not* currently used to group (folder tag
  when grouped by feature, and vice versa), a short time (full timestamp
  on hover), and a duration computed per FR-010's three-way rule:
  request/response round-trip when no validation applies; `—` when
  validation is configured but no round has occurred; time from request to
  the latest validation round's timestamp otherwise.
- **Scenario detail** (four independently collapsible sections, closed by
  default, only one scenario's detail expanded at a time):
  1. **Requisição** — method/path, correlation id, headers (collapsed by
     default), payload as a copyable JSON block.
  2. **Resposta** — status code as a color-coded badge (2xx/3xx/4xx/5xx)
     and body as a copyable JSON block; replaced by a technical-error
     indicator when the scenario's request had no valid response
     (Requisição still renders normally in that case).
  3. **Verificações da API** — table of check id/expected/operator/
     obtained/result, original order preserved (no reordering of
     failures to the top).
  4. **Validação** — omitted entirely when the scenario has no configured
     validation; a pending placeholder when validation is configured but
     no round has occurred yet; a list of independently-collapsible
     rounds (each with its own checks table and aggregated result) once
     at least one round has occurred. These three states are derived
     purely from `final_status` + `validation_rounds` length — no
     scenario-file re-parsing (research.md §2 of spec 010).

## Ambiente de execução view

Independently-present blocks — each is entirely omitted from the rendered
HTML (not just visually collapsed) when its underlying data is absent:

- **Identificação** (always shown): environment name, timezone, report
  language, execution id, Thomas version, start timestamp — fields not
  already shown in the header.
- **API sob teste** (always shown): base URL, timeout, SSL verification
  status, with custom headers in a collapsed-by-default sub-section.
- **Serviços de informação** (omitted when none configured): per service,
  its outcome status, source, collection timestamp, and extracted field
  values, or its error if collection failed.
- **Conectores** (omitted when none configured): name and type per
  connector (the environment's `connectors` field is a name-keyed object,
  each value requiring only `type` plus arbitrary connector-specific
  fields), with an on-demand "ver detalhes" panel rendering the full
  config generically as flattened key/value rows — no per-connector-type
  layout.
- **Variáveis preparatórias** (omitted when none present): a key/value
  table sourced from the execution record's `prepared_variables` field
  (see below).
- **Assinatura do relatório**: the SHA-256 signature (moved here from the
  spec-008 header) with a copy-to-clipboard action.

### Secret masking

Any key/value pair — connector config field at any nesting depth, or a
prepared variable — whose key case-insensitively contains `KEY`, `TOKEN`,
`SECRET`, or `PASSWORD` is masked by default (`••••••••••`) with an
on-demand reveal control. The real value is still present in the HTML
source (in a `data-real-value` attribute) so the reveal toggle works
without a server round-trip — this is a UI/at-a-glance safeguard, not
encryption; the report's self-contained, single-file design means anyone
with the file already has the raw execution/environment data.

### `prepared_variables` (execution record, additive field)

`execution_v1.json` carries an optional `prepared_variables` object —
the resolved `variables` dict `thomas request` held in memory at dispatch
time, written verbatim (raw values; masking happens at report-render
time, not at write time). Omitted entirely when `thomas request` ran with
no variables file. No `schema_version` bump (additive/optional field,
same precedent as `environment_v1.json`'s `company_logo_path`).
`thomas validate` round-trips the field unchanged, same as every other
top-level field it doesn't touch.

## Timeline view

- **Gantt visualization** (default): one row per scenario, with request,
  response, and validation-round markers positioned proportionally along
  a real time axis spanning all events in the record (not just that
  scenario's own). Each validation-round marker is colored by that
  round's own outcome; a badge at the row's end shows the scenario's
  final aggregated status. When every event in the record shares the same
  timestamp, all markers render at the 50% position rather than dividing
  by zero.
- **Log visualization** (toggle): a single chronological list of every
  event across all scenarios — request, response, validation round, and
  service-collection events — interleaved by timestamp.
- Clicking a scenario's row (either visualization) expands a local,
  timestamped event log for just that scenario.
- **Latency section**: summary statistics (average, P95, maximum request
  latency in ms) and an inline SVG scatter plot — X axis is real request
  time, Y axis is latency, points colored/grouped by endpoint path with a
  legend. Scenarios with a technical error (no valid response) are
  excluded, since there is no latency to measure. When no scenario has a
  measurable latency, an empty-state message is shown instead of a
  degenerate chart.

## Technical generation

- Template engine: **Jinja2**, one `template.html.j2` file in
  `src/thomas/report/`, rendered with a fully-resolved context (no data
  fetched or aggregated at template-render time — all business logic
  lives in `generator.py`, per Principle I/III: `_worst_of` and
  `_build_groups` are shared helpers reused across every status/grouping
  computation in the report).
- Output path: `reports/<execution_stem>_<timestamp>.html`.
- The company logo file (path from `environment.company_logo_path`, when
  present) is read from disk and inlined the same way as the Thomas logo.
- The SHA-256 digest of the `--execution` file is computed once during
  report generation (reading the file's raw bytes) and passed to the
  template as a plain resolved value, rendered inside the Ambiente de
  execução view.
- `thomas report --execution <file> --environment <file> [--output <dir>]`
  remains the only interface — no new CLI argument was introduced for
  `prepared_variables` or any other spec-010 data need.
