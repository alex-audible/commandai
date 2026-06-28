#!/usr/bin/env bash
# commandai installer for macOS, Linux, and WSL.
#
# Installs the `command-ai` console script (via pipx if available, else a venv)
# and wires up the `ai` shell function in your shell rc file (zsh or bash).
# (macOS is the primary target; Linux/WSL are supported. For native Windows
# PowerShell, use install.ps1 instead.)
#
#   ./install.sh
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHELL_SNIPPET="source \"$REPO_DIR/shell/ai.sh\""
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/command-ai"
CONFIG_FILE="$CONFIG_DIR/config.toml"

# Pick the rc file for the user's login shell (zsh on macOS, usually bash on Linux).
case "$(basename "${SHELL:-}")" in
  zsh)  RC_FILE="${HOME}/.zshrc" ;;
  bash) RC_FILE="${HOME}/.bashrc" ;;
  *)    if [ -n "${ZSH_VERSION:-}" ]; then RC_FILE="${HOME}/.zshrc";
        elif [ "$(uname -s)" = "Darwin" ]; then RC_FILE="${HOME}/.zshrc";
        else RC_FILE="${HOME}/.bashrc"; fi ;;
esac

info()  { printf '\033[34m›\033[0m %s\n' "$*"; }
ok()    { printf '\033[32m✓\033[0m %s\n' "$*"; }
warn()  { printf '\033[33m!\033[0m %s\n' "$*"; }

# 1. Install the package.
if command -v pipx >/dev/null 2>&1; then
  info "Installing with pipx…"
  pipx install --force "$REPO_DIR"
  ok "Installed command-ai via pipx."
else
  warn "pipx not found; falling back to a local virtualenv (.venv)."
  python3 -m venv "$REPO_DIR/.venv"
  # shellcheck disable=SC1091
  "$REPO_DIR/.venv/bin/pip" install --upgrade pip >/dev/null
  "$REPO_DIR/.venv/bin/pip" install "$REPO_DIR"
  # Symlink the console script onto PATH.
  mkdir -p "$HOME/.local/bin"
  ln -sf "$REPO_DIR/.venv/bin/command-ai" "$HOME/.local/bin/command-ai"
  ok "Installed into .venv and linked command-ai into ~/.local/bin."
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) warn "Add ~/.local/bin to your PATH (e.g. in ~/.zshrc):"
       echo '       export PATH="$HOME/.local/bin:$PATH"' ;;
  esac
fi

# 2. Seed a config file if missing.
if [ ! -f "$CONFIG_FILE" ]; then
  mkdir -p "$CONFIG_DIR"
  cp "$REPO_DIR/config.example.toml" "$CONFIG_FILE"
  ok "Wrote default config to $CONFIG_FILE"
else
  info "Config already exists at $CONFIG_FILE (left untouched)."
fi

# 3. Wire up the shell function.
if [ -f "$RC_FILE" ] && grep -Fq "$SHELL_SNIPPET" "$RC_FILE"; then
  info "Shell function already sourced in $RC_FILE."
else
  {
    echo ""
    echo "# commandai: ai() shell function"
    echo "$SHELL_SNIPPET"
  } >> "$RC_FILE"
  ok "Added the ai() function to $RC_FILE"
fi

echo ""
ok "Done. Open a new terminal (or run: source $RC_FILE), then try:"
echo "    ai list the 3 largest files in this directory"
