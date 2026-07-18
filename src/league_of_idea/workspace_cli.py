"""Nested CLI commands for the Research Idea Workspace."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import arena_bridge, connectors, paper_service, research, workspace_report, workspace_storage
from .llm import LLMError
from .pricing import load_pricing
from .rubric import RESEARCH_WORKSPACE_RUBRIC, load_rubric
from .runtime import RuntimeConfig
from .usage import BudgetConfig, BudgetExceeded
from .workspace_models import ProjectBrief, ResearchConstraint, ResearchProject, SearchHit

project_app = typer.Typer(help="Manage evidence-backed research projects.")
paper_app = typer.Typer(help="Import and analyze representative papers.")
gap_app = typer.Typer(help="Synthesize evidence-linked research gap hypotheses.")
idea_app = typer.Typer(help="Generate, critique, and revise versioned research ideas.")
shortlist_app = typer.Typer(help="Record the researcher's explicit Arena shortlist.")
arena_app = typer.Typer(help="Run shortlisted mature ideas in the Arena.")
console = Console()


def register(app: typer.Typer) -> None:
    app.add_typer(project_app, name="project")
    app.add_typer(paper_app, name="paper")
    app.add_typer(gap_app, name="gap")
    app.add_typer(idea_app, name="idea")
    app.add_typer(shortlist_app, name="shortlist")
    app.add_typer(arena_app, name="arena")


def _constraint(value: str) -> ResearchConstraint:
    if ":" not in value:
        raise ValueError("Constraints use category:description, e.g. compute:one GPU.")
    category, description = value.split(":", 1)
    return ResearchConstraint(category=category.strip(), description=description.strip())


def _load(project_id: str, projects_dir: Path) -> ResearchProject:
    try:
        return workspace_storage.load_project(project_id, projects_dir)
    except FileNotFoundError as exc:
        console.print(f"[bold red]Project lookup failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


def _ai_failure(exc: Exception, action: str) -> None:
    console.print(f"[bold red]{action} failed:[/bold red] {exc}")
    raise typer.Exit(code=1) from exc


def _search_hit_keys(hit: SearchHit) -> set[str]:
    keys = {f"{hit.source}:{hit.external_id.casefold()}"}
    if hit.doi:
        keys.add(f"doi:{hit.doi.casefold().removeprefix('https://doi.org/')}")
    return keys


def _print_search_hits(hits: list[SearchHit]) -> None:
    if not hits:
        console.print("[yellow]No literature results found.[/yellow]")
        return
    table = Table(title="Literature discovery results (metadata only)")
    table.add_column("Result")
    table.add_column("Source")
    table.add_column("Year")
    table.add_column("Title", overflow="fold")
    table.add_column("PDF")
    for hit in hits:
        table.add_row(hit.id, hit.source, str(hit.year or "—"), hit.title, "yes" if hit.pdf_url else "—")
    console.print(table)


@project_app.command("init")
def project_init(
    title: str = typer.Option(..., "--title"),
    direction: str = typer.Option(..., "--direction"),
    keywords: list[str] = typer.Option(..., "--keyword", help="Repeat 2–5 times."),
    background: str = typer.Option("", "--background"),
    constraints: list[str] = typer.Option([], "--constraint", help="category:description"),
    success_criteria: list[str] = typer.Option([], "--success-criterion"),
    max_calls: int | None = typer.Option(None, "--max-calls"),
    max_tokens: int | None = typer.Option(None, "--max-tokens"),
    max_cost_usd: float | None = typer.Option(None, "--max-cost-usd"),
    pricing_file: Path | None = typer.Option(None, "--pricing-file"),
    timeout_seconds: float = typer.Option(60.0, "--timeout-seconds"),
    max_retries: int = typer.Option(2, "--max-retries"),
    requests_per_second: float | None = typer.Option(None, "--requests-per-second"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    """Create a project brief before asking AI to generate anything."""
    try:
        brief = ProjectBrief(
            direction=direction,
            keywords=keywords,
            background=background,
            constraints=[_constraint(value) for value in constraints],
            success_criteria=success_criteria,
        )
        project = ResearchProject(
            title=title,
            brief=brief,
            budget=BudgetConfig(
                max_calls=max_calls, max_tokens=max_tokens, max_cost_usd=max_cost_usd
            ),
            pricing=load_pricing(pricing_file),
            runtime=RuntimeConfig(
                request_timeout_seconds=timeout_seconds,
                max_retries=max_retries,
                requests_per_second=requests_per_second,
            ),
        )
        workspace_storage.save_project(project, projects_dir)
    except (OSError, ValueError) as exc:
        _ai_failure(exc, "Project creation")
    console.print(f"Project created: [bold cyan]{project.id}[/bold cyan]")


@project_app.command("list")
def project_list(
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    project_ids = workspace_storage.list_projects(projects_dir)
    if not project_ids:
        console.print("[yellow]No research projects found.[/yellow]")
        return
    for project_id in project_ids:
        project = _load(project_id, projects_dir)
        console.print(f"{project.id}\t{project.title}")


@project_app.command("show")
def project_show(
    project_id: str = typer.Option(..., "--project", "-p"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    project = _load(project_id, projects_dir)
    table = Table(title=f"Research project — {project.title}")
    table.add_column("Field")
    table.add_column("Value", overflow="fold")
    table.add_row("Project", project.id)
    table.add_row("Direction", project.brief.direction)
    table.add_row("Keywords", ", ".join(project.brief.keywords))
    analyzed = sum(paper.card is not None for paper in project.papers)
    table.add_row("Papers", f"{analyzed}/{len(project.papers)} analyzed")
    table.add_row("Search hits", str(len(project.search_hits)))
    table.add_row("Gaps", str(len(project.gaps)))
    table.add_row("Ideas", str(len(project.ideas)))
    table.add_row("Critiques", str(len(project.critiques)))
    decision = project.latest_decision()
    table.add_row(
        "Shortlisted", str(len(decision.selected_version_ids) if decision else 0)
    )
    table.add_row("Arena runs", str(len(project.arena_runs)))
    console.print(table)


@project_app.command("report")
def project_report(
    project_id: str = typer.Option(..., "--project", "-p"),
    output: Path | None = typer.Option(None, "--output", "-o"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    project = _load(project_id, projects_dir)
    path = workspace_report.save_report(project, output)
    console.print(f"Project report written to [bold cyan]{path}[/bold cyan]")


@paper_app.command("add")
def paper_add(
    project_id: str = typer.Option(..., "--project", "-p"),
    file: Path = typer.Option(..., "--file", exists=True, dir_okay=False),
    title: str | None = typer.Option(None, "--title"),
    authors: list[str] = typer.Option([], "--author"),
    year: int | None = typer.Option(None, "--year"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    try:
        project = _load(project_id, projects_dir)
        paper = paper_service.add_source_file(
            project, file, title=title, authors=authors, year=year
        )
        workspace_storage.save_project(project, projects_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        _ai_failure(exc, "Paper import")
    console.print(f"Paper added: [bold cyan]{paper.id}[/bold cyan] ({paper.title})")


@paper_app.command("search")
def paper_search(
    project_id: str = typer.Option(..., "--project", "-p"),
    query: str = typer.Argument(..., help="Topic, title, author, or keywords."),
    sources: list[str] = typer.Option(
        ["arxiv", "crossref", "semantic-scholar"], "--source", "-s",
        help="Repeat --source or pass a comma-separated list.",
    ),
    limit: int = typer.Option(10, "--limit", min=1, max=50),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    """Discover scholarly metadata; results are not evidence until imported."""
    project = _load(project_id, projects_dir)
    selected = [source for value in sources for source in value.split(",") if source.strip()]
    try:
        hits = connectors.search(query, sources=selected, limit=limit, runtime=project.runtime)
    except (connectors.ConnectorError, ValueError) as exc:
        _ai_failure(exc, "Literature search")
    existing = {key for hit in project.search_hits for key in _search_hit_keys(hit)}
    added = 0
    for hit in hits:
        if existing & _search_hit_keys(hit):
            continue
        project.search_hits.append(hit)
        existing.update(_search_hit_keys(hit))
        added += 1
    workspace_storage.save_project(project, projects_dir)
    console.print(f"Found {len(hits)} results; saved {added} new metadata hits.")
    _print_search_hits(hits)


@paper_app.command("results")
def paper_results(
    project_id: str = typer.Option(..., "--project", "-p"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    """List saved discovery metadata (not yet imported evidence)."""
    project = _load(project_id, projects_dir)
    _print_search_hits(project.search_hits)


@paper_app.command("fetch")
def paper_fetch(
    project_id: str = typer.Option(..., "--project", "-p"),
    result_id: str = typer.Option(..., "--result", "-r"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    """Fetch an open PDF result and import it as a raw paper source."""
    project = _load(project_id, projects_dir)
    hit = project.get_search_hit(result_id)
    if hit is None:
        _ai_failure(ValueError(f"Unknown search result id: {result_id}"), "Search result lookup")
    destination = projects_dir / "sources" / project.id / f"{hit.id}.pdf"
    try:
        connectors.download_pdf(hit, destination, runtime=project.runtime)
        paper = paper_service.add_source_file(
            project,
            destination,
            title=hit.title,
            authors=hit.authors,
            year=hit.year,
            external_ids={hit.source: hit.external_id, **({"doi": hit.doi} if hit.doi else {})},
            source_url=hit.landing_url,
            abstract=hit.abstract,
        )
        workspace_storage.save_project(project, projects_dir)
    except (connectors.ConnectorError, OSError, RuntimeError, ValueError) as exc:
        _ai_failure(exc, "Paper fetch/import")
    console.print(f"Paper imported: [bold cyan]{paper.id}[/bold cyan] ({paper.title})")


@paper_app.command("list")
def paper_list(
    project_id: str = typer.Option(..., "--project", "-p"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    project = _load(project_id, projects_dir)
    for paper in project.papers:
        console.print(f"{paper.id}\t{'analyzed' if paper.card else 'raw'}\t{paper.title}")


@paper_app.command("show")
def paper_show(
    project_id: str = typer.Option(..., "--project", "-p"),
    paper_id: str = typer.Option(..., "--paper"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    paper = _load(project_id, projects_dir).get_paper(paper_id)
    if paper is None:
        _ai_failure(ValueError(f"Unknown paper id: {paper_id}"), "Paper lookup")
    console.print_json(paper.model_dump_json(indent=2, exclude={"source_text"}))


@paper_app.command("analyze")
def paper_analyze(
    project_id: str = typer.Option(..., "--project", "-p"),
    paper_id: str = typer.Option(..., "--paper"),
    model: str = typer.Option("openai:gpt-4o", "--model"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    load_dotenv()
    project = _load(project_id, projects_dir)
    try:
        card = research.analyze_paper(project, paper_id, model)
    except (BudgetExceeded, LLMError, ValueError) as exc:
        workspace_storage.save_project(project, projects_dir)
        _ai_failure(exc, "Paper analysis")
    workspace_storage.save_project(project, projects_dir)
    console.print(f"Paper card saved with {len(card.evidence)} evidence items.")


@gap_app.command("synthesize")
def gap_synthesize(
    project_id: str = typer.Option(..., "--project", "-p"),
    count: int = typer.Option(5, "--count", min=1),
    model: str = typer.Option("openai:gpt-4o", "--model"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    load_dotenv()
    project = _load(project_id, projects_dir)
    try:
        gaps = research.synthesize_gaps(project, model, count)
    except (BudgetExceeded, LLMError, ValueError) as exc:
        workspace_storage.save_project(project, projects_dir)
        _ai_failure(exc, "Gap synthesis")
    workspace_storage.save_project(project, projects_dir)
    for gap in gaps:
        console.print(f"{gap.id}\t{gap.confidence:.2f}\t{gap.title}")


@gap_app.command("list")
def gap_list(
    project_id: str = typer.Option(..., "--project", "-p"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    for gap in _load(project_id, projects_dir).gaps:
        console.print(f"{gap.id}\t{gap.confidence:.2f}\t{gap.title}")


@gap_app.command("show")
def gap_show(
    project_id: str = typer.Option(..., "--project", "-p"),
    gap_id: str = typer.Option(..., "--gap"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    gap = _load(project_id, projects_dir).get_gap(gap_id)
    if gap is None:
        _ai_failure(ValueError(f"Unknown gap id: {gap_id}"), "Gap lookup")
    console.print_json(gap.model_dump_json(indent=2))


@idea_app.command("generate")
def idea_generate(
    project_id: str = typer.Option(..., "--project", "-p"),
    count: int = typer.Option(5, "--count", min=1),
    model: str = typer.Option("openai:gpt-4o", "--model"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    load_dotenv()
    project = _load(project_id, projects_dir)
    try:
        ideas = research.generate_ideas(project, model, count)
    except (BudgetExceeded, LLMError, ValueError) as exc:
        workspace_storage.save_project(project, projects_dir)
        _ai_failure(exc, "Idea generation")
    workspace_storage.save_project(project, projects_dir)
    for idea in ideas:
        console.print(f"{idea.id}\t{idea.latest().id}\t{idea.latest().spec.title}")


@idea_app.command("list")
def idea_list(
    project_id: str = typer.Option(..., "--project", "-p"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    for idea in _load(project_id, projects_dir).ideas:
        latest = idea.latest()
        console.print(f"{idea.id}\tv{latest.number}\t{latest.id}\t{latest.spec.title}")


@idea_app.command("show")
def idea_show(
    project_id: str = typer.Option(..., "--project", "-p"),
    idea_id: str = typer.Option(..., "--idea"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    idea = _load(project_id, projects_dir).get_idea(idea_id)
    if idea is None:
        _ai_failure(ValueError(f"Unknown idea id: {idea_id}"), "Idea lookup")
    console.print_json(idea.model_dump_json(indent=2))


@idea_app.command("critique")
def idea_critique(
    project_id: str = typer.Option(..., "--project", "-p"),
    idea_id: str = typer.Option(..., "--idea"),
    role: str = typer.Option("strict-reviewer", "--role"),
    model: str = typer.Option("anthropic:claude-sonnet-4-6", "--model"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    load_dotenv()
    project = _load(project_id, projects_dir)
    try:
        critique = research.critique_idea(project, idea_id, model, role)
    except (BudgetExceeded, LLMError, ValueError) as exc:
        workspace_storage.save_project(project, projects_dir)
        _ai_failure(exc, "Idea critique")
    workspace_storage.save_project(project, projects_dir)
    console.print(f"{critique.id}\t{critique.verdict}\t{critique.summary}")


@idea_app.command("revise")
def idea_revise(
    project_id: str = typer.Option(..., "--project", "-p"),
    idea_id: str = typer.Option(..., "--idea"),
    model: str = typer.Option("openai:gpt-4o", "--model"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    load_dotenv()
    project = _load(project_id, projects_dir)
    try:
        version = research.revise_idea(project, idea_id, model)
    except (BudgetExceeded, LLMError, ValueError) as exc:
        workspace_storage.save_project(project, projects_dir)
        _ai_failure(exc, "Idea revision")
    workspace_storage.save_project(project, projects_dir)
    console.print(f"Created v{version.number}: [bold cyan]{version.id}[/bold cyan]")


@shortlist_app.command("set")
def shortlist_set(
    project_id: str = typer.Option(..., "--project", "-p"),
    versions: list[str] = typer.Option(..., "--version"),
    note: str = typer.Option("", "--note"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    project = _load(project_id, projects_dir)
    try:
        decision = research.set_shortlist(project, versions, note)
        workspace_storage.save_project(project, projects_dir)
    except ValueError as exc:
        _ai_failure(exc, "Shortlist")
    console.print(f"Human decision saved: [bold cyan]{decision.id}[/bold cyan]")


@shortlist_app.command("show")
def shortlist_show(
    project_id: str = typer.Option(..., "--project", "-p"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
) -> None:
    decision = _load(project_id, projects_dir).latest_decision()
    if decision is None:
        console.print("[yellow]No shortlist decision yet.[/yellow]")
        return
    console.print_json(decision.model_dump_json(indent=2))


@arena_app.command("run")
def arena_run(
    project_id: str = typer.Option(..., "--project", "-p"),
    judge_model: str = typer.Option("anthropic:claude-sonnet-4-6", "--judge-model"),
    rounds: int = typer.Option(3, "--rounds", "-r", min=1),
    pairing: str = typer.Option("swiss", "--pairing"),
    double_judge: bool = typer.Option(False, "--double-judge"),
    concurrency: int = typer.Option(1, "--concurrency", "-c", min=1),
    seed: int | None = typer.Option(None, "--seed"),
    rubric_file: Path | None = typer.Option(None, "--rubric-file"),
    projects_dir: Path = typer.Option(workspace_storage.DEFAULT_DIR, "--projects-dir"),
    sessions_dir: Path = typer.Option(".loi_sessions", "--sessions-dir"),
) -> None:
    load_dotenv()
    project = _load(project_id, projects_dir)
    try:
        session = arena_bridge.run_shortlist_arena(
            project,
            judge_model=judge_model,
            rounds=rounds,
            pairing_strategy=pairing,
            rubric=(
                load_rubric(rubric_file)
                if rubric_file is not None
                else RESEARCH_WORKSPACE_RUBRIC.model_copy(deep=True)
            ),
            double_judge=double_judge,
            max_concurrency=concurrency,
            seed=seed,
            sessions_dir=sessions_dir,
            progress=lambda message: console.log(message),
        )
    except (BudgetExceeded, LLMError, OSError, ValueError) as exc:
        workspace_storage.save_project(project, projects_dir)
        _ai_failure(exc, "Arena")
    workspace_storage.save_project(project, projects_dir)
    console.print(f"Arena session: [bold cyan]{session.id}[/bold cyan]")
