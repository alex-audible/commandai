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
- **Shell-context aware** — sees the previous command's exit code and your recent command history, so you can ask it to fix or follow up on what just ran — e.g. `ai fix that` after a failed `git push`. It never reads command output, only the command lines plus the exit status, and it can be turned off.
- **Runs in your current shell** — `cd`, `export`, and other shell-state changes persist, because the chosen command is `eval`'d by the `ai` shell function rather than a child process.
- **Safety gates** — the command is always shown before execution, and destructive patterns (`rm -rf`, `dd`, `mkfs`, `curl | sh`, `find … -exec rm`, anything piped into a shell, …) require typing `yes` to confirm. This is best-effort assistance, **not** a security boundary: the heuristic is a denylist and the model's own `danger` rating can be wrong — *you* reading the command is the real safeguard.
- **Local-first** — with the default local provider, inference runs through LM Studio on your machine and nothing leaves your laptop. With a **hosted** provider (e.g. OpenRouter) the prompt — including the directory listing, file names, and your recent shell history — is sent to that provider; see [Safety](#safety).
- **Multiple providers** — works with a local OpenAI-compatible server (LM Studio or Ollama, the default) or hosted [OpenRouter](https://openrouter.ai). Pick your provider once in settings, then just run `ai ...` with no flags. API keys are stored securely in your OS keychain.
- **Fully configurable** — endpoint, model, temperature, context depth, and more are all adjustable via config file, environment variable, or CLI flag.

---

## Requirements

- **macOS** (primary target), **Linux**, **WSL**, or **Windows** (PowerShell) — see [Platform support](#platform-support)
- Python 3.11 or later
- [LM Studio](https://lmstudio.ai) running a local server (see setup below)
- `pipx` (recommended) or a plain Python virtual environment
- Internet access only for the optional [web search](#web-search) step and for hosted providers like OpenRouter; the default local provider runs entirely on your machine. Web search uses the [`ddgs`](https://pypi.org/project/ddgs/) package, and secure API-key storage uses [`keyring`](https://pypi.org/project/keyring/); both are installed automatically as dependencies.

### Platform support

commandai is designed and tuned for **macOS**, and also runs on Linux, WSL, and
native Windows. The tool tells the model which OS/shell you're on, so it
generates commands appropriate to your platform (zsh/bash on macOS & Linux,
PowerShell or cmd on Windows).

| Platform | Install | Shell integration (`ai` command) |
|---|---|---|
| **macOS** (primary) | `./install.sh` | `shell/ai.sh` → `~/.zshrc` |
| **Linux** | `./install.sh` | `shell/ai.sh` → `~/.bashrc`/`~/.zshrc` (auto-detected) |
| **WSL** | `./install.sh` (inside WSL) | same as Linux — the recommended way to run on Windows |
| **Windows** (native PowerShell) | `powershell -ExecutionPolicy Bypass -File .\install.ps1` | `shell/ai.ps1` → `$PROFILE` |

Notes:
- On Linux/WSL the installer auto-detects bash vs zsh and wires the matching rc file.
- On native Windows, `install.ps1` adds an `ai` function to your PowerShell `$PROFILE` that runs the chosen command in the current session (so `cd`/`$env:` persist). For the most faithful experience on Windows, use **WSL** with `install.sh`.
- The destructive-command safety check understands both POSIX (`rm -rf`, `dd`, …) and Windows/PowerShell (`Remove-Item -Recurse`, `del /s`, `format`, …) patterns.

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

> 📚 See **[EXAMPLES.md](EXAMPLES.md)** for a full gallery of things you can ask `ai`,
> grouped by task (files, media/ffmpeg, git, Homebrew, system, networking, and more).

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

# Follow up on a command that just failed (uses shell context)
git push                       # ! [rejected] — remote has changes you don't have
ai fix that                    # suggests: git pull --rebase && git push

# Something ambiguous — yields multiple options
ai back up the database
```

### The selection UI

When the model returns its suggestion(s), you navigate with the arrow keys and press **Enter** to run the highlighted option. If there is only one option, pressing Enter immediately confirms it. Press **Ctrl-C** or select **Cancel** to quit without running anything.

Destructive commands (those matching known-dangerous patterns like `rm -rf`, or rated `danger: high` by the model) show an additional prompt that requires you to type `yes` in full before anything runs — a single keystroke will not confirm them.

### Useful flags

| Flag | Description |
|---|---|
| `-n`, `--dry-run` | Show the suggested command(s) without running or writing anything. |
| `-y`, `--yes` | Skip the interactive prompt and run the first option automatically. Also bypasses the danger confirmation, so use carefully. |
| `--no-context` | Do not send directory context to the model. Useful when the current folder is irrelevant or very large. |
| `--no-web` | Disable web search for this invocation, even if it is enabled in config. |
| `--no-shell-context` | Disable shell-context (recent history + previous exit code) for this invocation. |
| `--print-config` | Print the resolved configuration (endpoint, model, all settings) and exit. Useful for debugging. |
| `--provider {local,openrouter}` | Optional per-run override of the provider preset (sets endpoint/model). Normally set once in [settings](#providers). |
| `--set-api-key` | Prompt for and securely store the API key for the chosen provider, then exit. |
| `--model MODEL` | Use a different model for this invocation. |
| `--base-url URL` | Use a different endpoint for this invocation. |
| `--api-key KEY` | Use a specific API key for this invocation (overrides stored/config keys). **Visible in the process list (`ps`) while running** — prefer `AI_API_KEY` or `--set-api-key`. |
| `--insecure` | Permit sending the API key/prompt to a **non-loopback `http://`** endpoint in cleartext. Off by default (loopback `http://` and any `https://` are always allowed). |
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

# Provider preset: "local" (LM Studio / Ollama, default) or "openrouter".
# Set everything you want HERE so you never have to pass flags — once configured,
# you just type:  ai <request>
provider = "local"

# Endpoint / model — default from the provider above; set them to override.
# base_url = "http://localhost:1234/v1"
# model    = "gemma-4-26b-a4b"
# api_key  = "lm-studio"   # local ignores this value

# To use OpenRouter entirely from settings (no flags), set:
#   provider = "openrouter"
#   model    = "anthropic/claude-3.5-sonnet"   # any OpenRouter model id
# then store your key once with `ai --provider openrouter --set-api-key`
# (or put `api_key = "sk-or-v1-..."` here in plaintext).

# Generation
temperature       = 0.2
max_tokens        = 1024
timeout           = 120.0   # seconds to wait for a response
max_parse_retries = 2       # re-ask the model this many times if it returns invalid JSON

# Security
allow_insecure_http = false # allow a non-loopback http:// endpoint (cleartext key); prefer https://

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

# Shell context (recent history + previous exit code; never command output)
[shell]
shell_context = true     # set false to never send shell history/exit code
max_history   = 15       # how many recent command lines to include
```

### Providers

A *provider* is a preset for an OpenAI-compatible endpoint. Selecting one sets a sensible `base_url` and default model so you don't have to remember URLs.

| Provider | API key | Default `base_url` | Default model |
|---|---|---|---|
| `local` (default) | not needed | `http://localhost:1234/v1` | `gemma-4-26b-a4b` |
| `openrouter` | required | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` |

**Settings-first setup (recommended).** Configure your provider once and then just type `ai <request>` with no flags. To use OpenRouter from settings, put this in `~/.config/command-ai/config.toml`:

```toml
provider = "openrouter"
model    = "anthropic/claude-3.5-sonnet"   # any OpenRouter model id
```

Then provide your API key **once**, either:

- **(a) the secure way** — store it in your OS keychain:

  ```bash
  ai --provider openrouter --set-api-key
  ```

- **(b) plaintext in the config file** — add `api_key = "sk-or-v1-..."` to `config.toml`.

After that, day-to-day usage is simply:

```bash
ai <request>
```

**How the preset fills things in.** Selecting a provider auto-sets `base_url` and `model`; you can override either in settings (a `base_url` or `model` you set explicitly is kept). When `--provider` is given on the command line it is authoritative for the endpoint — it applies its preset over a `base_url` pinned in the config file. A config-file `base_url` is otherwise respected, so custom local servers (Ollama, llama.cpp, a non-default port) keep working.

**API key resolution.** Keys are resolved in this order:

```
--api-key flag / AI_API_KEY env  >  a real api_key in the config file  >  stored key (keychain or fallback file)  >  interactive prompt
```

Keys are stored in the OS keychain via the [`keyring`](https://pypi.org/project/keyring/) package (macOS Keychain, Windows Credential Locker, Linux Secret Service). If no keychain backend is available, they fall back to `~/.config/command-ai/credentials.json` with `0600` permissions. The key is masked in `ai --print-config` and never logged.

Use `ai --set-api-key` to store a key for the current provider (the prompt is hidden) and exit. If you run an OpenRouter request with no key configured, commandai prompts for it once and offers to save it for next time.

### Environment variables

Every setting can be overridden by an environment variable without touching the config file:

| Variable | Config key | Type | Default |
|---|---|---|---|
| `AI_PROVIDER` | `provider` | string | `local` |
| `AI_BASE_URL` | `base_url` | string | `http://localhost:1234/v1` |
| `AI_MODEL` | `model` | string | `gemma-4-26b-a4b` |
| `AI_API_KEY` | `api_key` | string | `lm-studio` |
| `AI_TEMPERATURE` | `temperature` | float | `0.2` |
| `AI_MAX_TOKENS` | `max_tokens` | int | `1024` |
| `AI_TIMEOUT` | `timeout` | float | `120.0` |
| `AI_ALLOW_INSECURE_HTTP` | `allow_insecure_http` | bool (`1`/`true`/`yes`/`on`) | `false` |
| `AI_MAX_PARSE_RETRIES` | `max_parse_retries` | int | `2` |
| `AI_MAX_FILES` | `max_files` | int | `200` |
| `AI_MAX_DEPTH` | `max_depth` | int | `2` |
| `AI_INCLUDE_HIDDEN` | `include_hidden` | bool (`1`/`true`/`yes`/`on`) | `false` |
| `AI_MAX_EXPLORATIONS` | `max_explorations` | int | `4` |
| `AI_WEB_SEARCH` | `web_search` | bool (`1`/`true`/`yes`/`on`) | `true` |
| `AI_MAX_SEARCHES` | `max_searches` | int | `3` |
| `AI_SEARCH_RESULTS` | `search_results` | int | `5` |
| `AI_SEARCH_TIMEOUT` | `search_timeout` | float | `15.0` |
| `AI_SHELL_CONTEXT` | `shell_context` | bool (`1`/`true`/`yes`/`on`) | `true` |
| `AI_MAX_HISTORY` | `max_history` | int | `15` |

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

2. **Shell context.** When enabled (the default), the `ai` shell function captures `$?` (the exit status of the command you ran immediately before `ai`, recorded as its very first line so nothing else can reset it) plus your recent command lines via zsh `fc` / bash `history`. These are written to a temp file passed as `--shell-context-file`, and the tool folds up to `max_history` lines of it into the model's prompt — so `ai fix that` knows what just ran and whether it failed. The current `ai ...` invocation is excluded from the captured history. Only the command lines and the exit status are sent, never command output. Disable it with `shell_context = false` in config or `--no-shell-context` on the command line.

3. **Explore loop.** The model may respond with an explore request (`{"action": "explore", "path": "some/subdir"}`) instead of a final answer. commandai resolves that path, lists it, appends the result to the conversation, and calls the model again. This repeats up to `max_explorations` times, giving the model genuine filesystem navigation without relying on flaky native tool-calling.

4. <a id="web-search"></a>**Web search.** When web search is enabled (the default), the model may instead respond with a search request (`{"action": "search", "query": "..."}`) when it needs current or external information — for example, the exact Homebrew cask name for a described tool. commandai runs a DuckDuckGo text search (via the `ddgs` package, no API key), feeds the rendered results back into the conversation, and calls the model again; the model then produces the final command. This is capped at `max_searches` searches per request. Searches only happen when the model asks for one — the rest of the flow stays local. Disable it with `web_search = false` in config or `--no-web` on the command line.

5. **Answer and selection.** Once the model responds with `{"action": "answer", "options": [...]}`, commandai renders each option with its summary and per-argument breakdown, then presents an interactive selection prompt.

6. **Current-shell execution.** The `ai` shell function (sourced from `shell/ai.sh`) calls `command-ai --output-file <tmpfile>`. The Python tool handles all interaction on **stderr**, leaving stdout clean. If the user confirms a command, it is written to the temp file. The shell function then `eval`s the contents of that file in the **current shell**, so `cd`, `export`, and any other shell-state changes persist. The chosen command is also recorded in shell history (via `print -s` on zsh, `history -s` on bash). If you invoke `command-ai` directly instead of via the `ai` function, the command runs in a subprocess and shell-state changes do not persist.

---

> **The real safety boundary is you reading the command before you run it.** The
> checks below are best-effort assistance, not guarantees. Because the tool asks
> a model to produce a shell command and then runs it, treat every suggestion as
> untrusted until you've read it.

- The command is **always shown and confirmed** before anything runs. There is no auto-execution unless you pass `-y`/`--yes` explicitly.
- **Destructive-command heuristic.** commandai applies its own denylist independently of the model's self-reported `danger` rating (so a mis-rated command is still caught), flagging patterns such as `rm -rf`, `rm -r …*`, `dd if=`, `mkfs`, `chmod -R 777`, `curl | sh`, `find … -exec rm`, anything piped into a shell, destructive `python -c`, disk/partition tools, and writes to block devices. A match (or a `high` model rating) triggers an extra confirmation where you must **type `yes` in full** — a single keystroke won't do it. This is a denylist and can be evaded; it is not a sandbox.
- Passing `-y`/`--yes` skips the interactive prompt **and** the danger confirmation. Only use it when you have already inspected the command.
- **Exploration is confined to the working directory.** The model may ask to look inside subdirectories before answering, but requests for paths outside the current directory (e.g. `~/.ssh`, `~/.aws`, `/etc`) are refused, so a misbehaving or prompt-injected model can't enumerate sensitive directories and leak the listing to the provider.
- **Cleartext-endpoint protection.** commandai refuses to send your API key and prompt to a non-loopback `http://` endpoint (which would transmit them unencrypted). Use `https://`, or override with `--insecure` / `allow_insecure_http = true`. Loopback `http://` (the default local server) is always allowed.
- **Untrusted context.** File names, directory contents, and web-search snippets are treated as data, not instructions: control characters are stripped and the model is told never to follow instructions embedded in them (a defense against prompt injection via a crafted filename or poisoned web result).
- **Key handling.** Keys live in the OS keychain (preferred) or a `0600` `credentials.json` fallback, are masked in `--print-config`, and are never logged. `--api-key` is visible in the process list (`ps`) while the command runs — prefer `AI_API_KEY` or `--set-api-key`.
- **Privacy — web search:** when the model chooses to search, only the search query (not your files or directory listing) is sent to DuckDuckGo. Set `web_search = false` or pass `--no-web` for fully offline operation.
- **Privacy — shell context:** recent command *lines* and the previous exit code are sent (never command output). With a **hosted** provider these leave your machine, so commandai best-effort **redacts** obvious inline secrets (API keys, `Authorization:` headers, `KEY=…` assignments, `mysql -p…`) before sending. Redaction is heuristic — disable shell context entirely with `--no-shell-context` or `shell_context = false` if in doubt. The current directory path and file names are also part of the prompt sent to a hosted provider.

For the full security review and the rationale behind these controls, see [SECURITY_AUDIT.md](SECURITY_AUDIT.md).

---

## Troubleshooting

**"Could not reach the model" / connection refused**

LM Studio's local server is not running or is on a different port. Open LM Studio, go to the **Developer** tab, and click **Start Server**. The default port is `1234`. If you changed it, set `AI_BASE_URL` or update `base_url` in your config. Also make sure the model is loaded — a started server with no loaded model returns empty responses.

**"Could not parse JSON from the model response" / malformed output**

The model returned something that was not valid JSON. commandai already hardens its parsing (stripping code fences, extracting the first balanced object) and automatically re-asks the model when parsing fails — up to `max_parse_retries` extra times (default 2). The error message also includes a snippet of what the model actually said, which helps diagnose the problem. Small or heavily-quantized local models tend to emit invalid JSON more often; you can make them more reliable by increasing `max_parse_retries` (config or `AI_MAX_PARSE_RETRIES`) and/or lowering `temperature`.

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

Run the test suite (network and UI are fully mocked; the cross-platform shell
tests in `tests/test_integration.py` spawn the real shell where present):

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

### Keeping docs in sync

Before pushing, make sure the README and `config.example.toml` reflect any
changes to CLI flags, environment variables, or config keys. This is enforced
two ways so it can't silently drift:

- **`tests/test_docs.py`** fails the build if a CLI flag, `AI_*` env var, or
  `Config` field isn't documented. It runs in the test suite (and therefore in
  [CI](.github/workflows/ci.yml)) on every push.
- **A committed pre-push hook** (`.githooks/pre-push`) runs the suite locally
  before a push completes. Activate it once per clone with:

  ```bash
  git config core.hooksPath .githooks
  ```

  `install.sh` / `install.ps1` set this for you automatically. (Git requires the
  pointer to be set per clone — a repository cannot enable its own hooks on
  clone, by design.)

When you change behavior, update the relevant prose/examples too — the test
checks that names are *documented*, not that the description is *correct*.

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
