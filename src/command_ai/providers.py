"""Known LLM providers and their endpoint defaults.

A *provider* is a preset for an OpenAI-compatible endpoint. Selecting one sets a
sensible ``base_url`` and default model so you don't have to remember URLs.

- ``local``      — an OpenAI-compatible server on your machine (LM Studio,
                   Ollama, llama.cpp, …). No API key needed.
- ``openrouter`` — https://openrouter.ai , a hosted gateway to many models.
                   Requires an API key.

Any provider can still be overridden with ``--base-url`` / ``--model`` /
``--api-key`` or the matching config keys / env vars.
"""

from __future__ import annotations

PROVIDERS: dict[str, dict] = {
    "local": {
        "label": "Local (LM Studio / OpenAI-compatible)",
        "base_url": "http://localhost:1234/v1",
        "default_model": "gemma-4-26b-a4b",
        "requires_key": False,
        "signup_url": None,
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o-mini",
        "requires_key": True,
        "signup_url": "https://openrouter.ai/keys",
    },
}

DEFAULT_PROVIDER = "local"


def get_provider(name: str | None) -> dict | None:
    """Look up a provider preset by name (case-insensitive)."""
    if not name:
        return None
    return PROVIDERS.get(name.strip().lower())


def provider_names() -> list[str]:
    return list(PROVIDERS)
