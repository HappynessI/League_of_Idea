"""Small, dependency-light scholarly search connectors.

The connectors intentionally return metadata discovery results only. A result
must be explicitly selected and, when possible, downloaded as a PDF before it
can enter the evidence-backed Paper Card workflow.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from .dedup import is_near_duplicate
from .runtime import RuntimeConfig, RuntimeController
from .workspace_models import SearchHit

DEFAULT_SOURCES = ("arxiv", "crossref", "semantic-scholar")
USER_AGENT = "LeagueOfIdea/0.7 (scholarly-discovery; mailto:{})"


class ConnectorError(RuntimeError):
    pass


def search(
    query: str,
    *,
    sources: list[str] | tuple[str, ...] = DEFAULT_SOURCES,
    limit: int = 10,
    runtime: RuntimeConfig | None = None,
) -> list[SearchHit]:
    """Search selected sources, normalize records, and remove duplicates."""
    if not query.strip():
        raise ValueError("Search query must not be empty.")
    if not 1 <= limit <= 50:
        raise ValueError("Search limit must be between 1 and 50.")
    selected = tuple(_normalize_source(source) for source in sources)
    unknown = sorted(set(selected) - set(DEFAULT_SOURCES))
    if unknown:
        raise ValueError(f"Unknown literature source(s): {', '.join(unknown)}")
    config = runtime or RuntimeConfig()
    controller = RuntimeController(config)
    results: list[SearchHit] = []
    for source in selected:
        if source == "arxiv":
            results.extend(_search_arxiv(query, limit, config, controller))
        elif source == "crossref":
            results.extend(_search_crossref(query, limit, config, controller))
        else:
            results.extend(_search_semantic_scholar(query, limit, config, controller))
    return deduplicate(results)


def deduplicate(results: list[SearchHit]) -> list[SearchHit]:
    """Deduplicate by DOI/external id first, then conservative title similarity."""
    kept: list[SearchHit] = []
    exact_keys: set[str] = set()
    for result in results:
        keys = _identity_keys(result)
        if keys & exact_keys:
            continue
        if any(is_near_duplicate(result.title, [item.title], threshold=0.94) for item in kept):
            continue
        kept.append(result)
        exact_keys.update(keys)
    return kept


def download_pdf(
    hit: SearchHit,
    destination,
    *,
    runtime: RuntimeConfig | None = None,
) -> None:
    """Download a selected open PDF, rejecting landing pages and non-HTTPS URLs."""
    url = hit.pdf_url
    if not url:
        raise ConnectorError(
            "This result has no known open PDF URL; download the paper manually and use paper add."
        )
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ConnectorError("Refusing to download a non-HTTPS paper URL.")
    config = runtime or RuntimeConfig()
    payload, headers = _request_bytes(url, config, RuntimeController(config))
    content_type = headers.get("Content-Type", "").lower()
    if not payload.startswith(b"%PDF") and "application/pdf" not in content_type:
        raise ConnectorError(
            "The selected URL did not return a PDF; download it manually and use paper add."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _search_arxiv(
    query: str, limit: int, config: RuntimeConfig, controller: RuntimeController
) -> list[SearchHit]:
    params = urllib.parse.urlencode(
        {"search_query": f"all:{query}", "start": 0, "max_results": limit, "sortBy": "relevance"}
    )
    body, _ = _request_bytes(
        f"https://export.arxiv.org/api/query?{params}", config, controller
    )
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ConnectorError("arXiv returned malformed Atom XML.") from exc
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: list[SearchHit] = []
    for entry in root.findall("atom:entry", ns):
        abstract_url = _xml_text(entry.find("atom:id", ns))
        external_id = abstract_url.rsplit("/", 1)[-1]
        pdf_url = None
        for link in entry.findall("atom:link", ns):
            if link.attrib.get("title") == "pdf":
                pdf_url = link.attrib.get("href")
        published = _parse_year(_xml_text(entry.find("atom:published", ns)))
        results.append(
            SearchHit(
                source="arxiv",
                external_id=external_id,
                title=_clean(_xml_text(entry.find("atom:title", ns))),
                authors=[
                    _xml_text(author.find("atom:name", ns))
                    for author in entry.findall("atom:author", ns)
                ],
                abstract=_clean(_xml_text(entry.find("atom:summary", ns))) or None,
                year=published,
                landing_url=abstract_url,
                pdf_url=pdf_url,
            )
        )
    return results


def _search_crossref(
    query: str, limit: int, config: RuntimeConfig, controller: RuntimeController
) -> list[SearchHit]:
    params = urllib.parse.urlencode(
        {"query": query, "rows": limit, "select": "DOI,title,author,abstract,published,issued,container-title,URL"}
    )
    mailto = os.environ.get("CROSSREF_MAILTO")
    if mailto:
        params += "&" + urllib.parse.urlencode({"mailto": mailto})
    body, _ = _request_bytes(
        f"https://api.crossref.org/works?{params}", config, controller
    )
    try:
        items = json.loads(body).get("message", {}).get("items", [])
    except (TypeError, json.JSONDecodeError) as exc:
        raise ConnectorError("Crossref returned malformed JSON.") from exc
    results: list[SearchHit] = []
    for item in items:
        doi = item.get("DOI")
        if not doi or not item.get("title"):
            continue
        year = _crossref_year(item)
        results.append(
            SearchHit(
                source="crossref",
                external_id=doi,
                title=_clean(item["title"][0]),
                authors=_crossref_authors(item.get("author", [])),
                abstract=_clean(_strip_jats(item.get("abstract", ""))) or None,
                year=year,
                venue=_first(item.get("container-title")),
                doi=doi,
                landing_url=item.get("URL") or f"https://doi.org/{doi}",
                pdf_url=_pdf_link(item.get("link", [])),
            )
        )
    return results


def _search_semantic_scholar(
    query: str, limit: int, config: RuntimeConfig, controller: RuntimeController
) -> list[SearchHit]:
    params = urllib.parse.urlencode(
        {
            "query": query,
            "limit": limit,
            "fields": "title,authors,abstract,year,venue,externalIds,url,openAccessPdf,citationCount",
        }
    )
    body, _ = _request_bytes(
        f"https://api.semanticscholar.org/graph/v1/paper/search?{params}",
        config,
        controller,
        headers={"x-api-key": os.environ["SEMANTIC_SCHOLAR_API_KEY"]}
        if os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
        else None,
    )
    try:
        items = json.loads(body).get("data", [])
    except (TypeError, json.JSONDecodeError) as exc:
        raise ConnectorError("Semantic Scholar returned malformed JSON.") from exc
    results: list[SearchHit] = []
    for item in items:
        if not item.get("paperId") or not item.get("title"):
            continue
        external_ids = item.get("externalIds") or {}
        results.append(
            SearchHit(
                source="semantic-scholar",
                external_id=item["paperId"],
                title=_clean(item["title"]),
                authors=[author.get("name", "") for author in item.get("authors") or [] if author.get("name")],
                abstract=_clean(item.get("abstract") or "") or None,
                year=item.get("year"),
                venue=item.get("venue") or None,
                doi=external_ids.get("DOI"),
                landing_url=item.get("url"),
                pdf_url=(item.get("openAccessPdf") or {}).get("url"),
                citation_count=item.get("citationCount"),
            )
        )
    return results


def _request_bytes(
    url: str,
    config: RuntimeConfig,
    controller: RuntimeController,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    request_headers = {
        "User-Agent": USER_AGENT.format(os.environ.get("CROSSREF_MAILTO", "")),
        "Accept": "application/json, application/atom+xml, application/pdf",
    }
    request_headers.update(headers or {})
    for attempt in range(config.max_retries + 1):
        controller.wait("literature")
        try:
            request = urllib.request.Request(url, headers=request_headers)
            with urllib.request.urlopen(request, timeout=config.request_timeout_seconds) as response:
                return response.read(), dict(response.headers.items())
        except urllib.error.HTTPError as exc:
            retryable = exc.code == 429 or exc.code >= 500
            if not retryable or attempt >= config.max_retries:
                raise ConnectorError(f"Literature provider returned HTTP {exc.code}: {url}") from exc
            retry_after = exc.headers.get("Retry-After")
            time.sleep(_retry_delay(attempt, retry_after))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if attempt >= config.max_retries:
                raise ConnectorError(f"Literature provider request failed: {exc}") from exc
            time.sleep(2**attempt)
    raise ConnectorError(f"Literature provider request failed: {url}")


def _retry_delay(attempt: int, retry_after: str | None) -> float:
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                return max(0.0, (parsedate_to_datetime(retry_after) - datetime.now().astimezone()).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    return float(2**attempt)


def _normalize_source(source: str) -> str:
    return source.strip().casefold().replace("_", "-").replace(" ", "-")


def _identity_keys(result: SearchHit) -> set[str]:
    keys = {f"{result.source}:{result.external_id.casefold()}"}
    if result.doi:
        keys.add(f"doi:{result.doi.casefold().removeprefix('https://doi.org/')}")
    return keys


def _xml_text(node) -> str:
    return "" if node is None or node.text is None else node.text.strip()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _parse_year(value: str) -> int | None:
    match = re.match(r"(\d{4})", value or "")
    return int(match.group(1)) if match else None


def _crossref_year(item: dict) -> int | None:
    for field in ("published", "published-print", "published-online", "issued", "created"):
        parts = (item.get(field) or {}).get("date-parts") or []
        if parts and parts[0]:
            return parts[0][0]
    return None


def _crossref_authors(authors: list[dict]) -> list[str]:
    return [
        _clean(" ".join(part for part in (author.get("given"), author.get("family")) if part))
        for author in authors
        if author.get("given") or author.get("family")
    ]


def _first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def _pdf_link(links: list[dict]) -> str | None:
    for link in links or []:
        content_type = (link.get("content-type") or "").casefold()
        if content_type == "application/pdf" or str(link.get("URL", "")).lower().endswith(".pdf"):
            return link.get("URL")
    return None


def _strip_jats(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value or "")
