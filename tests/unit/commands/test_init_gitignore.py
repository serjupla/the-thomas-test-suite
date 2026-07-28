"""Unit tests for .gitignore handling (US4)."""

import tempfile
from pathlib import Path

from thomas.scaffold.scaffolder import scaffold_project


class TestInitGitignore:
    """Test .gitignore handling."""

    def test_scaffold_creates_gitignore_when_missing(self):
        """Test that .gitignore is created when not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            gitignore = dest / ".gitignore"
            assert gitignore.exists()

    def test_scaffold_skips_existing_gitignore_without_force(self):
        """Test that existing .gitignore is skipped without --force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)

            # Create existing .gitignore
            gitignore = dest / ".gitignore"
            gitignore.write_text("CUSTOM")

            # Scaffold without force
            result = scaffold_project(destination=dest, force=False)

            # Should be skipped
            assert "CUSTOM" in gitignore.read_text()  # Not overwritten
            assert len(result.skipped) > 0

    def test_scaffold_overwrites_gitignore_with_force(self):
        """Test that .gitignore is overwritten with --force."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)

            # Create existing .gitignore
            gitignore = dest / ".gitignore"
            gitignore.write_text("CUSTOM")

            # Scaffold with force
            result = scaffold_project(destination=dest, force=True)

            # Should be overwritten
            assert "CUSTOM" not in gitignore.read_text()  # Overwritten
            assert ".gitignore" in str(result.overwritten)

    def test_scaffold_gitignore_has_recommended_entries(self):
        """Test that .gitignore contains recommended entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            gitignore = (dest / ".gitignore").read_text()

            # Check for key entries
            assert "config/environments/*.json" in gitignore
            assert "__pycache__" in gitignore
            assert ".venv" in gitignore
            assert "reports/" in gitignore
            assert ".DS_Store" in gitignore
