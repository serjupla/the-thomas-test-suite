"""Unit tests for thomas init with custom destination (US2)."""

import tempfile
from pathlib import Path

import pytest

from thomas.scaffold.errors import InvalidArgumentError
from thomas.scaffold.scaffolder import scaffold_project


class TestInitCustomDestination:
    """Test init with custom destination argument."""

    def test_scaffold_with_absolute_path(self):
        """Test scaffolding in custom absolute path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "my-project"
            result = scaffold_project(destination=dest)

            # Directory should be created
            assert dest.exists()
            # Files should exist
            assert (dest / "scenarios").exists()
            assert (dest / "README").exists()
            assert result.success

    def test_scaffold_with_relative_path(self):
        """Test scaffolding in custom relative path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            # Change to tmpdir
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                dest = Path("my-relative-project")
                result = scaffold_project(destination=dest)

                # Directory should be created
                assert dest.exists()
                # Files should exist
                assert (dest / "scenarios").exists()
                assert result.success
            finally:
                os.chdir(old_cwd)

    def test_scaffold_with_none_uses_cwd(self):
        """Test that None destination uses current working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = scaffold_project(destination=None)

                # Files should exist in current directory
                cwd = Path.cwd()
                assert (cwd / "scenarios").exists()
                assert (cwd / "README").exists()
                assert result.success
            finally:
                os.chdir(old_cwd)

    def test_scaffold_rejects_file_path(self):
        """Test that scaffolding rejects path to an existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "file.txt"
            file_path.touch()  # Create a file

            with pytest.raises(InvalidArgumentError):
                scaffold_project(destination=file_path)

    def test_scaffold_creates_nested_directories(self):
        """Test that scaffolding creates nested destination directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "deep" / "nested" / "project"
            result = scaffold_project(destination=dest)

            # All nested directories should be created
            assert dest.exists()
            assert (dest / "scenarios").exists()
            assert result.success

    def test_scaffold_path_resolution(self):
        """Test that destination path is properly resolved to absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "project"
            result = scaffold_project(destination=dest)

            # Result destination should be absolute
            assert result.destination.is_absolute()
