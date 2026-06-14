"""Command-line entry point. Translates commands into tournament calls."""

from __future__ import annotations

from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from . import storage, tournament
from .models import Session

app = typer.Typer(
    add_completion=False,
    help="League of Idea — an arena where ideas battle and Elo decides the winner.",
)
console = Console()


def _print_leaderboard(session: Session) -> None:
    table = Table(title=f"Leaderboard — session {session.id}")
    table.add_column("#", justify="right", style="bold")
    table.add_column("Elo", justify="right")
    table.add_column("W-L", justify="center")
    table.add_column("Gen", justify="center")
    table.add_column("Idea", overflow="fold")

    for rank, idea in enumerate(session.leaderboard(), start=1):
        table.add_row(
            str(rank),
            f"{idea.elo:.0f}",
            f"{idea.wins}-{idea.losses}",
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
        "anthropic/claude-sonnet-4-6", "--judge-model", help="Model used as judge."
    ),
    generator_model: str = typer.Option(
        "openai/gpt-4o", "--generator-model", help="Model used to generate/evolve ideas."
    ),
    pairing: str = typer.Option(
        "round-robin", "--pairing", help="Pairing strategy: round-robin | random."
    ),
    k: float = typer.Option(32.0, "--k", help="Elo K-factor."),
    no_evolve: bool = typer.Option(False, "--no-evolve", help="Disable idea evolution."),
    evolve_top: int = typer.Option(2, "--evolve-top", help="How many top ideas to evolve."),
    sessions_dir: Path = typer.Option(
        storage.DEFAULT_DIR, "--sessions-dir", help="Where to store session JSON."
    ),
) -> None:
    """Run a full tournament: generate → battle → score → (evolve) → rank."""
    load_dotenv()
    with console.status("[bold]Running tournament...[/bold]", spinner="dots"):
        session = tournament.run_tournament(
            goal,
            num_ideas=num_ideas,
            rounds=rounds,
            judge_model=judge_model,
            generator_model=generator_model,
            pairing_strategy=pairing,
            k=k,
            evolve=not no_evolve,
            evolve_top=evolve_top,
            base_dir=sessions_dir,
            progress=lambda msg: console.log(msg),
        )
    console.print()
    _print_leaderboard(session)
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
