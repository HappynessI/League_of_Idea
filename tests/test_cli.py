from typer.testing import CliRunner

from league_of_idea.cli import app
from league_of_idea.models import Session
from league_of_idea.storage import save_session
from league_of_idea.workspace_models import SearchHit


runner = CliRunner()


def test_estimate_uses_cost_safe_default():
    result = runner.invoke(app, ["estimate"])

    assert result.exit_code == 0
    assert "20" in result.stdout


def test_estimate_reports_invalid_input_without_traceback():
    result = runner.invoke(app, ["estimate", "--num-ideas", "1"])

    assert result.exit_code == 1
    assert "at least 2" in result.stdout


def test_report_command_exports_stored_session(tmp_path):
    sessions_dir = tmp_path / "sessions"
    output = tmp_path / "report.md"
    session = Session(
        goal="goal",
        num_ideas=2,
        rounds=1,
        judge_model="openai:judge",
        generator_model="openai:generator",
    )
    save_session(session, sessions_dir)

    result = runner.invoke(
        app,
        [
            "report",
            "--session",
            session.id,
            "--sessions-dir",
            str(sessions_dir),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.exists()
    assert session.id in output.read_text(encoding="utf-8")


def test_project_init_requires_and_saves_research_brief(tmp_path):
    projects_dir = tmp_path / "projects"
    result = runner.invoke(
        app,
        [
            "project", "init",
            "--title", "Agent reliability",
            "--direction", "Study failure prediction for agents",
            "--keyword", "agents",
            "--keyword", "reliability",
            "--constraint", "compute:one GPU",
            "--projects-dir", str(projects_dir),
        ],
    )
    assert result.exit_code == 0
    files = list(projects_dir.glob("*.json"))
    assert len(files) == 1
    assert "one GPU" in files[0].read_text(encoding="utf-8")


def test_project_init_rejects_too_few_keywords(tmp_path):
    result = runner.invoke(
        app,
        [
            "project", "init",
            "--title", "Project",
            "--direction", "Direction",
            "--keyword", "only-one",
            "--projects-dir", str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "Project creation failed" in result.stdout


def test_paper_search_persists_metadata_only(monkeypatch, tmp_path):
    projects_dir = tmp_path / "projects"
    created = runner.invoke(
        app,
        [
            "project", "init", "--title", "Search project", "--direction", "Agents",
            "--keyword", "agents", "--keyword", "retrieval", "--projects-dir", str(projects_dir),
        ],
    )
    assert created.exit_code == 0
    project_id = next(projects_dir.glob("*.json")).stem
    monkeypatch.setattr(
        "league_of_idea.workspace_cli.connectors.search",
        lambda *args, **kwargs: [SearchHit(source="arxiv", external_id="123", title="A paper", year=2024)],
    )
    result = runner.invoke(
        app,
        ["paper", "search", "agents", "--project", project_id, "--source", "arxiv", "--projects-dir", str(projects_dir)],
    )
    assert result.exit_code == 0
    assert "metadata only" in result.stdout
    listed = runner.invoke(app, ["paper", "results", "--project", project_id, "--projects-dir", str(projects_dir)])
    assert listed.exit_code == 0
    assert "A paper" in listed.stdout
