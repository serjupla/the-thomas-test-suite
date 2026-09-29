import re
from importlib import metadata
from pathlib import Path

import thomas
from thomas.cli import BANNER

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _pyproject_version() -> str:
    return re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.MULTILINE).group(1)


def test_version_in_source_checkout_matches_pyproject():
    assert thomas.__version__ == _pyproject_version()


def test_banner_shows_pyproject_version():
    assert f" v.{_pyproject_version()}" in BANNER


def test_falls_back_to_installed_metadata_outside_a_source_checkout(monkeypatch):
    monkeypatch.setattr(thomas, "_source_tree_version", lambda: None)
    monkeypatch.setattr(metadata, "version", lambda name: "9.9.9")
    assert thomas._resolve_version() == "9.9.9"


def test_falls_back_to_unknown_when_not_installed(monkeypatch):
    def _not_found(name):
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(thomas, "_source_tree_version", lambda: None)
    monkeypatch.setattr(metadata, "version", _not_found)
    assert thomas._resolve_version() == "unknown"


def test_source_tree_version_ignores_a_foreign_pyproject(tmp_path, monkeypatch):
    package_dir = tmp_path / "src" / "thomas"
    package_dir.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "someone-else"\nversion = "1.2.3"\n', encoding="utf-8")
    monkeypatch.setattr(thomas, "__file__", str(package_dir / "__init__.py"))
    assert thomas._source_tree_version() is None
