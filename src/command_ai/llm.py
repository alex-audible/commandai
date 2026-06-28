"""LLM interaction: prompt building, the OpenAI-compatible call, and parsing.

The model returns a single JSON object describing either an *explore* request
(to look deeper into the filesystem) or a final *answer* with one or more
command options. Parsing is intentionally defensive because local models often
wrap JSON in prose or code fences.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .config import Config


class LLMError(RuntimeError):
    """Raised when the endpoint is unreachable or returns nothing usable."""


@dataclass
class CommandOption:
    command: str
    summary: str = ""
    args: list[dict[str, str]] = field(default_factory=list)
    danger: str = "low"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CommandOption":
        raw_args = data.get("args") or []
        args: list[dict[str, str]] = []
        for a in raw_args:
            if isinstance(a, dict):
                part = str(a.get("part", a.get("arg", ""))).strip()
                explains = str(a.get("explains", a.get("description", ""))).strip()
                if part:
                    args.append({"part": part, "explains": explains})
            elif isinstance(a, str):
                args.append({"part": a, "explains": ""})
        danger = str(data.get("danger", "low")).strip().lower()
        if danger not in ("low", "medium", "high"):
            danger = "low"
        return cls(
            command=str(data.get("command", "")).strip(),
            summary=str(data.get("summary", data.get("description", ""))).strip(),
            args=args,
            danger=danger,
        )


@dataclass
class ExploreRequest:
    path: str


@dataclass
class SearchRequest:
    query: str


@dataclass
class AnswerResult:
    options: list[CommandOption]


SYSTEM_PROMPT = """\
You are "ai", a command-line assistant on the user's Mac. Convert the user's \
natural-language request into a concrete shell command they can run in their \
current shell (default: zsh on macOS).

You can SEE a summary of the current directory. If you need to look deeper into \
a subdirectory before answering, you may explore.

Respond with ONE JSON object and nothing else. Two shapes are allowed.

To look inside a directory first:
{"action": "explore", "path": "<relative or absolute path>"}

To give the final answer:
{"action": "answer",
 "options": [
   {"command": "<exact shell command>",
    "summary": "<one short line: what it does>",
    "args": [{"part": "<flag or token>", "explains": "<what it does>"}],
    "danger": "low|medium|high"}
 ]}

