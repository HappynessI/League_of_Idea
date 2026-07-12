"""Shared data structures — the contract between modules.

These pydantic models define the shape of every idea, match result and the
overall tournament session that is persisted to disk.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from .rubric import DEFAULT_RUBRIC, Rubric
from .pricing import PricingTable
from .usage import BudgetConfig, UsageStats


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Idea(BaseModel):
    """A single candidate idea competing in the arena."""

    id: str = Field(default_factory=_new_id)
    content: str
    elo: float = 1200.0
    generation: int = 0
    parent_id: str | None = None
    created_in_round: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    created_by: str = "unknown"


class MatchResult(BaseModel):
    """Structured verdict the judge model must return for one match."""

    winner: Literal["A", "B", "draw"]
    reasoning: str = ""
    scores_a: dict[str, float] = Field(default_factory=dict)
    scores_b: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    disputed: bool = False
    evaluations: int = Field(default=1, ge=1)


class Match(BaseModel):
    """A recorded match between two ideas in a given round."""

    round: int
    idea_a_id: str
    idea_b_id: str
    winner_id: str | None = None
    reasoning: str = ""
    scores_a: dict[str, float] = Field(default_factory=dict)
    scores_b: dict[str, float] = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0, le=1)
    rubric_version: str = "legacy"
    judge_model: str = "unknown"
    disputed: bool = False
    evaluations: int = Field(default=1, ge=1)


class Session(BaseModel):
    """A full tournament run — the unit of persistence."""

    id: str = Field(default_factory=_new_id)
    schema_version: int = 4
    status: Literal["running", "completed", "failed", "stopped"] = "running"
    goal: str
    num_ideas: int
    rounds: int
    judge_model: str
    generator_model: str
    rubric: Rubric = Field(default_factory=lambda: DEFAULT_RUBRIC.model_copy(deep=True))
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    usage: UsageStats = Field(default_factory=UsageStats)
    pricing: PricingTable = Field(default_factory=PricingTable)
    pairing_strategy: str = "swiss"
    double_judge: bool = False
    dedup_threshold: float = Field(default=0.86, ge=0, le=1)
    max_concurrency: int = Field(default=1, ge=1)
    k: float = 32.0
    evolve: bool = True
    evolve_top: int = 2
    seed: int | None = None
    completed_rounds: int = 0
    pairing_plans: dict[int, list[tuple[str, str]]] = Field(default_factory=dict)
    pending_results: dict[str, MatchResult] = Field(default_factory=dict)
    evolution_plans: dict[int, list[str]] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    ideas: list[Idea] = Field(default_factory=list)
    matches: list[Match] = Field(default_factory=list)

    def leaderboard(self) -> list[Idea]:
        """Ideas sorted by Elo, highest first."""
        return sorted(self.ideas, key=lambda i: i.elo, reverse=True)

    def get_idea(self, idea_id: str) -> Idea | None:
        return next((i for i in self.ideas if i.id == idea_id), None)
