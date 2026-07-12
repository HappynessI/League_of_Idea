"""Standard chess Elo rating — pure functions, no external dependencies.

This is the easiest module to unit-test and should stay free of any I/O or LLM
calls. See ``tests/test_elo.py``.
"""

from __future__ import annotations

DEFAULT_K = 32.0
DEFAULT_INITIAL_ELO = 1200.0


def expected_score(rating_a: float, rating_b: float) -> float:
    """Expected win probability of A against B."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def update_ratings(
    rating_a: float,
    rating_b: float,
    score_a: float,
    k: float = DEFAULT_K,
) -> tuple[float, float]:
    """Return updated (rating_a, rating_b) after one match.

    ``score_a`` is the actual result for A: 1.0 win, 0.0 loss, 0.5 draw.
    B's score is the symmetric complement.
    """
    exp_a = expected_score(rating_a, rating_b)
    exp_b = 1.0 - exp_a
    score_b = 1.0 - score_a
    new_a = rating_a + k * (score_a - exp_a)
    new_b = rating_b + k * (score_b - exp_b)
    return new_a, new_b