Rules:
- Prefer a single best option. Provide 2-3 options ONLY when the request is \
genuinely ambiguous, and make each option meaningfully different.
- Commands must be valid for macOS/zsh and runnable from the current directory.
- Break down the important flags/arguments in "args".
- Set "danger" to "high" for destructive/irreversible actions (deleting, \
overwriting, formatting, recursive force), "medium" for changes that modify \
files, "low" for read-only/safe actions.
- Output raw JSON only. No markdown, no code fences, no commentary.\
"""

WEB_SEARCH_BLOCK = """\
You may also search the web when you need current or external information you \
cannot get from the directory context — for example to find the exact Homebrew \
formula or package name for a described tool, or to confirm a tool's correct \
flags. Use this shape:
{"action": "search", "query": "<concise web search query>"}
Search only when needed, then use the results to produce your final answer.\
"""


def build_system_prompt(web_enabled: bool = False) -> str:
    """The system prompt, optionally including the web-search action."""
    if web_enabled:
        return SYSTEM_PROMPT + "\n\n" + WEB_SEARCH_BLOCK
    return SYSTEM_PROMPT


def build_messages(
    user_request: str,
    context_block: str,
    research_log: list[str] | None = None,
    web_enabled: bool = False,
) -> list[dict[str, str]]:
    """Construct the chat messages for one completion call.

    ``research_log`` holds the rendered results of any directory explorations
    or web searches performed so far this turn.
    """
    parts = [
        "Context about the current environment:",
        context_block,
    ]
    if research_log:
        parts.append("\nInformation you have already gathered:")
        parts.extend(research_log)
    parts.append("\nUser request:")
    parts.append(user_request)
    hint = (
        "\nReturn the JSON object now (explore a directory or search the web if "
        "you need more information, otherwise answer)."
        if web_enabled
        else "\nReturn the JSON object now (explore if you need to look deeper, "
        "otherwise answer)."
    )
    parts.append(hint)
    return [
        {"role": "system", "content": build_system_prompt(web_enabled)},
        {"role": "user", "content": "\n".join(parts)},
    ]


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first balanced JSON object out of a possibly-noisy reply."""
    if not text:
        raise LLMError("Empty response from the model.")

    # Fast path: the whole thing is JSON.
    stripped = text.strip()
    # Bound the work the balanced-brace scanner below can do, so a garbled
    # model response (e.g. thousands of stray "{") can't cause a long hang
    # even if max_tokens is raised.
    MAX_SCAN = 200_000
    if len(stripped) > MAX_SCAN:
        stripped = stripped[:MAX_SCAN]
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Strip common ```json ... ``` fences.
    if "```" in stripped:
        fenced = stripped.split("```")
        for chunk in fenced:
            chunk = chunk.strip()
            if chunk.startswith("json"):
                chunk = chunk[4:].strip()
            if chunk.startswith("{"):
                try:
                    return json.loads(chunk)
                except json.JSONDecodeError:
                    continue

    # Last resort: scan for the first balanced {...}, respecting strings.
    # Cap restart positions so a string of stray "{" stays O(n), not O(n²).
    attempts = 0
    start = stripped.find("{")
    while start != -1 and attempts < 50:
        attempts += 1
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(stripped)):
            ch = stripped[i]
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = stripped[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = stripped.find("{", start + 1)

    raise LLMError("Could not parse JSON from the model response.")


def _parse_answer(data: dict[str, Any]) -> AnswerResult:
    raw_options = data.get("options")
    if raw_options is None and "command" in data:
        # Model returned a single option without the wrapper.
        raw_options = [data]
    if not raw_options:
        raise LLMError("Answer contained no command options.")

    options = [CommandOption.from_dict(o) for o in raw_options if isinstance(o, dict)]
    options = [o for o in options if o.command]
    if not options:
        raise LLMError("Answer contained no usable commands.")
    return AnswerResult(options=options)


def parse_response(text: str) -> ExploreRequest | SearchRequest | AnswerResult:
    """Turn raw model text into a typed result."""
    data = extract_json(text)
    action = str(data.get("action", "")).strip().lower()
    has_answer = "options" in data or "command" in data

    # Explicit action wins; otherwise infer from which keys are present.
    if action == "search" or ("query" in data and not has_answer):
        query = str(data.get("query", "")).strip()
        if not query:
            raise LLMError("Search request missing a query.")
        return SearchRequest(query=query)

    if action == "explore" or ("path" in data and not has_answer):
        path = str(data.get("path", "")).strip()
        if not path:
            raise LLMError("Explore request missing a path.")
        return ExploreRequest(path=path)

    return _parse_answer(data)


class LLMClient:
    """Thin wrapper over the OpenAI-compatible chat completions endpoint."""

    def __init__(self, config: Config, client: Any | None = None):
        self.config = config
        self._client = client  # injectable for tests

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMError(
                "The 'openai' package is required. Install with: pip install openai"
            ) from exc
        self._client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            timeout=self.config.timeout,
        )
        return self._client

    def complete(self, messages: list[dict[str, str]]) -> str:
        client = self._ensure_client()
        try:
            resp = client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - surface a friendly error
            raise LLMError(
                f"Could not reach the model at {self.config.base_url} "
                f"(model '{self.config.model}'): {exc}"
            ) from exc
        try:
            content = resp.choices[0].message.content
        except (AttributeError, IndexError, KeyError) as exc:
            raise LLMError("Malformed response from the endpoint.") from exc
        if not content:
            raise LLMError("The model returned an empty message.")
        return content
