"""Command-line entry point and the explore→answer→confirm→run loop."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import Config, default_config_path, load_config
from .context import gather_context, list_directory
from .executor import (
    looks_dangerous,
    run_in_subprocess,
    write_command,
)
from .llm import (
    AnswerResult,
    ExploreRequest,
    LLMClient,
    LLMError,
    SearchRequest,
    build_messages,
    parse_response,
)
from .search import SearchError, render_results, web_search
from . import ui


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai",
        description="Ask for a shell command in plain English; review and run it.",
        epilog="Example: ai use ffmpeg to convert all the videos here from mov to mp4",
    )
    parser.add_argument("request", nargs="*", help="Natural-language request.")
    parser.add_argument("--model", help="Override the model name.")
    parser.add_argument("--base-url", dest="base_url", help="Override the endpoint base URL.")
    parser.add_argument("--api-key", dest="api_key", help="Override the API key.")
    parser.add_argument("--config", help="Path to a config TOML file.")
    parser.add_argument(
        "--output-file",
        dest="output_file",
        help="Write the chosen command here instead of running it (used by the shell wrapper).",
    )
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Pick the first option without prompting."
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Show the command(s) but do not run or write anything.",
    )
    parser.add_argument(
        "--no-context",
        action="store_true",
        help="Do not send directory context to the model.",
    )
    parser.add_argument(
        "--no-web",
        action="store_true",
        help="Disable web search even if enabled in config.",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print the resolved configuration and exit.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def resolve_config(args: argparse.Namespace) -> Config:
    overrides = {
        "model": args.model,
        "base_url": args.base_url,
        "api_key": args.api_key,
    }
    config_path = Path(args.config) if args.config else None
    return load_config(config_path=config_path, overrides=overrides)


def default_searcher(config: Config):
    """Return a callable that runs a web search and renders it, or an error note."""

    def _search(query: str) -> str:
        try:
            hits = web_search(query, config.search_results, config.search_timeout)
        except SearchError as exc:
            return f"Web search for {query!r} failed: {exc}"
        return render_results(query, hits)

    return _search


def run_conversation(
    request: str,
    config: Config,
    client: LLMClient,
    cwd: Path,
    no_context: bool = False,
    web_enabled: bool = False,
    searcher=None,
) -> AnswerResult:
    """Drive the explore/search loop until the model returns a final answer."""
    base_context = "(context disabled)" if no_context else gather_context(cwd, config)
    research_log: list[str] = []

    explores_left = max(0, config.max_explorations)
    searches_left = max(0, config.max_searches) if web_enabled else 0
    if searcher is None and web_enabled:
        searcher = default_searcher(config)

    max_turns = explores_left + searches_left + 1
    for _ in range(max_turns + 1):
        messages = build_messages(request, base_context, research_log, web_enabled=web_enabled)
        raw = client.complete(messages)
        result = parse_response(raw)

        if isinstance(result, AnswerResult):
            return result

        if isinstance(result, SearchRequest):
            if not web_enabled or searches_left <= 0 or searcher is None:
                research_log.append("(web search unavailable — answer with what you know)")
                continue
            searches_left -= 1
            ui.print_info(f"… searching the web for: {result.query}")
            research_log.append(searcher(result.query))
            continue

        # ExploreRequest: resolve the path, list it, feed back, and re-ask.
        if explores_left <= 0:
            research_log.append("(exploration limit reached — answer now)")
            continue
        explores_left -= 1
        target = Path(result.path)
        if not target.is_absolute():
            target = (cwd / target).resolve()
        ui.print_info(f"… exploring {target}")
        listing = list_directory(target, config)
        research_log.append(listing.render())

    raise LLMError(
        "Model kept gathering information without producing a command. Try rephrasing."
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = resolve_config(args)
    except Exception as exc:  # noqa: BLE001
        ui.print_error(f"Failed to load config: {exc}")
        return 2

    if args.print_config:
        ui.print_info(f"config file: {Path(args.config) if args.config else default_config_path()}")
        for fld in (
            "base_url",
            "model",
            "api_key",
            "temperature",
            "max_tokens",
            "timeout",
            "max_files",
            "max_depth",
            "include_hidden",
            "max_explorations",
            "web_search",
            "max_searches",
            "search_results",
            "search_timeout",
        ):
            val = getattr(config, fld)
            if fld == "api_key" and val:
                val = f"{str(val)[:3]}…{str(val)[-2:]}" if len(str(val)) > 6 else "set"
            ui.print_info(f"  {fld} = {val}")
        return 0

    request = " ".join(args.request).strip()
    if not request:
        parser.print_help(sys.stderr)
        return 2

    cwd = Path.cwd()
    client = LLMClient(config)
    web_enabled = config.web_search and not args.no_web

    try:
        ui.print_info(f"Thinking with {config.model} …")
        answer = run_conversation(
            request,
            config,
            client,
            cwd,
            no_context=args.no_context,
            web_enabled=web_enabled,
        )
    except LLMError as exc:
        ui.print_error(str(exc))
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        ui.print_info("Cancelled.")
        return 130

    # Dry run: just show options, never run or write.
    if args.dry_run:
        for i, opt in enumerate(answer.options, start=1):
            ui.render_option(opt, index=None if len(answer.options) == 1 else i)
        return 0

    try:
        chosen = ui.select_command(answer.options, assume_yes=args.yes)
    except KeyboardInterrupt:  # pragma: no cover
        ui.print_info("Cancelled.")
        return 130

    if chosen is None:
        ui.print_info("Cancelled — nothing run.")
        return 0

    # Safety gate for destructive commands.
    if chosen.danger == "high" or looks_dangerous(chosen.command):
        if not args.yes and not ui.confirm_dangerous(chosen):
            ui.print_info("Cancelled — nothing run.")
            return 0

    # Output-file mode: hand the command to the shell wrapper for current-shell eval.
    if args.output_file:
        write_command(chosen.command, args.output_file)
        return 0

    # Subprocess mode: run it here.
    ui.print_info(f"$ {chosen.command}")
    return run_in_subprocess(chosen.command, cwd=cwd)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
