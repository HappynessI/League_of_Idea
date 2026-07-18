"""Markdown export for evidence-backed research projects."""

from __future__ import annotations

from pathlib import Path

from .workspace_models import EvidenceReference, IdeaSpec, ResearchProject

DEFAULT_REPORT_DIR = Path(".loi_project_reports")


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _refs(refs: list[EvidenceReference]) -> str:
    return ", ".join(f"{ref.paper_id}/{ref.evidence_id}" for ref in refs) or "—"


def _bullets(values: list[str]) -> list[str]:
    return [f"- {_cell(value)}" for value in values] or ["- —"]


def render_markdown(project: ResearchProject) -> str:
    brief = project.brief
    lines = [
        f"# Research Idea Workspace — {_cell(project.title)}",
        "",
        f"Project id: `{project.id}`",
        "",
        "## Research brief",
        "",
        f"**Direction:** {_cell(brief.direction)}",
        "",
        f"**Keywords:** {', '.join(map(_cell, brief.keywords))}",
        "",
        f"**Background:** {_cell(brief.background) or '—'}",
        "",
        "### Real-world constraints",
        "",
        *(
            [f"- **{item.category}:** {_cell(item.description)}" for item in brief.constraints]
            or ["- —"]
        ),
        "",
        "## Paper cards and evidence",
        "",
    ]
    lines.extend(["## Literature discovery (metadata only)", ""])
    if project.search_hits:
        lines.extend(["These records are discovery leads, not evidence, until full text is imported.", ""])
        for hit in project.search_hits:
            pdf = f" · PDF: {hit.pdf_url}" if hit.pdf_url else ""
            doi = f" · DOI: {hit.doi}" if hit.doi else ""
            lines.append(
                f"- `{hit.id}` **{_cell(hit.title)}** ({hit.source}, {hit.year or 'year n/a'}){doi}{pdf}"
            )
    else:
        lines.append("No search results saved yet.")
    lines.append("")
    for paper in project.papers:
        lines.extend([f"### {_cell(paper.title)} (`{paper.id}`)", ""])
        if paper.card is None:
            lines.extend(["Not analyzed.", ""])
            continue
        card = paper.card
        lines.extend(
            [
                f"**Research problem:** {_cell(card.research_problem)}",
                "",
                f"**Methods:** {'; '.join(map(_cell, card.methods))}",
                "",
                "**Main innovations:**",
                "",
                *_bullets(card.main_innovations),
                "",
                "**Data and evaluation:**",
                "",
                *_bullets(card.data_and_evaluation),
                "",
                "**Limitations:**",
                "",
                *_bullets(card.limitations),
                "",
                f"**Relevance:** {_cell(card.relevance)}",
                "",
                "| Evidence id | Locator | Supported claim | Short quote |",
                "|---|---|---|---|",
            ]
        )
        for evidence in card.evidence:
            lines.append(
                f"| {evidence.id} | {_cell(evidence.source_locator)} | "
                f"{_cell(evidence.claim)} | {_cell(evidence.quote)} |"
            )
        lines.append("")

    lines.extend(["## Gap hypotheses (AI inference, requires validation)", ""])
    for gap in project.gaps:
        lines.extend(
            [
                f"### {_cell(gap.title)} (`{gap.id}`)",
                "",
                _cell(gap.description),
                "",
                f"**Why important:** {_cell(gap.why_important)}",
                "",
                f"**Why unresolved:** {_cell(gap.why_unresolved)}",
                "",
                f"**Evidence:** {_refs(gap.evidence_refs)}",
                "",
                f"**Confidence:** {gap.confidence:.2f}",
                "",
                "**Uncertainties:**",
                "",
                *_bullets(gap.uncertainties),
                "",
                "**Validation actions:**",
                "",
                *_bullets(gap.validation_actions),
                "",
            ]
        )

    lines.extend(["## Versioned research ideas", ""])
    for idea in project.ideas:
        lines.extend([f"### Idea `{idea.id}`", ""])
        for version in sorted(idea.versions, key=lambda item: item.number):
            lines.extend(
                _render_version(
                    version.id, version.number, version.spec, version.change_summary
                )
            )
        related = [item for item in project.critiques if item.idea_id == idea.id]
        for critique in related:
            lines.extend(
                [
                    f"#### Critique `{critique.id}` — {critique.reviewer_role}",
                    "",
                    f"Version: `{critique.version_id}` · Verdict: **{critique.verdict}**",
                    "",
                    _cell(critique.summary),
                    "",
                    *[
                        f"- **{issue.severity}:** {_cell(issue.problem)} → "
                        f"{_cell(issue.recommendation)}"
                        for issue in critique.issues
                    ],
                    "",
                ]
            )

    decision = project.latest_decision()
    lines.extend(["## Human shortlist", ""])
    if decision:
        lines.extend(
            [
                f"Decision `{decision.id}` at {decision.decided_at.isoformat()}",
                "",
                *[f"- `{version_id}`" for version_id in decision.selected_version_ids],
                "",
                f"Note: {_cell(decision.note) or '—'}",
            ]
        )
    else:
        lines.append("No shortlist decision yet.")
    lines.extend(["", "## Arena runs", ""])
    if project.arena_runs:
        for run in project.arena_runs:
            lines.append(
                f"- Session `{run.session_id}` ({run.status}) with "
                f"{len(run.entries)} frozen entries"
            )
    else:
        lines.append("No Arena run yet.")
    lines.extend(
        [
            "",
            "## Usage",
            "",
            f"{project.usage.calls} calls; {project.usage.total_tokens} tokens; "
            f"${project.usage.estimated_cost_usd:.4f} estimated cost.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_version(
    version_id: str, number: int, spec: IdeaSpec, change_summary: str
) -> list[str]:
    return [
        f"#### v{number}: {_cell(spec.title)} (`{version_id}`)",
        "",
        f"**Change:** {_cell(change_summary)}",
        "",
        f"**Research question:** {_cell(spec.research_question)}",
        "",
        f"**Motivation:** {_cell(spec.motivation)}",
        "",
        f"**Hypothesis:** {_cell(spec.hypothesis)}",
        "",
        f"**Gap ids:** {', '.join(spec.gap_ids)}",
        "",
        f"**Evidence:** {_refs(spec.evidence_refs)}",
        "",
        "**Proposed method:**",
        "",
        *_bullets(spec.proposed_method),
        "",
        "**Expected contributions:**",
        "",
        *_bullets(spec.expected_contributions),
        "",
        "**Evaluation plan:**",
        "",
        *_bullets(spec.evaluation_plan),
        "",
        "**Required resources:**",
        "",
        *_bullets(spec.required_resources),
        "",
        "**Risks:**",
        "",
        *_bullets(spec.main_risks),
        "",
        "**Falsification criteria:**",
        "",
        *_bullets(spec.falsification_criteria),
        "",
        "**Open questions:**",
        "",
        *_bullets(spec.open_questions),
        "",
    ]


def save_report(project: ResearchProject, output: Path | None = None) -> Path:
    path = output or DEFAULT_REPORT_DIR / f"{project.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(render_markdown(project), encoding="utf-8")
    temp_path.replace(path)
    return path
