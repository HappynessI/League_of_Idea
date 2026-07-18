"""Freeze human-shortlisted research versions into an Arena session."""

from __future__ import annotations

from pathlib import Path
from typing import Callable
import uuid

from .models import Idea, Session
from .rubric import RESEARCH_WORKSPACE_RUBRIC, Rubric
from . import storage, tournament
from .workspace_models import ArenaEntry, IdeaSpec, ProjectArenaRun, ResearchProject
from .usage import BudgetConfig, BudgetExceeded


def run_shortlist_arena(
    project: ResearchProject,
    *,
    judge_model: str,
    rounds: int = 3,
    pairing_strategy: str = "swiss",
    rubric: Rubric = RESEARCH_WORKSPACE_RUBRIC,
    double_judge: bool = False,
    max_concurrency: int = 1,
    seed: int | None = None,
    sessions_dir: Path = storage.DEFAULT_DIR,
    progress: Callable[[str], None] = lambda _: None,
) -> Session:
    decision = project.latest_decision()
    if decision is None:
        raise ValueError("Create a human shortlist before entering the Arena.")
    frozen: list[tuple[str, str, Idea]] = []
    for version_id in decision.selected_version_ids:
        found = project.find_version(version_id)
        if found is None:
            raise ValueError(f"Shortlist references a missing version: {version_id}")
        research_idea, version = found
        arena_idea = Idea(
            content=render_idea_for_arena(project, version.spec),
            created_by=version.created_by,
            source_ref=f"{project.id}/{research_idea.id}/{version.id}",
        )
        frozen.append((research_idea.id, version.id, arena_idea))
    session_id = uuid.uuid4().hex[:8]
    try:
        session = tournament.run_tournament(
            project.brief.direction,
            num_ideas=len(frozen),
            rounds=rounds,
            judge_model=judge_model,
            generator_model="research-workspace",
            rubric=rubric,
            budget=_remaining_budget(project),
            pricing=project.pricing,
            runtime=project.runtime,
            initial_ideas=[item[2] for item in frozen],
            session_id=session_id,
            double_judge=double_judge,
            max_concurrency=max_concurrency,
            pairing_strategy=pairing_strategy,
            evolve=False,
            seed=seed,
            base_dir=sessions_dir,
            progress=progress,
        )
    except Exception:
        try:
            failed = storage.load_session(session_id, sessions_dir)
        except FileNotFoundError:
            raise
        _record_arena_run(project, failed, frozen)
        raise
    _record_arena_run(project, session, frozen)
    return session


def _record_arena_run(
    project: ResearchProject,
    session: Session,
    frozen: list[tuple[str, str, Idea]],
) -> None:
    project.usage.calls += session.usage.calls
    project.usage.prompt_tokens += session.usage.prompt_tokens
    project.usage.completion_tokens += session.usage.completion_tokens
    project.usage.total_tokens += session.usage.total_tokens
    project.usage.estimated_cost_usd += session.usage.estimated_cost_usd
    project.usage.unpriced_calls += session.usage.unpriced_calls
    project.arena_runs.append(
        ProjectArenaRun(
            session_id=session.id,
            status=session.status,
            entries=[
                ArenaEntry(
                    research_idea_id=research_id,
                    version_id=version_id,
                    arena_idea_id=arena_idea.id,
                )
                for research_id, version_id, arena_idea in frozen
            ],
        )
    )


def render_idea_for_arena(project: ResearchProject, spec: IdeaSpec) -> str:
    """Render a complete, immutable IdeaSpec snapshot for pairwise judging."""
    gap_lines = []
    for gap_id in spec.gap_ids:
        gap = project.get_gap(gap_id)
        if gap is not None:
            gap_lines.append(
                f"- {gap.id}: {gap.title} — {gap.description} "
                f"(confidence {gap.confidence:.2f}; uncertainties: "
                f"{'; '.join(gap.uncertainties) or 'none recorded'})"
            )
    evidence_lines = []
    for ref in spec.evidence_refs:
        paper = project.get_paper(ref.paper_id)
        if paper is None or paper.card is None:
            continue
        evidence = next(
            (item for item in paper.card.evidence if item.id == ref.evidence_id), None
        )
        if evidence is not None:
            evidence_lines.append(
                f"- {paper.title} {evidence.source_locator}: {evidence.claim} "
                f"[short source quote: {evidence.quote}]"
            )
    constraint_lines = [
        f"- {item.category}: {item.description}" for item in project.brief.constraints
    ]
    sections = [
        f"Title: {spec.title}",
        f"Research question: {spec.research_question}",
        f"Motivation: {spec.motivation}",
        f"Hypothesis: {spec.hypothesis}",
        "Research gap hypotheses:\n" + ("\n".join(gap_lines) or "- none"),
        "Traceable literature evidence:\n" + ("\n".join(evidence_lines) or "- none"),
        "Researcher constraints:\n" + ("\n".join(constraint_lines) or "- none recorded"),
        "Proposed method:\n- " + "\n- ".join(spec.proposed_method),
        "Expected contributions:\n- " + "\n- ".join(spec.expected_contributions),
        "Evaluation plan:\n- " + "\n- ".join(spec.evaluation_plan),
        "Required resources:\n- " + "\n- ".join(spec.required_resources),
        "Main risks:\n- " + "\n- ".join(spec.main_risks),
        "Falsification criteria:\n- " + "\n- ".join(spec.falsification_criteria),
    ]
    return "\n\n".join(sections)


def _remaining_budget(project: ResearchProject) -> BudgetConfig:
    values: dict[str, int | float | None] = {
        "max_calls": None,
        "max_tokens": None,
        "max_cost_usd": None,
    }
    consumed = {
        "max_calls": project.usage.calls,
        "max_tokens": project.usage.total_tokens,
        "max_cost_usd": project.usage.estimated_cost_usd,
    }
    for field, used in consumed.items():
        limit = getattr(project.budget, field)
        if limit is not None:
            remaining = limit - used
            if remaining <= 0:
                raise BudgetExceeded(f"Project {field} budget is already exhausted.")
            values[field] = remaining
    return BudgetConfig.model_validate(values)
