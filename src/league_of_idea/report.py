"""Human-readable Markdown reports for persisted tournament sessions."""

from __future__ import annotations

from pathlib import Path

from .models import Session

DEFAULT_REPORT_DIR = Path(".loi_reports")


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _scores(scores: dict[str, float]) -> str:
    return ", ".join(f"{name}={value:g}" for name, value in scores.items()) or "—"


def render_markdown(session: Session) -> str:
    ideas = {idea.id: idea for idea in session.ideas}
    lines = [
        f"# League of Idea Report — {session.id}",
        "",
        f"> {_cell(session.goal)}",
        "",
        "## Run summary",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Status | {session.status} |",
        f"| Completed rounds | {session.completed_rounds} / {session.rounds} |",
        f"| Pairing | {session.pairing_strategy} |",
        f"| Generator | {_cell(session.generator_model)} |",
        f"| Judge | {_cell(session.judge_model)} |",
        f"| Rubric | {_cell(session.rubric.version)} |",
        f"| Usage | {session.usage.calls} calls; {session.usage.total_tokens} tokens |",
        f"| Created | {session.created_at.isoformat()} |",
        f"| Updated | {session.updated_at.isoformat()} |",
        "",
        "## Leaderboard",
        "",
        "| # | Idea id | Elo | W-D-L | Gen | Parent | Idea |",
        "|---:|---|---:|---:|---:|---|---|",
    ]
    for rank, idea in enumerate(session.leaderboard(), start=1):
        lines.append(
            f"| {rank} | {idea.id} | {idea.elo:.1f} | "
            f"{idea.wins}-{idea.draws}-{idea.losses} | {idea.generation} | "
            f"{idea.parent_id or '—'} | {_cell(idea.content)} |"
        )

    lines.extend(
        [
            "",
            "## Judging rubric",
            "",
            "| Criterion | Weight | Description |",
            "|---|---:|---|",
        ]
    )
    for criterion in session.rubric.criteria:
        lines.append(
            f"| {criterion.name} | {criterion.weight:g} | "
            f"{_cell(criterion.description)} |"
        )
    lines.extend(
        [
            "",
            "## Match evidence",
            "",
            "| Round | A | B | Winner | Scores A | Scores B | Confidence | Reasoning |",
            "|---:|---|---|---|---|---|---:|---|",
        ]
    )
    for match in session.matches:
        winner = match.winner_id or "draw"
        idea_a = ideas.get(match.idea_a_id)
        idea_b = ideas.get(match.idea_b_id)
        label_a = f"{match.idea_a_id}: {idea_a.content}" if idea_a else match.idea_a_id
        label_b = f"{match.idea_b_id}: {idea_b.content}" if idea_b else match.idea_b_id
        confidence = "—" if match.confidence is None else f"{match.confidence:.2f}"
        lines.append(
            f"| {match.round} | {_cell(label_a)} | {_cell(label_b)} | {winner} | "
            f"{_cell(_scores(match.scores_a))} | {_cell(_scores(match.scores_b))} | "
            f"{confidence} | {_cell(match.reasoning)} |"
        )

    if session.error:
        lines.extend(["", "## Stop reason", "", _cell(session.error)])
    lines.append("")
    return "\n".join(lines)


def save_report(session: Session, output: Path | None = None) -> Path:
    path = output or DEFAULT_REPORT_DIR / f"{session.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(render_markdown(session), encoding="utf-8")
    temp_path.replace(path)
    return path
