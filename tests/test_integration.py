"""Real-execution integration tests.

Unlike the rest of the suite — which mocks ``subprocess`` and fakes the platform
identity — these tests spawn the **actual** shell and assert real effects: exit
codes propagate, and a command really writes a file into the working directory.
This is what turns the CI matrix from "the decision logic is consistent" into
"the code actually runs on this OS".

Every test is gated on the relevant shell genuinely being present
(``shutil.which`` / ``os.name``), so the suite stays green on any host and only
exercises what that host can really run:

* POSIX shells (sh/bash/zsh/dash) — Linux and macOS runners.
* cmd.exe and PowerShell — the Windows runner.

The command is steered to a specific shell via ``AI_CURRENT_SHELL``, which
``executor.user_shell()`` honours first, so each test pins exactly which shell
family parses the command.
"""

from __future__ import annotations

import os
import shutil

import pytest

from command_ai import executor

POSIX = os.name == "posix"
WINDOWS = os.name == "nt"

# Real POSIX shells installed on this host (Linux/macOS always have at least sh).
_POSIX_SHELLS = (
    [name for name in ("sh", "bash", "zsh", "dash") if shutil.which(name)]
    if POSIX
    else []
)
# Prefer PowerShell 7 (pwsh) but fall back to Windows PowerShell 5.1.
_POWERSHELL = shutil.which("pwsh") or shutil.which("powershell")


@pytest.mark.skipif(not POSIX, reason="POSIX shells only")
@pytest.mark.parametrize("shell", _POSIX_SHELLS or ["sh"])
class TestPosixRealExecution:
    """Spawn a real POSIX shell through run_in_subprocess and check effects."""

    def test_exit_code_zero(self, monkeypatch, shell):
        monkeypatch.setenv("AI_CURRENT_SHELL", shutil.which(shell))
        assert executor.run_in_subprocess("exit 0") == 0

    def test_exit_code_propagates(self, monkeypatch, shell):
        monkeypatch.setenv("AI_CURRENT_SHELL", shutil.which(shell))
        assert executor.run_in_subprocess("exit 7") == 7

    def test_writes_file_in_cwd(self, monkeypatch, shell, tmp_path):
        monkeypatch.setenv("AI_CURRENT_SHELL", shutil.which(shell))
        rc = executor.run_in_subprocess("printf 'hi' > marker.txt", cwd=tmp_path)
        assert rc == 0
        assert (tmp_path / "marker.txt").read_text() == "hi"

    def test_command_reaches_shell_verbatim(self, monkeypatch, shell, tmp_path):
        # The command must arrive at the shell as a single argv element (one
        # round of parsing), so quoting/spacing is preserved rather than mangled.
        monkeypatch.setenv("AI_CURRENT_SHELL", shutil.which(shell))
        rc = executor.run_in_subprocess("printf '%s' 'a b  c' > q.txt", cwd=tmp_path)
        assert rc == 0
        assert (tmp_path / "q.txt").read_text() == "a b  c"


@pytest.mark.skipif(not WINDOWS, reason="cmd.exe is Windows-only")
class TestWindowsCmdRealExecution:
    """Spawn the real cmd.exe through run_in_subprocess and check effects."""

    def _comspec(self):
        return os.environ.get("COMSPEC", "cmd.exe")

    def test_exit_code_zero(self, monkeypatch):
        monkeypatch.setenv("AI_CURRENT_SHELL", self._comspec())
        assert executor.run_in_subprocess("exit /b 0") == 0

    def test_exit_code_propagates(self, monkeypatch):
        monkeypatch.setenv("AI_CURRENT_SHELL", self._comspec())
        assert executor.run_in_subprocess("exit /b 5") == 5

    def test_writes_file_in_cwd(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_CURRENT_SHELL", self._comspec())
        rc = executor.run_in_subprocess("echo hi> marker.txt", cwd=tmp_path)
        assert rc == 0
        assert "hi" in (tmp_path / "marker.txt").read_text()


@pytest.mark.skipif(not (WINDOWS and _POWERSHELL), reason="PowerShell not available")
class TestWindowsPowerShellRealExecution:
    """Spawn real PowerShell through run_in_subprocess and check effects."""

    def test_exit_code_zero(self, monkeypatch):
        monkeypatch.setenv("AI_CURRENT_SHELL", _POWERSHELL)
        assert executor.run_in_subprocess("exit 0") == 0

    def test_writes_file_in_cwd(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AI_CURRENT_SHELL", _POWERSHELL)
        rc = executor.run_in_subprocess(
            "Set-Content -Path marker.txt -Value hi -NoNewline", cwd=tmp_path
        )
        assert rc == 0
        content = (tmp_path / "marker.txt").read_text(encoding="utf-8", errors="ignore")
        assert "hi" in content
