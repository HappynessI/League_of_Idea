import pytest

from league_of_idea import tournament
from league_of_idea.models import Idea, MatchResult
from league_of_idea.storage import load_session


def _fake_generate(goal, n, model, **kwargs):
    return [Idea(content=f"idea {index}", created_by=model) for index in range(n)]


def _fake_evolve(goal, parent, model, **kwargs):
    return Idea(
        content=f"child of {parent.id}",
        generation=parent.generation + 1,
        parent_id=parent.id,
        created_by=model,
    )


def test_estimate_round_robin_calls_with_evolution():
    # generate + C(3,2) + evolve one + C(4,2)
    assert tournament.estimate_llm_calls(
        3, 2, "round-robin", evolve=True, evolve_top=1
    ) == 11


def test_estimate_swiss_calls_with_evolution():
    # generate + floor(3/2) + evolve one + floor(4/2)
    assert tournament.estimate_llm_calls(
        3, 2, "swiss", evolve=True, evolve_top=1
    ) == 5


def test_estimate_double_judge_counts_two_calls_per_match():
    assert tournament.estimate_llm_calls(
        4,
        1,
        "swiss",
        evolve=False,
        evolve_top=1,
        double_judge=True,
    ) == 5


def test_tournament_runs_without_real_api(monkeypatch, tmp_path):
    monkeypatch.setattr(tournament.generator, "generate_ideas", _fake_generate)
    monkeypatch.setattr(tournament.generator, "evolve_idea", _fake_evolve)
    monkeypatch.setattr(
        tournament.judge,
        "judge_match",
        lambda *args, **kwargs: MatchResult(winner="A", reasoning="test"),
    )

    session = tournament.run_tournament(
        "goal",
        num_ideas=3,
        rounds=2,
        judge_model="openai:judge",
        generator_model="openai:generator",
        pairing_strategy="round-robin",
        evolve=True,
        evolve_top=1,
        seed=7,
        base_dir=tmp_path,
    )

    assert session.status == "completed"
    assert session.completed_rounds == 2
    assert len(session.ideas) == 4
    assert len(session.matches) == 9
    assert session.ideas[-1].elo != session.ideas[0].elo
    assert load_session(session.id, tmp_path).status == "completed"


def test_failure_preserves_partial_session(monkeypatch, tmp_path):
    monkeypatch.setattr(tournament.generator, "generate_ideas", _fake_generate)
    calls = 0

    def flaky_judge(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("provider unavailable")
        return MatchResult(winner="A")

    monkeypatch.setattr(tournament.judge, "judge_match", flaky_judge)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        tournament.run_tournament(
            "goal",
            num_ideas=3,
            rounds=1,
            judge_model="openai:judge",
            generator_model="openai:generator",
            pairing_strategy="random",
            seed=1,
            base_dir=tmp_path,
        )

    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    saved = load_session(files[0].stem, tmp_path)
    assert saved.status == "failed"
    assert saved.error == "provider unavailable"
    assert len(saved.matches) == 0
    assert len(saved.pending_results) == 1

    monkeypatch.setattr(
        tournament.judge,
        "judge_match",
        lambda *args, **kwargs: MatchResult(winner="A", reasoning="resumed"),
    )
    resumed = tournament.resume_tournament(saved.id, base_dir=tmp_path)

    assert resumed.status == "completed"
    assert len(resumed.matches) == 3
    assert resumed.pending_results == {}
    unique_pairs = {
        frozenset((match.idea_a_id, match.idea_b_id)) for match in resumed.matches
    }
    assert len(unique_pairs) == 3
