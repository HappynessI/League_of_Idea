"""Orchestration — strings together generate → match → score → evolve → rank."""

from __future__ import annotations

import math
import random
from pathlib import Path
from typing import Callable

from . import elo, generator, judge, pairing, storage
from .models import Idea, Match, Session
from .rubric import DEFAULT_RUBRIC, Rubric
from .usage import BudgetConfig, BudgetExceeded, UsageStats, UsageTracker

# A no-op progress callback by default; the CLI passes a rich-aware one.
ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


def run_tournament(
    goal: str,
    *,
    num_ideas: int = 8,
    rounds: int = 3,
    judge_model: str,
    generator_model: str,
    rubric: Rubric = DEFAULT_RUBRIC,
    budget: BudgetConfig | None = None,
    pairing_strategy: str = "random",
    k: float = elo.DEFAULT_K,
    evolve: bool = True,
    evolve_top: int = 2,
    seed: int | None = None,
    base_dir: Path = storage.DEFAULT_DIR,
    progress: ProgressFn = _noop,
) -> Session:
    """Run a full tournament and return the persisted session."""
    _validate_options(goal, num_ideas, rounds, pairing_strategy, k, evolve_top)
    selected_budget = budget or BudgetConfig()
    usage = UsageStats()
    usage_tracker = UsageTracker(selected_budget, usage)
    progress(f"Generating {num_ideas} ideas...")
    ideas = generator.generate_ideas(
        goal, num_ideas, generator_model, usage_tracker=usage_tracker
    )
    session = Session(
        goal=goal,
        num_ideas=num_ideas,
        rounds=rounds,
        judge_model=judge_model,
        generator_model=generator_model,
        rubric=rubric.model_copy(deep=True),
        budget=selected_budget,
        usage=usage,
        pairing_strategy=pairing_strategy,
        k=k,
        evolve=evolve,
        evolve_top=evolve_top,
        seed=seed,
        ideas=ideas,
    )
    storage.save_session(session, base_dir)
    return _continue_tournament(session, base_dir, progress)


def resume_tournament(
    session_id: str,
    *,
    base_dir: Path = storage.DEFAULT_DIR,
    budget_override: BudgetConfig | None = None,
    progress: ProgressFn = _noop,
) -> Session:
    """Continue a failed or budget-stopped session without duplicate scoring."""
    session = storage.load_session(session_id, base_dir)
    if session.status == "completed":
        raise ValueError(f"Session {session_id} is already completed.")
    if budget_override is not None:
        session.budget = budget_override
    session.status = "running"
    session.error = None
    storage.save_session(session, base_dir)
    return _continue_tournament(session, base_dir, progress)


def _continue_tournament(
    session: Session,
    base_dir: Path,
    progress: ProgressFn,
) -> Session:
    usage_tracker = UsageTracker(session.budget, session.usage)

    try:
        for rnd in range(session.completed_rounds + 1, session.rounds + 1):
            progress(f"Round {rnd}/{session.rounds}: pairing & judging...")
            rng = _round_rng(session, rnd)
            _play_round(
                session,
                rnd,
                session.judge_model,
                session.pairing_strategy,
                session.k,
                progress,
                rng,
                base_dir,
                usage_tracker,
            )

            if session.evolve and rnd < session.rounds:
                _evolve_round(
                    session,
                    session.goal,
                    session.generator_model,
                    session.evolve_top,
                    progress,
                    usage_tracker,
                    base_dir,
                    rnd,
                )
            session.completed_rounds = rnd
            storage.save_session(session, base_dir)
    except BudgetExceeded as exc:
        session.status = "stopped"
        session.error = str(exc)
        storage.save_session(session, base_dir)
        progress(f"Stopped safely: {exc}")
        return session
    except Exception as exc:
        session.status = "failed"
        session.error = str(exc)
        storage.save_session(session, base_dir)
        raise

    session.status = "completed"
    storage.save_session(session, base_dir)
    progress(f"Done. Session {session.id} saved.")
    return session


def _round_rng(session: Session, rnd: int) -> random.Random:
    """Create a stable per-round RNG so interrupted rounds can be reconstructed."""
    seed_material = f"{session.seed if session.seed is not None else session.id}:{rnd}"
    return random.Random(seed_material)


