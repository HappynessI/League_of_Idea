import pytest

from league_of_idea import tournament
from league_of_idea.models import Idea, MatchResult
from league_of_idea.usage import BudgetConfig, BudgetExceeded, UsageStats, UsageTracker


def test_usage_tracker_stops_before_next_call():
    stats = UsageStats()
    tracker = UsageTracker(BudgetConfig(max_calls=1), stats)

    tracker.before_call()
    tracker.record(10, 5)

    with pytest.raises(BudgetExceeded, match="call budget"):
        tracker.before_call()
    assert stats.total_tokens == 15


def test_tournament_returns_partial_session_when_budget_is_reached(monkeypatch, tmp_path):
    def generate(goal, n, model, usage_tracker=None):
        usage_tracker.before_call()
        usage_tracker.record(10, 5)
        return [Idea(content=f"idea {index}") for index in range(n)]

    def judge(goal, idea_a, idea_b, model, rubric, usage_tracker):
        usage_tracker.before_call()
        usage_tracker.record(20, 5)
        return MatchResult(winner="A")

    monkeypatch.setattr(tournament.generator, "generate_ideas", generate)
    monkeypatch.setattr(tournament.judge, "judge_match", judge)

    session = tournament.run_tournament(
        "goal",
        num_ideas=3,
        rounds=1,
        judge_model="openai:judge",
        generator_model="openai:generator",
        budget=BudgetConfig(max_calls=2),
        base_dir=tmp_path,
        seed=1,
    )

    assert session.status == "stopped"
    assert session.usage.calls == 2
    assert len(session.matches) == 1
