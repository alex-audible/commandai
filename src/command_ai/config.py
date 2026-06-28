"""Configuration loading and merging.

Precedence (lowest to highest): built-in defaults < config file < environment
variables < CLI flags.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    import tomli as tomllib  # type: ignore


DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "gemma-4-26b-a4b"
DEFAULT_API_KEY = "lm-studio"  # LM Studio ignores the key but the SDK requires one


@dataclass
class Config:
    """Resolved runtime configuration."""

    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = DEFAULT_API_KEY
    temperature: float = 0.2
    max_tokens: int = 1024
    timeout: float = 120.0

    # Context gathering
    max_files: int = 200
    max_depth: int = 2
    include_hidden: bool = False

    # Exploration loop
    max_explorations: int = 4

    # Web search
    web_search: bool = True
    max_searches: int = 3
    search_results: int = 5
    search_timeout: float = 15.0

    def with_overrides(self, **kwargs: Any) -> "Config":
        """Return a copy with the given non-None overrides applied."""
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean)


def default_config_path() -> Path:
    """Location of the user config file, honouring XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "command-ai" / "config.toml"


# Maps a flat TOML key (also accepted under a [context] table) to the Config
# field name. Kept flat-friendly so a minimal config "just works".
_FILE_KEYS = {
    "base_url": "base_url",
    "model": "model",
    "api_key": "api_key",
    "temperature": "temperature",
    "max_tokens": "max_tokens",
    "timeout": "timeout",
    "max_files": "max_files",
    "max_depth": "max_depth",
    "include_hidden": "include_hidden",
    "max_explorations": "max_explorations",
    "web_search": "web_search",
    "max_searches": "max_searches",
    "search_results": "search_results",
    "search_timeout": "search_timeout",
}

_ENV_KEYS = {
    "AI_BASE_URL": ("base_url", str),
    "AI_MODEL": ("model", str),
    "AI_API_KEY": ("api_key", str),
    "AI_TEMPERATURE": ("temperature", float),
    "AI_MAX_TOKENS": ("max_tokens", int),
    "AI_TIMEOUT": ("timeout", float),
    "AI_MAX_FILES": ("max_files", int),
    "AI_MAX_DEPTH": ("max_depth", int),
    "AI_INCLUDE_HIDDEN": ("include_hidden", lambda v: str(v).lower() in ("1", "true", "yes", "on")),
    "AI_MAX_EXPLORATIONS": ("max_explorations", int),
    "AI_WEB_SEARCH": ("web_search", lambda v: str(v).lower() in ("1", "true", "yes", "on")),
    "AI_MAX_SEARCHES": ("max_searches", int),
    "AI_SEARCH_RESULTS": ("search_results", int),
    "AI_SEARCH_TIMEOUT": ("search_timeout", float),
}


def _flatten_toml(data: dict[str, Any]) -> dict[str, Any]:
    """Accept both flat keys and a [context]/[llm] table layout."""
    flat: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            flat.update(value)  # merge nested tables (context.*, llm.*)
        else:
            flat[key] = value
    return flat


def _from_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    flat = _flatten_toml(raw)
    out: dict[str, Any] = {}
    for file_key, field_name in _FILE_KEYS.items():
        if file_key in flat:
            out[field_name] = flat[file_key]
    return out


def _from_env(environ: dict[str, str] | None = None) -> dict[str, Any]:
    environ = environ if environ is not None else dict(os.environ)
    out: dict[str, Any] = {}
    for env_key, (field_name, caster) in _ENV_KEYS.items():
        if env_key in environ and environ[env_key] != "":
            try:
                out[field_name] = caster(environ[env_key])
            except (TypeError, ValueError):
                # Ignore malformed env values rather than crash the CLI.
                pass
    return out


def load_config(
    config_path: Path | None = None,
    environ: dict[str, str] | None = None,
    overrides: dict[str, Any] | None = None,
) -> Config:
    """Build a :class:`Config` from defaults, file, env, and explicit overrides."""
    cfg = Config()

    path = config_path if config_path is not None else default_config_path()
    file_values = _from_file(path)
    if file_values:
        cfg = cfg.with_overrides(**file_values)

    env_values = _from_env(environ)
    if env_values:
        cfg = cfg.with_overrides(**env_values)

    if overrides:
        cfg = cfg.with_overrides(**overrides)

    return cfg
