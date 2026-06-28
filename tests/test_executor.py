"""Tests for command_ai.executor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import command_ai.executor as executor
from command_ai.executor import (
    build_shell_invocation,
    is_windows,
    looks_dangerous,
    run_in_subprocess,
    shell_name,
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

    # Windows / PowerShell patterns
    def test_remove_item_recurse_force(self):
        assert looks_dangerous("Remove-Item -Recurse -Force C:\\data") is True

    def test_remove_item_recurse(self):
        assert looks_dangerous("Remove-Item -Recurse x") is True

    def test_del_s_q(self):
        assert looks_dangerous("del /s /q C:\\temp") is True

    def test_del_f_q(self):
        assert looks_dangerous("del /f /q x") is True

    def test_rd_s_q(self):
        assert looks_dangerous("rd /s /q x") is True

    def test_rmdir_s(self):
        assert looks_dangerous("rmdir /s x") is True

    def test_format_drive(self):
        assert looks_dangerous("format c:") is True

    def test_format_volume(self):
        assert looks_dangerous("Format-Volume -DriveLetter D") is True

    def test_clear_disk(self):
        assert looks_dangerous("Clear-Disk 1") is True

    def test_cipher_wipe(self):
        assert looks_dangerous("cipher /w:C") is True

    # False cases
    def test_ls(self):
        assert looks_dangerous("ls -la") is False

    # Windows / PowerShell safe cases
    def test_get_childitem_safe(self):
        assert looks_dangerous("Get-ChildItem") is False

    def test_dir_safe(self):
        assert looks_dangerous("dir") is False

    def test_del_plain_safe(self):
        # del without /s|/q|/f flags is not dangerous
        assert looks_dangerous("del file.txt") is False

    def test_remove_item_no_recurse_safe(self):
        assert looks_dangerous("Remove-Item file.txt") is False

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
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.setenv("SHELL", "/bin/fish")
        assert user_shell() == "/bin/fish"

    def test_ai_current_shell_wins(self, monkeypatch):
        monkeypatch.setenv("AI_CURRENT_SHELL", "/opt/homebrew/bin/fish")
        monkeypatch.setenv("SHELL", "/bin/bash")  # should be ignored
        assert user_shell() == "/opt/homebrew/bin/fish"

    def test_shell_used_when_no_hint(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.setenv("SHELL", "/bin/dash")
        assert user_shell() == "/bin/dash"

    def test_default_zsh_on_macos(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.setattr(executor.os, "name", "posix")
        monkeypatch.setattr(executor.platform, "system", lambda: "Darwin")
        assert user_shell() == "/bin/zsh"

    def test_default_bash_on_linux(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.setattr(executor.os, "name", "posix")
        monkeypatch.setattr(executor.platform, "system", lambda: "Linux")
        assert user_shell() == "/bin/bash"

    def test_default_comspec_on_windows(self, monkeypatch):
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.delenv("SHELL", raising=False)
        monkeypatch.setattr(executor.os, "name", "nt")
        monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
        assert user_shell() == r"C:\Windows\System32\cmd.exe"

    def test_returns_string(self):
        assert isinstance(user_shell(), str)


# ---------------------------------------------------------------------------
# is_windows
# ---------------------------------------------------------------------------

class TestIsWindows:
    def test_true_when_nt(self, monkeypatch):
        monkeypatch.setattr(executor.os, "name", "nt")
        assert is_windows() is True

    def test_false_when_posix(self, monkeypatch):
        monkeypatch.setattr(executor.os, "name", "posix")
        assert is_windows() is False


# ---------------------------------------------------------------------------
# shell_name
# ---------------------------------------------------------------------------

class TestShellName:
    def test_posix_zsh(self):
        assert shell_name("/bin/zsh") == "zsh"

    def test_posix_bash(self):
        assert shell_name("/usr/bin/bash") == "bash"

    def test_powershell_exe(self):
        assert shell_name("powershell.exe") == "powershell"

    def test_pwsh_bare(self):
        assert shell_name("pwsh") == "pwsh"

    def test_windows_cmd_backslash_path(self):
        assert shell_name(r"C:\Windows\System32\cmd.exe") == "cmd"

    def test_windows_pwsh_forward_slash_path(self):
        assert shell_name("C:/Program Files/PowerShell/pwsh.exe") == "pwsh"

    def test_strips_exe_case_insensitive_path(self):
        # forward-slash path with .exe
        assert shell_name("/some/dir/fish") == "fish"


# ---------------------------------------------------------------------------
# build_shell_invocation
# ---------------------------------------------------------------------------

class TestBuildShellInvocation:
    def test_bash(self):
        assert build_shell_invocation("/bin/bash", "ls") == ["/bin/bash", "-c", "ls"]

    def test_zsh(self):
        assert build_shell_invocation("/bin/zsh", "ls -la") == ["/bin/zsh", "-c", "ls -la"]

    def test_sh(self):
        assert build_shell_invocation("/bin/sh", "pwd") == ["/bin/sh", "-c", "pwd"]

    def test_fish(self):
        assert build_shell_invocation("/usr/bin/fish", "echo hi") == [
            "/usr/bin/fish", "-c", "echo hi"
        ]

    def test_dash(self):
        assert build_shell_invocation("/bin/dash", "true") == ["/bin/dash", "-c", "true"]

    def test_powershell(self):
        assert build_shell_invocation("powershell.exe", "Get-ChildItem") == [
            "powershell.exe", "-NoProfile", "-Command", "Get-ChildItem"
        ]

    def test_pwsh(self):
        assert build_shell_invocation("pwsh", "Get-Process") == [
            "pwsh", "-NoProfile", "-Command", "Get-Process"
        ]

    def test_cmd(self):
        assert build_shell_invocation("cmd", "dir") == ["cmd", "/c", "dir"]

    def test_cmd_exe_windows_path(self):
        # Verifies the / vs \ split: a full Windows path to cmd.exe maps to /c.
        shell = r"C:\Windows\System32\cmd.exe"
        assert build_shell_invocation(shell, "dir") == [shell, "/c", "dir"]

    def test_pwsh_windows_path(self):
        shell = "C:/Program Files/PowerShell/pwsh.exe"
        assert build_shell_invocation(shell, "ls") == [
            shell, "-NoProfile", "-Command", "ls"
        ]


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
        monkeypatch.delenv("AI_CURRENT_SHELL", raising=False)
        monkeypatch.setenv("SHELL", "/bin/zsh")
        run_in_subprocess("ls -la")
        assert calls[0][0] == "/bin/zsh"
        assert calls[0][1] == "-c"
        assert calls[0][2] == "ls -la"

    def test_uses_build_shell_invocation_for_windows(self, monkeypatch):
        # No real Windows shell spawn: subprocess.run is mocked. Verify the argv
        # comes from build_shell_invocation for a cmd.exe shell.
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setenv("AI_CURRENT_SHELL", r"C:\Windows\System32\cmd.exe")
        run_in_subprocess("dir")
        assert calls[0] == [r"C:\Windows\System32\cmd.exe", "/c", "dir"]

    def test_uses_build_shell_invocation_for_powershell(self, monkeypatch):
        calls = []
        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return SimpleNamespace(returncode=0)
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setenv("AI_CURRENT_SHELL", "pwsh")
        run_in_subprocess("Get-ChildItem")
        assert calls[0] == ["pwsh", "-NoProfile", "-Command", "Get-ChildItem"]

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
