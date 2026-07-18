#!/usr/bin/env python3
"""Locate and invoke the League of Idea CLI without duplicating its logic."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPOSITORY_MARKERS = ("pyproject.toml", "src/league_of_idea")


def _is_repository(path: Path) -> bool:
    return all((path / marker).exists() for marker in REPOSITORY_MARKERS)


def _repository_root() -> Path | None:
    configured = os.environ.get("LEAGUE_OF_IDEA_ROOT")
    if configured:
        path = Path(configured).expanduser().resolve()
        return path if _is_repository(path) else None

    skill_path = Path(__file__).resolve()
    candidates = [Path.cwd().resolve(), *Path.cwd().resolve().parents]
    candidates.extend([skill_path, *skill_path.parents])
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_dir() and _is_repository(candidate):
            return candidate
    return None


def _loi_command(root: Path | None) -> list[str] | None:
    configured = os.environ.get("LOI_BIN")
    if configured:
        executable = Path(configured).expanduser()
        if executable.is_file():
            return [str(executable)]

    if root is not None:
        candidates = [root / ".venv/bin/loi", root / ".venv/Scripts/loi.exe"]
        for candidate in candidates:
            if candidate.is_file():
                return [str(candidate)]

    executable = shutil.which("loi")
    if executable:
        return [executable]
    if importlib.util.find_spec("league_of_idea") is not None:
        return [sys.executable, "-m", "league_of_idea.cli"]
    return None


def _dotenv_has_key(path: Path, key: str) -> bool:
    if not path.is_file():
        return False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() == key and value.strip().strip('"\''):
            return True
    return False


def _key_configured(root: Path | None, key: str) -> bool:
    if os.environ.get(key):
        return True
    return root is not None and _dotenv_has_key(root / ".env", key)


def _cli_python(command: list[str] | None) -> tuple[str | None, bool | None]:
    if command is None:
        return None, None
    executable = Path(command[0])
    if executable.name in {"loi", "loi.exe"}:
        python = executable.parent / ("python.exe" if os.name == "nt" else "python")
    elif command[0] == sys.executable:
        python = Path(sys.executable)
    else:
        return None, None
    if not python.is_file():
        return None, None
    completed = subprocess.run(
        [str(python), "--version"], capture_output=True, text=True, check=False
    )
    version = (completed.stdout or completed.stderr).strip().removeprefix("Python ")
    parts = version.split(".")
    supported = len(parts) >= 2 and (int(parts[0]), int(parts[1])) >= (3, 11)
    return version or None, supported


def doctor(as_json: bool = False) -> int:
    root = _repository_root()
    command = _loi_command(root)
    cli_python, cli_python_supported = _cli_python(command)
    result = {
        "ready": command is not None,
        "wrapper_python": sys.version.split()[0],
        "cli_python": cli_python,
        "cli_python_supported": cli_python_supported,
        "repository_root": str(root) if root else None,
        "loi_command": command,
        "keys": {
            key: _key_configured(root, key)
            for key in (
                "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY",
                "SEMANTIC_SCHOLAR_API_KEY", "CROSSREF_MAILTO",
            )
        },
    }
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Ready: {'yes' if result['ready'] else 'no'}")
        print(
            f"Wrapper Python: {result['wrapper_python']}"
        )
        if cli_python:
            print(
                f"CLI Python: {cli_python} "
                f"({'supported' if cli_python_supported else 'requires 3.11+'})"
            )
        print(f"Repository: {result['repository_root'] or 'not found'}")
        print(f"CLI: {' '.join(command) if command else 'not found'}")
        print("Provider keys (values hidden):")
        for key, configured in result["keys"].items():
            print(f"  {key}: {'configured' if configured else 'missing'}")
        if command is None:
            print("Install from the repository root with:")
            print("  # Use Python 3.11 or newer")
            print("  python3 -m venv .venv")
            print("  .venv/bin/python -m pip install .")
    return 0 if result["ready"] else 1


def main() -> int:
    args = sys.argv[1:]
    if not args or args[0] in {"-h", "--help"}:
        print("Usage: loi.py doctor [--json] | <loi command> [arguments...]")
        print("Examples:")
        print("  loi.py estimate --num-ideas 8 --rounds 3")
        print('  loi.py run --goal "Research goal" --max-calls 30')
        return 0
    if args[0] == "doctor":
        unknown = [arg for arg in args[1:] if arg != "--json"]
        if unknown:
            print(f"Unknown doctor arguments: {' '.join(unknown)}", file=sys.stderr)
            return 2
        return doctor(as_json="--json" in args[1:])

    root = _repository_root()
    command = _loi_command(root)
    if command is None:
        print("League of Idea CLI not found. Run `loi.py doctor`.", file=sys.stderr)
        return 127
    completed = subprocess.run([*command, *args], cwd=root or Path.cwd())
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
