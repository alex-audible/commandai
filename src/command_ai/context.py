"""Gather contextual awareness of the working directory and environment.

We only ever read *names* and lightweight metadata (type, size) — never file
contents — so building context is cheap and avoids leaking file data.
"""

from __future__ import annotations

import os
import platform
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .config import Config


@dataclass
class DirListing:
    """A single directory's immediate children."""

    path: Path
    dirs: list[str]
    files: list[str]
    truncated: bool = False

    def render(self) -> str:
        lines = [f"{self.path}:"]
        for d in self.dirs:
            lines.append(f"  {d}/")
        for f in self.files:
            lines.append(f"  {f}")
        if self.truncated:
            lines.append("  … (truncated)")
        if not self.dirs and not self.files:
            lines.append("  (empty)")
        return "\n".join(lines)


def _is_wsl() -> bool:
    """Detect Windows Subsystem for Linux."""
    if "microsoft" in platform.release().lower():
        return True
    try:
        with open("/proc/version", "r", encoding="utf-8", errors="ignore") as fh:
            return "microsoft" in fh.read().lower()
    except OSError:
        return False


def _linux_distro() -> str:
    """Best-effort pretty distro name from /etc/os-release."""
    try:
        with open("/etc/os-release", "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "Linux"


def detected_shell() -> str:
    """The shell the generated command will run in, best-effort.

    Honours ``AI_CURRENT_SHELL`` (set by the shell integration), then ``$SHELL``
    (macOS/Linux/WSL), then a Windows default.
    """
    return (
        os.environ.get("AI_CURRENT_SHELL")
        or os.environ.get("SHELL")
        or (os.environ.get("COMSPEC", "cmd.exe") if os.name == "nt" else "/bin/sh")
    )


def environment_summary(cwd: Path | None = None) -> str:
    """Human-readable summary of the OS/shell the command will run in.

    This is what tells the model which platform's commands to generate, so it
    works on macOS (primary), Linux, WSL, and Windows.
    """
    cwd = cwd or Path.cwd()
    shell = detected_shell()
    sysname = platform.system()
    if sysname == "Darwin":
        os_label = f"macOS ({platform.mac_ver()[0] or platform.release()})"
    elif sysname == "Linux":
        os_label = _linux_distro()
        if _is_wsl():
            os_label += " on WSL (Windows Subsystem for Linux)"
    elif sysname == "Windows":
        os_label = f"Windows ({platform.release()})"
    else:
        os_label = f"{sysname} ({platform.release()})"
    return (
        f"Operating system: {os_label}\n"
        f"Shell: {shell}\n"
        f"Current directory: {cwd}"
    )


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def list_directory(
    path: Path,
    config: Config,
    max_entries: int | None = None,
) -> DirListing:
    """List the immediate children of *path* (dirs then files), capped."""
    path = path.expanduser()
    cap = max_entries if max_entries is not None else config.max_files
    dirs: list[str] = []
    files: list[str] = []
    truncated = False
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        return DirListing(path=path, dirs=[], files=[f"<error: {exc.__class__.__name__}>"])

    for entry in entries:
        if not config.include_hidden and _is_hidden(entry.name):
            continue
        if len(dirs) + len(files) >= cap:
            truncated = True
            break
        try:
            if entry.is_dir(follow_symlinks=False):
                dirs.append(entry.name)
            else:
                files.append(entry.name)
        except OSError:
            files.append(entry.name)
    return DirListing(path=path, dirs=dirs, files=files, truncated=truncated)


def build_tree(root: Path, config: Config) -> tuple[str, int]:
    """Build a depth- and count-limited indented tree rooted at *root*.

    Returns the rendered tree and the number of entries shown.
    """
    root = root.expanduser()
    lines: list[str] = []
    shown = 0
    budget = config.max_files

    def walk(directory: Path, depth: int, prefix: str) -> None:
        nonlocal shown
        if depth > config.max_depth or shown >= budget:
            return
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name.lower())
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            return
        for entry in entries:
            if shown >= budget:
                lines.append(f"{prefix}… (truncated)")
                return
            if not config.include_hidden and _is_hidden(entry.name):
                continue
            try:
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            marker = "/" if is_dir else ""
            lines.append(f"{prefix}{entry.name}{marker}")
            shown += 1
            if is_dir and depth < config.max_depth:
                walk(Path(entry.path), depth + 1, prefix + "  ")

    walk(root, 0, "")
    if not lines:
        return "(empty or unreadable)", 0
    return "\n".join(lines), shown


def extension_summary(root: Path, config: Config) -> str:
    """Count file extensions in the (depth-limited) tree to hint at file types."""
    root = root.expanduser()
    counts: Counter[str] = Counter()

    def walk(directory: Path, depth: int) -> None:
        if depth > config.max_depth:
            return
        try:
            entries = list(os.scandir(directory))
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            return
        for entry in entries:
            if not config.include_hidden and _is_hidden(entry.name):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if depth < config.max_depth:
                        walk(Path(entry.path), depth + 1)
                    continue
            except OSError:
                continue
            ext = Path(entry.name).suffix.lower()
            counts[ext if ext else "(no ext)"] += 1

    walk(root, 0)
    if not counts:
        return "none"
    top = counts.most_common(12)
    return ", ".join(f"{ext}×{n}" for ext, n in top)


def parse_shell_context(raw: str, max_history: int = 15) -> str | None:
    """Format the shell-context file written by the ``ai`` shell function.

    The file looks like::

        last_exit_status=1
        recent_history:
        git status
        git push

    Returns a labelled block for the prompt, or ``None`` if there is nothing
    useful to report.
    """
    if not raw:
        return None

    status: str | None = None
    history: list[str] = []
    in_history = False
    for line in raw.splitlines():
        if not in_history and line.startswith("last_exit_status="):
            status = line.split("=", 1)[1].strip()
        elif line.strip() == "recent_history:":
            in_history = True
        elif in_history:
            if line.strip():
                history.append(line.rstrip())

    if max_history >= 0:
        history = history[-max_history:] if max_history else []

    if status is None and not history:
        return None

    lines = ["Recent shell session (use this to fix or follow up on previous commands):"]
    if status is not None:
        suffix = " (non-zero means the previous command failed)" if status not in ("", "0") else ""
        lines.append(f"Previous command exit status: {status}{suffix}")
    if history:
        lines.append("Recent commands (oldest first, most recent last):")
        lines.extend(f"  {cmd}" for cmd in history)
    return "\n".join(lines)


def gather_context(cwd: Path | None = None, config: Config | None = None) -> str:
    """Assemble the full context block injected into the model prompt."""
    cwd = (cwd or Path.cwd()).expanduser()
    config = config or Config()

    tree, count = build_tree(cwd, config)
    exts = extension_summary(cwd, config)

    return (
        f"{environment_summary(cwd)}\n\n"
        f"File types present (extension×count): {exts}\n\n"
        f"Directory tree (depth ≤ {config.max_depth}, {count} entries shown):\n"
        f"{tree}"
    )
