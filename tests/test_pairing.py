import random

from league_of_idea import pairing
from league_of_idea.models import Idea


def _idea(name: str, elo: float) -> Idea:
    return Idea(id=name, content=name, elo=elo)


def test_swiss_pairs_every_even_field_idea_once():
    ideas = [_idea(str(index), 1200 - index * 10) for index in range(6)]

    pairs = pairing.swiss(ideas, rng=random.Random(1))

    flattened = [idea.id for pair in pairs for idea in pair]
    assert len(pairs) == 3
    assert sorted(flattened) == sorted(idea.id for idea in ideas)


def test_swiss_avoids_repeat_opponents_when_possible():
    ideas = [_idea(str(index), 1200 - index * 10) for index in range(4)]
    previous = {frozenset(("0", "1")), frozenset(("2", "3"))}

    pairs = pairing.swiss(
        ideas,
        previous_pairs=previous,
        rng=random.Random(1),
    )

    assert all(frozenset((a.id, b.id)) not in previous for a, b in pairs)


def test_swiss_bye_prefers_an_idea_with_more_previous_matches():
    ideas = [_idea("high", 1300), _idea("mid", 1200), _idea("low", 1100)]

    pairs = pairing.swiss(
        ideas,
        match_counts={"high": 2, "mid": 2, "low": 1},
        rng=random.Random(1),
    )

    paired_ids = {idea.id for pair in pairs for idea in pair}
    assert "mid" not in paired_ids
    assert "low" in paired_ids
