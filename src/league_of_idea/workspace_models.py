"""Versioned research-workspace data contracts for evidence-backed ideation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .pricing import PricingTable
from .runtime import RuntimeConfig
from .usage import BudgetConfig, UsageStats


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def now() -> datetime:
    return datetime.now(timezone.utc)


class ResearchConstraint(BaseModel):
    category: Literal["data", "compute", "time", "skills", "experiment", "ethics", "other"]
    description: str = Field(min_length=1)


class ProjectBrief(BaseModel):
    direction: str = Field(min_length=1)
    keywords: list[str] = Field(min_length=2, max_length=5)
    background: str = ""
    constraints: list[ResearchConstraint] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_keywords(self) -> "ProjectBrief":
        normalized = [keyword.casefold().strip() for keyword in self.keywords]
        if any(not keyword for keyword in normalized):
            raise ValueError("Keywords must not be empty.")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Keywords must be unique.")
        return self


class EvidenceItem(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ev"))
    claim: str = Field(min_length=1)
    source_locator: str = Field(min_length=1)
    quote: str = Field(min_length=1, max_length=500)


class PaperCard(BaseModel):
    research_problem: str = Field(min_length=1)
    methods: list[str] = Field(min_length=1)
    main_innovations: list[str] = Field(min_length=1)
    data_and_evaluation: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(min_length=1)
    relevance: str = Field(min_length=1)
    evidence: list[EvidenceItem] = Field(min_length=1)
    analyzed_by: str
    analyzed_at: datetime = Field(default_factory=now)


class Paper(BaseModel):
    id: str = Field(default_factory=lambda: new_id("paper"))
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    source_path: str
    source_type: Literal["text", "markdown", "pdf"]
    source_sha256: str
    source_text: str = Field(min_length=1)
    external_ids: dict[str, str] = Field(default_factory=dict)
    source_url: str | None = None
    abstract: str | None = None
    truncated_for_analysis: bool = False
    card: PaperCard | None = None
    created_at: datetime = Field(default_factory=now)


class SearchHit(BaseModel):
    """Metadata discovery result; it is not evidence until a full text is imported."""

    id: str = Field(default_factory=lambda: new_id("hit"))
    source: Literal["arxiv", "crossref", "semantic-scholar"]
    external_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    landing_url: str | None = None
    pdf_url: str | None = None
    citation_count: int | None = None
    retrieved_at: datetime = Field(default_factory=now)


class EvidenceReference(BaseModel):
    paper_id: str
    evidence_id: str


class GapHypothesis(BaseModel):
    id: str = Field(default_factory=lambda: new_id("gap"))
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    why_important: str = Field(min_length=1)
    why_unresolved: str = Field(min_length=1)
    evidence_refs: list[EvidenceReference] = Field(min_length=1)
    uncertainties: list[str] = Field(default_factory=list)
    validation_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    created_by: str
    created_at: datetime = Field(default_factory=now)


class IdeaSpec(BaseModel):
    title: str = Field(min_length=1)
    research_question: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    gap_ids: list[str] = Field(min_length=1)
    evidence_refs: list[EvidenceReference] = Field(default_factory=list)
    hypothesis: str = Field(min_length=1)
    proposed_method: list[str] = Field(min_length=1)
    expected_contributions: list[str] = Field(min_length=1)
    evaluation_plan: list[str] = Field(min_length=1)
    required_resources: list[str] = Field(min_length=1)
    main_risks: list[str] = Field(min_length=1)
    falsification_criteria: list[str] = Field(min_length=1)
    open_questions: list[str] = Field(default_factory=list)


class IdeaVersion(BaseModel):
    id: str = Field(default_factory=lambda: new_id("version"))
    number: int = Field(ge=1)
    spec: IdeaSpec
    created_by: str
    change_summary: str = "Initial version"
    parent_version_id: str | None = None
    created_at: datetime = Field(default_factory=now)


class ResearchIdea(BaseModel):
    id: str = Field(default_factory=lambda: new_id("idea"))
    versions: list[IdeaVersion] = Field(min_length=1)
    created_at: datetime = Field(default_factory=now)

    def latest(self) -> IdeaVersion:
        return max(self.versions, key=lambda item: item.number)

    def get_version(self, version_id: str) -> IdeaVersion | None:
        return next((item for item in self.versions if item.id == version_id), None)


class CritiqueIssue(BaseModel):
    severity: Literal["minor", "major", "fatal"]
    problem: str
    recommendation: str


class Critique(BaseModel):
    id: str = Field(default_factory=lambda: new_id("critique"))
    idea_id: str
    version_id: str
    reviewer_role: str
    strengths: list[str] = Field(default_factory=list)
    issues: list[CritiqueIssue]
    missing_evidence: list[str] = Field(default_factory=list)
    verdict: Literal["reject", "major-revision", "minor-revision", "promising"]
    summary: str = Field(min_length=1)
    created_by: str
    created_at: datetime = Field(default_factory=now)


class HumanDecision(BaseModel):
    id: str = Field(default_factory=lambda: new_id("decision"))
    selected_version_ids: list[str] = Field(min_length=2)
    note: str = ""
    decided_at: datetime = Field(default_factory=now)


class ArenaEntry(BaseModel):
    research_idea_id: str
    version_id: str
    arena_idea_id: str


class ProjectArenaRun(BaseModel):
    session_id: str
    entries: list[ArenaEntry]
    status: Literal["running", "completed", "failed", "stopped"]
    created_at: datetime = Field(default_factory=now)


class ResearchProject(BaseModel):
    id: str = Field(default_factory=lambda: new_id("project"))
    schema_version: int = 2
    title: str = Field(min_length=1)
    brief: ProjectBrief
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    usage: UsageStats = Field(default_factory=UsageStats)
    pricing: PricingTable = Field(default_factory=PricingTable)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    papers: list[Paper] = Field(default_factory=list)
    search_hits: list[SearchHit] = Field(default_factory=list)
    gaps: list[GapHypothesis] = Field(default_factory=list)
    ideas: list[ResearchIdea] = Field(default_factory=list)
    critiques: list[Critique] = Field(default_factory=list)
    decisions: list[HumanDecision] = Field(default_factory=list)
    arena_runs: list[ProjectArenaRun] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)

    def get_paper(self, paper_id: str) -> Paper | None:
        return next((item for item in self.papers if item.id == paper_id), None)

    def get_search_hit(self, hit_id: str) -> SearchHit | None:
        return next((item for item in self.search_hits if item.id == hit_id), None)

    def get_gap(self, gap_id: str) -> GapHypothesis | None:
        return next((item for item in self.gaps if item.id == gap_id), None)

    def get_idea(self, idea_id: str) -> ResearchIdea | None:
        return next((item for item in self.ideas if item.id == idea_id), None)

    def find_version(self, version_id: str) -> tuple[ResearchIdea, IdeaVersion] | None:
        for idea in self.ideas:
            version = idea.get_version(version_id)
            if version is not None:
                return idea, version
        return None

    def latest_decision(self) -> HumanDecision | None:
        return self.decisions[-1] if self.decisions else None
