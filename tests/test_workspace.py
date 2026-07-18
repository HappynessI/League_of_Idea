import json
from pathlib import Path

import pytest

from league_of_idea import ingest, research, workspace_report, workspace_storage
from league_of_idea.llm import LLMError
from league_of_idea.workspace_models import (
    EvidenceItem,
    Paper,
    PaperCard,
    ProjectBrief,
    ResearchProject,
)


def _project() -> ResearchProject:
    return ResearchProject(
        title="Test project",
        brief=ProjectBrief(
            direction="Reliable small-model agents",
            keywords=["agents", "reliability"],
            background="Can run local experiments.",
        ),
    )


def _paper(title: str, claim: str) -> Paper:
    evidence = EvidenceItem(claim=claim, source_locator="[L1-L2]", quote="real evidence")
    return Paper(
        title=title,
        source_path=f"/{title}.txt",
        source_type="text",
        source_sha256=title * 8,
        source_text="[L1-L2]\nreal evidence from the paper",
        card=PaperCard(
            research_problem="problem",
            methods=["method"],
            main_innovations=["innovation"],
            limitations=["limitation"],
            relevance="relevant",
            evidence=[evidence],
            analyzed_by="test:model",
        ),
    )


def test_text_ingestion_adds_stable_line_locators(tmp_path):
    path = tmp_path / "paper.md"
    path.write_text("first line\nsecond line", encoding="utf-8")
    source_type, text, digest, truncated = ingest.ingest_file(path)
    assert source_type == "markdown"
    assert text.startswith("[L1-L2]")
    assert ingest.source_locators(text) == {"[L1-L2]"}
    assert len(digest) == 64
    assert truncated is False


def test_project_storage_round_trip(tmp_path):
    project = _project()
    workspace_storage.save_project(project, tmp_path)
    loaded = workspace_storage.load_project(project.id, tmp_path)
    assert loaded == project
    assert workspace_storage.list_projects(tmp_path) == [project.id]


def test_legacy_project_schema_is_upgraded_on_load(tmp_path):
    project = _project()
    payload = project.model_dump()
    payload["schema_version"] = 1
    payload.pop("search_hits")
    (tmp_path / f"{project.id}.json").write_text(json.dumps(payload, default=str), encoding="utf-8")
    loaded = workspace_storage.load_project(project.id, tmp_path)
    assert loaded.schema_version == 2
    assert loaded.search_hits == []


def test_paper_analysis_rejects_invented_quote(monkeypatch):
    project = _project()
    paper = _paper("one", "claim")
    paper.card = None
    project.papers.append(paper)
    monkeypatch.setattr(
        research,
        "_call",
        lambda *args: {
            "research_problem": "problem",
            "methods": ["method"],
            "main_innovations": ["innovation"],
            "limitations": ["limit"],
            "relevance": "relevant",
            "evidence": [
                {"claim": "claim", "source_locator": "[L1-L2]", "quote": "invented"}
            ],
        },
    )
    with pytest.raises(LLMError, match="quotes not found"):
        research.analyze_paper(project, paper.id, "test:model")
    assert paper.card is None


def test_full_research_development_loop(monkeypatch, tmp_path):
    project = _project()
    project.papers = [_paper("one", "claim one"), _paper("two", "claim two")]
    ref = {
        "paper_id": project.papers[0].id,
        "evidence_id": project.papers[0].card.evidence[0].id,
    }

    responses = iter(
        [
            [
                {
                    "title": "Unresolved reliability gap",
                    "description": "Existing methods lack stress testing.",
                    "why_important": "Failures are costly.",
                    "why_unresolved": "Benchmarks are narrow.",
                    "evidence_refs": [ref],
                    "uncertainties": ["Coverage may exist elsewhere."],
                    "validation_actions": ["Search broader literature."],
                    "confidence": 0.6,
                }
            ],
        ]
    )
    monkeypatch.setattr(research, "_call", lambda *args: next(responses))
    gap = research.synthesize_gaps(project, "test:model", count=1)[0]

    spec = {
        "title": "Stress-test agent plans",
        "research_question": "Can adversarial plans predict failures?",
        "motivation": "Current tests are narrow.",
        "gap_ids": [gap.id],
        "evidence_refs": [ref],
        "hypothesis": "Adversarial plans expose more failures.",
        "proposed_method": ["Generate perturbations", "Measure failures"],
        "expected_contributions": ["A stress-test protocol"],
        "evaluation_plan": ["Compare against standard benchmark"],
        "required_resources": ["One GPU"],
        "main_risks": ["Synthetic perturbations may be unrealistic"],
        "falsification_criteria": ["No increase in detected failures"],
        "open_questions": ["Which tasks generalize?"],
    }
    critique = {
        "strengths": ["Falsifiable"],
        "issues": [
            {
                "severity": "major",
                "problem": "No human baseline",
                "recommendation": "Add expert perturbations",
            }
        ],
        "missing_evidence": ["External validity"],
        "verdict": "major-revision",
        "summary": "Promising but incomplete.",
    }
    revised = dict(spec)
    revised["evaluation_plan"] = ["Compare standard, expert, and generated perturbations"]
    responses = iter(
        [
            [spec, {**spec, "title": "Alternative stress test"}],
            critique,
            {"change_summary": "Added expert baseline", "spec": revised},
        ]
    )
    monkeypatch.setattr(research, "_call", lambda *args: next(responses))
    ideas = research.generate_ideas(project, "test:model", count=2)
    review = research.critique_idea(project, ideas[0].id, "review:model")
    version = research.revise_idea(project, ideas[0].id, "test:model")
    decision = research.set_shortlist(
        project, [version.id, ideas[1].latest().id], "Researcher approved."
    )

    assert review.version_id == version.parent_version_id
    assert version.number == 2
    assert len(decision.selected_version_ids) == 2
    report = workspace_report.render_markdown(project)
    assert "AI inference, requires validation" in report
    assert "Researcher approved" in report
    workspace_report.save_report(project, tmp_path / "report.md")


def test_gap_rejects_unknown_evidence_reference(monkeypatch):
    project = _project()
    project.papers = [_paper("one", "a"), _paper("two", "b")]
    monkeypatch.setattr(
        research,
        "_call",
        lambda *args: [
            {
                "title": "gap",
                "description": "desc",
                "why_important": "important",
                "why_unresolved": "unknown",
                "evidence_refs": [{"paper_id": "missing", "evidence_id": "missing"}],
                "confidence": 0.2,
            }
        ],
    )
    with pytest.raises(LLMError, match="Unknown or unanalyzed"):
        research.synthesize_gaps(project, "test:model", 1)
    assert project.gaps == []
