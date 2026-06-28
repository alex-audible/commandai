# commandai

Ask for a shell command in plain English. A local LLM suggests the exact command with a per-argument explanation. Pick it with arrow keys, press Enter, and it runs — in your current shell.

```
$ ai use ffmpeg to convert all the videos in this folder from mov to mp4

  Thinking with gemma-4-26b-a4b …

  ┌─────────────────────────────────────────────────────────────────────┐
  │  for f in *.mov; do ffmpeg -i "$f" "${f%.mov}.mp4"; done           │
  │                                                                     │
  │  Convert every .mov file in the current directory to .mp4          │
  │                                                                     │
  │  -i "$f"           input file (each .mov, iterated by the loop)    │
  │  "${f%.mov}.mp4"   output name (strips .mov suffix, adds .mp4)     │
  └─────────────────────────────────────────────────────────────────────┘

  ❯ Run:  for f in *.mov; do ffmpeg -i "$f" "${f%.mov}.mp4"; done
    Cancel
```

---

## Features

- **Natural-language input** — describe what you want; get an exact, runnable shell command back.
- **Per-argument explanations** — every flag and token is broken down so you understand what you are about to run.
- **Arrow-key selection** — browse options with the keyboard; press Enter to run the highlighted choice.
- **Multiple options for ambiguous requests** — when the intent is genuinely unclear the model returns 2–3 meaningfully different alternatives.
- **Filesystem-aware context** — the model sees a depth-limited directory tree and extension summary for the current folder, so suggestions are grounded in what is actually here.
- **Explore loop** — for deeper questions the model may peek into subdirectories before answering (capped at `max_explorations` hops).
- **Optional web search** — when the model needs an external fact it can search the web via DuckDuckGo (no API key required) — for example, finding the right Homebrew formula or cask for a described tool. Ask `ai brew install a tool that flashes bootable images to usb drives` and the model searches the web, finds e.g. balenaEtcher, and suggests `brew install --cask balenaetcher`. It is local-first: a web search only happens when the model decides it needs one, and it can be turned off.
- **Runs in your current shell** — `cd`, `export`, and other shell-state changes persist, because the chosen command is `eval`'d by the `ai` shell function rather than a child process.
- **Safety gates** — the command is always shown before execution; destructive patterns (`rm -rf`, `dd`, `mkfs`, `curl | sh`, …) require an extra explicit confirmation.
- **Local and private** — all inference runs through LM Studio on your machine; nothing leaves your laptop.
- **Fully configurable** — endpoint, model, temperature, context depth, and more are all adjustable via config file, environment variable, or CLI flag.

---

## Requirements

