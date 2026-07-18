"""Paper import helpers shared by manual and connector-backed workflows."""

from __future__ import annotations

from pathlib import Path

from . import ingest
from .workspace_models import Paper, ResearchProject


def add_source_file(
    project: ResearchProject,
    path: Path,
    *,
    title: str | None = None,
    authors: list[str] | None = None,
    year: int | None = None,
    external_ids: dict[str, str] | None = None,
    source_url: str | None = None,
    abstract: str | None = None,
) -> Paper:
    """Ingest a local source and append it, rejecting exact duplicate files."""
    source_type, source_text, digest, truncated = ingest.ingest_file(path)
    if any(item.source_sha256 == digest for item in project.papers):
        raise ValueError("This exact paper file is already in the project.")
    paper = Paper(
        title=title or path.stem,
        authors=authors or [],
        year=year,
        source_path=str(path.expanduser().resolve()),
        source_type=source_type,
        source_sha256=digest,
        source_text=source_text,
        external_ids=external_ids or {},
        source_url=source_url,
        abstract=abstract,
        truncated_for_analysis=truncated,
    )
    project.papers.append(paper)
    return paper
