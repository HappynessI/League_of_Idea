"""Shared data structures — the contract between modules.

These pydantic models define the shape of every idea, match result and the
overall tournament session that is persisted to disk.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class Idea(BaseModel):
    """A single candidate idea competing in the arena."""

    id: str = Field(default_factory=_new_id)
    content: str
    elo: float = 1200.0
    generation: int = 0
    parent_id: str | None = None
    wins: int = 0
    losses: int = 0
    created_by: str = "unknown"


class MatchResult(BaseModel):
    """Structured verdict the judge model must return for one match."""

    winner: Literal["A", "B"]
    reasoning: str = ""


class Match(BaseModel):
    """A recorded match between two ideas in a given round."""

    round: int
    idea_a_id: str
    idea_b_id: str
    winner_id: str
    reasoning: str = ""


class Session(BaseModel):
    """A full tournament run — the unit of persistence."""

    id: str = Field(default_factory=_new_id)
    goal: str
    num_ideas: int
    rounds: int
    judge_model: str
    generator_model: str
    ideas: list[Idea] = Field(default_factory=list)
    matches: list[Match] = Field(default_factory=list)

    def leaderboard(self) -> list[Idea]:
        """Ideas sorted by Elo, highest first."""
        return sorted(self.ideas, key=lambda i: i.elo, reverse=True)

    def get_idea(self, idea_id: str) -> Idea | None:
        return next((i for i in self.ideas if i.id == idea_id), None)