def _play_round(
    session: Session,
    rnd: int,
    judge_model: str,
    pairing_strategy: str,
    k: float,
    progress: ProgressFn,
    rng: random.Random,
    base_dir: Path,
    usage_tracker: UsageTracker,
) -> None:
    eligible_ideas = [idea for idea in session.ideas if idea.created_in_round < rnd]
    pairs = pairing.make_pairs(eligible_ideas, pairing_strategy, rng=rng)
    completed_pairs = {
        frozenset((match.idea_a_id, match.idea_b_id))
        for match in session.matches
        if match.round == rnd
    }
    played = 0
    for idea_a, idea_b in pairs:
        if frozenset((idea_a.id, idea_b.id)) in completed_pairs:
            continue
        # Randomize presentation order to avoid systematically favoring early ideas.
        if rng.random() < 0.5:
            idea_a, idea_b = idea_b, idea_a
        result = judge.judge_match(
            session.goal,
            idea_a,
            idea_b,
            judge_model,
            session.rubric,
            usage_tracker,
        )
        if result.winner == "draw":
            idea_a.elo, idea_b.elo = elo.update_ratings(
                idea_a.elo, idea_b.elo, score_a=0.5, k=k
            )
            idea_a.draws += 1
            idea_b.draws += 1
            winner_id = None
        else:
            winner, loser = (
                (idea_a, idea_b) if result.winner == "A" else (idea_b, idea_a)
            )
            winner.elo, loser.elo = elo.update_ratings(
                winner.elo, loser.elo, score_a=1.0, k=k
            )
            winner.wins += 1
            loser.losses += 1
            winner_id = winner.id

        session.matches.append(
            Match(
                round=rnd,
                idea_a_id=idea_a.id,
                idea_b_id=idea_b.id,
                winner_id=winner_id,
                reasoning=result.reasoning,
                scores_a=result.scores_a,
                scores_b=result.scores_b,
                confidence=result.confidence,
                rubric_version=session.rubric.version,
                judge_model=judge_model,
            )
        )
        played += 1
        # Preserve paid API work even if a later match fails or the process stops.
        storage.save_session(session, base_dir)
    progress(f"Round {rnd}: played {played} new matches ({len(pairs)} planned).")


def _evolve_round(
    session: Session,
    goal: str,
    generator_model: str,
    evolve_top: int,
    progress: ProgressFn,
    usage_tracker: UsageTracker,
    base_dir: Path,
    rnd: int,
) -> None:
    if rnd not in session.evolution_plans:
        session.evolution_plans[rnd] = [
            idea.id for idea in session.leaderboard()[:evolve_top]
        ]
        storage.save_session(session, base_dir)
    parent_ids = session.evolution_plans[rnd]
    top = [session.get_idea(parent_id) for parent_id in parent_ids]
    children: list[Idea] = []
    for parent in top:
        if parent is None:
            raise ValueError(f"Evolution parent is missing from session: {parent_ids}")
        if any(
            idea.parent_id == parent.id and idea.created_in_round == rnd
            for idea in session.ideas
        ):
            continue
        child = generator.evolve_idea(
            goal,
            parent,
            generator_model,
            usage_tracker=usage_tracker,
            created_in_round=rnd,
        )
        children.append(child)
        session.ideas.append(child)
        storage.save_session(session, base_dir)
    progress(f"Evolved {len(children)} new ideas from the top {evolve_top}.")


def estimate_llm_calls(
    num_ideas: int,
    rounds: int,
    pairing_strategy: str,
    *,
    evolve: bool,
    evolve_top: int,
) -> int:
    """Return the exact call count for the current sequential tournament design."""
    _validate_options("estimate", num_ideas, rounds, pairing_strategy, 32.0, evolve_top)
    total = 1  # initial generation call
    idea_count = num_ideas
    for rnd in range(1, rounds + 1):
        total += math.comb(idea_count, 2) if pairing_strategy == "round-robin" else idea_count
        if evolve and rnd < rounds:
            total += min(evolve_top, idea_count)
            idea_count += min(evolve_top, idea_count)
    return total


def _validate_options(
    goal: str,
    num_ideas: int,
    rounds: int,
    pairing_strategy: str,
    k: float,
    evolve_top: int,
) -> None:
    if not goal.strip():
        raise ValueError("Goal must not be empty.")
    if num_ideas < 2:
        raise ValueError("num_ideas must be at least 2.")
    if rounds < 1:
        raise ValueError("rounds must be at least 1.")
    if pairing_strategy not in pairing.STRATEGIES:
        raise ValueError(
            f"Unknown pairing strategy {pairing_strategy!r}; choose from "
            f"{', '.join(pairing.STRATEGIES)}."
        )
    if not math.isfinite(k) or k <= 0:
        raise ValueError("k must be a positive finite number.")
    if evolve_top < 1:
        raise ValueError("evolve_top must be at least 1.")
