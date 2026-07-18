"""Atomic JSON persistence for research workspace projects."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .workspace_models import ResearchProject

DEFAULT_DIR = Path(".loi_projects")


def project_path(project_id: str, base_dir: Path = DEFAULT_DIR) -> Path:
    return base_dir / f"{project_id}.json"


def save_project(project: ResearchProject, base_dir: Path = DEFAULT_DIR) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = project_path(project.id, base_dir)
    temp_path = path.with_suffix(".json.tmp")
    project.updated_at = datetime.now(timezone.utc)
    temp_path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    temp_path.replace(path)
    return path


def load_project(project_id: str, base_dir: Path = DEFAULT_DIR) -> ResearchProject:
    path = project_path(project_id, base_dir)
    if not path.exists():
        raise FileNotFoundError(f"No project {project_id!r} under {base_dir}")
    project = ResearchProject.model_validate_json(path.read_text(encoding="utf-8"))
    # SearchHit is additive, so older v0.6 projects remain readable and are
    # upgraded in memory on their next save without losing any existing data.
    if project.schema_version < 2:
        project.schema_version = 2
    return project


def list_projects(base_dir: Path = DEFAULT_DIR) -> list[str]:
    if not base_dir.exists():
        return []
    return sorted(path.stem for path in base_dir.glob("*.json"))
