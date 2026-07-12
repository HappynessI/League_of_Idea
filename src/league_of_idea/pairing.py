"""Pairing strategies — who plays whom.

Supports full round-robin, random sampling, and Swiss-style pairings that favor
nearby Elo ratings while avoiding repeat opponents when possible.
"""

from __future__ import annotations

import itertools
import random

from .models import Idea


def round_robin(ideas: list[Idea]) -> list[tuple[Idea, Idea]]:
    """Every distinct pair plays exactly once. Pairs grow ~O(n^2)."""
    return list(itertools.combinations(ideas, 2))


def random_pairs(
    ideas: list[Idea],
    num_matches: int | None = None,
    *,
    rng: random.Random | None = None,
) -> list[tuple[Idea, Idea]]:
    """Sample random distinct pairs.

    Defaults to ``len(ideas)`` matches when ``num_matches`` is not given.
    """
    all_pairs = list(itertools.combinations(ideas, 2))
    if not all_pairs:
        return []
    if num_matches is None:
        num_matches = len(ideas)
    num_matches = min(num_matches, len(all_pairs))
    return (rng or random).sample(all_pairs, num_matches)


def swiss(
    ideas: list[Idea],
    *,
    previous_pairs: set[frozenset[str]] | None = None,
    match_counts: dict[str, int] | None = None,
    rng: random.Random | None = None,
) -> list[tuple[Idea, Idea]]:
    """Greedily pair nearby ratings, preferring opponents that have not met.

    With an odd field, the lowest-rated idea among those with the most prior
    matches receives the bye. This avoids repeatedly sidelining a prior bye or
    a newly introduced child.
    """
    previous_pairs = previous_pairs or set()
    match_counts = match_counts or {}
    local_rng = rng or random.Random()
    remaining = list(ideas)
    local_rng.shuffle(remaining)
    remaining.sort(key=lambda idea: idea.elo, reverse=True)

    if len(remaining) % 2:
        bye = max(
            remaining,
            key=lambda idea: (match_counts.get(idea.id, 0), -idea.elo),
        )
        remaining.remove(bye)

    pairs: list[tuple[Idea, Idea]] = []
    while remaining:
        idea_a = remaining.pop(0)
        opponent = min(
            remaining,
            key=lambda idea_b: (
                frozenset((idea_a.id, idea_b.id)) in previous_pairs,
                abs(idea_a.elo - idea_b.elo),
            ),
        )
        remaining.remove(opponent)
        pairs.append((idea_a, opponent))
    return pairs


STRATEGIES = {
    "round-robin": round_robin,
    "random": random_pairs,
    "swiss": swiss,
}


def make_pairs(
    ideas: list[Idea],
    strategy: str = "swiss",
    *,
    rng: random.Random | None = None,
    previous_pairs: set[frozenset[str]] | None = None,
    match_counts: dict[str, int] | None = None,
) -> list[tuple[Idea, Idea]]:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown pairing strategy: {strategy!r}. Choose from {list(STRATEGIES)}.")
    if strategy == "random":
        return random_pairs(ideas, rng=rng)
    if strategy == "swiss":
        return swiss(
            ideas,
            previous_pairs=previous_pairs,
            match_counts=match_counts,
            rng=rng,
        )
    pairs = STRATEGIES[strategy](ideas)
    if rng is not None:
        rng.shuffle(pairs)
    return pairs
