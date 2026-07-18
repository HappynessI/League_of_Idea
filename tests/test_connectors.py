import json

from league_of_idea import connectors
from league_of_idea.workspace_models import SearchHit


ARXIV_XML = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>http://arxiv.org/abs/2401.12345</id><title>  A useful paper  </title>
<summary> An abstract. </summary><published>2024-01-20T00:00:00Z</published>
<author><name>Alice A</name></author><link title="pdf" href="https://arxiv.org/pdf/2401.12345" /></entry></feed>"""


def test_arxiv_connector_normalizes_atom(monkeypatch):
    monkeypatch.setattr(connectors, "_request_bytes", lambda *args, **kwargs: (ARXIV_XML.encode(), {}))
    hit = connectors._search_arxiv("agents", 5, connectors.RuntimeConfig(), connectors.RuntimeController(connectors.RuntimeConfig()))[0]
    assert hit.source == "arxiv"
    assert hit.external_id == "2401.12345"
    assert hit.title == "A useful paper"
    assert hit.year == 2024
    assert hit.pdf_url.endswith("2401.12345")


def test_crossref_connector_normalizes_json(monkeypatch):
    payload = {"message": {"items": [{
        "DOI": "10.1234/demo", "title": ["Demo paper"],
        "author": [{"given": "Alice", "family": "A"}],
        "published": {"date-parts": [[2023]]}, "container-title": ["Demo Journal"],
        "URL": "https://doi.org/10.1234/demo",
    }]}}
    monkeypatch.setattr(connectors, "_request_bytes", lambda *args, **kwargs: (json.dumps(payload).encode(), {}))
    hits = connectors._search_crossref("agents", 5, connectors.RuntimeConfig(), connectors.RuntimeController(connectors.RuntimeConfig()))
    assert hits[0].doi == "10.1234/demo"
    assert hits[0].authors == ["Alice A"]
    assert hits[0].year == 2023


def test_semantic_scholar_connector_normalizes_json(monkeypatch):
    payload = {"data": [{
        "paperId": "abc", "title": "S2 paper", "authors": [{"name": "Bob"}],
        "year": 2022, "externalIds": {"DOI": "10.1/s2"}, "url": "https://semanticscholar.org/paper/abc",
        "openAccessPdf": {"url": "https://example.org/paper.pdf"}, "citationCount": 9,
    }]}
    monkeypatch.setattr(connectors, "_request_bytes", lambda *args, **kwargs: (json.dumps(payload).encode(), {}))
    hits = connectors._search_semantic_scholar("agents", 5, connectors.RuntimeConfig(), connectors.RuntimeController(connectors.RuntimeConfig()))
    assert hits[0].external_id == "abc"
    assert hits[0].doi == "10.1/s2"
    assert hits[0].citation_count == 9


def test_deduplicate_uses_doi_and_title():
    first = SearchHit(source="arxiv", external_id="a", title="A Robust Method", doi="10.1/x")
    second = SearchHit(source="crossref", external_id="10.1/x", title="A Robust Method")
    third = SearchHit(source="semantic-scholar", external_id="s", title="A completely different study")
    assert connectors.deduplicate([first, second, third]) == [first, third]


def test_download_pdf_rejects_landing_page(monkeypatch, tmp_path):
    hit = SearchHit(source="arxiv", external_id="a", title="A", pdf_url="https://example.org/a")
    monkeypatch.setattr(connectors, "_request_bytes", lambda *args, **kwargs: (b"<html>", {"Content-Type": "text/html"}))
    try:
        connectors.download_pdf(hit, tmp_path / "a.pdf")
    except connectors.ConnectorError as exc:
        assert "did not return a PDF" in str(exc)
    else:
        raise AssertionError("expected ConnectorError")
