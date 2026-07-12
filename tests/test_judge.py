import pytest

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


def test_bidirectional_judge_combines_consistent_orientations(monkeypatch):
    rubric = Rubric(
        version="test-v1",
        criteria=[Criterion(name="quality", description="quality")],
    )
    responses = iter(
        [
            {
                "scores_a": {"quality": 9},
                "scores_b": {"quality": 5},
                "confidence": 0.9,
                "reasoning": "Original A wins.",
            },
            {
                "scores_a": {"quality": 5},
                "scores_b": {"quality": 9},
                "confidence": 0.7,
                "reasoning": "Original A still wins after swap.",
            },
        ]
    )
    monkeypatch.setattr(
        judge.llm, "complete_json", lambda *args, **kwargs: next(responses)
    )

    result = judge.judge_match(
        "goal",
        Idea(content="A"),
        Idea(content="B"),
        "openai:test",
        rubric,
        bidirectional=True,
    )

    assert result.winner == "A"
    assert result.disputed is False
    assert result.evaluations == 2
    assert result.confidence == pytest.approx(0.8)


def test_bidirectional_disagreement_becomes_disputed_draw(monkeypatch):
    rubric = Rubric(
        version="test-v1",
        criteria=[Criterion(name="quality", description="quality")],
    )
    responses = iter(
        [
            {
                "scores_a": {"quality": 9},
                "scores_b": {"quality": 5},
                "confidence": 0.8,
                "reasoning": "A wins forward.",
            },
            {
                "scores_a": {"quality": 9},
                "scores_b": {"quality": 5},
                "confidence": 0.8,
                "reasoning": "B wins when shown first.",
            },
        ]
    )
    monkeypatch.setattr(
        judge.llm, "complete_json", lambda *args, **kwargs: next(responses)
    )

    result = judge.judge_match(
        "goal",
        Idea(content="A"),
        Idea(content="B"),
        "openai:test",
        rubric,
        bidirectional=True,
    )

    assert result.winner == "draw"
    assert result.disputed is True
    assert result.evaluations == 2
