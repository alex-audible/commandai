"""Tests for command_ai.context."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from command_ai.config import Config
from command_ai.context import (
    DirListing,
    build_tree,
    environment_summary,
    extension_summary,
    gather_context,
    list_directory,
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
        monkeypatch.setenv("SHELL", "/bin/fish")
        result = environment_summary()
        assert "/bin/fish" in result


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
