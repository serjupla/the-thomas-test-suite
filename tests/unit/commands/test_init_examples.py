"""Unit tests for thomas init examples (US3)."""

import json
import tempfile
from pathlib import Path

from thomas.scaffold.scaffolder import scaffold_project


class TestInitExamples:
    """Test example project files created by init."""

    def test_scaffold_creates_mock_server(self):
        """Test that mock_server.py is created and is valid Python."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            mock_server = dest / "examples" / "mock_server.py"
            assert mock_server.exists()

            # Check it's valid Python
            import py_compile

            py_compile.compile(str(mock_server), doraise=True)

    def test_scaffold_creates_example_config(self):
        """Test that example environment config points to localhost."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            example_env = dest / "examples/config/environments/example.json"
            assert example_env.exists()

            data = json.loads(example_env.read_text())
            assert data["api_base_url"] == "http://localhost:8000"
            assert data["schema_version"] == "1.0"

    def test_scaffold_creates_example_scenarios(self):
        """Test that example scenarios are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            scenarios_dir = dest / "examples/scenarios/generic_example"
            assert (scenarios_dir / "billing.json").exists()
            assert (scenarios_dir / "valid_transfers.json").exists()
            assert (scenarios_dir / "invalid_transfers.json").exists()

    def test_scaffold_example_scenarios_valid_json(self):
        """Test that all example scenarios are valid JSON with schema_version."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            scenarios_dir = dest / "examples/scenarios/generic_example"

            for scenario_file in scenarios_dir.glob("*.json"):
                data = json.loads(scenario_file.read_text())
                assert data["schema_version"] == "1.0"
                assert "feature" in data
                assert "request" in data
                assert "api_checks" in data

    def test_scaffold_example_variables(self):
        """Test that example variables are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            vars_file = dest / "examples/config/variables.example.json"
            assert vars_file.exists()

            data = json.loads(vars_file.read_text())
            assert data["schema_version"] == "1.0"
            assert "variables" in data
            assert "account_id" in data["variables"]
