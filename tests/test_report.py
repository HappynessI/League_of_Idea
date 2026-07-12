from league_of_idea.models import Idea, Match, Session
from league_of_idea.report import render_markdown, save_report


def test_report_contains_ranking_rubric_usage_and_evidence(tmp_path):
    idea_a = Idea(content="Idea A | with pipe", elo=1216, wins=1)
    idea_b = Idea(content="Idea B", elo=1184, losses=1)
    session = Session(
        goal="Improve research quality",
        num_ideas=2,
        rounds=1,
        judge_model="openai:judge",
        generator_model="openai:generator",
        ideas=[idea_a, idea_b],
        matches=[
            Match(
                round=1,
                idea_a_id=idea_a.id,
                idea_b_id=idea_b.id,
                winner_id=idea_a.id,
                reasoning="A is stronger.",
                scores_a={"novelty": 8},
                scores_b={"novelty": 6},
                confidence=0.8,
                rubric_version="research-v1",
            )
        ],
    )
    session.usage.calls = 2
    session.usage.total_tokens = 100

    markdown = render_markdown(session)

    assert "## Leaderboard" in markdown
    assert "research-v1" in markdown
    assert "2 calls; 100 tokens" in markdown
    assert "A is stronger." in markdown
    assert "Idea A \\| with pipe" in markdown

    path = save_report(session, tmp_path / "nested" / "report.md")
    assert path.read_text(encoding="utf-8") == markdown
