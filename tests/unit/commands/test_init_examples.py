"""Unit tests for thomas init examples (US3)."""

import json
import tempfile
from pathlib import Path

from thomas.scaffold.scaffolder import scaffold_project


class TestInitExamples:
    """Test example project files created by init."""

    def test_scaffold_does_not_create_mock_server(self):
        """Test that no local mock server is scaffolded anymore."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            assert not (dest / "examples" / "mock_server.py").exists()

    def test_scaffold_creates_example_config(self):
        """Test that example environment config points to a real public API."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            example_env = dest / "examples/config/environments/example.json"
            assert example_env.exists()

            data = json.loads(example_env.read_text())
            assert data["schema_version"] == 1
            assert data["api"]["base_url"] == "https://jsonplaceholder.typicode.com"
            assert data["connectors"]["fake_ledger"]["type"] == "fake"

    def test_scaffold_creates_example_scenarios(self):
        """Test that example scenarios are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            scenarios_dir = dest / "examples/scenarios/quickstart"
            assert (scenarios_dir / "01_read_existing_post.json").exists()
            assert (scenarios_dir / "02_create_new_post.json").exists()
            assert (scenarios_dir / "03_create_and_confirm_order.json").exists()

    def test_scaffold_example_scenarios_valid_json(self):
        """Test that all example scenarios are valid JSON against the current scenario schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            scenarios_dir = dest / "examples/scenarios/quickstart"

            for scenario_file in scenarios_dir.glob("*.json"):
                data = json.loads(scenario_file.read_text())
                assert data["schema_version"] == 1
                assert "feature" in data
                assert "scenario_id" in data
                assert "endpoint" in data
                assert "api_checks" in data

    def test_scaffold_example_scenarios_cover_three_capabilities(self):
        """Test that the 3 example scenarios demonstrate read, write, and delayed validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            scenarios_dir = dest / "examples/scenarios/quickstart"

            read_scenario = json.loads((scenarios_dir / "01_read_existing_post.json").read_text())
            write_scenario = json.loads((scenarios_dir / "02_create_new_post.json").read_text())
            validated_scenario = json.loads((scenarios_dir / "03_create_and_confirm_order.json").read_text())

            assert read_scenario["endpoint"]["method"] == "GET"
            assert "validations" not in read_scenario

            assert write_scenario["endpoint"]["method"] == "POST"
            assert "validations" not in write_scenario

            assert validated_scenario["correlation"]["source"] == "api_response"
            assert len(validated_scenario["validations"]) > 0

    def test_scaffold_example_variables(self):
        """Test that example variables are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            scaffold_project(destination=dest)

            vars_file = dest / "examples/config/variables.example.json"
            assert vars_file.exists()

            data = json.loads(vars_file.read_text())
            assert data["schema_version"] == 1
            assert "variables" in data
            assert "post_title" in data["variables"]
