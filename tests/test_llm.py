"""Tests for command_ai.llm."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from command_ai.config import Config
from command_ai.llm import (
    AnswerResult,
    CommandOption,
    ExploreRequest,
    LLMClient,
    LLMError,
    SYSTEM_PROMPT,
    SearchRequest,
    WEB_SEARCH_BLOCK,
    _loads,
    build_messages,
    build_system_prompt,
    extract_json,
    parse_response,
)


# ---------------------------------------------------------------------------
# CommandOption.from_dict
# ---------------------------------------------------------------------------

class TestCommandOptionFromDict:
    def test_basic(self):
        opt = CommandOption.from_dict({"command": "ls -la", "summary": "List files"})
        assert opt.command == "ls -la"
        assert opt.summary == "List files"
        assert opt.danger == "low"
        assert opt.args == []

    def test_danger_clamped_to_low_on_invalid(self):
        opt = CommandOption.from_dict({"command": "foo", "danger": "extreme"})
        assert opt.danger == "low"

    def test_danger_high(self):
        opt = CommandOption.from_dict({"command": "rm -rf /", "danger": "high"})
        assert opt.danger == "high"

    def test_danger_medium(self):
        opt = CommandOption.from_dict({"command": "mv file.txt /tmp", "danger": "medium"})
        assert opt.danger == "medium"

    def test_danger_uppercase_normalised(self):
        opt = CommandOption.from_dict({"command": "foo", "danger": "HIGH"})
        assert opt.danger == "high"

    def test_args_with_part_and_explains(self):
        opt = CommandOption.from_dict({
            "command": "ls",
            "args": [{"part": "-la", "explains": "long list with hidden"}]
        })
        assert len(opt.args) == 1
        assert opt.args[0]["part"] == "-la"
        assert opt.args[0]["explains"] == "long list with hidden"

    def test_args_with_arg_key_alias(self):
        opt = CommandOption.from_dict({
            "command": "ls",
            "args": [{"arg": "-l", "description": "long format"}]
        })
        assert len(opt.args) == 1
        assert opt.args[0]["part"] == "-l"
        assert opt.args[0]["explains"] == "long format"

    def test_args_as_strings(self):
        opt = CommandOption.from_dict({"command": "ls", "args": ["-la", "-h"]})
        assert len(opt.args) == 2
        assert opt.args[0]["part"] == "-la"
        assert opt.args[0]["explains"] == ""

    def test_empty_part_skipped(self):
        opt = CommandOption.from_dict({
            "command": "ls",
            "args": [{"part": "", "explains": "nothing"}]
        })
        assert opt.args == []

    def test_summary_falls_back_to_description(self):
        opt = CommandOption.from_dict({"command": "ls", "description": "desc fallback"})
        assert opt.summary == "desc fallback"

    def test_missing_command(self):
        opt = CommandOption.from_dict({})
        assert opt.command == ""

    def test_none_args_defaults_to_empty(self):
        opt = CommandOption.from_dict({"command": "ls", "args": None})
        assert opt.args == []


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------

class TestBuildMessages:
    def test_returns_list_with_system_and_user(self):
        msgs = build_messages("list files", "ctx block")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_user_contains_request(self):
        msgs = build_messages("list files", "ctx block")
        assert "list files" in msgs[1]["content"]

    def test_user_contains_context_block(self):
        msgs = build_messages("list files", "MY CTX BLOCK")
        assert "MY CTX BLOCK" in msgs[1]["content"]

    def test_research_log_included(self):
        log = ["dir1: a.txt\n  b.txt"]
        msgs = build_messages("list files", "ctx", research_log=log)
        assert "dir1" in msgs[1]["content"]

    def test_no_research_log_omitted(self):
        msgs = build_messages("list files", "ctx")
        assert "already gathered" not in msgs[1]["content"]

    def test_system_prompt_present(self):
        msgs = build_messages("x", "ctx")
        assert len(msgs[0]["content"]) > 50  # non-trivial system prompt

    def test_web_disabled_system_prompt_matches(self):
        msgs = build_messages("x", "ctx", web_enabled=False)
        assert msgs[0]["content"] == build_system_prompt(False)

    def test_web_enabled_system_prompt_matches(self):
        msgs = build_messages("x", "ctx", web_enabled=True)
        assert msgs[0]["content"] == build_system_prompt(True)

    def test_web_enabled_hint_mentions_search(self):
        msgs = build_messages("x", "ctx", web_enabled=True)
        assert "search the web" in msgs[1]["content"]

    def test_web_disabled_hint_no_search(self):
        msgs = build_messages("x", "ctx", web_enabled=False)
        assert "search the web" not in msgs[1]["content"]


# ---------------------------------------------------------------------------
# build_system_prompt
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    def test_web_disabled_returns_base_prompt(self):
        assert build_system_prompt(web_enabled=False) == SYSTEM_PROMPT

    def test_default_is_web_disabled(self):
        assert build_system_prompt() == SYSTEM_PROMPT

    def test_web_enabled_appends_block(self):
        result = build_system_prompt(web_enabled=True)
        assert result == SYSTEM_PROMPT + "\n\n" + WEB_SEARCH_BLOCK

    def test_web_enabled_contains_search_action(self):
        result = build_system_prompt(web_enabled=True)
        assert '"action": "search"' in result

    def test_web_disabled_no_search_action(self):
        assert '"action": "search"' not in build_system_prompt(web_enabled=False)


# ---------------------------------------------------------------------------
# _loads (tolerant json.loads)
# ---------------------------------------------------------------------------

class TestLoads:
    def test_plain_object(self):
        assert _loads('{"a": 1}') == {"a": 1}

    def test_literal_tab_inside_string(self):
        # Real tab character inside a quoted string value (strict=False).
        result = _loads('{"a":"x\ty"}')
        assert result == {"a": "x\ty"}

    def test_literal_newline_inside_string(self):
        result = _loads('{"a":"x\ny"}')
        assert result == {"a": "x\ny"}

    def test_trailing_comma_object(self):
        assert _loads('{"a":1,}') == {"a": 1}

    def test_trailing_comma_nested_array(self):
        assert _loads('{"a":[1,2,],}') == {"a": [1, 2]}

    def test_trailing_comma_with_whitespace(self):
        assert _loads('{"a": 1 , }') == {"a": 1}


# ---------------------------------------------------------------------------
# extract_json
# ---------------------------------------------------------------------------

class TestExtractJson:
    def test_raw_json(self):
        result = extract_json('{"action": "answer", "options": []}')
        assert result["action"] == "answer"

    def test_json_in_fenced_block(self):
        text = '```json\n{"action": "explore", "path": "/tmp"}\n```'
        result = extract_json(text)
        assert result["action"] == "explore"

    def test_json_in_fenced_block_no_lang(self):
        text = '```\n{"action": "explore", "path": "/tmp"}\n```'
        result = extract_json(text)
        assert result["path"] == "/tmp"

    def test_json_embedded_in_prose(self):
        text = 'Here is the answer: {"command": "ls -la"} which will work.'
        result = extract_json(text)
        assert result["command"] == "ls -la"

    def test_empty_string_raises_llm_error(self):
        with pytest.raises(LLMError):
            extract_json("")

    def test_garbage_raises_llm_error(self):
        with pytest.raises(LLMError):
            extract_json("this is not JSON at all!!!")

    def test_nested_json_object(self):
        data = '{"a": {"b": 1}}'
        result = extract_json(data)
        assert result["a"]["b"] == 1

    def test_json_with_escaped_quotes(self):
        data = '{"command": "echo \\"hello\\"", "summary": "test"}'
        result = extract_json(data)
        assert result["command"] == 'echo "hello"'

    def test_multiple_json_objects_returns_first(self):
        text = 'prefix {"key": "first"} suffix {"key": "second"}'
        result = extract_json(text)
        assert result["key"] == "first"

    # --- hardening: <think> stripping ---

    def test_strips_think_block(self):
        text = '<think>let me reason</think>\n{"command": "ls"}'
        result = extract_json(text)
        assert result["command"] == "ls"

    def test_strips_think_block_containing_braces(self):
        text = '<think>I should use ls {foo}</think>\n{"action":"answer","options":[{"command":"ls"}]}'
        result = extract_json(text)
        assert result["options"][0]["command"] == "ls"

    def test_strips_thinking_tag(self):
        text = '<thinking>hmm {x}</thinking>{"command": "pwd"}'
        result = extract_json(text)
        assert result["command"] == "pwd"

    def test_strips_reasoning_tag(self):
        text = '<reasoning>step {1}</reasoning>{"command": "echo hi"}'
        result = extract_json(text)
        assert result["command"] == "echo hi"

    def test_strips_think_tag_case_insensitive(self):
        text = '<THINK>noise {y}</THINK>{"command": "ls -la"}'
        result = extract_json(text)
        assert result["command"] == "ls -la"

    # --- hardening: literal control chars + trailing commas ---

    def test_literal_newline_in_string_value(self):
        text = '{"command":"a\nb"}'  # real newline
        result = extract_json(text)
        assert result["command"] == "a\nb"

    def test_literal_tab_in_string_value(self):
        text = '{"command":"a\tb"}'  # real tab
        result = extract_json(text)
        assert result["command"] == "a\tb"

    def test_trailing_comma_in_array_and_object(self):
        text = '{"options":[{"command":"ls"},],}'
        result = extract_json(text)
        assert result["options"][0]["command"] == "ls"

    # --- still-invalid input that the retry layer (not extract_json) handles ---

    def test_unescaped_inner_quotes_raises(self):
        # Genuinely invalid JSON: unescaped double-quotes inside a string.
        with pytest.raises(LLMError):
            extract_json('{"command":"echo "hi""}')


# ---------------------------------------------------------------------------
# parse_response
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_explore_with_action_field(self):
        text = '{"action": "explore", "path": "/tmp/mydir"}'
        result = parse_response(text)
        assert isinstance(result, ExploreRequest)
        assert result.path == "/tmp/mydir"

    def test_explore_with_path_no_options(self):
        # "path" present but no "options" -> ExploreRequest
        text = '{"path": "/some/dir"}'
        result = parse_response(text)
        assert isinstance(result, ExploreRequest)
        assert result.path == "/some/dir"

    def test_explore_missing_path_raises(self):
        text = '{"action": "explore", "path": ""}'
        with pytest.raises(LLMError, match="missing a path"):
            parse_response(text)

    def test_search_with_action_field(self):
        text = '{"action": "search", "query": "homebrew formula for x"}'
        result = parse_response(text)
        assert isinstance(result, SearchRequest)
        assert result.query == "homebrew formula for x"

    def test_search_with_query_no_action(self):
        # "query" present, no action, no options/command -> SearchRequest
        text = '{"query": "best ffmpeg flags"}'
        result = parse_response(text)
        assert isinstance(result, SearchRequest)
        assert result.query == "best ffmpeg flags"

    def test_search_missing_query_raises(self):
        text = '{"action": "search"}'
        with pytest.raises(LLMError, match="missing a query"):
            parse_response(text)

    def test_search_empty_query_raises(self):
        text = '{"action": "search", "query": ""}'
        with pytest.raises(LLMError, match="missing a query"):
            parse_response(text)

    def test_explore_still_works_with_search_present(self):
        # explore action should still produce ExploreRequest
        text = '{"action": "explore", "path": "p"}'
        result = parse_response(text)
        assert isinstance(result, ExploreRequest)
        assert result.path == "p"

    def test_answer_with_options_still_works(self):
        text = '{"options": [{"command": "ls"}]}'
        result = parse_response(text)
        assert isinstance(result, AnswerResult)
        assert result.options[0].command == "ls"

    def test_bare_command_still_works(self):
        text = '{"command": "ls -la"}'
        result = parse_response(text)
        assert isinstance(result, AnswerResult)
        assert result.options[0].command == "ls -la"

    def test_query_with_command_treated_as_answer(self):
        # query present but command also present -> not a search, an answer
        text = '{"query": "x", "command": "ls"}'
        result = parse_response(text)
        assert isinstance(result, AnswerResult)

    def test_think_block_then_answer(self):
        text = '<think>I should use ls {foo}</think>\n{"action":"answer","options":[{"command":"ls"}]}'
        result = parse_response(text)
        assert isinstance(result, AnswerResult)
        assert result.options[0].command == "ls"

    def test_answer_with_options(self):
        text = '{"action": "answer", "options": [{"command": "ls -la", "summary": "list"}]}'
        result = parse_response(text)
        assert isinstance(result, AnswerResult)
        assert len(result.options) == 1
        assert result.options[0].command == "ls -la"

    def test_answer_with_multiple_options(self):
        text = (
            '{"action": "answer", "options": ['
            '{"command": "ls -la"}, {"command": "ls -lh"}]}'
        )
        result = parse_response(text)
        assert isinstance(result, AnswerResult)
        assert len(result.options) == 2

    def test_bare_command_no_wrapper(self):
        # Model returned a single option without the wrapper
        text = '{"command": "ls -la", "summary": "list all"}'
        result = parse_response(text)
        assert isinstance(result, AnswerResult)
        assert result.options[0].command == "ls -la"

    def test_empty_options_raises(self):
        text = '{"action": "answer", "options": []}'
        with pytest.raises(LLMError, match="no command options"):
            parse_response(text)

    def test_options_with_no_command_raises(self):
        text = '{"action": "answer", "options": [{"summary": "no command here"}]}'
        with pytest.raises(LLMError, match="no usable commands"):
            parse_response(text)

    def test_garbage_text_raises(self):
        with pytest.raises(LLMError):
            parse_response("not JSON at all")

    def test_empty_text_raises(self):
        with pytest.raises(LLMError):
            parse_response("")

    def test_danger_field_preserved(self):
        text = '{"action": "answer", "options": [{"command": "rm -rf /", "danger": "high"}]}'
        result = parse_response(text)
        assert result.options[0].danger == "high"


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------

class FakeCompletion:
    """Fake response from client.chat.completions.create()."""
    def __init__(self, content):
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


class FakeOpenAIClient:
    """Fake OpenAI client."""
    def __init__(self, content):
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kw: FakeCompletion(content)
            )
        )


class ErrorOpenAIClient:
    """Fake client that raises on create."""
    def __init__(self, exc):
        self._exc = exc
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._raise)
        )

    def _raise(self, **kw):
        raise self._exc


class TestLLMClient:
    def test_complete_success(self):
        fake_client = FakeOpenAIClient('{"command": "ls"}')
        cfg = Config()
        llm = LLMClient(cfg, client=fake_client)
        result = llm.complete([{"role": "user", "content": "hi"}])
        assert result == '{"command": "ls"}'

    def test_complete_passes_model_and_params(self):
        calls = []
        def fake_create(**kw):
            calls.append(kw)
            return FakeCompletion("ok")
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        cfg = Config(model="test-model", temperature=0.5, max_tokens=100)
        llm = LLMClient(cfg, client=fake_client)
        llm.complete([{"role": "user", "content": "hi"}])
        assert calls[0]["model"] == "test-model"
        assert calls[0]["temperature"] == 0.5
        assert calls[0]["max_tokens"] == 100

    def test_empty_content_raises_llm_error(self):
        fake_client = FakeOpenAIClient("")
        cfg = Config()
        llm = LLMClient(cfg, client=fake_client)
        with pytest.raises(LLMError, match="empty"):
            llm.complete([])

    def test_none_content_raises_llm_error(self):
        fake_client = FakeOpenAIClient(None)
        cfg = Config()
        llm = LLMClient(cfg, client=fake_client)
        with pytest.raises(LLMError):
            llm.complete([])

    def test_exception_from_create_raises_llm_error(self):
        fake_client = ErrorOpenAIClient(ConnectionError("refused"))
        cfg = Config()
        llm = LLMClient(cfg, client=fake_client)
        with pytest.raises(LLMError, match="Could not reach"):
            llm.complete([])

    def test_malformed_response_raises_llm_error(self):
        # Simulate a response object with no choices
        bad_resp = SimpleNamespace(choices=[])
        def bad_create(**kw):
            return bad_resp
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=bad_create))
        )
        cfg = Config()
        llm = LLMClient(cfg, client=fake_client)
        with pytest.raises(LLMError):
            llm.complete([])
