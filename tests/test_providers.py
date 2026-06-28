"""Tests for command_ai.providers."""

from __future__ import annotations

import pytest

from command_ai.providers import (
    DEFAULT_PROVIDER,
    PROVIDERS,
    get_provider,
    provider_names,
)


# ---------------------------------------------------------------------------
# PROVIDERS dict + constants
# ---------------------------------------------------------------------------

class TestProvidersDict:
    def test_has_local_and_openrouter(self):
        assert "local" in PROVIDERS
        assert "openrouter" in PROVIDERS

    def test_default_provider_is_local(self):
        assert DEFAULT_PROVIDER == "local"

    def test_local_does_not_require_key(self):
        assert PROVIDERS["local"]["requires_key"] is False

    def test_local_base_url(self):
        assert PROVIDERS["local"]["base_url"] == "http://localhost:1234/v1"

    def test_local_default_model(self):
        assert PROVIDERS["local"]["default_model"] == "gemma-4-26b-a4b"

    def test_openrouter_requires_key(self):
        assert PROVIDERS["openrouter"]["requires_key"] is True

    def test_openrouter_base_url(self):
        assert PROVIDERS["openrouter"]["base_url"] == "https://openrouter.ai/api/v1"

    def test_openrouter_default_model(self):
        assert PROVIDERS["openrouter"]["default_model"] == "openai/gpt-4o-mini"

    def test_openrouter_has_signup_url(self):
        assert PROVIDERS["openrouter"]["signup_url"]

    def test_local_signup_url_none(self):
        assert PROVIDERS["local"]["signup_url"] is None


# ---------------------------------------------------------------------------
# get_provider
# ---------------------------------------------------------------------------

class TestGetProvider:
    def test_local(self):
        prov = get_provider("local")
        assert prov is PROVIDERS["local"]

    def test_openrouter(self):
        prov = get_provider("openrouter")
        assert prov is PROVIDERS["openrouter"]

    def test_case_insensitive(self):
        assert get_provider("LOCAL") is PROVIDERS["local"]
        assert get_provider("OpenRouter") is PROVIDERS["openrouter"]

    def test_strips_whitespace(self):
        assert get_provider("  openrouter  ") is PROVIDERS["openrouter"]

    def test_unknown_returns_none(self):
        assert get_provider("nope") is None

    def test_none_returns_none(self):
        assert get_provider(None) is None

    def test_empty_string_returns_none(self):
        assert get_provider("") is None


# ---------------------------------------------------------------------------
# provider_names
# ---------------------------------------------------------------------------

class TestProviderNames:
    def test_returns_both(self):
        assert provider_names() == ["local", "openrouter"]

    def test_returns_list(self):
        assert isinstance(provider_names(), list)
