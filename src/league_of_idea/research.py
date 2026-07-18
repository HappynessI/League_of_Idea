"""Evidence-backed LLM workflows for developing research ideas."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field

from . import llm
from .ingest import MAX_ANALYSIS_CHARS, locator_segments, source_locators
from .runtime import RuntimeController
from .usage import UsageTracker
from .workspace_models import (
    Critique,
    CritiqueIssue,
    EvidenceItem,
    EvidenceReference,
    GapHypothesis,
    IdeaSpec,
    IdeaVersion,
    PaperCard,
    ResearchIdea,
    ResearchProject,
)

SYSTEM = (
    "You are a rigorous research collaborator. Separate source-supported facts "
    "from inference, never invent citations, and treat uncertainty explicitly."
)


class _RawEvidence(BaseModel):
    claim: str
    source_locator: str
    quote: str = Field(max_length=500)


class _RawPaperCard(BaseModel):
    research_problem: str
    methods: list[str]
    main_innovations: list[str]
    data_and_evaluation: list[str] = Field(default_factory=list)
    limitations: list[str]
    relevance: str
    evidence: list[_RawEvidence] = Field(min_length=1)


class _RawGap(BaseModel):
    title: str
    description: str
    why_important: str
    why_unresolved: str
    evidence_refs: list[EvidenceReference] = Field(min_length=1)
    uncertainties: list[str] = Field(default_factory=list)
    validation_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class _RawCritique(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    issues: list[CritiqueIssue]
    missing_evidence: list[str] = Field(default_factory=list)
    verdict: Literal["reject", "major-revision", "minor-revision", "promising"]
    summary: str


class _RawRevision(BaseModel):
    change_summary: str
    spec: IdeaSpec


def _call(project: ResearchProject, model: str, prompt: str):
    tracker = UsageTracker(project.budget, project.usage, project.pricing)
    runtime = RuntimeController(project.runtime)
    return llm.complete_json(
        model, prompt, system=SYSTEM, usage_tracker=tracker, runtime=runtime
    )


def analyze_paper(project: ResearchProject, paper_id: str, model: str) -> PaperCard:
    paper = project.get_paper(paper_id)
    if paper is None:
        raise ValueError(f"Unknown paper id: {paper_id}")
    analysis_text = paper.source_text[:MAX_ANALYSIS_CHARS]
    prompt = f"""Project brief:
{project.brief.model_dump_json(indent=2)}

Paper title: {paper.title}
Locator-labelled source:
{analysis_text}

Create a structured paper card. Every evidence item must use one exact locator
visible above and a short verbatim quote from that locator. Limitations must be
the paper's stated or directly observable limitations; label cautious inference
in the wording. Return only JSON matching this schema:
{json.dumps(_RawPaperCard.model_json_schema(), ensure_ascii=False)}
"""
    raw = _RawPaperCard.model_validate(_call(project, model, prompt))
    allowed = source_locators(analysis_text)
    invalid = [item.source_locator for item in raw.evidence if item.source_locator not in allowed]
    if invalid:
        raise llm.LLMError(f"Paper analysis invented source locators: {invalid}")
    segments = locator_segments(analysis_text)
    false_quotes = [
        item.quote
        for item in raw.evidence
        if _normalize(item.quote) not in _normalize(segments[item.source_locator])
    ]
    if false_quotes:
        raise llm.LLMError("Paper analysis returned quotes not found at their locators.")
    card = PaperCard(
        **raw.model_dump(exclude={"evidence"}),
        evidence=[EvidenceItem(**item.model_dump()) for item in raw.evidence],
        analyzed_by=model,
    )
    paper.card = card
    return card


def synthesize_gaps(
    project: ResearchProject, model: str, count: int = 5
) -> list[GapHypothesis]:
    cards = [paper for paper in project.papers if paper.card is not None]
    if len(cards) < 2:
        raise ValueError("Analyze at least two papers before synthesizing gaps.")
    evidence_catalog = [
        {
            "paper_id": paper.id,
            "title": paper.title,
            "card": paper.card.model_dump(mode="json"),
        }
        for paper in cards
    ]
    prompt = f"""Project brief:
{project.brief.model_dump_json(indent=2)}

