"""Documentation-sync checks: fail the build when docs drift from the code.

These run in the normal suite (and therefore in CI on every push) and via the
committed pre-push hook, so adding a CLI flag, an ``AI_*`` env var, or a Config
field without documenting it turns the build red instead of rotting silently.

They verify that the relevant *names* are documented — not that the prose is
correct; keeping descriptions accurate is still a human/review job.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

import command_ai.cli as cli
from command_ai.config import Config, _ENV_KEYS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
README = PROJECT_ROOT / "README.md"
CONFIG_EXAMPLE = PROJECT_ROOT / "config.example.toml"

# Internal plumbing / argparse built-ins that don't need a user-facing mention.
_FLAG_EXCLUDES = {"--help"}


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _long_flags() -> list[str]:
    flags: set[str] = set()
    for action in cli.build_parser()._actions:
        for opt in action.option_strings:
            if opt.startswith("--"):
                flags.add(opt)
    return sorted(flags - _FLAG_EXCLUDES)


@pytest.mark.parametrize("flag", _long_flags())
def test_cli_flag_is_documented_in_readme(flag):
    assert flag in _readme_text(), f"CLI flag {flag} is not documented in README.md"


@pytest.mark.parametrize("env_var", sorted(_ENV_KEYS))
def test_env_var_is_documented_in_readme(env_var):
    assert env_var in _readme_text(), f"Env var {env_var} is not documented in README.md"


@pytest.mark.parametrize("field_name", [f.name for f in fields(Config)])
def test_config_field_is_in_example(field_name):
    text = CONFIG_EXAMPLE.read_text(encoding="utf-8")
    assert field_name in text, f"Config field {field_name!r} is not in config.example.toml"


def test_env_keys_map_to_real_config_fields():
    # Internal consistency: every env var targets an actual Config field.
    valid = {f.name for f in fields(Config)}
    for env_var, (field_name, _caster) in _ENV_KEYS.items():
        assert field_name in valid, f"{env_var} maps to unknown Config field {field_name!r}"
