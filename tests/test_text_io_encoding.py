"""Guard: every text I/O call in src/ and tests/ names its encoding (spec 020, FR-009, SC-005).

Complements ruff PLW1514, which only flags receivers it can infer as
pathlib.Path or builtin open (see research.md R6).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNED_DIRS = ("src", "tests")
_PATH_TEXT_METHODS = {"read_text", "write_text"}
_SUBPROCESS_TEXT_FUNCS = {"run", "Popen", "check_output", "check_call"}
_TEXT_FLAGS = {"text", "universal_newlines"}


def _keywords(call: ast.Call) -> dict[str, ast.expr]:
    return {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}


def _is_true(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_text_mode(call: ast.Call) -> bool:
    """True when the open mode is missing or is a string literal without "b"."""
    mode = _keywords(call).get("mode")
    if mode is None and len(call.args) >= 2:
        mode = call.args[1]
    if mode is None:
        return True
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and "b" not in mode.value


def _violation(call: ast.Call) -> str | None:
    keywords = _keywords(call)
    if "encoding" in keywords:
        return None
    func = call.func

    if isinstance(func, ast.Attribute) and func.attr in _PATH_TEXT_METHODS:
        return f".{func.attr}() without encoding="

    is_builtin_open = isinstance(func, ast.Name) and func.id == "open"
    is_method_open = isinstance(func, ast.Attribute) and func.attr == "open"
    if (is_builtin_open or is_method_open) and _is_text_mode(call):
        return "text-mode open() without encoding="

    if (
        isinstance(func, ast.Attribute)
        and func.attr in _SUBPROCESS_TEXT_FUNCS
        and isinstance(func.value, ast.Name)
        and func.value.id == "subprocess"
        and any(_is_true(keywords[flag]) for flag in _TEXT_FLAGS if flag in keywords)
    ):
        return f"subprocess.{func.attr}(text=True) without encoding="

    is_file_handler = (isinstance(func, ast.Name) and func.id == "FileHandler") or (
        isinstance(func, ast.Attribute) and func.attr == "FileHandler"
    )
    if is_file_handler:
        return "logging.FileHandler() without encoding="

    return None


def find_violations(source: str) -> list[tuple[int, str]]:
    return sorted(
        (node.lineno, reason)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and (reason := _violation(node)) is not None
    )


def test_no_text_io_without_explicit_encoding():
    violations = []
    for directory in SCANNED_DIRS:
        for path in sorted((REPO_ROOT / directory).rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            relative = path.relative_to(REPO_ROOT).as_posix()
            violations.extend(f"{relative}:{line}: {reason}" for line, reason in find_violations(source))

    assert not violations, "Text I/O without an explicit encoding:\n" + "\n".join(violations)


@pytest.mark.parametrize(
    "snippet",
    [
        "p.read_text()",
        "p.write_text(s)",
        "open(f)",
        'open(f, "w")',
        'p.open("r")',
        "subprocess.run(c, text=True)",
        "subprocess.check_output(c, universal_newlines=True)",
        "logging.FileHandler(f)",
    ],
)
def test_guard_flags_unencoded_text_io(snippet):
    assert find_violations(snippet)


@pytest.mark.parametrize(
    "snippet",
    [
        'p.read_text(encoding="utf-8")',
        'p.write_text(s, encoding="utf-8", newline="\\n")',
        'open(f, "rb")',
        'p.open(mode="wb")',
        'open(f, encoding="utf-8")',
        "p.read_bytes()",
        "subprocess.run(c, capture_output=True)",
        'subprocess.run(c, text=True, encoding="utf-8")',
        'logging.FileHandler(f, encoding="utf-8")',
    ],
)
def test_guard_accepts_encoded_or_binary_io(snippet):
    assert not find_violations(snippet)
