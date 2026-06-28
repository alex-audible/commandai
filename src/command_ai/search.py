"""Optional web search, used to ground commands in real, current information.

For requests like "brew install a tool that flashes bootable images to USB
drives", the model often needs an external fact (the exact formula/cask name).
It can request a search; we run it via DuckDuckGo (no API key) and feed the
results back into the conversation.

Network access only happens when the model actually asks to search, and web
search can be disabled entirely (config ``web_search = false`` or ``--no-web``).
"""

from __future__ import annotations

from dataclasses import dataclass


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
        lines.append(f"  {i}. {hit.title}")
        if hit.url:
            lines.append(f"     {hit.url}")
        if hit.snippet:
            lines.append(f"     {hit.snippet}")
    return "\n".join(lines)
