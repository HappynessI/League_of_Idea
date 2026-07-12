from typer.testing import CliRunner

from league_of_idea.cli import app


runner = CliRunner()


def test_estimate_uses_cost_safe_default():
    result = runner.invoke(app, ["estimate"])

    assert result.exit_code == 0
    assert "35" in result.stdout


def test_estimate_reports_invalid_input_without_traceback():
    result = runner.invoke(app, ["estimate", "--num-ideas", "1"])

    assert result.exit_code == 1
    assert "at least 2" in result.stdout
