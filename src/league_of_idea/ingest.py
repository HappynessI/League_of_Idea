"""Local paper ingestion with stable source locators."""

from __future__ import annotations

import hashlib
from pathlib import Path

MAX_ANALYSIS_CHARS = 120_000


def ingest_file(path: Path) -> tuple[str, str, str, bool]:
    """Return source type, locator-labelled text, sha256 and truncation flag."""
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Paper source does not exist: {path}")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        source_type = "pdf"
        text = _extract_pdf(path)
    elif suffix in {".md", ".markdown"}:
        source_type = "markdown"
        text = _label_lines(raw.decode("utf-8"))
    elif suffix in {".txt", ".text"}:
        source_type = "text"
        text = _label_lines(raw.decode("utf-8"))
    else:
        raise ValueError("Paper files must be PDF, Markdown, or UTF-8 text.")
    if not text.strip():
        raise ValueError(f"No extractable text found in {path.name}.")
    truncated = len(text) > MAX_ANALYSIS_CHARS
    return source_type, text, digest, truncated


def source_locators(text: str) -> set[str]:
    return {
        line.split("]", 1)[0] + "]"
        for line in text.splitlines()
        if line.startswith("[") and "]" in line
    }


def locator_segments(text: str) -> dict[str, str]:
    """Map each generated locator to its source block."""
    segments: dict[str, str] = {}
    current: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("[") and "]" in line:
            if current is not None:
                segments[current] = "\n".join(body)
            current = line.split("]", 1)[0] + "]"
            body = []
        elif current is not None:
            body.append(line)
    if current is not None:
        segments[current] = "\n".join(body)
    return segments


def _label_lines(text: str, chunk_size: int = 20) -> str:
    lines = text.splitlines()
    chunks: list[str] = []
    for start in range(0, len(lines), chunk_size):
        end = min(start + chunk_size, len(lines))
        body = "\n".join(lines[start:end]).strip()
        if body:
            chunks.append(f"[L{start + 1}-L{end}]\n{body}")
    return "\n\n".join(chunks)


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("PDF ingestion requires pypdf; reinstall league-of-idea.") from exc
    pages: list[str] = []
    for number, page in enumerate(PdfReader(path).pages, start=1):
        body = (page.extract_text() or "").strip()
        if body:
            pages.append(f"[P{number}]\n{body}")
    return "\n\n".join(pages)
