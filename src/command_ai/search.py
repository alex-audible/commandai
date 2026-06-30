"""Optional web search, used to ground commands in real, current information.

For requests like "brew install a tool that flashes bootable images to USB
drives", the model often needs an external fact (the exact formula/cask name).
It can request a search; we run it via DuckDuckGo (no API key) and feed the
results back into the conversation.

Network access only happens when the model actually asks to search, and web
search can be disabled entirely (config ``web_search = false`` or ``--no-web``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Web results are attacker-influenceable (a page that ranks for the model's
# query). Strip control characters so a snippet can't forge prompt structure and
# cap each field's length so one result can't dominate the prompt (F-01).
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def _clean(text: str, limit: int) -> str:
    cleaned = _CONTROL_RE.sub(" ", text)
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


class SearchError(RuntimeError):
    """Raised when a web search cannot be performed or returns nothing usable."""


@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str


def web_search(query: str, max_results: int = 5, timeout: float = 15.0) -> list[SearchHit]:
    """Run a DuckDuckGo text search and return up to *max_results* hits.

    Uses the ``ddgs`` package (formerly ``duckduckgo_search``). Raises
    :class:`SearchError` if the package is missing or the request fails.
    """
    DDGS = _import_ddgs()
    hits: list[SearchHit] = []
    try:
        with DDGS(timeout=timeout) as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                hits.append(
                    SearchHit(
                        title=str(r.get("title", "")).strip(),
                        url=str(r.get("href", r.get("url", ""))).strip(),
                        snippet=str(r.get("body", r.get("snippet", ""))).strip(),
                    )
                )
    except SearchError:
        raise
    except Exception as exc:  # noqa: BLE001 - surface a friendly error
        raise SearchError(f"web search failed: {exc}") from exc
    return hits


def _import_ddgs():
    """Import the DDGS client, tolerating the old package name."""
    try:
        from ddgs import DDGS  # current package name
        return DDGS
    except ImportError:
        pass
    try:
        from duckduckgo_search import DDGS  # legacy package name
        return DDGS
    except ImportError as exc:
        raise SearchError(
            "Web search needs the 'ddgs' package. Install it with: pip install ddgs"
        ) from exc


def render_results(query: str, hits: list[SearchHit]) -> str:
    """Format search hits for injection back into the model prompt."""
    if not hits:
        return f"Web search for {query!r}: no results."
    lines = [f"Web search results for {query!r}:"]
    for i, hit in enumerate(hits, start=1):
        lines.append(f"  {i}. {_clean(hit.title, 200)}")
        if hit.url:
            lines.append(f"     {_clean(hit.url, 300)}")
        if hit.snippet:
            lines.append(f"     {_clean(hit.snippet, 500)}")
    return "\n".join(lines)
