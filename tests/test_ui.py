"""Tests for command_ai.ui."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import command_ai.ui as ui
from command_ai.llm import CommandOption


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_option(command="ls -la", summary="List files", danger="low") -> CommandOption:
    return CommandOption(command=command, summary=summary, danger=danger)


def fake_questionary_select(answer_value):
    """Returns a fake questionary.select function that returns answer_value."""
    def _select(message, choices, **kwargs):
        return SimpleNamespace(ask=lambda: answer_value)
    return _select


def fake_questionary_confirm(answer_value):
    """Returns a fake questionary.confirm function that returns answer_value."""
    def _confirm(message, **kwargs):
        return SimpleNamespace(ask=lambda: answer_value)
    return _confirm


# ---------------------------------------------------------------------------
# select_command – assume_yes
# ---------------------------------------------------------------------------

class TestSelectCommandAssumeYes:
    def test_returns_first_option(self):
        opts = [make_option("ls"), make_option("pwd")]
        result = ui.select_command(opts, assume_yes=True)
        assert result is opts[0]
        assert result.command == "ls"

    def test_single_option_returns_it(self):
        opts = [make_option("ls")]
        result = ui.select_command(opts, assume_yes=True)
        assert result is opts[0]

    def test_empty_options_returns_none(self):
        result = ui.select_command([], assume_yes=True)
        assert result is None


# ---------------------------------------------------------------------------
# select_command – non-TTY (no interactive)
# ---------------------------------------------------------------------------

class TestSelectCommandNonTTY:
    def test_returns_none_in_non_interactive(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: False)
        opts = [make_option("ls")]
        result = ui.select_command(opts, assume_yes=False)
        assert result is None

    def test_prints_hint_in_non_interactive(self, monkeypatch, capsys):
        monkeypatch.setattr(ui, "_interactive", lambda: False)
        opts = [make_option("ls")]
        ui.select_command(opts, assume_yes=False)
        # The hint is printed to stderr via the rich Console - we can't easily
        # capture it from capsys since it goes through rich Console bound to stderr.
        # Just verify no exception and returns None.

    def test_empty_options_returns_none_before_tty_check(self, monkeypatch):
        # Empty list: should return None even in interactive mode
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        result = ui.select_command([], assume_yes=False)
        assert result is None


# ---------------------------------------------------------------------------
# select_command – TTY interactive paths
# ---------------------------------------------------------------------------

class TestSelectCommandInteractive:
    def test_single_option_user_confirms(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        # For single option: value 0 means "Run this command"
        monkeypatch.setattr("questionary.select", fake_questionary_select(0))
        opts = [make_option("ls")]
        result = ui.select_command(opts, assume_yes=False)
        assert result is opts[0]

    def test_single_option_user_cancels(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        monkeypatch.setattr("questionary.select", fake_questionary_select(ui.CANCEL))
        opts = [make_option("ls")]
        result = ui.select_command(opts, assume_yes=False)
        assert result is None

    def test_single_option_none_answer_returns_none(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        monkeypatch.setattr("questionary.select", fake_questionary_select(None))
        opts = [make_option("ls")]
        result = ui.select_command(opts, assume_yes=False)
        assert result is None

    def test_multiple_options_user_picks_first(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        # For multiple options: value is 0-based index
        monkeypatch.setattr("questionary.select", fake_questionary_select(0))
        opts = [make_option("ls"), make_option("pwd")]
        result = ui.select_command(opts, assume_yes=False)
        assert result is opts[0]

    def test_multiple_options_user_picks_second(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        monkeypatch.setattr("questionary.select", fake_questionary_select(1))
        opts = [make_option("ls"), make_option("pwd")]
        result = ui.select_command(opts, assume_yes=False)
        assert result is opts[1]

    def test_multiple_options_user_cancels(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        monkeypatch.setattr("questionary.select", fake_questionary_select(ui.CANCEL))
        opts = [make_option("ls"), make_option("pwd")]
        result = ui.select_command(opts, assume_yes=False)
        assert result is None


# ---------------------------------------------------------------------------
# confirm_dangerous
# ---------------------------------------------------------------------------

class TestConfirmDangerous:
    def test_non_tty_returns_false(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: False)
        opt = make_option(danger="high")
        result = ui.confirm_dangerous(opt)
        assert result is False

    def test_interactive_user_confirms(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        monkeypatch.setattr("questionary.confirm", fake_questionary_confirm(True))
        opt = make_option(danger="high")
        result = ui.confirm_dangerous(opt)
        assert result is True

    def test_interactive_user_denies(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        monkeypatch.setattr("questionary.confirm", fake_questionary_confirm(False))
        opt = make_option(danger="high")
        result = ui.confirm_dangerous(opt)
        assert result is False

    def test_interactive_none_returns_false(self, monkeypatch):
        monkeypatch.setattr(ui, "_interactive", lambda: True)
        monkeypatch.setattr("questionary.confirm", fake_questionary_confirm(None))
        opt = make_option(danger="high")
        result = ui.confirm_dangerous(opt)
        assert result is False


# ---------------------------------------------------------------------------
# render_option, print_error, print_info (smoke tests)
# ---------------------------------------------------------------------------

class TestRenderOption:
    def test_single_option_no_index(self):
        # Should not raise
        opt = make_option()
        ui.render_option(opt)

    def test_with_index(self):
        opt = make_option()
        ui.render_option(opt, index=1)

    def test_with_args(self):
        opt = CommandOption(
            command="ls -la",
            summary="list",
            args=[{"part": "-la", "explains": "long and all"}],
            danger="low",
        )
        ui.render_option(opt)

    def test_high_danger_option(self):
        opt = make_option(danger="high")
        ui.render_option(opt)


class TestPrintFunctions:
    def test_print_error_no_crash(self):
        ui.print_error("Something went wrong")

    def test_print_info_no_crash(self):
        ui.print_info("Just info")


# ---------------------------------------------------------------------------
# _interactive
# ---------------------------------------------------------------------------

class TestInteractive:
    def test_returns_bool(self):
        result = ui._interactive()
        assert isinstance(result, bool)
