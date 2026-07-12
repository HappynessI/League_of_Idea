"""Command-line entry point. Translates commands into tournament calls."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import report as report_module
from . import storage, tournament
from .llm import LLMError
from .models import Session
from .rubric import load_rubric
from .usage import BudgetConfig

app = typer.Typer(
    add_completion=False,
    help="League of Idea — an arena where ideas battle and Elo decides the winner.",
)
console = Console()


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
        "random", "--pairing", help="Pairing strategy: round-robin | random."
    ),
    k: float = typer.Option(32.0, "--k", help="Elo K-factor."),
    no_evolve: bool = typer.Option(False, "--no-evolve", help="Disable idea evolution."),
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
        )
        console.print(f"Estimated LLM calls: [bold yellow]{calls}[/bold yellow]")
        selected_rubric = load_rubric(rubric_file)
        selected_budget = BudgetConfig(max_calls=max_calls, max_tokens=max_tokens)
        with console.status("[bold]Running tournament...[/bold]", spinner="dots"):
            session = tournament.run_tournament(
                goal,
                num_ideas=num_ideas,
                rounds=rounds,
                judge_model=judge_model,
                generator_model=generator_model,
                rubric=selected_rubric,
                budget=selected_budget,
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
        f"Usage: {session.usage.calls} calls, {session.usage.total_tokens} tokens; "
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
    sessions_dir: Path = typer.Option(
        storage.DEFAULT_DIR, "--sessions-dir", help="Where session JSON is stored."
    ),
) -> None:
    """Resume a failed or budget-stopped tournament."""
    try:
        loaded = storage.load_session(session, sessions_dir)
        budget_override = None
        if max_calls is not None or max_tokens is not None:
            budget_override = BudgetConfig(
                max_calls=max_calls if max_calls is not None else loaded.budget.max_calls,
                max_tokens=max_tokens if max_tokens is not None else loaded.budget.max_tokens,
            )
        with console.status("[bold]Resuming tournament...[/bold]", spinner="dots"):
            resumed = tournament.resume_tournament(
                session,
                base_dir=sessions_dir,
                budget_override=budget_override,
                progress=lambda msg: console.log(msg),
            )
    except (LLMError, OSError, ValueError) as exc:
        console.print(f"[bold red]Resume failed:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    _print_leaderboard(resumed)
    console.print(
        f"Usage: {resumed.usage.calls} calls, {resumed.usage.total_tokens} tokens; "
        f"status: [bold]{resumed.status}[/bold]"
    )


@app.command()
def estimate(
    num_ideas: int = typer.Option(8, "--num-ideas", "-n", help="Initial idea count."),
    rounds: int = typer.Option(3, "--rounds", "-r", help="Number of tournament rounds."),
    pairing: str = typer.Option(
        "random", "--pairing", help="Pairing strategy: round-robin | random."
    ),
    no_evolve: bool = typer.Option(False, "--no-evolve", help="Disable idea evolution."),
    evolve_top: int = typer.Option(2, "--evolve-top", help="How many top ideas to evolve."),
) -> None:
    """Estimate paid LLM calls without contacting a provider."""
    try:
        calls = tournament.estimate_llm_calls(
            num_ideas,
            rounds,
            pairing,
            evolve=not no_evolve,
            evolve_top=evolve_top,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"Estimated LLM calls: [bold yellow]{calls}[/bold yellow]")


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
