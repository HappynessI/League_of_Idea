import pytest

from league_of_idea import arena_bridge, research, storage
from league_of_idea.models import Session
from league_of_idea.workspace_models import (
    GapHypothesis,
    IdeaSpec,
    IdeaVersion,
    ProjectBrief,
    ResearchIdea,
    ResearchProject,
)


def _spec(title, gap_id):
    return IdeaSpec(
        title=title,
        research_question="question",
        motivation="motivation",
        gap_ids=[gap_id],
        hypothesis="hypothesis",
        proposed_method=["method"],
        expected_contributions=["contribution"],
        evaluation_plan=["evaluation"],
        required_resources=["resource"],
        main_risks=["risk"],
        falsification_criteria=["criterion"],
    )


def test_arena_uses_frozen_human_shortlist(monkeypatch, tmp_path):
    project = ResearchProject(
        title="project",
        brief=ProjectBrief(direction="direction", keywords=["one", "two"]),
    )
    gap = GapHypothesis(
        title="gap", description="desc", why_important="why",
        why_unresolved="why", evidence_refs=[{"paper_id": "p", "evidence_id": "e"}],
        confidence=0.5, created_by="model",
    )
    project.gaps.append(gap)
    first = ResearchIdea(
        versions=[IdeaVersion(number=1, spec=_spec("first", gap.id), created_by="model:a")]
    )
    second = ResearchIdea(
        versions=[IdeaVersion(number=1, spec=_spec("second", gap.id), created_by="model:b")]
    )
    project.ideas = [first, second]
    research.set_shortlist(project, [first.latest().id, second.latest().id], "approved")
    captured = {}

    def fake_run(goal, **kwargs):
        captured.update(kwargs)
        return Session(
            goal=goal, num_ideas=2, rounds=1,
            judge_model="judge:model", generator_model="research-workspace",
            ideas=kwargs["initial_ideas"], status="completed",
        )

    monkeypatch.setattr(arena_bridge.tournament, "run_tournament", fake_run)
    session = arena_bridge.run_shortlist_arena(
        project, judge_model="judge:model", rounds=1, sessions_dir=tmp_path
    )
    assert captured["evolve"] is False
    assert "Falsification criteria" in session.ideas[0].content
    assert "Research gap hypotheses" in session.ideas[0].content
    assert session.ideas[0].source_ref.endswith(first.latest().id)
    assert project.arena_runs[0].session_id == session.id


def test_shortlist_rejects_two_versions_of_same_idea():
    project = ResearchProject(
        title="project",
        brief=ProjectBrief(direction="direction", keywords=["one", "two"]),
    )
    gap_id = "gap"
    idea = ResearchIdea(
        versions=[
            IdeaVersion(number=1, spec=_spec("v1", gap_id), created_by="model"),
            IdeaVersion(number=2, spec=_spec("v2", gap_id), created_by="model"),
        ]
    )
    project.ideas = [idea]
    try:
        research.set_shortlist(project, [item.id for item in idea.versions])
    except ValueError as exc:
        assert "at most one version" in str(exc)
    else:
        raise AssertionError("Expected shortlist validation error")


def test_failed_arena_records_paid_usage(monkeypatch, tmp_path):
    project = ResearchProject(
        title="project",
        brief=ProjectBrief(direction="direction", keywords=["one", "two"]),
    )
    first = ResearchIdea(
        versions=[IdeaVersion(number=1, spec=_spec("first", "gap"), created_by="model")]
    )
    second = ResearchIdea(
        versions=[IdeaVersion(number=1, spec=_spec("second", "gap"), created_by="model")]
    )
    project.ideas = [first, second]
    research.set_shortlist(project, [first.latest().id, second.latest().id])

    def fail_after_payment(goal, **kwargs):
        session = Session(
            id=kwargs["session_id"], goal=goal, num_ideas=2, rounds=1,
            judge_model="judge:model", generator_model="research-workspace",
            ideas=kwargs["initial_ideas"], status="failed", error="provider failed",
        )
        session.usage.calls = 1
        session.usage.total_tokens = 100
        storage.save_session(session, kwargs["base_dir"])
        raise RuntimeError("provider failed")

    monkeypatch.setattr(arena_bridge.tournament, "run_tournament", fail_after_payment)
    with pytest.raises(RuntimeError, match="provider failed"):
        arena_bridge.run_shortlist_arena(
            project, judge_model="judge:model", rounds=1, sessions_dir=tmp_path
        )
    assert project.usage.calls == 1
    assert project.usage.total_tokens == 100
    assert project.arena_runs[0].status == "failed"
