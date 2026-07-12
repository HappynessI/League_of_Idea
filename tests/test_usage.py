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

    resumed = tournament.resume_tournament(
        session.id,
        base_dir=tmp_path,
        budget_override=BudgetConfig(max_calls=4),
    )

    assert resumed.status == "completed"
    assert resumed.usage.calls == 4
    assert len(resumed.matches) == 3


def test_resume_does_not_pair_partially_evolved_children_in_previous_round(
    monkeypatch, tmp_path
):
    def record(tracker):
        tracker.before_call()
        tracker.record(1, 1)

    def generate(goal, n, model, usage_tracker=None):
        record(usage_tracker)
        return [Idea(content=f"idea {index}") for index in range(n)]

    def judge(goal, idea_a, idea_b, model, rubric, usage_tracker):
        record(usage_tracker)
        return MatchResult(winner="A")

    def evolve(
        goal, parent, model, usage_tracker=None, created_in_round=0
    ):
        record(usage_tracker)
        return Idea(
            content=f"child {parent.id}",
            parent_id=parent.id,
            generation=parent.generation + 1,
            created_in_round=created_in_round,
        )

    monkeypatch.setattr(tournament.generator, "generate_ideas", generate)
    monkeypatch.setattr(tournament.generator, "evolve_idea", evolve)
    monkeypatch.setattr(tournament.judge, "judge_match", judge)

    stopped = tournament.run_tournament(
        "goal",
        num_ideas=2,
        rounds=2,
        judge_model="openai:judge",
        generator_model="openai:generator",
        evolve_top=2,
        budget=BudgetConfig(max_calls=3),
        base_dir=tmp_path,
    )
    assert stopped.status == "stopped"
    assert len(stopped.ideas) == 3

    resumed = tournament.resume_tournament(
        stopped.id,
        base_dir=tmp_path,
        budget_override=BudgetConfig(max_calls=8),
    )

    assert resumed.status == "completed"
    assert len(resumed.ideas) == 4
    assert len([match for match in resumed.matches if match.round == 1]) == 1
    assert len([match for match in resumed.matches if match.round == 2]) == 4
