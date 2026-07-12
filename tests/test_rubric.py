import pytest
from pydantic import ValidationError

from league_of_idea.rubric import Criterion, Rubric, load_rubric


def test_weighted_total_uses_configured_weights():
    rubric = Rubric(
        version="test-v1",
        criteria=[
            Criterion(name="quality", description="quality", weight=3),
            Criterion(name="cost", description="cost", weight=1),
        ],
    )

    assert rubric.weighted_total({"quality": 9, "cost": 1}) == 7


def test_score_keys_must_match_rubric():
    rubric = load_rubric()

    with pytest.raises(ValueError, match="keys mismatch"):
        rubric.weighted_total({"novelty": 5})


def test_criterion_names_are_unique():
    with pytest.raises(ValidationError, match="unique"):
        Rubric(
            version="bad",
            criteria=[
                Criterion(name="same", description="one"),
                Criterion(name="same", description="two"),
            ],
        )
