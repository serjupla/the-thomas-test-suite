# Contributing to The Thomas

Thanks for your interest in contributing! This document describes the
pull request workflow and where to find the project's design principles.

## Source of truth

Design decisions and acceptance criteria for this project are governed by
[`docs/constitution.md`](docs/constitution.md) —
the constitution. If a proposed change conflicts with the constitution,
the constitution wins. When in doubt about whether a design choice fits
The Thomas's philosophy (declarative JSON scenarios, no code per test
case, time-decoupled validation, accessibility to non-programmers), read
the constitution first.

Normative technical documentation — schemas, CLI commands, the
validation engine, connectors — lives in
[`docs/architecture/`](docs/architecture/). Any implementation must
follow what's documented there; if a change requires deviating from it,
update the relevant architecture document in the same pull request.

## Pull request workflow

1. Fork the repository and create a branch off `main`.
2. Make your change. If it affects behavior documented in
   `docs/architecture/`, update those docs in the same PR.
3. Add or update automated tests covering your change (`pytest`).
4. Run linting and tests locally before opening the PR:

   ```bash
   pip install -e ".[dev]"
   ruff check .
   pytest
   ```

5. Open a pull request against `main`, describing what changed and why.
6. The CI workflow (`.github/workflows/ci.yml`) runs lint and tests
   automatically on your PR — it must pass before merge.
7. A maintainer reviews and merges via GitHub's standard PR flow. The
   Thomas does not use a custom approval process.

## Versioning

This project follows [Semantic Versioning](https://semver.org/).

## Contributor License Agreement

No CLA is required today. If external contribution volume grows
significantly in the future, a Contributor License Agreement (CLA) may
be introduced to preserve broader usability of community-contributed
code — this is only a possibility being signaled in advance, not a
current requirement.

## Code of Conduct

By participating in this project, you agree to abide by the
[Code of Conduct](CODE_OF_CONDUCT.md).
