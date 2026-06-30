"""Secure-ish storage for provider API keys.

Order of preference:

1. The OS keychain via the ``keyring`` package (macOS Keychain, Windows
   Credential Locker, Linux Secret Service) — the appropriate place for secrets.
2. A fallback ``credentials.json`` next to the config file, created with
   ``0600`` permissions, used only when no keychain backend is available.

Keys are stored per provider (service ``command-ai``, username = provider name).
The key value never passes through anything that logs it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import default_config_path

SERVICE = "command-ai"


def _keyring():
    """Return the keyring module if a usable backend is available, else None."""
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring

        backend = keyring.get_keyring()
        if isinstance(backend, FailKeyring):
            return None
        return keyring
    except Exception:
        return None


def _cred_file() -> Path:
    return default_config_path().parent / "credentials.json"


def _file_get(provider: str) -> str | None:
    path = _cred_file()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        value = data.get(provider)
        return value or None
    except (OSError, ValueError):
        return None


def _warn(message: str) -> None:
    """Surface a permissions warning without ever logging the key value."""
    try:
        from . import ui

        ui.print_error(message)
    except Exception:
        import sys

        print(f"command-ai: {message}", file=sys.stderr)


def _file_set(provider: str, key: str) -> None:
    path = _cred_file()
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Restrict the directory too (best-effort; no-op on platforms without POSIX
    # modes), so the credentials file isn't reachable via a loose parent dir.
    try:
        os.chmod(parent, 0o700)
    except OSError:
        pass

    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    data[provider] = key

    # Write atomically with restrictive permissions FROM CREATION: open the temp
    # file with mode 0600 (so there is no world-readable window like write_text +
    # chmod has), then os.replace() into place. A failure to lock perms is loud,
    # not swallowed (F-05).
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        _warn(f"Could not restrict permissions on {path}; it may be readable by other users.")


def get_api_key(provider: str) -> str | None:
    """Fetch a stored API key for *provider*, from keychain or the fallback file."""
    kr = _keyring()
    if kr is not None:
        try:
            value = kr.get_password(SERVICE, provider)
            if value:
                return value
        except Exception:
            pass
    return _file_get(provider)


def set_api_key(provider: str, key: str) -> str:
    """Store *key* for *provider*. Returns where it was saved: 'keychain' or 'file'."""
    kr = _keyring()
    if kr is not None:
        try:
            kr.set_password(SERVICE, provider, key)
            return "keychain"
        except Exception:
            pass
    _file_set(provider, key)
    return "file"


def storage_location() -> str:
    """Human-readable description of where keys will be stored."""
    return "the OS keychain" if _keyring() is not None else f"{_cred_file()} (0600)"
