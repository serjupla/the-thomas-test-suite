# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-07-27

### Added

- Core engine (F00): versioned JSON schemas (scenario, environment,
  variables, execution record), recursive scenario loading, preparatory
  variable resolution (`{{variable_name}}`), correlation ID resolution
  (from API response or request payload), and the `thomas request`
  command — dispatches scenario requests, polls `/info` endpoints,
  evaluates `api_checks`, and writes an append-only execution record.
- Generic comparison/operators engine shared by API checks and future
  data-source validations.
- Public release (F01): Apache 2.0 `LICENSE` and `NOTICE`, `CONTRIBUTING.md`,
  `CODE_OF_CONDUCT.md`, `SECURITY.md`, GitHub CI workflow (lint + test),
  issue/PR templates, brand assets (`assets/logo/`), and a runnable
  zero-infrastructure quickstart example (`examples/mock_server.py` plus
  fictional scenarios) documented in `README.md`.
- Initial PyPI packaging under the distribution name
  `the-thomas-test-suite` (CLI command remains `thomas`).

[0.1.0]: https://github.com/serjupla/the-thomas-test-suite/releases/tag/v0.1.0
