"""Tests for command_ai.config."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from command_ai.config import (
    Config,
    DEFAULT_API_KEY,
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    default_config_path,
    load_config,
)


# ---------------------------------------------------------------------------
# Config dataclass and with_overrides
# ---------------------------------------------------------------------------

class TestConfigDefaults:
    def test_default_base_url(self):
        cfg = Config()
        assert cfg.base_url == DEFAULT_BASE_URL

    def test_default_model(self):
        cfg = Config()
        assert cfg.model == DEFAULT_MODEL

    def test_default_api_key(self):
        cfg = Config()
        assert cfg.api_key == DEFAULT_API_KEY

    def test_default_temperature(self):
        cfg = Config()
        assert cfg.temperature == 0.2

    def test_default_max_tokens(self):
        cfg = Config()
        assert cfg.max_tokens == 1024

    def test_default_timeout(self):
        cfg = Config()
        assert cfg.timeout == 120.0

    def test_default_max_files(self):
        cfg = Config()
        assert cfg.max_files == 200

    def test_default_max_depth(self):
        cfg = Config()
        assert cfg.max_depth == 2

    def test_default_include_hidden(self):
        cfg = Config()
        assert cfg.include_hidden is False

    def test_default_max_explorations(self):
        cfg = Config()
        assert cfg.max_explorations == 4

    def test_default_web_search(self):
        cfg = Config()
        assert cfg.web_search is True

    def test_default_max_searches(self):
        cfg = Config()
        assert cfg.max_searches == 3

    def test_default_search_results(self):
        cfg = Config()
        assert cfg.search_results == 5

    def test_default_search_timeout(self):
        cfg = Config()
        assert cfg.search_timeout == 15.0

    def test_default_shell_context(self):
        cfg = Config()
        assert cfg.shell_context is True

    def test_default_max_history(self):
        cfg = Config()
        assert cfg.max_history == 15

    def test_default_max_parse_retries(self):
        cfg = Config()
        assert cfg.max_parse_retries == 2


class TestWithOverrides:
    def test_override_single_field(self):
        cfg = Config()
        new = cfg.with_overrides(model="my-model")
        assert new.model == "my-model"
        assert new.base_url == cfg.base_url  # unchanged

    def test_none_values_ignored(self):
        cfg = Config()
        new = cfg.with_overrides(model=None, temperature=None)
        assert new.model == cfg.model
        assert new.temperature == cfg.temperature

    def test_override_multiple_fields(self):
        cfg = Config()
        new = cfg.with_overrides(model="x", temperature=0.9, max_tokens=512)
        assert new.model == "x"
        assert new.temperature == 0.9
        assert new.max_tokens == 512

    def test_original_unchanged(self):
        cfg = Config()
        original_model = cfg.model
        cfg.with_overrides(model="new-model")
        assert cfg.model == original_model

    def test_override_bool_field(self):
        cfg = Config()
        new = cfg.with_overrides(include_hidden=True)
        assert new.include_hidden is True


# ---------------------------------------------------------------------------
# default_config_path
# ---------------------------------------------------------------------------

class TestDefaultConfigPath:
    def test_default_uses_home_config(self, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        path = default_config_path()
        assert path == Path.home() / ".config" / "command-ai" / "config.toml"

    def test_honors_xdg_config_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        path = default_config_path()
        assert path == tmp_path / "command-ai" / "config.toml"

    def test_returns_path_object(self, monkeypatch):
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        path = default_config_path()
        assert isinstance(path, Path)


# ---------------------------------------------------------------------------
# load_config – file loading
# ---------------------------------------------------------------------------

class TestLoadConfigFile:
    def test_no_file_returns_defaults(self, tmp_path):
        missing = tmp_path / "nonexistent.toml"
        cfg = load_config(config_path=missing)
        assert cfg == Config()

    def test_flat_toml_keys(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('model = "my-model"\ntemperature = 0.7\n', encoding="utf-8")
        cfg = load_config(config_path=toml)
        assert cfg.model == "my-model"
        assert cfg.temperature == 0.7

    def test_nested_llm_table(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('[llm]\nmodel = "nested-model"\nmax_tokens = 2048\n', encoding="utf-8")
        cfg = load_config(config_path=toml)
        assert cfg.model == "nested-model"
        assert cfg.max_tokens == 2048

    def test_nested_context_table(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('[context]\nmax_depth = 5\ninclude_hidden = true\n', encoding="utf-8")
        cfg = load_config(config_path=toml)
        assert cfg.max_depth == 5
        assert cfg.include_hidden is True

    def test_nested_explore_table(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('[explore]\nmax_explorations = 10\n', encoding="utf-8")
        cfg = load_config(config_path=toml)
        assert cfg.max_explorations == 10

    def test_mixed_flat_and_nested(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text(
            'base_url = "http://example.com/v1"\n[llm]\nmodel = "cool-model"\n',
            encoding="utf-8"
        )
        cfg = load_config(config_path=toml)
        assert cfg.base_url == "http://example.com/v1"
        assert cfg.model == "cool-model"

    def test_flat_web_search_keys(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text(
            "web_search = false\nmax_searches = 6\nsearch_results = 8\n"
            "search_timeout = 20.0\n",
            encoding="utf-8",
        )
        cfg = load_config(config_path=toml)
        assert cfg.web_search is False
        assert cfg.max_searches == 6
        assert cfg.search_results == 8
        assert cfg.search_timeout == 20.0

    def test_nested_web_table_flattened(self, tmp_path):
        # Prove the loader flattens a [web] table.
        toml = tmp_path / "config.toml"
        toml.write_text(
            "[web]\nweb_search = false\nmax_searches = 2\n"
            "search_results = 4\nsearch_timeout = 11.0\n",
            encoding="utf-8",
        )
        cfg = load_config(config_path=toml)
        assert cfg.web_search is False
        assert cfg.max_searches == 2
        assert cfg.search_results == 4
        assert cfg.search_timeout == 11.0

    def test_flat_shell_context_keys(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text("shell_context = false\nmax_history = 7\n", encoding="utf-8")
        cfg = load_config(config_path=toml)
        assert cfg.shell_context is False
        assert cfg.max_history == 7

    def test_nested_shell_table_flattened(self, tmp_path):
        # Prove the loader flattens a [shell] table.
        toml = tmp_path / "config.toml"
        toml.write_text(
            "[shell]\nshell_context = false\nmax_history = 3\n", encoding="utf-8"
        )
        cfg = load_config(config_path=toml)
        assert cfg.shell_context is False
        assert cfg.max_history == 3

    def test_flat_max_parse_retries_key(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text("max_parse_retries = 4\n", encoding="utf-8")
        cfg = load_config(config_path=toml)
        assert cfg.max_parse_retries == 4


# ---------------------------------------------------------------------------
# load_config – env vars
# ---------------------------------------------------------------------------

class TestLoadConfigEnv:
    def test_ai_base_url(self):
        env = {"AI_BASE_URL": "http://myserver/v1"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.base_url == "http://myserver/v1"

    def test_ai_model(self):
        env = {"AI_MODEL": "gpt-4"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.model == "gpt-4"

    def test_ai_api_key(self):
        env = {"AI_API_KEY": "secret-key"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.api_key == "secret-key"

    def test_ai_temperature_float(self):
        env = {"AI_TEMPERATURE": "0.5"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.temperature == 0.5

    def test_ai_max_tokens_int(self):
        env = {"AI_MAX_TOKENS": "2048"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_tokens == 2048

    def test_ai_timeout_float(self):
        env = {"AI_TIMEOUT": "60.0"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.timeout == 60.0

    def test_ai_max_files_int(self):
        env = {"AI_MAX_FILES": "50"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_files == 50

    def test_ai_max_depth_int(self):
        env = {"AI_MAX_DEPTH": "3"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_depth == 3

    def test_ai_include_hidden_true_variants(self):
        for val in ("1", "true", "yes", "on", "True", "YES", "ON"):
            env = {"AI_INCLUDE_HIDDEN": val}
            cfg = load_config(config_path=Path("/nonexistent"), environ=env)
            assert cfg.include_hidden is True, f"Expected True for {val!r}"

    def test_ai_include_hidden_false_variants(self):
        for val in ("0", "false", "no", "off", "False"):
            env = {"AI_INCLUDE_HIDDEN": val}
            cfg = load_config(config_path=Path("/nonexistent"), environ=env)
            assert cfg.include_hidden is False, f"Expected False for {val!r}"

    def test_ai_max_explorations_int(self):
        env = {"AI_MAX_EXPLORATIONS": "8"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_explorations == 8

    def test_ai_web_search_true_variants(self):
        for val in ("1", "true", "yes", "on", "TRUE", "Yes"):
            env = {"AI_WEB_SEARCH": val}
            cfg = load_config(config_path=Path("/nonexistent"), environ=env)
            assert cfg.web_search is True, f"Expected True for {val!r}"

    def test_ai_web_search_false_variants(self):
        for val in ("0", "false", "no", "off", "False"):
            env = {"AI_WEB_SEARCH": val}
            cfg = load_config(config_path=Path("/nonexistent"), environ=env)
            assert cfg.web_search is False, f"Expected False for {val!r}"

    def test_ai_max_searches_int(self):
        env = {"AI_MAX_SEARCHES": "7"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_searches == 7

    def test_ai_search_results_int(self):
        env = {"AI_SEARCH_RESULTS": "9"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.search_results == 9

    def test_ai_search_timeout_float(self):
        env = {"AI_SEARCH_TIMEOUT": "30.5"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.search_timeout == 30.5

    def test_malformed_max_searches_ignored(self):
        env = {"AI_MAX_SEARCHES": "nope"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_searches == Config().max_searches

    def test_malformed_search_timeout_ignored(self):
        env = {"AI_SEARCH_TIMEOUT": "soon"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.search_timeout == Config().search_timeout

    def test_ai_shell_context_true_variants(self):
        for val in ("1", "true", "yes", "on", "TRUE", "On"):
            env = {"AI_SHELL_CONTEXT": val}
            cfg = load_config(config_path=Path("/nonexistent"), environ=env)
            assert cfg.shell_context is True, f"Expected True for {val!r}"

    def test_ai_shell_context_false_variants(self):
        for val in ("0", "false", "no", "off", "False"):
            env = {"AI_SHELL_CONTEXT": val}
            cfg = load_config(config_path=Path("/nonexistent"), environ=env)
            assert cfg.shell_context is False, f"Expected False for {val!r}"

    def test_ai_max_history_int(self):
        env = {"AI_MAX_HISTORY": "25"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_history == 25

    def test_malformed_max_history_ignored(self):
        env = {"AI_MAX_HISTORY": "lots"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_history == Config().max_history

    def test_ai_max_parse_retries_int(self):
        env = {"AI_MAX_PARSE_RETRIES": "5"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_parse_retries == 5

    def test_malformed_max_parse_retries_ignored(self):
        env = {"AI_MAX_PARSE_RETRIES": "many"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_parse_retries == Config().max_parse_retries

    def test_malformed_temperature_ignored(self):
        env = {"AI_TEMPERATURE": "not-a-float"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.temperature == Config().temperature  # default

    def test_malformed_max_tokens_ignored(self):
        env = {"AI_MAX_TOKENS": "abc"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_tokens == Config().max_tokens  # default

    def test_malformed_timeout_ignored(self):
        env = {"AI_TIMEOUT": "bad"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.timeout == Config().timeout

    def test_malformed_max_files_ignored(self):
        env = {"AI_MAX_FILES": "!!"}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.max_files == Config().max_files

    def test_empty_env_var_ignored(self):
        env = {"AI_MODEL": ""}
        cfg = load_config(config_path=Path("/nonexistent"), environ=env)
        assert cfg.model == Config().model  # default

    def test_empty_environ_dict(self):
        cfg = load_config(config_path=Path("/nonexistent"), environ={})
        assert cfg == Config()


# ---------------------------------------------------------------------------
# load_config – precedence
# ---------------------------------------------------------------------------

class TestLoadConfigPrecedence:
    def test_env_overrides_file(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('model = "file-model"\n', encoding="utf-8")
        env = {"AI_MODEL": "env-model"}
        cfg = load_config(config_path=toml, environ=env)
        assert cfg.model == "env-model"

    def test_overrides_override_env(self, tmp_path):
        env = {"AI_MODEL": "env-model"}
        cfg = load_config(
            config_path=Path("/nonexistent"),
            environ=env,
            overrides={"model": "override-model"}
        )
        assert cfg.model == "override-model"

    def test_overrides_override_file(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('model = "file-model"\n', encoding="utf-8")
        cfg = load_config(config_path=toml, overrides={"model": "cli-model"})
        assert cfg.model == "cli-model"

    def test_none_overrides_ignored(self, tmp_path):
        env = {"AI_MODEL": "env-model"}
        cfg = load_config(
            config_path=Path("/nonexistent"),
            environ=env,
            overrides={"model": None}
        )
        assert cfg.model == "env-model"

    def test_full_precedence_chain(self, tmp_path):
        toml = tmp_path / "config.toml"
        toml.write_text('model = "file-model"\ntemperature = 0.3\n', encoding="utf-8")
        env = {"AI_TEMPERATURE": "0.5"}
        cfg = load_config(config_path=toml, environ=env, overrides={"max_tokens": 512})
        # file sets model
        assert cfg.model == "file-model"
        # env overrides file's temperature
        assert cfg.temperature == 0.5
        # override sets max_tokens
        assert cfg.max_tokens == 512
