"""Tests for command_ai.credentials.

No real keychain writes — _keyring is always monkeypatched. The file fallback
is redirected under tmp_path via monkeypatching default_config_path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import command_ai.credentials as credentials


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeKeyringModule:
    """A stand-in for the `keyring` module backed by an in-memory dict."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, user):
        return self.store.get((service, user))

    def set_password(self, service, user, value):
        self.store[(service, user)] = value


class RaisingKeyringModule:
    """A keyring stand-in whose operations always raise (forces file fallback)."""

    def get_password(self, service, user):
        raise RuntimeError("keychain locked")

    def set_password(self, service, user, value):
        raise RuntimeError("keychain locked")


def _redirect_cred_file(monkeypatch, tmp_path):
    """Make _cred_file() resolve under tmp_path/command-ai/credentials.json."""
    fake_cfg = tmp_path / "command-ai" / "config.toml"
    monkeypatch.setattr(credentials, "default_config_path", lambda: fake_cfg)
    return fake_cfg.parent / "credentials.json"


# ---------------------------------------------------------------------------
# File fallback path (_keyring -> None)
# ---------------------------------------------------------------------------

class TestFileFallback:
    def test_set_returns_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        _redirect_cred_file(monkeypatch, tmp_path)
        where = credentials.set_api_key("openrouter", "sk-x")
        assert where == "file"

    def test_round_trip(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-x")
        assert credentials.get_api_key("openrouter") == "sk-x"

    def test_unset_provider_is_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-x")
        assert credentials.get_api_key("local") is None

    def test_get_with_no_file_is_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        _redirect_cred_file(monkeypatch, tmp_path)
        assert credentials.get_api_key("openrouter") is None

    def test_file_mode_0600(self, monkeypatch, tmp_path):
        if os.name == "nt":
            pytest.skip("POSIX permission check not applicable on Windows")
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        cred_file = _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-x")
        mode = cred_file.stat().st_mode & 0o777
        assert mode == 0o600

    def test_second_provider_does_not_clobber_first(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-or")
        credentials.set_api_key("local", "sk-local")
        assert credentials.get_api_key("openrouter") == "sk-or"
        assert credentials.get_api_key("local") == "sk-local"

    def test_file_contains_json(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        cred_file = _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-x")
        data = json.loads(cred_file.read_text(encoding="utf-8"))
        assert data["openrouter"] == "sk-x"

    def test_corrupt_file_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        cred_file = _redirect_cred_file(monkeypatch, tmp_path)
        cred_file.parent.mkdir(parents=True, exist_ok=True)
        cred_file.write_text("not json{{{", encoding="utf-8")
        assert credentials.get_api_key("openrouter") is None


# ---------------------------------------------------------------------------
# Keychain path (_keyring -> fake module)
# ---------------------------------------------------------------------------

class TestKeychain:
    def test_set_returns_keychain(self, monkeypatch, tmp_path):
        fake = FakeKeyringModule()
        monkeypatch.setattr(credentials, "_keyring", lambda: fake)
        _redirect_cred_file(monkeypatch, tmp_path)
        where = credentials.set_api_key("openrouter", "sk-kc")
        assert where == "keychain"

    def test_get_reads_from_keychain(self, monkeypatch, tmp_path):
        fake = FakeKeyringModule()
        monkeypatch.setattr(credentials, "_keyring", lambda: fake)
        _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-kc")
        assert credentials.get_api_key("openrouter") == "sk-kc"

    def test_no_file_written(self, monkeypatch, tmp_path):
        fake = FakeKeyringModule()
        monkeypatch.setattr(credentials, "_keyring", lambda: fake)
        cred_file = _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-kc")
        assert not cred_file.exists()

    def test_stored_under_service_and_provider(self, monkeypatch, tmp_path):
        fake = FakeKeyringModule()
        monkeypatch.setattr(credentials, "_keyring", lambda: fake)
        _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-kc")
        assert fake.store[(credentials.SERVICE, "openrouter")] == "sk-kc"

    def test_get_unset_provider_none(self, monkeypatch, tmp_path):
        fake = FakeKeyringModule()
        monkeypatch.setattr(credentials, "_keyring", lambda: fake)
        _redirect_cred_file(monkeypatch, tmp_path)
        assert credentials.get_api_key("openrouter") is None


# ---------------------------------------------------------------------------
# Keychain raises -> file fallback
# ---------------------------------------------------------------------------

class TestKeychainRaisesFallback:
    def test_set_falls_back_to_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: RaisingKeyringModule())
        _redirect_cred_file(monkeypatch, tmp_path)
        where = credentials.set_api_key("openrouter", "sk-x")
        assert where == "file"

    def test_get_falls_back_to_file(self, monkeypatch, tmp_path):
        # set via file fallback (keyring raises), then get must also fall back.
        monkeypatch.setattr(credentials, "_keyring", lambda: RaisingKeyringModule())
        _redirect_cred_file(monkeypatch, tmp_path)
        credentials.set_api_key("openrouter", "sk-x")
        assert credentials.get_api_key("openrouter") == "sk-x"

    def test_file_set_with_corrupt_existing_file(self, monkeypatch, tmp_path):
        # _file_set must tolerate a corrupt existing credentials.json.
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        cred_file = _redirect_cred_file(monkeypatch, tmp_path)
        cred_file.parent.mkdir(parents=True, exist_ok=True)
        cred_file.write_text("garbage{{{not json", encoding="utf-8")
        credentials.set_api_key("openrouter", "sk-new")
        assert credentials.get_api_key("openrouter") == "sk-new"


# ---------------------------------------------------------------------------
# storage_location
# ---------------------------------------------------------------------------

class TestStorageLocation:
    def test_returns_str(self):
        assert isinstance(credentials.storage_location(), str)

    def test_keychain_message_when_keyring_present(self, monkeypatch):
        fake = FakeKeyringModule()
        monkeypatch.setattr(credentials, "_keyring", lambda: fake)
        result = credentials.storage_location()
        assert "keychain" in result.lower()

    def test_file_path_when_no_keyring(self, monkeypatch, tmp_path):
        monkeypatch.setattr(credentials, "_keyring", lambda: None)
        cred_file = _redirect_cred_file(monkeypatch, tmp_path)
        result = credentials.storage_location()
        assert "credentials.json" in result
        assert "0600" in result


# ---------------------------------------------------------------------------
# _keyring (real call — just confirm it returns module-or-None without error)
# ---------------------------------------------------------------------------

class TestKeyringResolution:
    def test_returns_module_or_none(self):
        # Should not raise; result is either a module-like object or None.
        result = credentials._keyring()
        assert result is None or hasattr(result, "get_password")
