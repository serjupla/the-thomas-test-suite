<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/serjupla/the-thomas-test-suite/main/assets/logo/thomas-logo-dark.svg">
    <img src="https://raw.githubusercontent.com/serjupla/the-thomas-test-suite/main/assets/logo/thomas-logo.svg" alt="The Thomas logo" width="360">
  </picture>
</p>

<p align="center">
  <a href="https://pypi.org/project/the-thomas-test-suite/"><img alt="PyPI version" src="https://img.shields.io/pypi/v/the-thomas-test-suite?cacheSeconds=3600"></a>
  <a href="https://github.com/serjupla/the-thomas-test-suite/actions/workflows/ci.yml"><img alt="Build status" src="https://github.com/serjupla/the-thomas-test-suite/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue.svg"></a>
</p>

# The Thomas Test Suite

The Thomas is a **data-driven API test automation** tool. It fires HTTP
requests from scenarios described entirely in JSON and validates their
side effects across multiple heterogeneous data sources (relational
databases, NoSQL, messaging topics), with native support for asynchronous
processing of indeterminate duration.

What sets The Thomas apart from other API testing frameworks (Karate,
Tavern, Robot Framework) is the simultaneous combination of five
characteristics no single researched tool brings together:

1. **100% declarative JSON scenarios** — no custom DSL syntax, no need to
   write code (Java, Python, or otherwise) per test case.
2. **Data-driven assertions**, configured by data (query + operator +
   expected value), not by code — a non-programmer can edit a scenario.
3. **Multiple heterogeneous data sources** (Oracle, DB2, MongoDB, Kafka)
   under the same declarative interface.
4. **Execution physically decoupled in time** between dispatch and
   validation, as a core design feature — not a workaround.
5. **Low enough barrier to entry** for product and QA teams to use during
   functional acceptance testing, not just developers.

## Installation

```bash
pip install the-thomas-test-suite

# To run `thomas validate` against Oracle:
pip install "the-thomas-test-suite[oracle]"
```

## Quickstart

### Option 1: Bootstrap a new project (recommended for new users)

```bash
pip install the-thomas-test-suite

# Create a new Thomas project in current directory
thomas init

# Start the bundled mock server
cd . && python examples/mock_server.py &

# In another terminal: run the example scenarios
thomas request \
  --environment examples/config/environments/example.json \
  --folder examples/scenarios \
  --variables examples/config/variables.example.json

# Validate side effects in a connected data source (e.g. Oracle)
thomas validate \
  --execution executions/<execution-file>.json \
  --environment examples/config/environments/example.json

# Generate a self-contained, bilingual HTML report
thomas report \
  --execution executions/<execution-file>.json \
  --environment examples/config/environments/example.json \
  --output reports
```

`thomas init` creates a ready-to-use project structure with examples, templates,
and a mock server for learning. No git clone required.

### Option 2: Clone repository and run examples

The example below runs entirely against a local mock HTTP service — no
external infrastructure or credentials required.

```bash
git clone https://github.com/serjupla/the-thomas-test-suite.git
cd the-thomas-test-suite
pip install -e .

# In one terminal: start the fictional mock service
python examples/mock_server.py

# In another terminal: dispatch the example scenarios
thomas request \
  --environment examples/config/environments/example.json \
  --folder examples/scenarios \
  --variables examples/config/variables.example.json
```

## Example Output

You should see a console summary table and an execution record written
under `executions/`. The bundled scenarios demonstrate variable
substitution (`{{variable_name}}`), correlation ID extraction from both
the API response and the request payload, and a scenario left
`awaiting_validation` until `thomas validate` runs against a connected
data source (see the Oracle example scenario under
`examples/scenarios/generic_example/oracle_settlement_confirmation.json`).

![thomas request running against the bundled examples](https://raw.githubusercontent.com/serjupla/the-thomas-test-suite/main/assets/screenshot.png)

## Active development

The Thomas is under active development. `thomas request`, `thomas
validate` (data-source validation), and `thomas report` (self-contained,
bilingual HTML report) are all fully functional, together with a first
real connector (Oracle, via the `thomas[oracle]` extra). Upcoming work
adds further connectors (DB2, MongoDB, Kafka) and multi-environment
refinement. See [docs/ROADMAP.md](docs/ROADMAP.md) for the full feature
roadmap and current status (the roadmap is a process document kept in
Portuguese by the maintainer; feature names and statuses are summarized
here in English).

## Architecture

Normative design documentation — schemas, contracts, CLI commands, and
the validation engine — lives in
[docs/architecture/](docs/architecture/).

## How it compares

| | The Thomas | Karate | Tavern | Zerocode |
|---|---|---|---|---|
| Scenario format | 100% declarative JSON | Gherkin + embedded JS | YAML | JSON |
| Non-programmer editable | Yes | Partial | Partial | Partial |
| Multiple heterogeneous data sources (DB/NoSQL/messaging) as first-class validation | Yes | No | No | No |
| Time-decoupled validation (dispatch now, validate later/repeatedly) | Yes, core feature | No | No | No |
| Requires JVM/Java | No (Python) | Yes | No (Python) | Yes |

## License & Brand

The Thomas Test Suite is licensed under the [Apache License 2.0](LICENSE)
— see [NOTICE](NOTICE) for attribution. The license permits commercial
and free use and requires preservation of copyright/license notices.

**"The Thomas" name and logo are the project's brand**, protected
separately from the code license. Forks are free to use the code under
Apache 2.0, but must not present themselves publicly as "The Thomas" or
reuse its name/logo — see [assets/logo/README.md](assets/logo/README.md)
for the full brand policy.

This project follows [Semantic Versioning](https://semver.org/). See
[CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute.
