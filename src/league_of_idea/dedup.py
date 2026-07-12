"""Deterministic near-duplicate detection without extra embedding API calls."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", normalize(text)))


def similarity(first: str, second: str) -> float:
    normalized_first = normalize(first)
    normalized_second = normalize(second)
    if not normalized_first or not normalized_second:
        return 0.0
    sequence = SequenceMatcher(None, normalized_first, normalized_second).ratio()
    tokens_first = _tokens(normalized_first)
    tokens_second = _tokens(normalized_second)
    union = tokens_first | tokens_second
    jaccard = len(tokens_first & tokens_second) / len(union) if union else 0.0
    return max(sequence, jaccard)


def is_near_duplicate(
    candidate: str,
    existing: list[str],
    *,
    threshold: float = 0.86,
) -> bool:
    return any(similarity(candidate, item) >= threshold for item in existing)
