"""Shared fixtures for the commandai test suite."""

from __future__ import annotations

import pytest

from command_ai.config import Config
from command_ai.llm import CommandOption


@pytest.fixture()
def default_config() -> Config:
    return Config()


@pytest.fixture()
def simple_option() -> CommandOption:
    return CommandOption(command="ls -la", summary="List files", danger="low")


@pytest.fixture()
def dangerous_option() -> CommandOption:
    return CommandOption(command="rm -rf /tmp/foo", summary="Delete recursively", danger="high")
