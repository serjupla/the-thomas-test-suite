# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-07-27

### Added

- SSL verification control (F003): granular `ssl_verify` configuration per API 
  and service in environment files, enabling testing against services with 
  self-signed certificates. Fully backward compatible with schema version 1.
- Environment metadata (F003): optional `company_name` and `department_name` 
  fields in environment files for audit trails and future reporting features. 
  Backward compatible, adititive only.
- Custom request headers (F004): support for custom HTTP headers at scenario 
  endpoint level and environment API/services level, with scenario-level 
  precedence and variable resolution (`{{variable_name}}` in header values). 
  Enables authentication headers and application-specific headers per test. 
  Backward compatible with schema version 1.
- Thomas Init scaffolding (F005): `thomas init [destination] [--force]` command 
  to bootstrap a complete, ready-to-use Thomas project without git clone. 
  Includes project structure, example scenarios, mock HTTP server, templates, 
  path validation (symlinks, mount points), scenarios folder protection, 
  idempotent behavior, and clear error messages. Lowers barrier to entry for 
  new users.

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

[0.2.0]: https://github.com/serjupla/the-thomas-test-suite/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/serjupla/the-thomas-test-suite/releases/tag/v0.1.0
