"""Tests for command_ai.executor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from command_ai.executor import (
    looks_dangerous,
    run_in_subprocess,
    user_shell,
    write_command,
)


# ---------------------------------------------------------------------------
# looks_dangerous
# ---------------------------------------------------------------------------

class TestLooksDangerous:
    # True cases
    def test_rm_rf(self):
        assert looks_dangerous("rm -rf /tmp/mydir") is True

    def test_rm_fr(self):
        assert looks_dangerous("rm -fr /tmp/mydir") is True

    def test_rm_recursive_wildcard(self):
        assert looks_dangerous("rm -r /tmp/*") is True

    def test_dd_if(self):
        assert looks_dangerous("dd if=/dev/zero of=/dev/sda") is True

    def test_mkfs(self):
        assert looks_dangerous("mkfs.ext4 /dev/sdb") is True

    def test_shutdown(self):
        assert looks_dangerous("sudo shutdown -h now") is True

    def test_reboot(self):
        assert looks_dangerous("reboot") is True

    def test_write_to_dev_sda(self):
        assert looks_dangerous("cat something > /dev/sda") is True

    def test_fork_bomb(self):
        assert looks_dangerous(":() { :|:& };:") is True

    def test_chmod_r_777(self):
        assert looks_dangerous("chmod -R 777 /") is True

    def test_curl_pipe_bash(self):
        assert looks_dangerous("curl http://example.com/install.sh | bash") is True

    def test_wget_pipe_sh(self):
        assert looks_dangerous("wget -O - http://example.com/setup | sh") is True

    def test_write_to_dev_disk(self):
        assert looks_dangerous("dd if=/dev/zero > /dev/disk0") is True

    # New patterns
    def test_git_clean_fdx(self):
        assert looks_dangerous("git clean -fdx") is True

    def test_git_clean_xdf(self):
        assert looks_dangerous("git clean -xdf") is True

    def test_truncate(self):
        assert looks_dangerous("truncate -s 0 f") is True

    def test_find_delete(self):
        assert looks_dangerous("find . -name '*.log' -delete") is True

    def test_diskutil_erasedisk(self):
        assert looks_dangerous("diskutil eraseDisk JHFS+ X disk2") is True

    def test_chflags_recursive(self):
        assert looks_dangerous("chflags -R nouchg /x") is True

    def test_crontab_r(self):
        assert looks_dangerous("crontab -r") is True

    def test_rsync_delete(self):
        assert looks_dangerous("rsync -a --delete a/ b/") is True

    def test_rm_recursive_no_force(self):
        assert looks_dangerous("rm -r mydir") is True

    def test_rm_glob(self):
        assert looks_dangerous("rm -- *") is True

    # False cases
    def test_ls(self):
        assert looks_dangerous("ls -la") is False

    def test_echo(self):
        assert looks_dangerous("echo hello world") is False

    def test_ffmpeg_convert(self):
        assert looks_dangerous("ffmpeg -i input.mov output.mp4") is False

    def test_grep(self):
        assert looks_dangerous("grep -r pattern .") is False

    def test_find(self):
        assert looks_dangerous("find . -name '*.py'") is False

    def test_cp(self):
        assert looks_dangerous("cp file.txt backup.txt") is False

    def test_empty_string(self):
        assert looks_dangerous("") is False

    def test_rm_without_rf(self):
        # plain rm without -r or -f flags matching the dangerous pattern
        assert looks_dangerous("rm file.txt") is False

    def test_rm_f_without_r(self):
        # rm -f alone is not matched by dangerous patterns (only rm -rf / -fr / -r)
        assert looks_dangerous("rm -f file.txt") is False

    def test_git_status(self):
        assert looks_dangerous("git status") is False

    def test_git_clean_dry_run(self):
        # -n dry-run with no -f should not be flagged
        assert looks_dangerous("git clean -n") is False

    def test_rsync_without_delete(self):
        assert looks_dangerous("rsync -a a/ b/") is False

    def test_find_without_delete(self):
        assert looks_dangerous("find . -name '*.py'") is False


# ---------------------------------------------------------------------------
# write_command
# ---------------------------------------------------------------------------

class TestWriteCommand:
    def test_writes_command_to_file(self, tmp_path):
        out_file = tmp_path / "command.sh"
        write_command("ls -la", out_file)
        content = out_file.read_text(encoding="utf-8")
        assert "ls -la" in content

    def test_trailing_newline(self, tmp_path):
        out_file = tmp_path / "command.sh"
        write_command("ls -la", out_file)
        content = out_file.read_text(encoding="utf-8")
        assert content.endswith("\n")

    def test_strips_trailing_newlines_then_adds_one(self, tmp_path):
        out_file = tmp_path / "command.sh"
        write_command("ls -la\n\n", out_file)
        content = out_file.read_text(encoding="utf-8")
        assert content == "ls -la\n"

    def test_accepts_string_path(self, tmp_path):
        out_file = tmp_path / "command.sh"
        write_command("pwd", str(out_file))
        assert out_file.exists()

    def test_accepts_path_object(self, tmp_path):
        out_file = tmp_path / "command.sh"
        write_command("pwd", out_file)
        assert out_file.exists()

    def test_creates_file(self, tmp_path):
        out_file = tmp_path / "new_command.sh"
        assert not out_file.exists()
        write_command("echo hello", out_file)
        assert out_file.exists()


# ---------------------------------------------------------------------------
# user_shell
# ---------------------------------------------------------------------------

class TestUserShell:
    def test_returns_shell_env(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/fish")
        assert user_shell() == "/bin/fish"

    def test_defaults_to_zsh_when_no_shell_env(self, monkeypatch):
        monkeypatch.delenv("SHELL", raising=False)
        assert user_shell() == "/bin/zsh"

    def test_returns_string(self):
        assert isinstance(user_shell(), str)


# ---------------------------------------------------------------------------
# run_in_subprocess
# ---------------------------------------------------------------------------

class TestRunInSubprocess:
    def test_returns_zero_on_success(self, monkeypatch):
        fake_result = SimpleNamespace(returncode=0)
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return fake_result
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setenv("SHELL", "/bin/zsh")
        rc = run_in_subprocess("true")
        assert rc == 0

    def test_returns_nonzero_on_failure(self, monkeypatch):
        fake_result = SimpleNamespace(returncode=1)
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: fake_result)
        rc = run_in_subprocess("false")
        assert rc == 1

    def test_passes_shell_and_command(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setenv("SHELL", "/bin/zsh")
        run_in_subprocess("ls -la")
        assert calls[0][0] == "/bin/zsh"
        assert calls[0][1] == "-c"
        assert calls[0][2] == "ls -la"

    def test_passes_cwd(self, monkeypatch, tmp_path):
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(subprocess, "run", fake_run)
        run_in_subprocess("ls", cwd=tmp_path)
        assert calls[0]["cwd"] == str(tmp_path)

    def test_no_cwd_passes_none(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(subprocess, "run", fake_run)
        run_in_subprocess("ls")
        assert calls[0]["cwd"] is None

    def test_real_exit_code(self):
        """Run a real harmless command and check the exit code."""
        import os
        shell = os.environ.get("SHELL", "/bin/zsh")
        rc = run_in_subprocess("exit 3")
        assert rc == 3

    def test_real_success(self):
        rc = run_in_subprocess("exit 0")
        assert rc == 0
