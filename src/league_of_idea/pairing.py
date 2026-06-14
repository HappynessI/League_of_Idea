"""Pairing strategies — who plays whom.

MVP supports ``round_robin`` (every pair once, fairest) and ``random`` (cheaper).
Swiss pairing is planned but not yet implemented.
"""

from __future__ import annotations

import itertools
import random

from .models import Idea


def round_robin(ideas: list[Idea]) -> list[tuple[Idea, Idea]]:
    """Every distinct pair plays exactly once. Pairs grow ~O(n^2)."""
    return list(itertools.combinations(ideas, 2))


def random_pairs(ideas: list[Idea], num_matches: int | None = None) -> list[tuple[Idea, Idea]]:
    """Sample random distinct pairs.

    Defaults to ``len(ideas)`` matches when ``num_matches`` is not given.
    """
    all_pairs = list(itertools.combinations(ideas, 2))
    if not all_pairs:
        return []
    if num_matches is None:
        num_matches = len(ideas)
    num_matches = min(num_matches, len(all_pairs))
    return random.sample(all_pairs, num_matches)


def swiss(ideas: list[Idea]) -> list[tuple[Idea, Idea]]:  # pragma: no cover - planned
    """Pair ideas with nearby Elo. NOT YET IMPLEMENTED."""
    raise NotImplementedError("Swiss pairing is on the roadmap, not yet implemented.")


STRATEGIES = {
    "round-robin": round_robin,
    "random": random_pairs,
}


def make_pairs(ideas: list[Idea], strategy: str = "round-robin") -> list[tuple[Idea, Idea]]:
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown pairing strategy: {strategy!r}. Choose from {list(STRATEGIES)}.")
    return STRATEGIES[strategy](ideas)
