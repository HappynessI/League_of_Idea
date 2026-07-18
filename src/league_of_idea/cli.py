"""Command-line entry point. Translates commands into tournament calls."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import report as report_module
from . import storage, tournament
from .analysis import creator_attribution
from .llm import LLMError
from .models import Session
from .pricing import load_pricing
from .rubric import load_rubric
from .usage import BudgetConfig
from .runtime import RuntimeConfig
from . import workspace_cli

app = typer.Typer(
    add_completion=False,
    help="League of Idea — evidence-backed research ideation and Idea Arena.",
)
console = Console()
workspace_cli.register(app)


def _print_leaderboard(session: Session) -> None:
    table = Table(title=f"Leaderboard — session {session.id}")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Elo", justify="right")
    table.add_column("W-D-L", justify="center")
    table.add_column("Gen", justify="center")
    table.add_column("Idea", overflow="fold")

    for rank, idea in enumerate(session.leaderboard(), start=1):
        table.add_row(
            str(rank),
            f"{idea.elo:.0f}",
            f"{idea.wins}-{idea.draws}-{idea.losses}",
            str(idea.generation),
            idea.content,
        )
    console.print(table)


@app.command()
def run(
    goal: str = typer.Option(..., "--goal", "-g", help="Research goal / question."),
    num_ideas: int = typer.Option(8, "--num-ideas", "-n", help="Initial idea count."),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Number of tournament rounds."),
    judge_model: str = typer.Option(
        "anthropic:claude-sonnet-4-6", "--judge-model", help="Model used as judge."
    ),
    generator_model: str = typer.Option(
        "openai:gpt-4o", "--generator-model", help="Model used to generate/evolve ideas."
    ),
    pairing: str = typer.Option(
        "swiss", "--pairing", help="Pairing strategy: swiss | random | round-robin."
    ),
    k: float = typer.Option(32.0, "--k", help="Elo K-factor."),
    no_evolve: bool = typer.Option(False, "--no-evolve", help="Disable idea evolution."),
    double_judge: bool = typer.Option(
        False, "--double-judge", help="Judge each match in both A/B orientations."
    ),
    evolve_top: int = typer.Option(2, "--evolve-top", help="How many top ideas to evolve."),
    seed: int | None = typer.Option(None, "--seed", help="Random seed for reproducible pairing."),
    rubric_file: Path | None = typer.Option(
        None, "--rubric-file", help="Optional JSON file defining versioned judging criteria."
    ),
    max_calls: int | None = typer.Option(
        None, "--max-calls", help="Stop safely before exceeding this many LLM calls."
    ),
    max_tokens: int | None = typer.Option(
        None, "--max-tokens", help="Stop safely once reported token usage reaches this value."
    ),
    max_cost_usd: float | None = typer.Option(
        None, "--max-cost-usd", help="Stop once estimated provider cost reaches this value."
    ),
    pricing_file: Path | None = typer.Option(
        None, "--pricing-file", help="Versioned JSON model pricing table."
    ),
    dedup_threshold: float = typer.Option(
        0.86, "--dedup-threshold", help="Near-duplicate similarity threshold from 0 to 1."
    ),
    concurrency: int = typer.Option(
        1, "--concurrency", "-c", help="Maximum concurrent judge matches."
    ),
    timeout_seconds: float = typer.Option(
        60.0, "--timeout-seconds", help="Timeout for each provider request."
    ),
    max_retries: int = typer.Option(
        2, "--max-retries", help="Retries for transient provider failures."
    ),
    requests_per_second: float | None = typer.Option(
        None, "--requests-per-second", help="Per-provider request rate limit."
    ),
    sessions_dir: Path = typer.Option(
        storage.DEFAULT_DIR, "--sessions-dir", help="Where to store session JSON."
    ),
) -> None:
    """Run a full tournament: generate → battle → score → (evolve) → rank."""
    load_dotenv()
    try:
        calls = tournament.estimate_llm_calls(
            num_ideas,
            rounds,
            pairing,
            evolve=not no_evolve,
            evolve_top=evolve_top,
            double_judge=double_judge,
        )
        console.print(f"Estimated minimum LLM calls: [bold yellow]{calls}[/bold yellow]")
        selected_rubric = load_rubric(rubric_file)
        selected_budget = BudgetConfig(
            max_calls=max_calls,
            max_tokens=max_tokens,
            max_cost_usd=max_cost_usd,
        )
        selected_pricing = load_pricing(pricing_file)
        with console.status("[bold]Running tournament...[/bold]", spinner="dots"):
            session = tournament.run_tournament(
                goal,
                num_ideas=num_ideas,
                rounds=rounds,
                judge_model=judge_model,
                generator_model=generator_model,
                rubric=selected_rubric,
                budget=selected_budget,
                pricing=selected_pricing,
                double_judge=double_judge,
                dedup_threshold=dedup_threshold,
                max_concurrency=concurrency,
                runtime=RuntimeConfig(
                    request_timeout_seconds=timeout_seconds,
                    max_retries=max_retries,
                    requests_per_second=requests_per_second,
                ),
                pairing_strategy=pairing,
                k=k,
                evolve=not no_evolve,
                evolve_top=evolve_top,
                seed=seed,
                base_dir=sessions_dir,
                progress=lambda msg: console.log(msg),
            )
    except (LLMError, OSError, ValueError) as exc:
        console.print(f"[bold red]Tournament failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print()
    _print_leaderboard(session)
    console.print(
        f"Usage: {session.usage.calls} calls, {session.usage.total_tokens} tokens, "
        f"${session.usage.estimated_cost_usd:.4f}; "
        f"status: [bold]{session.status}[/bold]"
    )
    console.print(f"\nSession id: [bold cyan]{session.id}[/bold cyan]  "
                  f"(view again with: loi rank --session {session.id})")


@app.command()
def rank(
    session: str = typer.Option(..., "--session", "-s", help="Session id to display."),
    sessions_dir: Path = typer.Option(
        storage.DEFAULT_DIR, "--sessions-dir", help="Where session JSON is stored."
    ),
) -> None:
    """Show the leaderboard for a stored session."""
    try:
        loaded = storage.load_session(session, sessions_dir)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    _print_leaderboard(loaded)


@app.command()
def resume(
    session: str = typer.Option(..., "--session", "-s", help="Session id to continue."),
    max_calls: int | None = typer.Option(
        None, "--max-calls", help="Optional new total LLM call budget."
    ),
    max_tokens: int | None = typer.Option(
        None, "--max-tokens", help="Optional new total token budget."
    ),
    max_cost_usd: float | None = typer.Option(
        None, "--max-cost-usd", help="Optional new total cost budget in USD."
    ),
    concurrency: int | None = typer.Option(
        None, "--concurrency", "-c", help="Optional new judge concurrency."
    ),
    timeout_seconds: float | None = typer.Option(None, "--timeout-seconds"),
    max_retries: int | None = typer.Option(None, "--max-retries"),
    requests_per_second: float | None = typer.Option(None, "--requests-per-second"),
    sessions_dir: Path = typer.Option(
        storage.DEFAULT_DIR, "--sessions-dir", help="Where session JSON is stored."
    ),
) -> None:
    """Resume a failed or budget-stopped tournament."""
    try:
        loaded = storage.load_session(session, sessions_dir)
        budget_override = None
        if max_calls is not None or max_tokens is not None or max_cost_usd is not None:
            budget_override = BudgetConfig(
                max_calls=max_calls if max_calls is not None else loaded.budget.max_calls,
                max_tokens=max_tokens if max_tokens is not None else loaded.budget.max_tokens,
                max_cost_usd=(
                    max_cost_usd
                    if max_cost_usd is not None
                    else loaded.budget.max_cost_usd
                ),
            )
        runtime_override = None
        if any(
            value is not None
            for value in (timeout_seconds, max_retries, requests_per_second)
        ):
            runtime_override = RuntimeConfig(
                request_timeout_seconds=(
                    timeout_seconds
                    if timeout_seconds is not None
                    else loaded.runtime.request_timeout_seconds
                ),
                max_retries=(
                    max_retries
                    if max_retries is not None
                    else loaded.runtime.max_retries
                ),
                requests_per_second=(
                    requests_per_second
                    if requests_per_second is not None
                    else loaded.runtime.requests_per_second
                ),
            )
        with console.status("[bold]Resuming tournament...[/bold]", spinner="dots"):
            resumed = tournament.resume_tournament(
                session,
                base_dir=sessions_dir,
                budget_override=budget_override,
                concurrency_override=concurrency,
                runtime_override=runtime_override,
                progress=lambda msg: console.log(msg),
            )
    except (LLMError, OSError, ValueError) as exc:
        console.print(f"[bold red]Resume failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    _print_leaderboard(resumed)
    console.print(
        f"Usage: {resumed.usage.calls} calls, {resumed.usage.total_tokens} tokens, "
        f"${resumed.usage.estimated_cost_usd:.4f}; "
        f"status: [bold]{resumed.status}[/bold]"
    )


@app.command()
def estimate(
    num_ideas: int = typer.Option(8, "--num-ideas", "-n", help="Initial idea count."),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Number of tournament rounds."),
    pairing: str = typer.Option(
        "swiss", "--pairing", help="Pairing strategy: swiss | random | round-robin."
    ),
    no_evolve: bool = typer.Option(False, "--no-evolve", help="Disable idea evolution."),
    double_judge: bool = typer.Option(
        False, "--double-judge", help="Count two judge calls per match."
    ),
    evolve_top: int = typer.Option(2, "--evolve-top", help="How many top ideas to evolve."),
) -> None:
    """Estimate minimum planned LLM calls without contacting a provider."""
    try:
        calls = tournament.estimate_llm_calls(
            num_ideas,
            rounds,
            pairing,
            evolve=not no_evolve,
            evolve_top=evolve_top,
            double_judge=double_judge,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"Estimated minimum LLM calls: [bold yellow]{calls}[/bold yellow]")


@app.command()
def report(
    session: str = typer.Option(..., "--session", "-s", help="Session id to export."),
    output: Path | None = typer.Option(None, "--output", "-o", help="Markdown output path."),
    sessions_dir: Path = typer.Option(
        storage.DEFAULT_DIR, "--sessions-dir", help="Where session JSON is stored."
    ),
) -> None:
    """Export a session leaderboard and match evidence as Markdown."""
    try:
        loaded = storage.load_session(session, sessions_dir)
        path = report_module.save_report(loaded, output)
    except (FileNotFoundError, OSError, ValueError) as exc:
        console.print(f"[bold red]Report failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"Report written to [bold cyan]{path}[/bold cyan]")


@app.command()
def analyze(
    session: str = typer.Option(..., "--session", "-s", help="Session id to analyze."),
    sessions_dir: Path = typer.Option(storage.DEFAULT_DIR, "--sessions-dir"),
) -> None:
    """Compare idea performance by creator model."""
    try:
        loaded = storage.load_session(session, sessions_dir)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    table = Table(title=f"Creator attribution — session {loaded.id}")
    columns = (
        ("Model", "left"), ("Ideas", "right"), ("Avg Elo", "right"),
        ("Best Elo", "right"), ("W-D-L", "right"),
    )
    for name, justify in columns:
        table.add_column(name, justify=justify)
    for row in creator_attribution(loaded):
        table.add_row(
            row.model, str(row.ideas), f"{row.average_elo:.1f}",
            f"{row.best_elo:.1f}", f"{row.wins}-{row.draws}-{row.losses}",
        )
    console.print(table)


@app.command(name="list")
def list_cmd(
    sessions_dir: Path = typer.Option(
        storage.DEFAULT_DIR, "--sessions-dir", help="Where session JSON is stored."
    ),
) -> None:
    """List stored session ids."""
    ids = storage.list_sessions(sessions_dir)
    if not ids:
        console.print("[yellow]No sessions found.[/yellow]")
        return
    for sid in ids:
        console.print(sid)


if __name__ == "__main__":
    app()
