"""Persist and load tournament sessions as JSON.

State lives under a sessions directory (default ``./.loi_sessions``). Each
session is a single ``<session_id>.json`` file.
"""

from __future__ import annotations

from pathlib import Path

from .models import Session

DEFAULT_DIR = Path(".loi_sessions")


def _session_path(session_id: str, base_dir: Path) -> Path:
    return base_dir / f"{session_id}.json"


def save_session(session: Session, base_dir: Path = DEFAULT_DIR) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = _session_path(session.id, base_dir)
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_session(session_id: str, base_dir: Path = DEFAULT_DIR) -> Session:
    path = _session_path(session_id, base_dir)
    if not path.exists():
        raise FileNotFoundError(f"No session {session_id!r} under {base_dir}")
    return Session.model_validate_json(path.read_text(encoding="utf-8"))


def list_sessions(base_dir: Path = DEFAULT_DIR) -> list[str]:
    if not base_dir.exists():
        return []
    return sorted(p.stem for p in base_dir.glob("*.json"))
