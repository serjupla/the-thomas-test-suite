# Security Policy

## Supported Versions

The Thomas is currently pre-1.0 and under active development. Security
fixes are applied to the latest released version on the `main` branch.

## Reporting a Vulnerability

If you discover a security vulnerability in The Thomas, please report it
privately rather than opening a public issue:

- Preferred: use [GitHub Security Advisories](https://github.com/serjupla/the-thomas-test-suite/security/advisories/new)
  to report privately.
- Alternative: email serjupla@gmail.com with details of the issue.

Please include:

- A description of the vulnerability and its potential impact.
- Steps to reproduce, or a proof-of-concept if available.
- The version/commit you tested against.

We aim to acknowledge reports within a few days. Please do not disclose
the vulnerability publicly until it has been addressed.

## Scope

The Thomas processes JSON scenario/environment/variable files and
dispatches HTTP requests based on their contents. Environment files may
contain connector credentials — these must never be committed to version
control (see `.gitignore`) and are redacted from logs at all levels,
including DEBUG.
