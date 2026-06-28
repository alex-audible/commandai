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
import re
import subprocess
from pathlib import Path

# Patterns that are almost always destructive; used to upgrade the danger
# warning even if the model under-rates a command.
_DANGEROUS_PATTERNS = [
    r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r",  # rm -rf / -fr
    r"\brm\s+-[a-z]*r\b",                                # any recursive rm
    r"\brm\b[^|<>]*\*",                                  # rm touching a glob
    r"\bdd\s+if=",                                       # dd
    r"\bmkfs\b",                                          # format
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
]

_DANGEROUS_RE = re.compile("|".join(_DANGEROUS_PATTERNS), re.IGNORECASE)


def looks_dangerous(command: str) -> bool:
    """Heuristic: does this command match a known-destructive pattern?"""
    return bool(_DANGEROUS_RE.search(command or ""))


def write_command(command: str, output_file: str | Path) -> None:
    """Write the command for the shell wrapper to eval (output-file mode)."""
    path = Path(output_file)
    path.write_text(command.rstrip("\n") + "\n", encoding="utf-8")


def user_shell() -> str:
    """The shell to run subprocess-mode commands under."""
    return os.environ.get("SHELL", "/bin/zsh")


def run_in_subprocess(command: str, cwd: Path | None = None) -> int:
    """Run *command* via the user's shell, inheriting cwd and environment."""
    shell = user_shell()
    completed = subprocess.run(
        [shell, "-c", command],
        cwd=str(cwd) if cwd else None,
        check=False,
    )
    return completed.returncode
