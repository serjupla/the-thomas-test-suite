"""Integration tests for thomas init end-to-end (US1 + US2)."""

import tempfile
from pathlib import Path

from thomas.scaffold.scaffolder import scaffold_project


class TestInitE2E:
    """End-to-end init tests."""

    def test_init_creates_complete_project_structure(self):
        """Test that init creates a complete, working project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-project"

            # First run: create project
            result1 = scaffold_project(destination=dest)
            assert result1.success
            assert len(result1.created) > 0
            assert (dest / "scenarios").exists()
            assert (dest / "config/environments/example.json.dist").exists()
            assert (dest / ".gitignore").exists()

    def test_init_is_idempotent(self):
        """Test that running init twice is idempotent (no data loss)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-project"

            # First run: create project
            scaffold_project(destination=dest)

            # Add a user file to scenarios
            user_file = dest / "scenarios" / "my_test.json"
            user_file.write_text('{"feature": "test"}')

            # Second run: init again
            result2 = scaffold_project(destination=dest)

            # Should still succeed with exit 0
            assert result2.success
            # All files should be skipped (already exist)
            assert len(result2.created) == 0
            assert len(result2.skipped) > 0
            # User file should be untouched
            assert user_file.exists()
            assert user_file.read_text() == '{"feature": "test"}'

    def test_init_with_force_refreshes_templates(self):
        """Test that --force overwrites template files but protects scenarios."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-project"

            # First run
            scaffold_project(destination=dest)

            # Modify a template file
            readme = dest / "README"
            readme.write_text("MODIFIED")

            # Second run with force
            result2 = scaffold_project(destination=dest, force=True)

            # README should be overwritten
            assert len(result2.overwritten) > 0
            assert "MODIFIED" not in readme.read_text()

            # Scenarios should still be protected
            assert len(result2.protected) > 0

    def test_init_preserves_user_scenarios(self):
        """Test that user scenarios are never overwritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "test-project"

            # First run
            scaffold_project(destination=dest)

            # Add user scenario
            user_scenario = dest / "scenarios" / "user_test.json"
            user_scenario.write_text('{"scenario": "user"}')

            # Force refresh (should never touch scenarios)
            result = scaffold_project(destination=dest, force=True)

            # scenarios/ should be protected
            assert any("scenarios" in str(p) for p in result.protected)
            # User file should exist
            assert user_scenario.exists()