Evidence-backed paper cards:
{json.dumps(evidence_catalog, ensure_ascii=False)}

Propose exactly {count} gap hypotheses. A gap is an inference to validate, not a
fact. Reference only paper_id/evidence_id pairs present above. Include contrary
signals, uncertainty, and concrete validation actions. Return only a JSON array
whose items match this schema:
{json.dumps(_RawGap.model_json_schema(), ensure_ascii=False)}
"""
    data = _call(project, model, prompt)
    if not isinstance(data, list):
        raise llm.LLMError("Gap synthesis must return a JSON array.")
    raw_gaps = [_RawGap.model_validate(item) for item in data]
    if len(raw_gaps) != count:
        raise llm.LLMError(f"Requested {count} gaps, but the model returned {len(raw_gaps)}.")
    if len({gap.title.casefold().strip() for gap in raw_gaps}) != len(raw_gaps):
        raise llm.LLMError("Gap synthesis returned duplicate titles.")
    for raw in raw_gaps:
        _validate_evidence_refs(project, raw.evidence_refs)
    gaps = [GapHypothesis(**raw.model_dump(), created_by=model) for raw in raw_gaps]
    project.gaps.extend(gaps)
    return gaps


def generate_ideas(
    project: ResearchProject, model: str, count: int = 5
) -> list[ResearchIdea]:
    if not project.gaps:
        raise ValueError("Synthesize at least one gap before generating ideas.")
    prompt = f"""Project brief and real-world constraints:
{project.brief.model_dump_json(indent=2)}

Gap hypotheses:
{json.dumps([gap.model_dump(mode='json') for gap in project.gaps], ensure_ascii=False)}

Evidence catalog:
{json.dumps(_evidence_catalog(project), ensure_ascii=False)}

Create exactly {count} distinct, executable research ideas. Each must include a
falsifiable hypothesis, evaluation plan, resources, risks and falsification
criteria. Reference only listed gap ids and valid evidence refs. Do not promise
novelty as a fact. Return only a JSON array matching this item schema:
{json.dumps(IdeaSpec.model_json_schema(), ensure_ascii=False)}
"""
    data = _call(project, model, prompt)
    if not isinstance(data, list):
        raise llm.LLMError("Idea generation must return a JSON array.")
    if len(data) != count:
        raise llm.LLMError(f"Requested {count} ideas, but the model returned {len(data)}.")
    ideas: list[ResearchIdea] = []
    for item in data:
        spec = IdeaSpec.model_validate(item)
        _validate_idea_spec(project, spec)
        version = IdeaVersion(number=1, spec=spec, created_by=model)
        ideas.append(ResearchIdea(versions=[version]))
    titles = [idea.latest().spec.title.casefold().strip() for idea in ideas]
    if len(set(titles)) != len(titles):
        raise llm.LLMError("Idea generation returned duplicate titles.")
    project.ideas.extend(ideas)
    return ideas


def critique_idea(
    project: ResearchProject,
    idea_id: str,
    model: str,
    reviewer_role: str = "strict-reviewer",
) -> Critique:
    idea = project.get_idea(idea_id)
    if idea is None:
        raise ValueError(f"Unknown idea id: {idea_id}")
    version = idea.latest()
    prompt = f"""Act as {reviewer_role}. Review this research idea against the
project evidence and constraints. Look for unsupported novelty, mismatched
method/question, weak baselines, non-falsifiable evaluation, resource mismatch,
and hallucinated evidence.

Brief: {project.brief.model_dump_json(indent=2)}
Gaps: {json.dumps([gap.model_dump(mode='json') for gap in project.gaps], ensure_ascii=False)}
Evidence catalog: {json.dumps(_evidence_catalog(project), ensure_ascii=False)}
Idea: {version.spec.model_dump_json(indent=2)}

