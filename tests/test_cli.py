"""Tests for command_ai.cli."""

from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import pytest

import command_ai.cli as cli
import command_ai.search as search
import command_ai.ui as ui
from command_ai.config import Config
from command_ai.llm import (
    AnswerResult,
    CommandOption,
    ExploreRequest,
    LLMError,
    SearchRequest,
)
from command_ai.search import SearchError, SearchHit


# ---------------------------------------------------------------------------
# Fake LLM client helpers
# ---------------------------------------------------------------------------

class FakeLLMClient:
    """LLM client that returns a queue of canned responses."""

    def __init__(self, responses: list[str]):
        self._responses = iter(responses)

    def complete(self, messages) -> str:
        return next(self._responses)


class FakeLLMClientRaises:
    """LLM client that always raises LLMError."""
    def complete(self, messages) -> str:
        raise LLMError("test error")


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_returns_argument_parser(self):
        parser = cli.build_parser()
        assert isinstance(parser, argparse.ArgumentParser)

    def test_request_nargs_star(self):
        parser = cli.build_parser()
        args = parser.parse_args(["list", "files"])
        assert args.request == ["list", "files"]

    def test_request_empty(self):
        parser = cli.build_parser()
        args = parser.parse_args([])
        assert args.request == []

    def test_model_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--model", "gpt-4", "do", "something"])
        assert args.model == "gpt-4"

    def test_base_url_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--base-url", "http://x/v1", "do", "x"])
        assert args.base_url == "http://x/v1"

    def test_api_key_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--api-key", "mykey", "do", "x"])
        assert args.api_key == "mykey"

    def test_config_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--config", "/tmp/c.toml", "do", "x"])
        assert args.config == "/tmp/c.toml"

    def test_output_file_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--output-file", "/tmp/cmd.sh", "do", "x"])
        assert args.output_file == "/tmp/cmd.sh"

    def test_yes_flag_short(self):
        parser = cli.build_parser()
        args = parser.parse_args(["-y", "do", "x"])
        assert args.yes is True

    def test_yes_flag_long(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--yes", "do", "x"])
        assert args.yes is True

    def test_dry_run_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["-n", "do", "x"])
        assert args.dry_run is True

    def test_no_context_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--no-context", "do", "x"])
        assert args.no_context is True

    def test_no_web_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--no-web", "do", "x"])
        assert args.no_web is True

    def test_no_web_default_false(self):
        parser = cli.build_parser()
        args = parser.parse_args(["do", "x"])
        assert args.no_web is False

    def test_print_config_flag(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--print-config"])
        assert args.print_config is True

    def test_version_flag_exits(self):
        parser = cli.build_parser()
        with pytest.raises(SystemExit) as exc_info:
            parser.parse_args(["--version"])
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# resolve_config
# ---------------------------------------------------------------------------

class TestResolveConfig:
    def test_returns_config(self):
        parser = cli.build_parser()
        args = parser.parse_args(["do", "something"])
        cfg = cli.resolve_config(args)
        assert isinstance(cfg, Config)

    def test_model_override(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--model", "custom-model", "do", "x"])
        cfg = cli.resolve_config(args)
        assert cfg.model == "custom-model"

    def test_base_url_override(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--base-url", "http://custom/v1", "do", "x"])
        cfg = cli.resolve_config(args)
        assert cfg.base_url == "http://custom/v1"

    def test_api_key_override(self):
        parser = cli.build_parser()
        args = parser.parse_args(["--api-key", "mykey", "do", "x"])
        cfg = cli.resolve_config(args)
        assert cfg.api_key == "mykey"

    def test_config_path(self, tmp_path):
        toml = tmp_path / "c.toml"
        toml.write_text('model = "file-model"\n', encoding="utf-8")
        parser = cli.build_parser()
        args = parser.parse_args(["--config", str(toml), "do", "x"])
        cfg = cli.resolve_config(args)
        assert cfg.model == "file-model"


# ---------------------------------------------------------------------------
# default_searcher
# ---------------------------------------------------------------------------

class TestDefaultSearcher:
    def test_returns_rendered_results(self, monkeypatch):
        hits = [SearchHit(title="Title", url="http://x.com", snippet="snip")]
        monkeypatch.setattr(cli, "web_search", lambda q, n, t: hits)
        searcher = cli.default_searcher(Config())
        result = searcher("my query")
        assert "Web search results for 'my query':" in result
        assert "Title" in result
        assert "http://x.com" in result

    def test_passes_config_params(self, monkeypatch):
        captured = {}
        def fake_web_search(q, n, t):
            captured["query"] = q
            captured["n"] = n
            captured["t"] = t
            return []
        monkeypatch.setattr(cli, "web_search", fake_web_search)
        cfg = Config(search_results=9, search_timeout=22.0)
        searcher = cli.default_searcher(cfg)
        searcher("a query")
        assert captured["query"] == "a query"
        assert captured["n"] == 9
        assert captured["t"] == 22.0

    def test_search_error_returns_failure_note(self, monkeypatch):
        def boom(q, n, t):
            raise SearchError("network unreachable")
        monkeypatch.setattr(cli, "web_search", boom)
        searcher = cli.default_searcher(Config())
        result = searcher("my query")
        assert result.startswith("Web search for 'my query' failed:")
        assert "network unreachable" in result

    def test_empty_results_renders_no_results(self, monkeypatch):
        monkeypatch.setattr(cli, "web_search", lambda q, n, t: [])
        searcher = cli.default_searcher(Config())
        result = searcher("q")
        assert "no results" in result


# ---------------------------------------------------------------------------
# run_conversation
# ---------------------------------------------------------------------------

ANSWER_JSON = '{"action": "answer", "options": [{"command": "ls -la", "summary": "list files", "danger": "low"}]}'
EXPLORE_JSON = '{"action": "explore", "path": "."}'
SEARCH_JSON = '{"action": "search", "query": "homebrew formula for foo"}'


class TestRunConversation:
    def test_returns_answer_result(self, tmp_path):
        client = FakeLLMClient([ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation("list files", cfg, client, tmp_path)
        assert isinstance(result, AnswerResult)
        assert result.options[0].command == "ls -la"

    def test_explore_then_answer(self, tmp_path):
        # First response: explore; second: answer
        client = FakeLLMClient([EXPLORE_JSON, ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation("list files", cfg, client, tmp_path)
        assert isinstance(result, AnswerResult)

    def test_never_answers_raises_llm_error(self, tmp_path):
        # Always explores — should raise after max_explorations+1
        cfg = Config(max_explorations=2)
        responses = [EXPLORE_JSON] * 10  # more than enough
        client = FakeLLMClient(responses)
        with pytest.raises(LLMError, match="kept gathering"):
            cli.run_conversation("list files", cfg, client, tmp_path)

    def test_no_context_mode(self, tmp_path):
        client = FakeLLMClient([ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation("list files", cfg, client, tmp_path, no_context=True)
        assert isinstance(result, AnswerResult)

    def test_llm_error_propagates(self, tmp_path):
        client = FakeLLMClientRaises()
        cfg = Config()
        with pytest.raises(LLMError):
            cli.run_conversation("list files", cfg, client, tmp_path)

    def test_explore_resolves_relative_path(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        explore_relative = '{"action": "explore", "path": "subdir"}'
        client = FakeLLMClient([explore_relative, ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation("list files", cfg, client, tmp_path)
        assert isinstance(result, AnswerResult)

    def test_single_exploration_allowed(self, tmp_path):
        """max_explorations=1 means we loop twice (0 explores + 1 extra = 2 turns)."""
        cfg = Config(max_explorations=1)
        client = FakeLLMClient([EXPLORE_JSON, ANSWER_JSON])
        result = cli.run_conversation("x", cfg, client, tmp_path)
        assert isinstance(result, AnswerResult)

    # --- web search behaviors ---

    def test_search_then_answer_calls_searcher(self, tmp_path):
        calls = []
        def fake_searcher(query):
            calls.append(query)
            return "search results block"
        client = FakeLLMClient([SEARCH_JSON, ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation(
            "find a tool", cfg, client, tmp_path,
            web_enabled=True, searcher=fake_searcher,
        )
        assert isinstance(result, AnswerResult)
        assert len(calls) == 1
        assert calls[0] == "homebrew formula for foo"

    def test_search_not_called_when_web_disabled(self, tmp_path):
        calls = []
        def fake_searcher(query):
            calls.append(query)
            return "should not be used"
        # model asks to search, then answers; web disabled -> searcher never called
        client = FakeLLMClient([SEARCH_JSON, ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation(
            "find a tool", cfg, client, tmp_path,
            web_enabled=False, searcher=fake_searcher,
        )
        assert isinstance(result, AnswerResult)
        assert calls == []

    def test_search_limit_respected(self, tmp_path):
        calls = []
        def fake_searcher(query):
            calls.append(query)
            return "results"
        # model searches twice, then answers; max_searches=1 -> only one search runs
        client = FakeLLMClient([SEARCH_JSON, SEARCH_JSON, ANSWER_JSON])
        cfg = Config(max_searches=1)
        result = cli.run_conversation(
            "find a tool", cfg, client, tmp_path,
            web_enabled=True, searcher=fake_searcher,
        )
        assert isinstance(result, AnswerResult)
        assert len(calls) == 1

    def test_default_searcher_built_when_none(self, tmp_path, monkeypatch):
        # web_enabled True, searcher None -> internal default_searcher is used,
        # which calls cli.web_search (monkeypatched to avoid network).
        hits = [SearchHit(title="T", url="http://x", snippet="s")]
        monkeypatch.setattr(cli, "web_search", lambda q, n, t: hits)
        client = FakeLLMClient([SEARCH_JSON, ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation(
            "find a tool", cfg, client, tmp_path,
            web_enabled=True, searcher=None,
        )
        assert isinstance(result, AnswerResult)

    def test_search_then_explore_then_answer(self, tmp_path):
        def fake_searcher(query):
            return "search results"
        client = FakeLLMClient([SEARCH_JSON, EXPLORE_JSON, ANSWER_JSON])
        cfg = Config()
        result = cli.run_conversation(
            "find a tool", cfg, client, tmp_path,
            web_enabled=True, searcher=fake_searcher,
        )
        assert isinstance(result, AnswerResult)


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

def make_fake_llm_class(responses: list[str]):
    """Return a class whose instances have .complete() returning queued responses."""
    class FakeClass:
        def __init__(self, config, **kwargs):
            self._responses = iter(responses)

        def complete(self, messages) -> str:
            return next(self._responses)

    return FakeClass


class TestMain:
    def _patch_llm(self, monkeypatch, responses: list[str]):
        monkeypatch.setattr(cli, "LLMClient", make_fake_llm_class(responses))

    def _patch_select(self, monkeypatch, return_value):
        monkeypatch.setattr(ui, "select_command", lambda opts, **kw: return_value)

    def test_no_request_returns_2(self, monkeypatch):
        rc = cli.main([])
        assert rc == 2

    def test_print_config_returns_0(self, monkeypatch):
        rc = cli.main(["--print-config"])
        assert rc == 0

    def test_dry_run_returns_0(self, monkeypatch):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        rc = cli.main(["--dry-run", "list", "files"])
        assert rc == 0

    def test_dry_run_does_not_call_select(self, monkeypatch):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        called = []
        monkeypatch.setattr(ui, "select_command", lambda *a, **kw: called.append(1) or None)
        cli.main(["--dry-run", "list", "files"])
        assert len(called) == 0

    def test_cancel_returns_0(self, monkeypatch):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        self._patch_select(monkeypatch, None)
        rc = cli.main(["list", "files"])
        assert rc == 0

    def test_output_file_writes_command(self, monkeypatch, tmp_path):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        opt = CommandOption(command="ls -la", summary="list", danger="low")
        self._patch_select(monkeypatch, opt)
        out = tmp_path / "cmd.sh"
        rc = cli.main(["--output-file", str(out), "list", "files"])
        assert rc == 0
        assert out.exists()
        content = out.read_text(encoding="utf-8")
        assert "ls -la" in content

    def test_output_file_returns_0(self, monkeypatch, tmp_path):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        opt = CommandOption(command="ls -la", summary="list", danger="low")
        self._patch_select(monkeypatch, opt)
        out = tmp_path / "cmd.sh"
        rc = cli.main(["--output-file", str(out), "list", "files"])
        assert rc == 0

    def test_llm_error_returns_1(self, monkeypatch):
        class ErrorLLMClient:
            def __init__(self, config, **kwargs):
                pass
            def complete(self, messages):
                raise LLMError("boom")
        monkeypatch.setattr(cli, "LLMClient", ErrorLLMClient)
        rc = cli.main(["list", "files"])
        assert rc == 1

    def test_subprocess_mode_returns_exit_code(self, monkeypatch):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        opt = CommandOption(command="exit 7", summary="exit", danger="low")
        self._patch_select(monkeypatch, opt)
        import command_ai.executor as executor
        import subprocess
        # monkeypatch subprocess.run to return exit code 7
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: SimpleNamespace(returncode=7))
        rc = cli.main(["list", "files"])
        assert rc == 7

    def test_high_danger_with_yes_skips_confirm(self, monkeypatch, tmp_path):
        danger_json = '{"action": "answer", "options": [{"command": "rm -rf /tmp/x", "summary": "delete", "danger": "high"}]}'
        self._patch_llm(monkeypatch, [danger_json])
        opt = CommandOption(command="rm -rf /tmp/x", summary="delete", danger="high")
        self._patch_select(monkeypatch, opt)
        out = tmp_path / "cmd.sh"
        rc = cli.main(["--yes", "--output-file", str(out), "delete", "stuff"])
        assert rc == 0

    def test_high_danger_without_yes_non_tty_cancels(self, monkeypatch, tmp_path):
        """Non-interactive + high danger + no --yes = confirm_dangerous returns False -> cancel."""
        danger_json = '{"action": "answer", "options": [{"command": "rm -rf /tmp/x", "summary": "delete", "danger": "high"}]}'
        self._patch_llm(monkeypatch, [danger_json])
        opt = CommandOption(command="rm -rf /tmp/x", summary="delete", danger="high")
        self._patch_select(monkeypatch, opt)
        monkeypatch.setattr(ui, "_interactive", lambda: False)
        rc = cli.main(["list", "files"])
        assert rc == 0  # cancelled, not run

    def test_no_context_flag(self, monkeypatch, tmp_path):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        opt = CommandOption(command="ls", summary="list", danger="low")
        self._patch_select(monkeypatch, opt)
        out = tmp_path / "cmd.sh"
        rc = cli.main(["--no-context", "--output-file", str(out), "list", "files"])
        assert rc == 0

    def test_yes_flag_picks_first(self, monkeypatch, tmp_path):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        # Don't patch select_command, but assume_yes=True means it returns options[0]
        # which is "ls -la" with low danger
        monkeypatch.setattr(ui, "_interactive", lambda: False)
        out = tmp_path / "cmd.sh"
        rc = cli.main(["--yes", "--output-file", str(out), "list", "files"])
        assert rc == 0
        content = out.read_text(encoding="utf-8")
        assert "ls -la" in content

    def test_explore_then_answer_main(self, monkeypatch, tmp_path):
        self._patch_llm(monkeypatch, [EXPLORE_JSON, ANSWER_JSON])
        opt = CommandOption(command="ls -la", summary="list", danger="low")
        self._patch_select(monkeypatch, opt)
        out = tmp_path / "cmd.sh"
        rc = cli.main(["--output-file", str(out), "list", "files"])
        assert rc == 0

    def test_no_web_happy_path(self, monkeypatch, tmp_path):
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        opt = CommandOption(command="ls -la", summary="list", danger="low")
        self._patch_select(monkeypatch, opt)
        out = tmp_path / "cmd.sh"
        rc = cli.main(["--no-web", "--output-file", str(out), "list", "files"])
        assert rc == 0
        assert "ls -la" in out.read_text(encoding="utf-8")

    def test_no_web_passes_web_enabled_false(self, monkeypatch):
        # Capture kwargs passed to run_conversation.
        captured = {}
        def fake_run_conversation(request, config, client, cwd, **kwargs):
            captured.update(kwargs)
            return AnswerResult(options=[CommandOption(command="ls", danger="low")])
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        monkeypatch.setattr(cli, "run_conversation", fake_run_conversation)
        self._patch_select(monkeypatch, None)  # cancel so nothing runs
        cli.main(["--no-web", "list", "files"])
        assert captured["web_enabled"] is False

    def test_web_enabled_true_by_default(self, monkeypatch):
        # Without --no-web, and config.web_search default True -> web_enabled True.
        captured = {}
        def fake_run_conversation(request, config, client, cwd, **kwargs):
            captured.update(kwargs)
            return AnswerResult(options=[CommandOption(command="ls", danger="low")])
        self._patch_llm(monkeypatch, [ANSWER_JSON])
        monkeypatch.setattr(cli, "run_conversation", fake_run_conversation)
        self._patch_select(monkeypatch, None)
        cli.main(["list", "files"])
        assert captured["web_enabled"] is True

    def test_print_config_masks_long_api_key(self, monkeypatch, capsys, tmp_path):
        # Provide a long api key via config file and assert it is masked in output.
        toml = tmp_path / "c.toml"
        toml.write_text('api_key = "supersecretkey123"\n', encoding="utf-8")
        # print_info writes to a rich Console bound to stderr; capture via capsys.
        printed = []
        monkeypatch.setattr(ui, "print_info", lambda msg: printed.append(msg))
        rc = cli.main(["--config", str(toml), "--print-config"])
        assert rc == 0
        joined = "\n".join(printed)
        # The raw key must NOT appear; the masked form (with ellipsis) should.
        assert "supersecretkey123" not in joined
        assert "sup…23" in joined

    def test_print_config_short_api_key_shows_set(self, monkeypatch, tmp_path):
        toml = tmp_path / "c.toml"
        toml.write_text('api_key = "abc"\n', encoding="utf-8")
        printed = []
        monkeypatch.setattr(ui, "print_info", lambda msg: printed.append(msg))
        rc = cli.main(["--config", str(toml), "--print-config"])
        assert rc == 0
        joined = "\n".join(printed)
        assert "abc" not in joined
        assert "api_key = set" in joined
