from typer.testing import CliRunner

from league_of_idea.cli import app
from league_of_idea.models import Session
from league_of_idea.storage import save_session


runner = CliRunner()


def test_estimate_uses_cost_safe_default():
    result = runner.invoke(app, ["estimate"])

    assert result.exit_code == 0
    assert "35" in result.stdout


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
