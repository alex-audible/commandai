# commandai shell integration — defines the `ai` function.
#
# Source this from your ~/.zshrc (or ~/.bashrc):
#     source /path/to/commandai/shell/ai.sh
#
# Why a function? A child process cannot change its parent shell's directory or
# environment. This wrapper lets the Python tool do all the interaction, then
# evals the single chosen command in YOUR current shell, so `cd`, exports, etc.
# persist — and the command is added to your shell history.
#
# Requires the `command-ai` console script on PATH (installed via pipx/pip).

ai() {
  if [ "$#" -eq 0 ]; then
    command-ai
    return $?
  fi

  # Pass flags straight through without the eval dance.
  case "$1" in
    --version|--help|-h|--print-config|--dry-run|-n)
      command-ai "$@"
      return $?
      ;;
  esac

  local _ai_tmp
  _ai_tmp="$(mktemp -t command-ai.XXXXXX)" || {
    echo "ai: could not create temp file" >&2
    return 1
  }

  # The tool renders everything on stderr and writes the chosen command (if any)
  # to the temp file. stdout is left clean.
  command-ai --output-file "$_ai_tmp" "$@"
  local _ai_status=$?

  if [ "$_ai_status" -ne 0 ]; then
    rm -f "$_ai_tmp"
    return "$_ai_status"
  fi

  if [ ! -s "$_ai_tmp" ]; then
    # Cancelled or nothing chosen.
    rm -f "$_ai_tmp"
    return 0
  fi

  local _ai_cmd
  _ai_cmd="$(cat "$_ai_tmp")"
  rm -f "$_ai_tmp"

  # Record in history so you can re-run/edit it later.
  if [ -n "$ZSH_VERSION" ]; then
    print -s -- "$_ai_cmd"
  elif [ -n "$BASH_VERSION" ]; then
    history -s -- "$_ai_cmd"
  fi

  # Run it in the CURRENT shell so cd/exports persist.
  eval "$_ai_cmd"
}
