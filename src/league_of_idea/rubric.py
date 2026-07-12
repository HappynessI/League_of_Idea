"""Versioned judging rubrics used to make tournament results interpretable."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, model_validator


class Criterion(BaseModel):
    name: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_-]*$")
    description: str = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0)


class Rubric(BaseModel):
    version: str = Field(min_length=1)
    criteria: list[Criterion] = Field(min_length=1)
    tie_margin: float = Field(default=0.25, ge=0)

    @model_validator(mode="after")
    def unique_names(self) -> "Rubric":
        names = [criterion.name for criterion in self.criteria]
        if len(names) != len(set(names)):
            raise ValueError("Rubric criterion names must be unique.")
        return self

    def weighted_total(self, scores: dict[str, float]) -> float:
        self.validate_scores(scores)
        weight_sum = sum(criterion.weight for criterion in self.criteria)
        return sum(
            scores[criterion.name] * criterion.weight for criterion in self.criteria
        ) / weight_sum

    def validate_scores(self, scores: dict[str, float]) -> None:
        expected = {criterion.name for criterion in self.criteria}
        actual = set(scores)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(f"Rubric score keys mismatch; missing={missing}, extra={extra}.")
        if any(score < 1 or score > 10 for score in scores.values()):
            raise ValueError("Rubric scores must be between 1 and 10.")


DEFAULT_RUBRIC = Rubric(
    version="research-v1",
    criteria=[
        Criterion(
            name="novelty",
            description="Originality and non-obviousness of the core mechanism.",
        ),
        Criterion(
            name="feasibility",
            description="Practical ability to execute, test, or deploy the idea.",
        ),
        Criterion(
            name="relevance",
            description="How directly the idea advances the stated goal.",
        ),
    ],
)


def load_rubric(path: Path | None = None) -> Rubric:
    """Load a JSON rubric or return the built-in research rubric."""
    if path is None:
        return DEFAULT_RUBRIC.model_copy(deep=True)
    return Rubric.model_validate_json(path.read_text(encoding="utf-8"))
