import threading

from league_of_idea import tournament
from league_of_idea.models import Idea, MatchResult


def _generate(goal, n, model, usage_tracker=None, **kwargs):
    return [Idea(id=f"idea-{index}", content=f"idea {index}") for index in range(n)]


def _deterministic_judge(
    goal,
    idea_a,
    idea_b,
    model,
    rubric,
    usage_tracker,
    bidirectional=False,
    runtime=None,
):
    usage_tracker.before_call()
    usage_tracker.record(1, 1)
    winner = "A" if idea_a.id < idea_b.id else "B"
    return MatchResult(winner=winner)


def test_concurrent_judges_overlap(monkeypatch, tmp_path):
    barrier = threading.Barrier(2)

    def synchronized_judge(
        goal,
        idea_a,
        idea_b,
        model,
        rubric,
        usage_tracker,
        bidirectional=False,
        runtime=None,
    ):
        barrier.wait(timeout=2)
        return _deterministic_judge(
            goal,
            idea_a,
            idea_b,
            model,
            rubric,
            usage_tracker,
            bidirectional,
        )

    monkeypatch.setattr(tournament.generator, "generate_ideas", _generate)
    monkeypatch.setattr(tournament.judge, "judge_match", synchronized_judge)

    session = tournament.run_tournament(
        "goal",
        num_ideas=4,
        rounds=1,
        judge_model="openai:judge",
        generator_model="openai:generator",
        pairing_strategy="swiss",
        evolve=False,
        max_concurrency=2,
        seed=7,
        base_dir=tmp_path,
    )

    assert session.status == "completed"
    assert len(session.matches) == 2
    assert session.usage.calls == 2


def test_concurrency_does_not_change_elo_order(monkeypatch, tmp_path):
    monkeypatch.setattr(tournament.generator, "generate_ideas", _generate)
    monkeypatch.setattr(tournament.judge, "judge_match", _deterministic_judge)

    sequential = tournament.run_tournament(
        "goal",
        num_ideas=4,
        rounds=1,
        judge_model="openai:judge",
        generator_model="openai:generator",
        pairing_strategy="round-robin",
        evolve=False,
        max_concurrency=1,
        seed=11,
        base_dir=tmp_path / "sequential",
    )
    concurrent = tournament.run_tournament(
        "goal",
        num_ideas=4,
        rounds=1,
        judge_model="openai:judge",
        generator_model="openai:generator",
        pairing_strategy="round-robin",
        evolve=False,
        max_concurrency=3,
        seed=11,
        base_dir=tmp_path / "concurrent",
    )

    sequential_state = {
        idea.id: (idea.elo, idea.wins, idea.draws, idea.losses)
        for idea in sequential.ideas
    }
    concurrent_state = {
        idea.id: (idea.elo, idea.wins, idea.draws, idea.losses)
        for idea in concurrent.ideas
    }
    assert concurrent_state == sequential_state


def test_concurrency_rejects_token_or_cost_budget():
    from league_of_idea.usage import BudgetConfig

    try:
        tournament.run_tournament(
            "goal",
            num_ideas=2,
            rounds=1,
            judge_model="openai:judge",
            generator_model="openai:generator",
            budget=BudgetConfig(max_tokens=100),
            max_concurrency=2,
        )
    except ValueError as exc:
        assert "concurrency 1" in str(exc)
    else:
        raise AssertionError("Expected unsafe concurrent token budget to be rejected")
