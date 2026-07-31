"""Integration tests for thomas init end-to-end (US1 + US2)."""

import json
import tempfile
from pathlib import Path

import responses

from thomas.cli import main
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


def _post_echo_callback(request):
    """Mimics jsonplaceholder.typicode.com/posts: echoes the payload, adds id=101."""
    payload = json.loads(request.body)
    body = {**payload, "id": 101}
    return (201, {"Content-Type": "application/json"}, json.dumps(body))


@responses.activate
def test_generated_quickstart_examples_run_request_validate_report_without_local_server(tmp_path, monkeypatch):
    """US1 + US2: thomas init's generated examples run end-to-end against a mocked
    public API, with no local server involved, and the delayed-validation scenario
    is confirmed immediately in its first validate round."""
    monkeypatch.chdir(tmp_path)
    scaffold_project(destination=tmp_path)

    responses.add(
        responses.GET,
        "https://jsonplaceholder.typicode.com/posts/1",
        json={"id": 1, "userId": 1, "title": "sample", "body": "sample body"},
        status=200,
    )
    responses.add_callback(
        responses.POST,
        "https://jsonplaceholder.typicode.com/posts",
        callback=_post_echo_callback,
    )

    request_exit_code = main([
        "request",
        "--environment", "examples/config/environments/example.json",
        "--folder", "examples/scenarios",
        "--variables", "examples/config/variables.example.json",
    ])
    assert request_exit_code == 0

    execution_files = list((tmp_path / "executions").glob("*.json"))
    assert len(execution_files) == 1
    execution_path = execution_files[0]

    record = json.loads(execution_path.read_text())
    results_by_id = {r["scenario_id"]: r for r in record["results"]}
    assert results_by_id["read_existing_post"]["api_result"] == "passed"
    assert results_by_id["create_new_post"]["api_result"] == "passed"
    assert results_by_id["create_and_confirm_order"]["api_result"] == "passed"
    assert results_by_id["create_and_confirm_order"]["final_status"] == "awaiting_validation"

    validate_exit_code = main([
        "validate",
        "--execution", str(execution_path),
        "--environment", "examples/config/environments/example.json",
    ])
    assert validate_exit_code == 0

    record = json.loads(execution_path.read_text())
    results_by_id = {r["scenario_id"]: r for r in record["results"]}
    validated = results_by_id["create_and_confirm_order"]
    assert len(validated["validation_rounds"]) == 1
    assert validated["validation_rounds"][0]["results"][0]["passed"] is True
    assert validated["final_status"] == "passed"

    report_exit_code = main([
        "report",
        "--execution", str(execution_path),
        "--environment", "examples/config/environments/example.json",
    ])
    assert report_exit_code == 0

    html_files = list((tmp_path / "reports").glob("*.html"))
    assert len(html_files) == 1
    html = html_files[0].read_text()
    assert "order_confirmed" in html
