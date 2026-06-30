"""Command-line entry point and the explore→answer→confirm→run loop."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, credentials, providers
from .config import Config, default_config_path, load_config
from .context import gather_context, list_directory, parse_shell_context
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
    parser.add_argument(
        "--provider",
        choices=providers.provider_names(),
        help="LLM provider preset (sets endpoint/model). Default: local.",
    )
    parser.add_argument("--model", help="Override the model name.")
    parser.add_argument("--base-url", dest="base_url", help="Override the endpoint base URL.")
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="Override the API key. NOTE: visible in the process list (ps) while running; "
        "prefer AI_API_KEY or --set-api-key.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Allow sending the API key/prompt to a non-loopback http:// endpoint in "
        "cleartext. Not recommended.",
    )
    parser.add_argument(
        "--set-api-key",
        action="store_true",
        help="Prompt for and securely store the API key for the chosen provider, then exit.",
    )
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
        "--shell-context-file",
        dest="shell_context_file",
        help="Path to a file with recent shell context (written by the ai shell function).",
    )
    parser.add_argument(
        "--no-shell-context",
        action="store_true",
        help="Ignore recent shell history/exit-code context for this run.",
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
        "provider": args.provider,
        "model": args.model,
        "base_url": args.base_url,
        "api_key": args.api_key,
        "allow_insecure_http": True if getattr(args, "insecure", False) else None,
    }
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path=config_path, overrides=overrides)

    # The --provider flag, used explicitly on the command line, is authoritative
    # for the endpoint: apply its preset over any base_url/model pinned in the
    # config file (but not over --base-url/--model given on the same command).
    if args.provider:
        prov = providers.get_provider(args.provider)
        if prov:
            updates: dict = {}
            if not args.base_url:
                updates["base_url"] = prov["base_url"]
            if not args.model:
                updates["model"] = prov["default_model"]
            if updates:
                config = config.with_overrides(**updates)
    return config


def resolve_api_key(args: argparse.Namespace, config: Config) -> str | None:
    """Resolve the API key for the chosen provider.

    Precedence: explicit --api-key / AI_API_KEY (already in config.api_key) >
    stored key (keychain/file) > interactive prompt. Returns None if a required
    key can't be obtained (e.g. non-interactive with nothing stored).
    """
    prov = providers.get_provider(config.provider) or providers.get_provider(
        providers.DEFAULT_PROVIDER
    )
    if not prov["requires_key"]:
        return config.api_key

    # An explicitly-provided key (flag or env) wins and is not the local placeholder.
    explicit = args.api_key or os.environ.get("AI_API_KEY")
    if explicit:
        return explicit
    if config.api_key and config.api_key not in ("", "lm-studio"):
        return config.api_key

    stored = credentials.get_api_key(config.provider)
    if stored:
        return stored

    # Nothing stored: ask for it interactively, offer to save.
    key = ui.prompt_api_key(config.provider, prov)
    if not key:
        return None
    if ui.confirm_store_key(credentials.storage_location()):
        where = credentials.set_api_key(config.provider, key)
        ui.print_info(f"Saved to {where}.")
    return key


def default_searcher(config: Config):
    """Return a callable that runs a web search and renders it, or an error note."""

    def _search(query: str) -> str:
        try:
            hits = web_search(query, config.search_results, config.search_timeout)
        except SearchError as exc:
            return f"Web search for {query!r} failed: {exc}"
        return render_results(query, hits)

    return _search


def read_shell_context(args: argparse.Namespace, config: Config) -> str | None:
    """Load and format the shell-context file, honouring config/flag toggles."""
    if args.no_shell_context or not config.shell_context or not args.shell_context_file:
        return None
    try:
        raw = Path(args.shell_context_file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_shell_context(raw, max_history=config.max_history)


_CORRECTION = (
    "Your previous reply could not be parsed. Reply with ONLY a single JSON "
    "object in the required format — no prose, no markdown, no code fences, and "
    "make sure all strings are properly quoted and escaped."
)


def complete_and_parse(client: LLMClient, messages, config: Config):
    """Call the model and parse its reply, re-asking on unparseable output.

    Local models occasionally emit malformed JSON; rather than fail the whole
    request, we show the model its mistake and ask again, up to
    ``config.max_parse_retries`` extra times.
    """
    convo = list(messages)
    last_error: LLMError | None = None
    last_raw = ""
    for attempt in range(max(0, config.max_parse_retries) + 1):
        raw = client.complete(convo)
        last_raw = raw
        try:
            return parse_response(raw)
        except LLMError as exc:
            last_error = exc
            if attempt < max(0, config.max_parse_retries):
                ui.print_info("Model reply was malformed; asking it to try again…")
                convo = convo + [
                    {"role": "assistant", "content": raw[:4000]},
                    {"role": "user", "content": _CORRECTION},
                ]
    snippet = (last_raw or "").strip().replace("\n", " ")[:160]
    raise LLMError(
        f"{last_error}"
        + (f" Model said: {snippet!r}" if snippet else "")
    )


def run_conversation(
    request: str,
    config: Config,
    client: LLMClient,
    cwd: Path,
    no_context: bool = False,
    web_enabled: bool = False,
    searcher=None,
    shell_context: str | None = None,
) -> AnswerResult:
    """Drive the explore/search loop until the model returns a final answer."""
    base_context = "(context disabled)" if no_context else gather_context(cwd, config)
    if shell_context:
        base_context = f"{base_context}\n\n{shell_context}"
    research_log: list[str] = []

    explores_left = max(0, config.max_explorations)
    searches_left = max(0, config.max_searches) if web_enabled else 0
    if searcher is None and web_enabled:
        searcher = default_searcher(config)

    max_turns = explores_left + searches_left + 1
    for _ in range(max_turns + 1):
        messages = build_messages(request, base_context, research_log, web_enabled=web_enabled)
        result = complete_and_parse(client, messages, config)

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
        # Resolve the requested path against cwd (joining an absolute path or a
        # leading '~' is discarded/ignored here — `.resolve()` does not expand
        # '~'), then confine exploration to the working-directory subtree. A
        # model — possibly steered by prompt injection — must not enumerate
        # ~/.ssh, ~/.aws, /etc, … and leak those listings to the provider (F-04).
        target = (cwd / result.path).resolve()
        cwd_resolved = cwd.resolve()
        if target != cwd_resolved and cwd_resolved not in target.parents:
            ui.print_info(f"… refused to explore outside the working directory: {result.path}")
            research_log.append(
                f"(refused: {result.path!r} is outside the working directory; "
                "only the current directory and its subdirectories may be explored)"
            )
            continue
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

    # Set-and-store an API key, then exit.
    if args.set_api_key:
        prov = providers.get_provider(config.provider)
        if not prov:
            ui.print_error(f"Unknown provider: {config.provider}")
            return 2
        if not prov["requires_key"]:
            ui.print_info(f"Provider '{config.provider}' does not require an API key.")
            return 0
        key = ui.prompt_api_key(config.provider, prov)
        if not key:
            ui.print_error("No key entered.")
            return 1
        where = credentials.set_api_key(config.provider, key)
        ui.print_info(f"Saved {config.provider} API key to {where}.")
        return 0

    if args.print_config:
        ui.print_info(f"config file: {Path(args.config) if args.config else default_config_path()}")
        for fld in (
            "provider",
            "base_url",
            "model",
            "api_key",
            "temperature",
            "max_tokens",
            "timeout",
            "allow_insecure_http",
            "max_files",
            "max_depth",
            "include_hidden",
            "max_explorations",
            "web_search",
            "max_searches",
            "search_results",
            "search_timeout",
            "shell_context",
            "max_history",
            "max_parse_retries",
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

    # Resolve the API key for the provider (may prompt + store for OpenRouter).
    api_key = resolve_api_key(args, config)
    if api_key is None:
        prov = providers.get_provider(config.provider)
        ui.print_error(
            f"{prov['label'] if prov else config.provider} needs an API key. "
            f"Run `ai --provider {config.provider} --set-api-key`, or set AI_API_KEY."
        )
        return 2
    config = config.with_overrides(api_key=api_key)

    cwd = Path.cwd()
    client = LLMClient(config)
    web_enabled = config.web_search and not args.no_web
    shell_context = read_shell_context(args, config)

    try:
        ui.print_info(f"Thinking with {config.model} …")
        answer = run_conversation(
            request,
            config,
            client,
            cwd,
            no_context=args.no_context,
            web_enabled=web_enabled,
            shell_context=shell_context,
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
