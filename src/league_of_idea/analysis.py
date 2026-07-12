"""Post-tournament attribution summaries."""

from __future__ import annotations

from pydantic import BaseModel

from .models import Idea, Session


class CreatorStats(BaseModel):
    model: str
    ideas: int
    average_elo: float
    best_elo: float
    wins: int
    draws: int
    losses: int


def creator_attribution(session: Session) -> list[CreatorStats]:
    """Aggregate idea performance by the model that created each idea."""
    grouped: dict[str, list[Idea]] = {}
    for idea in session.ideas:
        grouped.setdefault(idea.created_by, []).append(idea)
    rows = [
        CreatorStats(
            model=model,
            ideas=len(ideas),
            average_elo=sum(idea.elo for idea in ideas) / len(ideas),
            best_elo=max(idea.elo for idea in ideas),
            wins=sum(idea.wins for idea in ideas),
            draws=sum(idea.draws for idea in ideas),
            losses=sum(idea.losses for idea in ideas),
        )
        for model, ideas in grouped.items()
    ]
    return sorted(rows, key=lambda row: (-row.average_elo, row.model))