- macOS (the shell function targets zsh/bash on macOS)
- Python 3.11 or later
- [LM Studio](https://lmstudio.ai) running a local server (see setup below)
- `pipx` (recommended) or a plain Python virtual environment
- Internet access only for the optional [web search](#web-search) step; everything else runs locally. Web search uses the [`ddgs`](https://pypi.org/project/ddgs/) package, which is installed automatically as a dependency.

---

## LM Studio setup

1. **Download LM Studio** from [lmstudio.ai](https://lmstudio.ai) and open it.

2. **Download the model.** Search for `gemma-4-26b-a4b` in the model browser and download it. This is the default model; see [Configuration](#configuration) if you want to use something else.

3. **Load the model.** Select it in LM Studio and wait for it to load into memory.

4. **Start the local server.** Open the **Developer** tab (the `</>` icon in the left sidebar) and click **Start Server**. LM Studio will serve an OpenAI-compatible API at `http://localhost:1234` by default.

5. **Verify the server is running:**

   ```bash
   curl -s http://localhost:1234/v1/models | python3 -m json.tool
   ```

   You should see a JSON object listing your loaded model. If the command hangs or errors, go back and confirm the server is started in LM Studio.

---

## Install

### Recommended: one-liner

From the repository root:

```bash
./install.sh
```

The script does three things:

1. **Installs the `command-ai` console script** using `pipx` if it is available, or falls back to a local `.venv` with a symlink into `~/.local/bin`.
2. **Seeds your config file** at `~/.config/command-ai/config.toml` from `config.example.toml` (skipped if the file already exists).
3. **Appends the shell function source line** to `~/.zshrc` so the `ai` command is available in every new shell.

After the script finishes, open a new terminal (or run `source ~/.zshrc`) and try:

```bash
ai list the 3 largest files in this directory
```

### Manual install

**Using pipx (recommended):**

```bash
pipx install .
```

**Using a plain virtual environment:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Then add the shell function to your `~/.zshrc`:

```bash
echo 'source "/path/to/commandai/shell/ai.sh"' >> ~/.zshrc
source ~/.zshrc
```

Replace `/path/to/commandai` with the absolute path to this repository. The `command-ai` console script must be on your `PATH` before the shell function is sourced.

---

## Usage

### Basic examples

```bash
# Convert video files
ai use ffmpeg to convert all the videos in this folder from mov to mp4

# Find large files
ai find the 5 largest files here

# Create an archive
ai create a gzipped tarball of the src folder

# Let the model search the web for the right Homebrew cask
ai brew install a tool that flashes bootable images to usb drives

# Something ambiguous — yields multiple options
ai back up the database
```

### The selection UI

When the model returns its suggestion(s), you navigate with the arrow keys and press **Enter** to run the highlighted option. If there is only one option, pressing Enter immediately confirms it. Press **Ctrl-C** or select **Cancel** to quit without running anything.

Destructive commands (those rated `danger: high` by the model, or those matching known-dangerous patterns like `rm -rf`) show an additional prompt that requires you to type a confirmation before anything runs.

### Useful flags

| Flag | Description |
|---|---|
| `-n`, `--dry-run` | Show the suggested command(s) without running or writing anything. |
| `-y`, `--yes` | Skip the interactive prompt and run the first option automatically. Also bypasses the danger confirmation, so use carefully. |
| `--no-context` | Do not send directory context to the model. Useful when the current folder is irrelevant or very large. |
| `--no-web` | Disable web search for this invocation, even if it is enabled in config. |
| `--print-config` | Print the resolved configuration (endpoint, model, all settings) and exit. Useful for debugging. |
| `--model MODEL` | Use a different model for this invocation. |
| `--base-url URL` | Use a different endpoint for this invocation. |
| `--config PATH` | Load config from a specific TOML file instead of the default location. |
| `--version` | Print the version and exit. |

### Without the shell function

You can invoke the console script directly:

```bash
command-ai find the 5 largest files here
# or
python -m command_ai find the 5 largest files here
```

This works for the vast majority of commands. The only difference is that the command runs in a subprocess rather than your current shell, so `cd` and environment variable changes will **not** persist after the command finishes. See [How it works](#how-it-works) for the reason.

---

## Configuration

### Config file

The config file lives at `~/.config/command-ai/config.toml`. If `$XDG_CONFIG_HOME` is set, commandai uses `$XDG_CONFIG_HOME/command-ai/config.toml` instead. `install.sh` creates this file from the included example. All keys are optional; any omitted setting falls back to its built-in default.

```toml
# ~/.config/command-ai/config.toml

# Endpoint / model
base_url = "http://localhost:1234/v1"
model    = "gemma-4-26b-a4b"
api_key  = "lm-studio"   # LM Studio ignores this value; any non-empty string works

# Generation
temperature = 0.2
max_tokens  = 1024
timeout     = 120.0      # seconds to wait for a response

# Directory context sent to the model
[context]
max_files      = 200     # maximum entries in the directory tree
max_depth      = 2       # how many levels deep the tree goes
include_hidden = false   # include dotfiles and dot-directories

# Filesystem exploration loop
[explore]
max_explorations = 4     # how many subdirectory peeks the model may make before answering

# Web search (DuckDuckGo, no API key)
[web]
web_search     = true    # set false to disable web search entirely
max_searches   = 3       # maximum web searches per request
search_results = 5       # results returned per search
search_timeout = 15.0    # seconds
```

### Environment variables

Every setting can be overridden by an environment variable without touching the config file:

| Variable | Config key | Type | Default |
|---|---|---|---|
| `AI_BASE_URL` | `base_url` | string | `http://localhost:1234/v1` |
| `AI_MODEL` | `model` | string | `gemma-4-26b-a4b` |
| `AI_API_KEY` | `api_key` | string | `lm-studio` |
| `AI_TEMPERATURE` | `temperature` | float | `0.2` |
| `AI_MAX_TOKENS` | `max_tokens` | int | `1024` |
| `AI_TIMEOUT` | `timeout` | float | `120.0` |
| `AI_MAX_FILES` | `max_files` | int | `200` |
| `AI_MAX_DEPTH` | `max_depth` | int | `2` |
| `AI_INCLUDE_HIDDEN` | `include_hidden` | bool (`1`/`true`/`yes`/`on`) | `false` |
| `AI_MAX_EXPLORATIONS` | `max_explorations` | int | `4` |
| `AI_WEB_SEARCH` | `web_search` | bool (`1`/`true`/`yes`/`on`) | `true` |
| `AI_MAX_SEARCHES` | `max_searches` | int | `3` |
| `AI_SEARCH_RESULTS` | `search_results` | int | `5` |
| `AI_SEARCH_TIMEOUT` | `search_timeout` | float | `15.0` |

### Precedence

Settings are merged in this order (later sources win):

```
built-in default  <  config file  <  environment variable  <  CLI flag
```

### Using a different model or endpoint

To point commandai at a different model or a remote OpenAI-compatible endpoint, either edit the config file or use CLI flags:

```bash
# One-off with a different model
ai --model llama-3-8b-instruct list the largest files here

# Point at a remote endpoint. Pass the key via the environment, NOT --api-key:
# anything you type after `ai ...` is saved to your shell history in cleartext,
# so an inline --api-key would leak the secret into ~/.zsh_history.
AI_API_KEY="$OPENAI_API_KEY" ai --base-url https://api.openai.com/v1 --model gpt-4o summarise this repo

# Or set permanently via environment variables / the config file (the safe home for keys)
export AI_MODEL=llama-3-8b-instruct
export AI_BASE_URL=http://localhost:5678/v1
export AI_API_KEY="$OPENAI_API_KEY"
```

---

## How it works

1. **Context gathering.** Before asking the model anything, commandai builds a compact snapshot of the current directory: a depth-limited file tree (controlled by `max_depth` and `max_files`) and a summary of file extensions present. It also records the OS and shell. Only file names and metadata are read — file contents are never sent to the model.

2. **Explore loop.** The model may respond with an explore request (`{"action": "explore", "path": "some/subdir"}`) instead of a final answer. commandai resolves that path, lists it, appends the result to the conversation, and calls the model again. This repeats up to `max_explorations` times, giving the model genuine filesystem navigation without relying on flaky native tool-calling.

3. <a id="web-search"></a>**Web search.** When web search is enabled (the default), the model may instead respond with a search request (`{"action": "search", "query": "..."}`) when it needs current or external information — for example, the exact Homebrew cask name for a described tool. commandai runs a DuckDuckGo text search (via the `ddgs` package, no API key), feeds the rendered results back into the conversation, and calls the model again; the model then produces the final command. This is capped at `max_searches` searches per request. Searches only happen when the model asks for one — the rest of the flow stays local. Disable it with `web_search = false` in config or `--no-web` on the command line.

4. **Answer and selection.** Once the model responds with `{"action": "answer", "options": [...]}`, commandai renders each option with its summary and per-argument breakdown, then presents an interactive selection prompt.

5. **Current-shell execution.** The `ai` shell function (sourced from `shell/ai.sh`) calls `command-ai --output-file <tmpfile>`. The Python tool handles all interaction on **stderr**, leaving stdout clean. If the user confirms a command, it is written to the temp file. The shell function then `eval`s the contents of that file in the **current shell**, so `cd`, `export`, and any other shell-state changes persist. The chosen command is also recorded in shell history (via `print -s` on zsh, `history -s` on bash). If you invoke `command-ai` directly instead of via the `ai` function, the command runs in a subprocess and shell-state changes do not persist.

---

## Safety

- The command is **always shown and confirmed** before anything runs. There is no auto-execution unless you pass `-y`/`--yes` explicitly.
- Each option includes a `danger` field (`low` / `medium` / `high`) set by the model. commandai also applies its own heuristic that flags patterns such as `rm -rf`, `rm -r ...*`, `dd if=`, `mkfs`, `chmod -R 777`, `curl | sh`, fork bombs, and writes to `/dev/disk` or `/dev/sd*`. Either a `high` model rating or a heuristic match triggers an extra confirmation step.
- Passing `-y`/`--yes` skips the interactive prompt **and** bypasses the extra danger confirmation. Only use it in contexts where you have already inspected the command.
- **Privacy:** when the model chooses to search, only the search query (not your files or directory listing) is sent to DuckDuckGo. Set `web_search = false` in config or pass `--no-web` for fully offline operation.

---

## Troubleshooting

**"Could not reach the model" / connection refused**

LM Studio's local server is not running or is on a different port. Open LM Studio, go to the **Developer** tab, and click **Start Server**. The default port is `1234`. If you changed it, set `AI_BASE_URL` or update `base_url` in your config. Also make sure the model is loaded — a started server with no loaded model returns empty responses.

**Commands run in a subprocess; `cd` does not persist**

The `ai` shell function is not active. Either `shell/ai.sh` has not been sourced, or you are invoking `command-ai` directly. Run `type ai` in your shell — if it says `ai not found` or `ai is /path/to/command-ai`, the function is not set up. Source it manually:

```bash
source /path/to/commandai/shell/ai.sh
```

Or re-run `./install.sh` to have it added to `~/.zshrc` automatically.

**`ai: command not found`**

Open a new terminal, or run `source ~/.zshrc`. If that does not help, check that `~/.local/bin` is on your `PATH` (the installer prints a warning if it is not):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Add that line to `~/.zshrc` to make it permanent.

**Python version too old**

commandai requires Python 3.11 or later. Check your version with `python3 --version`. On macOS you can install a newer version via [Homebrew](https://brew.sh): `brew install python@3.13`.

---

## Development

Install with dev dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the test suite (227 tests; network and UI are fully mocked):

```bash
pytest
```

Or use the project venv directly without activating:

```bash
.venv/bin/pytest
```

To see coverage:

```bash
pytest --cov=command_ai --cov-report=term-missing
```

---

## Uninstall

**If installed with pipx:**

```bash
pipx uninstall commandai
```

**If installed with a venv:**

```bash
rm -rf /path/to/commandai/.venv
rm -f ~/.local/bin/command-ai
```

Either way, remove the shell function source line from `~/.zshrc`:

```bash
# Remove the line that looks like:
# source "/path/to/commandai/shell/ai.sh"
```

Then open a new terminal or `source ~/.zshrc`.

---

## License

MIT — see [pyproject.toml](pyproject.toml).
