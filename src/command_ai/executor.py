"""Execute the chosen command, or hand it to the shell wrapper.

Two modes:

* **output-file mode** (``--output-file PATH``): write the command to PATH and
  return. The ``ai`` shell function then ``eval``s it in the *current* shell,
  so ``cd``/exports persist and it lands in shell history.
* **subprocess mode** (default): run the command in a subprocess that inherits
  the current working directory and environment. Fine for most commands;
  ``cd`` won't persist because that's impossible from a child process.
"""

from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path

# Patterns that are almost always destructive; used to upgrade the danger
# warning even if the model under-rates a command. Covers POSIX (macOS/Linux)
# and, at the end, Windows / PowerShell equivalents.
_DANGEROUS_PATTERNS = [
    r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r",  # rm -rf / -fr
    r"\brm\s+-[a-z]*r\b",                                # any recursive rm
    r"\brm\b[^|<>]*\*",                                  # rm touching a glob
    r"\bdd\s+if=",                                       # dd
    r"\bmkfs\b",                                          # format (linux)
    r"\b(sudo\s+)?shutdown\b|\breboot\b",
    r">\s*/dev/sd",                                       # writing to a disk
    r">\s*/dev/disk",
    r":\(\)\s*\{.*\};:",                                 # fork bomb
    r"\bchmod\s+-R\s+777\b",
    r"\b(curl|wget)\b.*\|\s*(sudo\s+)?(bash|sh|zsh)\b",  # curl | sh
    r"\bgit\s+clean\b[^|]*-[a-z]*f",                     # git clean -f*
    r"\btruncate\b",                                      # truncate a file
    r"\bfind\b.*-delete\b",                               # find … -delete
    r"\b(diskutil|newfs_\w+)\b",                          # macOS disk ops
    r"\bchflags\b[^|]*-R",                                # recursive chflags
    r"\bcrontab\s+-r\b",                                  # wipe crontab
    r"\brsync\b.*--delete",                               # mirror-delete
    r"\bfind\b[^|]*-exec\s+rm\b",                         # find … -exec rm
    r"\|\s*(sudo\s+)?(bash|sh|zsh|fish)\b",              # anything piped into a shell
    r"\bpython[0-9.]*\s+-c\b.*(shutil\.rmtree|rmtree|os\.remove|os\.unlink|\.unlink\()",  # destructive python -c
    r">\s*/dev/(nvme|mmcblk|vd|hd)",                      # writing to a block device
    r"\b(shred|wipefs|wipe)\b",                           # secure-wipe tools
    r"\b(fdisk|parted|sgdisk|gdisk|gparted)\b",          # partition editors
    # --- Windows / PowerShell ---
    r"\bdel\b[^|]*\/[a-z]*[sqf]",                         # del /s /q /f
    r"\b(rd|rmdir)\b[^|]*\/s",                            # rd /s, rmdir /s
    r"\bformat\b\s+[a-z]:",                               # format c:
    r"Remove-Item\b[^|]*-Recurse",                        # Remove-Item -Recurse [-Force]
    r"\bFormat-Volume\b|\bClear-Disk\b|\bRemove-Partition\b",
    r"\bcipher\b[^|]*\/w",                                # secure wipe free space
]

_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)


def looks_dangerous(command: str) -> bool:
    """Heuristic: does this command match a known-destructive pattern?"""
    return bool(_DANGEROUS_RE.search(command or ""))


def write_command(command: str, output_file: str | Path) -> None:
    """Write the command for the shell wrapper to eval (output-file mode)."""
    path = Path(output_file)
    path.write_text(command.rstrip("\n") + "\n", encoding="utf-8")


def is_windows() -> bool:
    return os.name == "nt"


def user_shell() -> str:
    """The shell to run subprocess-mode commands under.

    Resolution order: an explicit hint from the shell integration
    (``AI_CURRENT_SHELL``), then ``$SHELL`` (set on macOS/Linux/WSL), then a
    sensible per-OS default (zsh on macOS, bash on Linux, PowerShell/cmd on
    Windows).
    """
    hint = os.environ.get("AI_CURRENT_SHELL")
    if hint:
        return hint
    env_shell = os.environ.get("SHELL")
    if env_shell:
        return env_shell
    if is_windows():
        return os.environ.get("COMSPEC", "powershell.exe")
    return "/bin/zsh" if platform.system() == "Darwin" else "/bin/bash"


def shell_name(shell: str) -> str:
    """Bare shell name, e.g. '/usr/bin/bash' -> 'bash', 'powershell.exe' -> 'powershell'.

    Splits on both separators so a Windows path is handled even on POSIX.
    """
    base = re.split(r"[\\/]", shell)[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def build_shell_invocation(shell: str, command: str) -> list[str]:
    """Build the argv to run *command* under *shell*, per shell family."""
    name = shell_name(shell)
    if name in ("powershell", "pwsh"):
        return [shell, "-NoProfile", "-Command", command]
    if name == "cmd":
        return [shell, "/c", command]
    # POSIX shells: bash, zsh, sh, dash, fish, ksh, …
    return [shell, "-c", command]


def run_in_subprocess(command: str, cwd: Path | None = None) -> int:
    """Run *command* via the user's shell, inheriting cwd and environment."""
    shell = user_shell()
    completed = subprocess.run(
        build_shell_invocation(shell, command),
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    return completed.returncode
