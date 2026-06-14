"""Orchestration — strings together generate → match → score → evolve → rank."""

from __future__ import annotations

from typing import Callable

from . import elo, generator, judge, pairing, storage
from .models import Idea, Match, Session

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
    pairing_strategy: str = "round-robin",
    k: float = elo.DEFAULT_K,
    evolve: bool = True,
    evolve_top: int = 2,
    base_dir=storage.DEFAULT_DIR,
    progress: ProgressFn = _noop,
) -> Session:
    """Run a full tournament and return the persisted session."""
    progress(f"Generating {num_ideas} ideas...")
    ideas = generator.generate_ideas(goal, num_ideas, generator_model)
    session = Session(
        goal=goal,
        num_ideas=num_ideas,
        rounds=rounds,
        judge_model=judge_model,
        generator_model=generator_model,
        ideas=ideas,
    )

    for rnd in range(1, rounds + 1):
        progress(f"Round {rnd}/{rounds}: pairing & judging...")
        _play_round(session, rnd, judge_model, pairing_strategy, k, progress)

        # Evolve high-Elo ideas into the next generation (except after the last round).
        if evolve and rnd < rounds:
            _evolve_round(session, goal, generator_model, evolve_top, progress)

        storage.save_session(session, base_dir)

    storage.save_session(session, base_dir)
    progress(f"Done. Session {session.id} saved.")
    return session


def _play_round(
    session: Session,
    rnd: int,
    judge_model: str,
    pairing_strategy: str,
    k: float,
    progress: ProgressFn,
) -> None:
    pairs = pairing.make_pairs(session.ideas, pairing_strategy)
    for idea_a, idea_b in pairs:
        result = judge.judge_match(session.goal, idea_a, idea_b, judge_model)
        winner, loser = (idea_a, idea_b) if result.winner == "A" else (idea_b, idea_a)

        new_w, new_l = elo.update_ratings(winner.elo, loser.elo, score_a=1.0, k=k)
        winner.elo, loser.elo = new_w, new_l
        winner.wins += 1
        loser.losses += 1

        session.matches.append(
            Match(
                round=rnd,
                idea_a_id=idea_a.id,
                idea_b_id=idea_b.id,
                winner_id=winner.id,
                reasoning=result.reasoning,
            )
        )
    progress(f"Round {rnd}: played {len(pairs)} matches.")


def _evolve_round(
    session: Session,
    goal: str,
    generator_model: str,
    evolve_top: int,
    progress: ProgressFn,
) -> None:
    top = session.leaderboard()[:evolve_top]
    children: list[Idea] = []
    for parent in top:
        child = generator.evolve_idea(goal, parent, generator_model)
        # Seed the child near its parent so it must earn its rank.
        child.elo = parent.elo
        children.append(child)
    session.ideas.extend(children)
    progress(f"Evolved {len(children)} new ideas from the top {evolve_top}.")
