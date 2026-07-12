"""Unit tests for the pure Elo module."""

from league_of_idea import elo


def test_expected_score_symmetry():
    a, b = 1200.0, 1200.0
    assert elo.expected_score(a, b) == 0.5


def test_expected_score_favors_higher():
    assert elo.expected_score(1600, 1200) > 0.5
    assert elo.expected_score(1200, 1600) < 0.5


def test_update_conserves_points():
    a, b = 1200.0, 1200.0
    new_a, new_b = elo.update_ratings(a, b, score_a=1.0, k=32)
    # Equal start, A wins: A gains exactly what B loses.
    assert round(new_a + new_b, 6) == round(a + b, 6)
    assert new_a > a > new_b


def test_upset_moves_more_than_expected_win():
    # Underdog winning gains more than a favorite winning.
    underdog_gain = elo.update_ratings(1200, 1600, score_a=1.0)[0] - 1200
    favorite_gain = elo.update_ratings(1600, 1200, score_a=1.0)[0] - 1600
    assert underdog_gain > favorite_gain


def test_draw_nudges_toward_each_other():
    new_a, new_b = elo.update_ratings(1600, 1200, score_a=0.5)
    assert new_a < 1600
    assert new_b > 1200
