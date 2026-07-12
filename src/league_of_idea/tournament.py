"""Orchestration — strings together generate → match → score → evolve → rank."""

from __future__ import annotations

import math
import random
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from . import elo, generator, judge, pairing, storage
from .models import Idea, Match, Session
from .pricing import PricingTable
from .rubric import DEFAULT_RUBRIC, Rubric
from .runtime import RuntimeConfig, RuntimeController
from .usage import (
    BudgetConfig,
    BudgetExceeded,
    UsageReservation,
    UsageStats,
    UsageTracker,
)

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
    pricing: PricingTable | None = None,
    double_judge: bool = False,
    dedup_threshold: float = 0.86,
    max_concurrency: int = 1,
    runtime: RuntimeConfig | None = None,
    pairing_strategy: str = "swiss",
    k: float = elo.DEFAULT_K,
    evolve: bool = True,
    evolve_top: int = 2,
    seed: int | None = None,
    base_dir: Path = storage.DEFAULT_DIR,
    progress: ProgressFn = _noop,
) -> Session:
    """Run a full tournament and return the persisted session."""
    _validate_options(
        goal,
        num_ideas,
        rounds,
        pairing_strategy,
        k,
        evolve_top,
        dedup_threshold,
        max_concurrency,
    )
    selected_budget = budget or BudgetConfig()
    selected_pricing = pricing or PricingTable()
    selected_runtime = runtime or RuntimeConfig()
    runtime_controller = RuntimeController(selected_runtime)
    if max_concurrency > 1 and (
        selected_budget.max_tokens is not None
        or selected_budget.max_cost_usd is not None
    ):
        raise ValueError(
            "Concurrent judging supports max_calls, but token/cost budgets require "
            "--concurrency 1 to prevent parallel overshoot."
        )
    if selected_budget.max_cost_usd is not None:
        missing = [
            model
            for model in (generator_model, judge_model)
            if selected_pricing.price_for(model) is None
        ]
        if missing:
            raise ValueError(
                "A cost budget requires prices for every model; missing: "
                + ", ".join(missing)
            )
    usage = UsageStats()
    usage_tracker = UsageTracker(selected_budget, usage, selected_pricing)
    progress(f"Generating {num_ideas} ideas...")
    ideas = generator.generate_ideas(
        goal,
        num_ideas,
        generator_model,
        usage_tracker=usage_tracker,
        dedup_threshold=dedup_threshold,
        runtime=runtime_controller,
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
        pricing=selected_pricing,
        pairing_strategy=pairing_strategy,
        double_judge=double_judge,
        dedup_threshold=dedup_threshold,
        max_concurrency=max_concurrency,
        runtime=selected_runtime,
        k=k,
        evolve=evolve,
        evolve_top=evolve_top,
        seed=seed,
        ideas=ideas,
    )
    storage.save_session(session, base_dir)
    return _continue_tournament(session, base_dir, progress, runtime_controller)


def resume_tournament(
    session_id: str,
    *,
    base_dir: Path = storage.DEFAULT_DIR,
    budget_override: BudgetConfig | None = None,
    concurrency_override: int | None = None,
    runtime_override: RuntimeConfig | None = None,
    progress: ProgressFn = _noop,
) -> Session:
    """Continue a failed or budget-stopped session without duplicate scoring."""
    session = storage.load_session(session_id, base_dir)
    if session.status == "completed":
        raise ValueError(f"Session {session_id} is already completed.")
    if budget_override is not None:
        session.budget = budget_override
    if concurrency_override is not None:
        if concurrency_override < 1:
            raise ValueError("concurrency must be at least 1.")
        session.max_concurrency = concurrency_override
    if runtime_override is not None:
        session.runtime = runtime_override
    if session.max_concurrency > 1 and (
        session.budget.max_tokens is not None
        or session.budget.max_cost_usd is not None
    ):
        raise ValueError(
            "Concurrent judging supports max_calls, but token/cost budgets require "
            "concurrency 1."
        )
    session.status = "running"
    session.error = None
    storage.save_session(session, base_dir)
    return _continue_tournament(session, base_dir, progress)


