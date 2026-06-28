"""Tests for command_ai.context."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import command_ai.context as context
from command_ai.config import Config
from command_ai.context import (
    DirListing,
    _is_wsl,
    _linux_distro,
    build_tree,
    detected_shell,
    environment_summary,
    extension_summary,
    gather_context,
    list_directory,
    parse_shell_context,
)


# ---------------------------------------------------------------------------
# environment_summary
# ---------------------------------------------------------------------------

class TestEnvironmentSummary:
    def test_contains_os(self):
        result = environment_summary()
        assert "Operating system:" in result

    def test_contains_shell(self):
        result = environment_summary()
        assert "Shell:" in result

    def test_contains_current_directory(self, tmp_path):
        result = environment_summary(cwd=tmp_path)
        assert "Current directory:" in result
        assert str(tmp_path) in result

    def test_uses_provided_cwd(self, tmp_path):
        result = environment_summary(cwd=tmp_path)
        assert str(tmp_path) in result

    def test_uses_shell_env(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.setenv("SHELL", "/bin/fish")
        result = environment_summary()
        assert "/bin/fish" in result

    def test_macos_label(self, monkeypatch):
        monkeypatch.setattr(context.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(context.platform, "mac_ver", lambda: ("14.0", "", ""))
        result = environment_summary()
        assert "macOS" in result
        assert "14.0" in result

    def test_linux_label_distro(self, monkeypatch):
        monkeypatch.setattr(context.platform, "system", lambda: "Linux")
        monkeypatch.setattr(context, "_linux_distro", lambda: "Ubuntu 22.04")
        monkeypatch.setattr(context, "_is_wsl", lambda: False)
        result = environment_summary()
        assert "Ubuntu 22.04" in result
        assert "WSL" not in result

    def test_linux_label_wsl(self, monkeypatch):
        monkeypatch.setattr(context.platform, "system", lambda: "Linux")
        monkeypatch.setattr(context, "_linux_distro", lambda: "Ubuntu 22.04")
        monkeypatch.setattr(context, "_is_wsl", lambda: True)
        result = environment_summary()
        assert "Ubuntu 22.04" in result
        assert "WSL" in result

    def test_windows_label(self, monkeypatch):
        monkeypatch.setattr(context.platform, "system", lambda: "Windows")
        monkeypatch.setattr(context.platform, "release", lambda: "10")
        result = environment_summary()
        assert "Windows (10)" in result

    def test_other_os_label(self, monkeypatch):
        monkeypatch.setattr(context.platform, "system", lambda: "FreeBSD")
        monkeypatch.setattr(context.platform, "release", lambda: "14.0-RELEASE")
        result = environment_summary()
        assert "FreeBSD" in result


# ---------------------------------------------------------------------------
# detected_shell
# ---------------------------------------------------------------------------

class TestDetectedShell:
    def test_ai_current_shell_wins(self, monkeypatch):
        monkeypatch.setenv("AI_CURRENT_SHELL", "/opt/fish")
        monkeypatch.setenv("SHELL", "/bin/bash")
        assert detected_shell() == "/opt/fish"

    def test_shell_used_when_no_hint(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.setenv("SHELL", "/bin/dash")
        assert detected_shell() == "/bin/dash"

    def test_posix_default_sh(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.setattr(context.os, "name", "posix")
        assert detected_shell() == "/bin/sh"

    def test_windows_default_comspec(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.setattr(context.os, "name", "nt")
        monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
        assert detected_shell() == r"C:\Windows\System32\cmd.exe"

    def test_windows_default_cmd_when_no_comspec(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.delenv("COMSPEC", raising=False)
        monkeypatch.setattr(context.os, "name", "nt")
        assert detected_shell() == "cmd.exe"


# ---------------------------------------------------------------------------
# _is_wsl
# ---------------------------------------------------------------------------

class TestIsWsl:
    def test_true_from_release_string(self, monkeypatch):
        monkeypatch.setattr(
            context.platform, "release", lambda: "5.15.0-microsoft-standard"
        )
        assert _is_wsl() is True

    def test_false_when_release_clean_and_no_proc_version(self, monkeypatch):
        monkeypatch.setattr(context.platform, "release", lambda: "6.1.0-generic")

        def fake_open(*args, **kwargs):
            raise OSError("no /proc/version")

        monkeypatch.setattr("builtins.open", fake_open)
        assert _is_wsl() is False

    def test_true_from_proc_version(self, monkeypatch):
        import io

        monkeypatch.setattr(context.platform, "release", lambda: "6.1.0-generic")

        def fake_open(*args, **kwargs):
            return io.StringIO("Linux version 6.1.0 ... Microsoft ... WSL2")

        monkeypatch.setattr("builtins.open", fake_open)
        assert _is_wsl() is True


# ---------------------------------------------------------------------------
# _linux_distro
# ---------------------------------------------------------------------------

class TestLinuxDistro:
    def test_parses_pretty_name(self, monkeypatch):
        import io

        def fake_open(*args, **kwargs):
            return io.StringIO('NAME="Ubuntu"\nPRETTY_NAME="Ubuntu 22.04"\n')

        monkeypatch.setattr("builtins.open", fake_open)
        assert _linux_distro() == "Ubuntu 22.04"

    def test_oserror_returns_linux(self, monkeypatch):
        def fake_open(*args, **kwargs):
            raise OSError("no /etc/os-release")

        monkeypatch.setattr("builtins.open", fake_open)
        assert _linux_distro() == "Linux"

    def test_no_pretty_name_returns_linux(self, monkeypatch):
        import io

        def fake_open(*args, **kwargs):
            return io.StringIO('NAME="Arch"\nID=arch\n')

        monkeypatch.setattr("builtins.open", fake_open)
        assert _linux_distro() == "Linux"


# ---------------------------------------------------------------------------
# DirListing.render
# ---------------------------------------------------------------------------

class TestDirListingRender:
    def test_renders_dirs_and_files(self, tmp_path):
        listing = DirListing(path=tmp_path, dirs=["subdir"], files=["file.txt"])
        rendered = listing.render()
        assert "subdir/" in rendered
        assert "file.txt" in rendered

    def test_renders_truncated(self, tmp_path):
        listing = DirListing(path=tmp_path, dirs=[], files=["a.txt"], truncated=True)
        rendered = listing.render()
        assert "truncated" in rendered

    def test_renders_empty(self, tmp_path):
        listing = DirListing(path=tmp_path, dirs=[], files=[])
        rendered = listing.render()
        assert "(empty)" in rendered

    def test_path_in_first_line(self, tmp_path):
        listing = DirListing(path=tmp_path, dirs=[], files=[])
        rendered = listing.render()
        first_line = rendered.split("\n")[0]
        assert str(tmp_path) in first_line


# ---------------------------------------------------------------------------
# list_directory
# ---------------------------------------------------------------------------

class TestListDirectory:
    def test_lists_files_and_dirs(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.txt").write_text("hello")
        cfg = Config()
        result = list_directory(tmp_path, cfg)
        assert "subdir" in result.dirs
        assert "file.txt" in result.files

    def test_cap_total_entries(self, tmp_path):
        for i in range(10):
            (tmp_path / f"file{i}.txt").write_text("x")
        cfg = Config(max_files=5)
        result = list_directory(tmp_path, cfg)
        assert len(result.dirs) + len(result.files) == 5
        assert result.truncated is True

    def test_hidden_files_excluded_by_default(self, tmp_path):
        (tmp_path / ".hidden").write_text("secret")
        (tmp_path / "visible.txt").write_text("hi")
        cfg = Config(include_hidden=False)
        result = list_directory(tmp_path, cfg)
        assert ".hidden" not in result.files
        assert "visible.txt" in result.files

    def test_hidden_files_included_when_configured(self, tmp_path):
        (tmp_path / ".hidden").write_text("secret")
        cfg = Config(include_hidden=True)
        result = list_directory(tmp_path, cfg)
        assert ".hidden" in result.files

    def test_nonexistent_path_returns_error(self, tmp_path):
        missing = tmp_path / "nonexistent"
        cfg = Config()
        result = list_directory(missing, cfg)
        assert len(result.files) == 1
        assert "error" in result.files[0].lower()

    def test_max_entries_override(self, tmp_path):
        for i in range(20):
            (tmp_path / f"f{i}.txt").write_text("x")
        cfg = Config(max_files=100)
        result = list_directory(tmp_path, cfg, max_entries=3)
        assert len(result.dirs) + len(result.files) == 3
        assert result.truncated is True

    def test_no_truncation_when_within_cap(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        cfg = Config(max_files=100)
        result = list_directory(tmp_path, cfg)
        assert result.truncated is False

    def test_dirs_and_files_sorted(self, tmp_path):
        (tmp_path / "zzz").mkdir()
        (tmp_path / "aaa").mkdir()
        (tmp_path / "mmm.txt").write_text("x")
        cfg = Config()
        result = list_directory(tmp_path, cfg)
        assert result.dirs == sorted(result.dirs, key=str.lower)
        assert result.files == sorted(result.files, key=str.lower)


# ---------------------------------------------------------------------------
# build_tree
# ---------------------------------------------------------------------------

class TestBuildTree:
    def test_flat_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        cfg = Config()
        tree, count = build_tree(tmp_path, cfg)
        assert "a.txt" in tree
        assert "b.txt" in tree
        assert count == 2

    def test_nested_directory(self, tmp_path):
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.txt").write_text("x")
        cfg = Config(max_depth=2)
        tree, count = build_tree(tmp_path, cfg)
        assert "subdir/" in tree
        assert "nested.txt" in tree

    def test_depth_limit(self, tmp_path):
        d1 = tmp_path / "level1"
        d1.mkdir()
        d2 = d1 / "level2"
        d2.mkdir()
        d3 = d2 / "level3"
        d3.mkdir()
        (d3 / "deep.txt").write_text("x")
        cfg = Config(max_depth=1)
        tree, _ = build_tree(tmp_path, cfg)
        assert "level1/" in tree
        assert "deep.txt" not in tree

    def test_count_cap(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text("x")
        cfg = Config(max_files=5)
        tree, count = build_tree(tmp_path, cfg)
        assert count == 5
        assert "truncated" in tree

    def test_hidden_files_excluded(self, tmp_path):
        (tmp_path / ".hidden").write_text("x")
        (tmp_path / "visible.txt").write_text("x")
        cfg = Config(include_hidden=False)
        tree, _ = build_tree(tmp_path, cfg)
        assert ".hidden" not in tree
        assert "visible.txt" in tree

    def test_hidden_files_included(self, tmp_path):
        (tmp_path / ".hidden").write_text("x")
        cfg = Config(include_hidden=True)
        tree, _ = build_tree(tmp_path, cfg)
        assert ".hidden" in tree

    def test_empty_directory(self, tmp_path):
        cfg = Config()
        tree, count = build_tree(tmp_path, cfg)
        assert "empty" in tree.lower() or count == 0

    def test_dirs_marked_with_slash(self, tmp_path):
        (tmp_path / "mydir").mkdir()
        cfg = Config()
        tree, _ = build_tree(tmp_path, cfg)
        assert "mydir/" in tree


# ---------------------------------------------------------------------------
# extension_summary
# ---------------------------------------------------------------------------

class TestExtensionSummary:
    def test_counts_extensions(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.txt").write_text("x")
        (tmp_path / "c.py").write_text("x")
        cfg = Config()
        result = extension_summary(tmp_path, cfg)
        assert ".txt" in result
        assert ".py" in result
        assert "×2" in result  # two .txt files

    def test_no_extension_files(self, tmp_path):
        (tmp_path / "Makefile").write_text("x")
        cfg = Config()
        result = extension_summary(tmp_path, cfg)
        assert "(no ext)" in result

    def test_empty_directory_returns_none(self, tmp_path):
        cfg = Config()
        result = extension_summary(tmp_path, cfg)
        assert result == "none"

    def test_hidden_files_excluded(self, tmp_path):
        (tmp_path / ".gitignore").write_text("x")
        (tmp_path / "main.py").write_text("x")
        cfg = Config(include_hidden=False)
        result = extension_summary(tmp_path, cfg)
        assert ".gitignore" not in result

    def test_counts_in_subdirectories(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.py").write_text("x")
        (tmp_path / "top.py").write_text("x")
        cfg = Config(max_depth=2)
        result = extension_summary(tmp_path, cfg)
        assert ".py" in result
        assert "×2" in result

    def test_depth_limit_respected(self, tmp_path):
        d1 = tmp_path / "l1"
        d1.mkdir()
        d2 = d1 / "l2"
        d2.mkdir()
        d3 = d2 / "l3"
        d3.mkdir()
        (d3 / "deep.xyz").write_text("x")
        cfg = Config(max_depth=1)
        result = extension_summary(tmp_path, cfg)
        assert ".xyz" not in result


# ---------------------------------------------------------------------------
# gather_context
# ---------------------------------------------------------------------------

class TestGatherContext:
    def test_returns_string(self, tmp_path):
        cfg = Config()
        result = gather_context(cwd=tmp_path, config=cfg)
        assert isinstance(result, str)

    def test_includes_os_info(self, tmp_path):
        cfg = Config()
        result = gather_context(cwd=tmp_path, config=cfg)
        assert "Operating system:" in result

    def test_includes_file_types(self, tmp_path):
        (tmp_path / "hello.py").write_text("x")
        cfg = Config()
        result = gather_context(cwd=tmp_path, config=cfg)
        assert "File types present" in result

    def test_includes_directory_tree(self, tmp_path):
        (tmp_path / "hello.txt").write_text("x")
        cfg = Config()
        result = gather_context(cwd=tmp_path, config=cfg)
        assert "Directory tree" in result

    def test_uses_defaults_when_no_config(self, tmp_path):
        # Should not crash with no config
        result = gather_context(cwd=tmp_path)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# parse_shell_context
# ---------------------------------------------------------------------------

FULL_SHELL_CTX = (
    "last_exit_status=1\n"
    "recent_history:\n"
    "cd ~/proj\n"
    "git status\n"
    "git push\n"
)


class TestParseShellContext:
    def test_returns_labelled_block(self):
        result = parse_shell_context(FULL_SHELL_CTX)
        assert result is not None
        assert result.startswith(
            "Recent shell session (use this to fix or follow up on previous commands):"
        )

    def test_includes_exit_status_line(self):
        result = parse_shell_context(FULL_SHELL_CTX)
        assert "Previous command exit status: 1" in result

    def test_nonzero_status_has_failed_suffix(self):
        result = parse_shell_context(FULL_SHELL_CTX)
        assert "Previous command exit status: 1 (non-zero means the previous command failed)" in result

    def test_zero_status_no_failed_suffix(self):
        raw = "last_exit_status=0\nrecent_history:\nls\n"
        result = parse_shell_context(raw)
        assert "Previous command exit status: 0" in result
        assert "failed" not in result

    def test_includes_recent_commands_header(self):
        result = parse_shell_context(FULL_SHELL_CTX)
        assert "Recent commands (oldest first, most recent last):" in result

    def test_commands_indented(self):
        result = parse_shell_context(FULL_SHELL_CTX)
        assert "  cd ~/proj" in result
        assert "  git status" in result
        assert "  git push" in result

    def test_commands_order_preserved(self):
        result = parse_shell_context(FULL_SHELL_CTX)
        cd_idx = result.index("cd ~/proj")
        status_idx = result.index("git status")
        push_idx = result.index("git push")
        assert cd_idx < status_idx < push_idx

    def test_max_history_keeps_last_n(self):
        result = parse_shell_context(FULL_SHELL_CTX, max_history=1)
        assert "git push" in result  # most recent kept
        assert "cd ~/proj" not in result
        assert "git status" not in result

    def test_max_history_two(self):
        result = parse_shell_context(FULL_SHELL_CTX, max_history=2)
        assert "git status" in result
        assert "git push" in result
        assert "cd ~/proj" not in result

    def test_max_history_zero_no_history_lines(self):
        result = parse_shell_context(FULL_SHELL_CTX, max_history=0)
        # status is still present, but no command lines and no commands header
        assert result is not None
        assert "Previous command exit status: 1" in result
        assert "Recent commands" not in result
        assert "git push" not in result

    def test_empty_string_returns_none(self):
        assert parse_shell_context("") is None

    def test_only_history_header_no_status_no_commands_returns_none(self):
        assert parse_shell_context("recent_history:\n") is None

    def test_only_status_no_history(self):
        result = parse_shell_context("last_exit_status=0\n")
        assert result is not None
        assert "Previous command exit status: 0" in result
        assert "Recent commands" not in result

    def test_only_history_no_status(self):
        raw = "recent_history:\nls -la\npwd\n"
        result = parse_shell_context(raw)
        assert result is not None
        assert "ls -la" in result
        assert "pwd" in result
        assert "exit status" not in result

    def test_blank_lines_in_history_skipped(self):
        raw = "last_exit_status=2\nrecent_history:\nls\n\n\npwd\n"
        result = parse_shell_context(raw)
        assert "  ls" in result
        assert "  pwd" in result

    def test_empty_status_value_no_failed_suffix(self):
        # status == "" should not get the failed suffix
        raw = "last_exit_status=\nrecent_history:\nls\n"
        result = parse_shell_context(raw)
        assert "Previous command exit status: " in result
        assert "failed" not in result
