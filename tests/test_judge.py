from league_of_idea import judge
from league_of_idea.models import Idea
from league_of_idea.rubric import Criterion, Rubric


def test_judge_computes_winner_from_weighted_scores(monkeypatch):
    rubric = Rubric(
        version="test-v1",
        criteria=[
            Criterion(name="impact", description="impact", weight=2),
            Criterion(name="cost", description="cost", weight=1),
        ],
    )
    monkeypatch.setattr(
        judge.llm,
        "complete_json",
        lambda *args, **kwargs: {
            "scores_a": {"impact": 9, "cost": 3},
            "scores_b": {"impact": 6, "cost": 8},
            "confidence": 0.9,
            "reasoning": "A has higher weighted impact.",
        },
    )

    result = judge.judge_match(
        "goal", Idea(content="A"), Idea(content="B"), "openai:test", rubric
    )

    assert result.winner == "A"
    assert result.confidence == 0.9


def test_judge_returns_draw_inside_margin(monkeypatch):
    rubric = Rubric(
        version="test-v1",
        criteria=[Criterion(name="quality", description="quality")],
        tie_margin=0.5,
    )
    monkeypatch.setattr(
        judge.llm,
        "complete_json",
        lambda *args, **kwargs: {
            "scores_a": {"quality": 8.0},
            "scores_b": {"quality": 7.6},
            "confidence": 0.5,
            "reasoning": "Too close to call.",
        },
    )

    result = judge.judge_match(
        "goal", Idea(content="A"), Idea(content="B"), "openai:test", rubric
    )

    assert result.winner == "draw"