def _continue_tournament(
    session: Session,
    base_dir: Path,
    progress: ProgressFn,
    runtime_controller: RuntimeController | None = None,
) -> Session:
    usage_tracker = UsageTracker(session.budget, session.usage, session.pricing)
    runtime_controller = runtime_controller or RuntimeController(session.runtime)

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
                runtime_controller,
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
                    runtime_controller,
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
    runtime: RuntimeController,
) -> None:
    if rnd not in session.pairing_plans:
        eligible_ideas = [idea for idea in session.ideas if idea.created_in_round < rnd]
        previous_pairs = {
            frozenset((match.idea_a_id, match.idea_b_id))
            for match in session.matches
            if match.round < rnd
        }
        match_counts = {
            idea.id: sum(
                idea.id in (match.idea_a_id, match.idea_b_id)
                for match in session.matches
                if match.round < rnd
            )
            for idea in eligible_ideas
        }
        planned = pairing.make_pairs(
            eligible_ideas,
            pairing_strategy,
            rng=rng,
            previous_pairs=previous_pairs,
            match_counts=match_counts,
        )
        presented: list[tuple[str, str]] = []
        for idea_a, idea_b in planned:
            if rng.random() < 0.5:
                idea_a, idea_b = idea_b, idea_a
            presented.append((idea_a.id, idea_b.id))
        session.pairing_plans[rnd] = presented
        storage.save_session(session, base_dir)
    pairs: list[tuple[Idea, Idea]] = []
    for idea_a_id, idea_b_id in session.pairing_plans[rnd]:
        idea_a = session.get_idea(idea_a_id)
        idea_b = session.get_idea(idea_b_id)
        if idea_a is None or idea_b is None:
            raise ValueError(
                f"Pairing plan references missing ideas: {idea_a_id}, {idea_b_id}."
            )
        pairs.append((idea_a, idea_b))
    completed_pairs = {
        frozenset((match.idea_a_id, match.idea_b_id))
        for match in session.matches
        if match.round == rnd
    }
    missing = [
        (idea_a, idea_b)
        for idea_a, idea_b in pairs
        if frozenset((idea_a.id, idea_b.id)) not in completed_pairs
        and _pending_key(rnd, idea_a, idea_b) not in session.pending_results
    ]
    _evaluate_matches(
        session,
        rnd,
        missing,
        judge_model,
        usage_tracker,
        base_dir,
        runtime,
    )

    played = 0
    for idea_a, idea_b in pairs:
        pair = frozenset((idea_a.id, idea_b.id))
        if pair in completed_pairs:
            session.pending_results.pop(_pending_key(rnd, idea_a, idea_b), None)
            continue
        key = _pending_key(rnd, idea_a, idea_b)
        result = session.pending_results.get(key)
        if result is None:
            raise RuntimeError(f"Missing evaluated result for planned match {key}.")
        _apply_match_result(session, rnd, idea_a, idea_b, result, judge_model, k)
        session.pending_results.pop(key)
        played += 1
        storage.save_session(session, base_dir)
    progress(f"Round {rnd}: played {played} new matches ({len(pairs)} planned).")


def _pending_key(rnd: int, idea_a: Idea, idea_b: Idea) -> str:
    return f"{rnd}:{idea_a.id}:{idea_b.id}"


def _evaluate_matches(
    session: Session,
    rnd: int,
    pairs: list[tuple[Idea, Idea]],
    judge_model: str,
    usage_tracker: UsageTracker,
    base_dir: Path,
    runtime: RuntimeController,
) -> None:
    calls_per_match = 2 if session.double_judge else 1
    budget_error: BudgetExceeded | None = None
    with ThreadPoolExecutor(max_workers=session.max_concurrency) as executor:
        for start in range(0, len(pairs), session.max_concurrency):
            chunk = pairs[start : start + session.max_concurrency]
            futures: dict[Future[MatchResult], tuple[str, UsageReservation]] = {}
            for idea_a, idea_b in chunk:
                try:
                    reservation = usage_tracker.reserve_calls(calls_per_match)
                except BudgetExceeded as exc:
                    budget_error = exc
                    break
                key = _pending_key(rnd, idea_a, idea_b)
                future = executor.submit(
                    _judge_reserved,
                    session,
                    idea_a,
                    idea_b,
                    judge_model,
                    reservation,
                    runtime,
                )
                futures[future] = (key, reservation)

            first_error: Exception | None = None
            for future in as_completed(futures):
                key, _ = futures[future]
                try:
                    result = future.result()
                    with usage_tracker.locked():
                        session.pending_results[key] = result
                        storage.save_session(session, base_dir)
                except Exception as exc:
                    if first_error is None:
                        first_error = exc
            if first_error is not None:
                raise first_error
            if budget_error is not None:
                raise budget_error


def _judge_reserved(
    session: Session,
    idea_a: Idea,
    idea_b: Idea,
    judge_model: str,
    reservation: UsageReservation,
    runtime: RuntimeController,
) -> MatchResult:
    try:
        return judge.judge_match(
            session.goal,
            idea_a,
            idea_b,
            judge_model,
            session.rubric,
            reservation,
            session.double_judge,
            runtime,
        )
    finally:
        reservation.release()


def _apply_match_result(
    session: Session,
    rnd: int,
    idea_a: Idea,
    idea_b: Idea,
    result: MatchResult,
    judge_model: str,
    k: float,
) -> None:
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
            disputed=result.disputed,
            evaluations=result.evaluations,
        )
    )


def _evolve_round(
    session: Session,
    goal: str,
    generator_model: str,
    evolve_top: int,
    progress: ProgressFn,
    usage_tracker: UsageTracker,
    base_dir: Path,
    rnd: int,
    runtime: RuntimeController,
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
            existing_contents=[idea.content for idea in session.ideas],
            dedup_threshold=session.dedup_threshold,
            runtime=runtime,
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
    double_judge: bool = False,
) -> int:
    """Return minimum planned calls; generation retries can increase the total."""
    _validate_options(
        "estimate", num_ideas, rounds, pairing_strategy, 32.0, evolve_top, 0.86, 1
    )
    total = 1  # initial generation call
    idea_count = num_ideas
    for rnd in range(1, rounds + 1):
        if pairing_strategy == "round-robin":
            matches = math.comb(idea_count, 2)
        elif pairing_strategy == "swiss":
            matches = idea_count // 2
        else:
            matches = min(idea_count, math.comb(idea_count, 2))
        total += matches * (2 if double_judge else 1)
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
    dedup_threshold: float,
    max_concurrency: int,
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
    if not 0 <= dedup_threshold <= 1:
        raise ValueError("dedup_threshold must be between 0 and 1.")
    if max_concurrency < 1:
        raise ValueError("max_concurrency must be at least 1.")
