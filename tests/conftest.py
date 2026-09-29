"""Shared fixtures that simulate Windows conditions on any OS (spec 020, R7)."""

from __future__ import annotations

import builtins
import io
import locale
import pathlib
import sys
from pathlib import Path

import pytest

_SIMULATED_ENCODING = "cp1252"


def write_utf8(path: Path, text: str, bom: bool = False) -> None:
    """Write `text` as UTF-8 bytes (optionally BOM-prefixed), independent of the default encoding."""
    data = text.encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def _default_encoding_open(original_open):
    """Wrap an `open` so text-mode calls with no explicit encoding use the simulated default.

    On Python >= 3.11 the platform default is resolved in C, so patching
    `locale.getpreferredencoding` alone has no effect on `open()` or
    `Path.read_text()`; this wrapper reproduces the Windows behaviour instead.
    """

    def _open(file, mode="r", buffering=-1, encoding=None, *args, **kwargs):
        if "b" not in mode and encoding in (None, "locale"):
            encoding = _SIMULATED_ENCODING
        return original_open(file, mode, buffering, encoding, *args, **kwargs)

    return _open


def apply_cp1252_default_encoding(monkeypatch: pytest.MonkeyPatch, probe_dir: Path) -> None:
    """Make every text I/O call without an explicit encoding use cp1252, as on a Windows machine.

    Usable with `pytest.MonkeyPatch.context()` when a test needs the simulation
    for only part of its body; otherwise use the `cp1252_default_encoding` fixture.
    """
    if sys.flags.utf8_mode:
        pytest.skip("interpreter runs in UTF-8 mode")

    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: _SIMULATED_ENCODING)
    if hasattr(locale, "getencoding"):
        monkeypatch.setattr(locale, "getencoding", lambda: _SIMULATED_ENCODING)

    patched_open = _default_encoding_open(io.open)
    monkeypatch.setattr(builtins, "open", patched_open)
    monkeypatch.setattr(io, "open", patched_open)
    normal_accessor = getattr(pathlib, "_NormalAccessor", None)  # Python 3.10 routes Path.open here
    if normal_accessor is not None:
        monkeypatch.setattr(normal_accessor, "open", staticmethod(patched_open))

    probe = probe_dir / "_cp1252_probe.txt"
    with open(probe, "w", encoding=None) as handle:
        handle.write("á")
    assert probe.read_bytes() == b"\xe1", "cp1252 default-encoding simulation is not active"
    probe.write_text("á", encoding=None)
    assert probe.read_bytes() == b"\xe1", "cp1252 simulation does not reach pathlib"
    probe.unlink()


@pytest.fixture
def cp1252_default_encoding(monkeypatch, tmp_path):
    """Simulate a Windows cp1252 default text encoding for the whole test."""
    apply_cp1252_default_encoding(monkeypatch, tmp_path)


class Cp1252Console:
    """Captured cp1252 stdout/stderr that raise on unencodable characters unless reconfigured."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self.stdout = io.TextIOWrapper(io.BytesIO(), encoding=_SIMULATED_ENCODING, errors="strict")
        self.stderr = io.TextIOWrapper(io.BytesIO(), encoding=_SIMULATED_ENCODING, errors="strict")

    def install(self) -> None:
        """Swap sys.stdout/sys.stderr for the cp1252 streams.

        Call it from the test body: pytest's own capture re-installs its
        sys.stdout between fixture setup and the test call.
        """
        self._monkeypatch.setattr(sys, "stdout", self.stdout)
        self._monkeypatch.setattr(sys, "stderr", self.stderr)

    @staticmethod
    def _read(stream: io.TextIOWrapper) -> str:
        stream.flush()
        return stream.buffer.getvalue().decode(_SIMULATED_ENCODING)

    def out(self) -> str:
        return self._read(self.stdout)

    def err(self) -> str:
        return self._read(self.stderr)


@pytest.fixture
def cp1252_console(monkeypatch):
    """Strict cp1252 stdout/stderr (a legacy Windows console or redirect); call `.install()` in the test."""
    return Cp1252Console(monkeypatch)
