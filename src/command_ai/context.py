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


def environment_summary(cwd: Path | None = None) -> str:
    """Human-readable summary of the OS/shell the command will run in."""
    cwd = cwd or Path.cwd()
    shell = os.environ.get("SHELL", "/bin/sh")
    sysname = platform.system()
    if sysname == "Darwin":
        os_label = f"macOS ({platform.mac_ver()[0] or platform.release()})"
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
