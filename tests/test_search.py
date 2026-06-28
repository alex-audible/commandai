"""Tests for command_ai.search (web search). No real network calls — DDGS is mocked."""

from __future__ import annotations

import pytest

import command_ai.search as search
from command_ai.search import (
    SearchError,
    SearchHit,
    render_results,
    web_search,
)


# ---------------------------------------------------------------------------
# Fake DDGS infrastructure
# ---------------------------------------------------------------------------

def make_fake_ddgs(results, *, capture=None):
    """Return a fake DDGS class supporting the context-manager + .text() protocol."""

    class FakeDDGS:
        def __init__(self, timeout=None):
            self.timeout = timeout
            if capture is not None:
                capture["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results=5):
            if capture is not None:
                capture["query"] = query
                capture["max_results"] = max_results
            return results

    return FakeDDGS


def make_failing_text_ddgs(exc):
    """Fake DDGS whose .text() raises a generic exception."""

    class FailingDDGS:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, e, tb):
            return False

        def text(self, query, max_results=5):
            raise exc

    return FailingDDGS


# ---------------------------------------------------------------------------
# SearchHit dataclass
# ---------------------------------------------------------------------------

class TestSearchHit:
    def test_fields(self):
        hit = SearchHit(title="T", url="http://x", snippet="S")
        assert hit.title == "T"
        assert hit.url == "http://x"
        assert hit.snippet == "S"


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------

class TestWebSearch:
    def test_normal_mapping(self, monkeypatch):
        results = [
            {"title": "First", "href": "http://a.com", "body": "snippet a"},
            {"title": "Second", "href": "http://b.com", "body": "snippet b"},
        ]
        monkeypatch.setattr(search, "_import_ddgs", lambda: make_fake_ddgs(results))
        hits = web_search("test query")
        assert len(hits) == 2
        assert hits[0].title == "First"
        assert hits[0].url == "http://a.com"
        assert hits[0].snippet == "snippet a"
        assert hits[1].url == "http://b.com"

    def test_url_snippet_fallback_keys(self, monkeypatch):
        # Use 'url' and 'snippet' instead of 'href' and 'body'
        results = [{"title": "T", "url": "http://fallback.com", "snippet": "the snippet"}]
        monkeypatch.setattr(search, "_import_ddgs", lambda: make_fake_ddgs(results))
        hits = web_search("q")
        assert hits[0].url == "http://fallback.com"
        assert hits[0].snippet == "the snippet"

    def test_missing_keys_become_empty(self, monkeypatch):
        results = [{}]
        monkeypatch.setattr(search, "_import_ddgs", lambda: make_fake_ddgs(results))
        hits = web_search("q")
        assert hits[0].title == ""
        assert hits[0].url == ""
        assert hits[0].snippet == ""

    def test_passes_max_results_and_timeout(self, monkeypatch):
        capture = {}
        monkeypatch.setattr(
            search, "_import_ddgs", lambda: make_fake_ddgs([], capture=capture)
        )
        web_search("my query", max_results=3, timeout=9.0)
        assert capture["query"] == "my query"
        assert capture["max_results"] == 3
        assert capture["timeout"] == 9.0

    def test_empty_results(self, monkeypatch):
        monkeypatch.setattr(search, "_import_ddgs", lambda: make_fake_ddgs([]))
        hits = web_search("q")
        assert hits == []

    def test_import_error_propagates_search_error(self, monkeypatch):
        def boom():
            raise SearchError("Web search needs the 'ddgs' package.")
        monkeypatch.setattr(search, "_import_ddgs", boom)
        with pytest.raises(SearchError, match="ddgs"):
            web_search("q")

    def test_generic_exception_wrapped_as_search_error(self, monkeypatch):
        monkeypatch.setattr(
            search,
            "_import_ddgs",
            lambda: make_failing_text_ddgs(RuntimeError("network down")),
        )
        with pytest.raises(SearchError, match="web search failed"):
            web_search("q")

    def test_generic_exception_message_includes_cause(self, monkeypatch):
        monkeypatch.setattr(
            search,
            "_import_ddgs",
            lambda: make_failing_text_ddgs(ValueError("boom-cause")),
        )
        with pytest.raises(SearchError, match="boom-cause"):
            web_search("q")

    def test_search_error_from_text_propagates_unwrapped(self, monkeypatch):
        # A SearchError raised inside the with-block must propagate as-is,
        # not get wrapped in "web search failed: ...".
        original = SearchError("inner explicit error")
        monkeypatch.setattr(
            search, "_import_ddgs", lambda: make_failing_text_ddgs(original)
        )
        with pytest.raises(SearchError) as exc_info:
            web_search("q")
        assert exc_info.value is original
        assert "web search failed" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# _import_ddgs
# ---------------------------------------------------------------------------

class TestImportDdgs:
    def test_returns_a_class(self):
        # ddgs is installed in the venv, so this should succeed.
        ddgs_cls = search._import_ddgs()
        assert isinstance(ddgs_cls, type)


# ---------------------------------------------------------------------------
# render_results
# ---------------------------------------------------------------------------

class TestRenderResults:
    def test_empty_hits(self):
        result = render_results("my query", [])
        assert result == "Web search for 'my query': no results."

    def test_non_empty_header(self):
        hits = [SearchHit(title="T", url="http://x", snippet="S")]
        result = render_results("my query", hits)
        assert result.startswith("Web search results for 'my query':")

    def test_includes_title_url_snippet(self):
        hits = [SearchHit(title="MyTitle", url="http://example.com", snippet="My Snippet")]
        result = render_results("q", hits)
        assert "MyTitle" in result
        assert "http://example.com" in result
        assert "My Snippet" in result

    def test_multiple_hits_numbered(self):
        hits = [
            SearchHit(title="A", url="http://a", snippet="sa"),
            SearchHit(title="B", url="http://b", snippet="sb"),
        ]
        result = render_results("q", hits)
        assert "1. A" in result
        assert "2. B" in result

    def test_hit_without_url_or_snippet(self):
        hits = [SearchHit(title="OnlyTitle", url="", snippet="")]
        result = render_results("q", hits)
        assert "OnlyTitle" in result
