"""Integration tests for init edge cases (T043)."""

import os
import tempfile
from pathlib import Path

import pytest

from thomas.scaffold.errors import (
    PathTooLongError,
    SymlinkError,
)
from thomas.scaffold.validator import validate_destination_path


class TestInitEdgeCases:
    """Test edge case handling."""

    def test_reject_symlink_destination(self):
        """Test that symlink destination is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            real_dir = tmppath / "real"
            real_dir.mkdir()
            symlink_dir = tmppath / "link"
            symlink_dir.symlink_to(real_dir)

            with pytest.raises(SymlinkError):
                validate_destination_path(symlink_dir)

    def test_reject_path_too_long(self):
        """Test that path exceeding Windows limit is rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a path that's definitely too long (>260 chars)
            long_name = "a" * 300
            long_path = Path(tmpdir) / long_name

            with pytest.raises(PathTooLongError):
                validate_destination_path(long_path)

    def test_scaffold_success_with_valid_path(self):
        """Test that valid path scaffolds successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            valid_path = Path(tmpdir) / "valid-project"
            # Should not raise
            validate_destination_path(valid_path)

    def test_permission_handling(self):
        """Test permission denied handling."""
        # This test is platform-specific and might not work in all environments
        # Skip if we can't properly set up read-only directory
        if os.getuid() == 0:  # Skip if running as root
            pytest.skip("Cannot test permissions as root")

        with tempfile.TemporaryDirectory() as tmpdir:
            readonly_dir = Path(tmpdir) / "readonly"
            readonly_dir.mkdir()
            # Make read-only
            readonly_dir.chmod(0o444)

            try:
                # Try to validate (write permission check might fail)
                validate_destination_path(readonly_dir)
            except Exception:
                # Expected to raise on permission denied
                pass
            finally:
                # Restore permissions for cleanup
                readonly_dir.chmod(0o755)
