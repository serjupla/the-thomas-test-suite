"""Unit tests for thomas init command — basic scaffolding (US1)."""

import json
import tempfile
from pathlib import Path

from thomas.scaffold.scaffolder import scaffold_project


class TestInitBasicScaffolding:
    """Test basic scaffolding in empty directory."""

    def test_scaffold_creates_required_directories(self):
        """Test that scaffolding creates required directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            # Check all required directories exist
            assert (dest / "scenarios").exists()
            assert (dest / "config").exists()
            assert (dest / "config/environments").exists()
            assert (dest / "examples").exists()
            assert (dest / "examples/config").exists()
            assert (dest / "examples/config/environments").exists()
            assert (dest / "examples/scenarios").exists()
            assert (dest / "examples/scenarios/generic_example").exists()

    def test_scaffold_creates_required_files(self):
        """Test that scaffolding creates required template files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            # Check all required files exist
            assert (dest / "config/environments/example.json.dist").exists()
            assert (dest / "config/variables.example.json").exists()
            assert (dest / ".gitignore").exists()
            assert (dest / "README").exists()

    def test_scaffold_creates_valid_json_files(self):
        """Test that all JSON files are valid and have schema_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            # Check environment config
            env_file = dest / "config/environments/example.json.dist"
            env_data = json.loads(env_file.read_text())
            assert env_data["schema_version"] == "1.0"
            assert "api_base_url" in env_data

            # Check variables
            vars_file = dest / "config/variables.example.json"
            vars_data = json.loads(vars_file.read_text())
            assert vars_data["schema_version"] == "1.0"
            assert "variables" in vars_data

    def test_scaffold_result_created_status(self):
        """Test that scaffold result correctly reports created files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            result = scaffold_project(destination=dest)

            # Should have created files and directories
            assert len(result.created) > 0
            assert len(result.skipped) == 0
            assert len(result.overwritten) == 0
            assert result.success

    def test_scaffold_idempotent_first_run(self):
        """Test that init succeeds with exit code 0 on first run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            result = scaffold_project(destination=dest)

            assert result.success
            assert len(result.created) > 0

    def test_scaffold_existing_scenarios_protected(self):
        """Test that existing scenarios/ is never created if already present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)

            # Create scenarios directory first
            scenarios_dir = dest / "scenarios"
            scenarios_dir.mkdir(parents=True)

            # Run scaffold
            result = scaffold_project(destination=dest)

            # scenarios/ should be reported as protected/skipped
            assert scenarios_dir.exists()
            assert len(result.protected) > 0 or "scenarios" in str(result.skipped)

    def test_scaffold_gitignore_content(self):
        """Test that .gitignore contains recommended entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            gitignore = (dest / ".gitignore").read_text()
            # Check for key entries
            assert "config/environments/*.json" in gitignore
            assert "__pycache__" in gitignore
            assert ".venv" in gitignore