Verdict must be one of reject, major-revision, minor-revision, promising.
Return only JSON matching:
{json.dumps(_RawCritique.model_json_schema(), ensure_ascii=False)}
"""
    raw = _RawCritique.model_validate(_call(project, model, prompt))
    critique = Critique(
        idea_id=idea.id,
        version_id=version.id,
        reviewer_role=reviewer_role,
        created_by=model,
        **raw.model_dump(),
    )
    project.critiques.append(critique)
    return critique


def revise_idea(project: ResearchProject, idea_id: str, model: str) -> IdeaVersion:
    idea = project.get_idea(idea_id)
    if idea is None:
        raise ValueError(f"Unknown idea id: {idea_id}")
    current = idea.latest()
    critiques = [item for item in project.critiques if item.version_id == current.id]
    if not critiques:
        raise ValueError("Critique the latest idea version before revising it.")
    prompt = f"""Revise the idea using the critiques, while preserving strong
parts and respecting the evidence and project constraints. Do not claim that a
critique has been resolved unless the revised content actually addresses it.

Current idea: {current.spec.model_dump_json(indent=2)}
Critiques: {json.dumps([item.model_dump(mode='json') for item in critiques], ensure_ascii=False)}
Available gaps:
{json.dumps([gap.model_dump(mode='json') for gap in project.gaps], ensure_ascii=False)}
Evidence catalog:
{json.dumps(_evidence_catalog(project), ensure_ascii=False)}

Return only JSON matching:
{json.dumps(_RawRevision.model_json_schema(), ensure_ascii=False)}
"""
    raw = _RawRevision.model_validate(_call(project, model, prompt))
    _validate_idea_spec(project, raw.spec)
    version = IdeaVersion(
        number=current.number + 1,
        spec=raw.spec,
        created_by=model,
        change_summary=raw.change_summary,
        parent_version_id=current.id,
    )
    idea.versions.append(version)
    return version


def set_shortlist(
    project: ResearchProject, version_ids: list[str], note: str = ""
):
    from .workspace_models import HumanDecision

    unique_ids = list(dict.fromkeys(version_ids))
    if len(unique_ids) < 2:
        raise ValueError("Shortlist at least two distinct idea versions.")
    found = [project.find_version(version_id) for version_id in unique_ids]
    missing = [
        version_id
        for version_id, result in zip(unique_ids, found, strict=True)
        if result is None
    ]
    if missing:
        raise ValueError(f"Unknown idea version ids: {missing}")
    idea_ids = [result[0].id for result in found if result is not None]
    if len(set(idea_ids)) != len(idea_ids):
        raise ValueError("Select at most one version from each research idea.")
    decision = HumanDecision(selected_version_ids=unique_ids, note=note)
    project.decisions.append(decision)
    return decision


def _validate_evidence_refs(
    project: ResearchProject, refs: list[EvidenceReference]
) -> None:
    for ref in refs:
        paper = project.get_paper(ref.paper_id)
        if paper is None or paper.card is None:
            raise llm.LLMError(f"Unknown or unanalyzed paper reference: {ref.paper_id}")
        if not any(item.id == ref.evidence_id for item in paper.card.evidence):
            raise llm.LLMError(
                f"Unknown evidence reference: {ref.paper_id}/{ref.evidence_id}"
            )


def _validate_idea_spec(project: ResearchProject, spec: IdeaSpec) -> None:
    missing_gaps = [gap_id for gap_id in spec.gap_ids if project.get_gap(gap_id) is None]
    if missing_gaps:
        raise llm.LLMError(f"Idea references unknown gaps: {missing_gaps}")
    _validate_evidence_refs(project, spec.evidence_refs)


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _evidence_catalog(project: ResearchProject) -> list[dict[str, object]]:
    return [
        {
            "paper_id": paper.id,
            "paper_title": paper.title,
            "evidence": [item.model_dump(mode="json") for item in paper.card.evidence],
        }
        for paper in project.papers
        if paper.card is not None
    ]
