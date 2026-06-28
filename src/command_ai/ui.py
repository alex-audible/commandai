"""Interactive presentation and selection.

All user-facing output goes to **stderr** so that stdout (and any
``--output-file``) stays clean for the chosen command, which the shell wrapper
needs to ``eval``.
"""

from __future__ import annotations

import sys
from typing import Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .llm import CommandOption

# Console bound to stderr; everything interactive is rendered here.
console = Console(stderr=True, highlight=False)

_DANGER_STYLES = {
    "low": "green",
    "medium": "yellow",
    "high": "bold red",
}


def _danger_label(danger: str) -> Text:
    style = _DANGER_STYLES.get(danger, "green")
    return Text(danger.upper(), style=style)


def render_option(option: CommandOption, index: int | None = None) -> None:
    """Pretty-print a single command option to stderr."""
    title = "Suggested command" if index is None else f"Option {index}"
    body = Table.grid(padding=(0, 1))
    body.add_column(justify="left", no_wrap=False)

    cmd = Text(option.command, style="bold cyan")
    body.add_row(cmd)
    if option.summary:
        body.add_row(Text(option.summary, style="white"))

    if option.args:
        body.add_row(Text(""))
        arg_table = Table(show_header=True, header_style="dim", box=None, pad_edge=False)
        arg_table.add_column("part", style="cyan", no_wrap=False)
        arg_table.add_column("explanation", style="white", no_wrap=False)
        for a in option.args:
            arg_table.add_row(a.get("part", ""), a.get("explains", ""))
        body.add_row(arg_table)

    subtitle = Text.assemble(("danger: ", "dim"), _danger_label(option.danger))
    console.print(Panel(body, title=title, subtitle=subtitle, border_style="blue"))


def print_error(message: str) -> None:
    console.print(Text(f"✖ {message}", style="bold red"))


def print_info(message: str) -> None:
    console.print(Text(message, style="dim"))


def _interactive() -> bool:
    """True only when we have a real TTY to drive arrow-key selection."""
    try:
        return sys.stdin.isatty() and sys.stderr.isatty()
    except (AttributeError, ValueError):  # pragma: no cover
        return False


CANCEL = "__cancel__"


def select_command(
    options: Sequence[CommandOption],
    assume_yes: bool = False,
) -> CommandOption | None:
    """Show options and let the user choose. Returns ``None`` if cancelled.

    - ``assume_yes`` skips the prompt and picks the first option.
    - With a single option, Enter confirms; with several, arrow keys choose.
    """
    if not options:
        return None

    for i, opt in enumerate(options, start=1):
        render_option(opt, index=None if len(options) == 1 else i)

    if assume_yes:
        return options[0]

    if not _interactive():
        # No TTY (piped/CI): do not auto-run; require an explicit --yes.
        print_info("Non-interactive stdin: re-run with --yes to execute the first option.")
        return None

    import questionary

    if len(options) == 1:
        choices = [
            questionary.Choice(title="Run this command", value=0),
            questionary.Choice(title="Cancel", value=CANCEL),
        ]
        message = "Run it?"
    else:
        choices = [
            questionary.Choice(title=f"{i}. {opt.command}", value=i - 1)
            for i, opt in enumerate(options, start=1)
        ]
        choices.append(questionary.Choice(title="Cancel", value=CANCEL))
        message = "Choose a command (↑/↓, Enter):"

    answer = questionary.select(
        message,
        choices=choices,
        qmark="»",
        instruction="(↑/↓ then Enter)",
    ).ask()

    if answer is None or answer == CANCEL:
        return None
    return options[answer]


def prompt_api_key(provider_name: str, provider_info: dict) -> str | None:
    """Interactively ask for an API key (hidden input). None if not a TTY/empty."""
    if not _interactive():
        return None
    import getpass

    label = provider_info.get("label", provider_name)
    console.print(
        Panel(
            Text(f"{label} needs an API key to use.", style="bold"),
            border_style="yellow",
        )
    )
    signup = provider_info.get("signup_url")
    if signup:
        print_info(f"Get one at: {signup}")
    try:
        key = getpass.getpass(f"Enter your {label} API key (input hidden): ")
    except (EOFError, KeyboardInterrupt):
        return None
    key = key.strip()
    return key or None


def confirm_store_key(location: str) -> bool:
    """Ask whether to persist the key. Returns False when non-interactive."""
    if not _interactive():
        return False
    import questionary

    return bool(
        questionary.confirm(
            f"Save this key in {location} for next time?",
            default=True,
        ).ask()
    )


def confirm_dangerous(option: CommandOption) -> bool:
    """Extra confirmation for high-danger commands. Returns True to proceed."""
    console.print(
        Panel(
            Text(
                "This command is flagged as HIGH danger (destructive or "
                "irreversible). Review it carefully.",
                style="bold red",
            ),
            border_style="red",
        )
    )
    if not _interactive():
        return False
    import questionary

    return bool(
        questionary.confirm(
            "Type to confirm you really want to run it",
            default=False,
        ).ask()
    )
