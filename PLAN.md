# commandai — Implementation Plan

A brief, fast CLI that turns a natural-language request into a concrete shell
command, explains it, and runs it in your current shell after you confirm.

```
ai use ffmpeg to convert all the videos in this folder from mov to mp4
```

## Goals (from the request)

1. Ask in natural language, get the exact shell command back.
2. Show a description of the command **and each argument**.
3. Contextual awareness of the current directory's file structure.
4. Ability to navigate (explore) the local filesystem before answering.
5. Talk to a local LM Studio OpenAI-compatible endpoint
   (`http://localhost:1234`), **configurable**.
6. On ambiguity, present multiple options, each with a description.
7. Short, fast invocation: `ai <free text>`.
8. Show the command before running; confirm with **arrow keys + Enter**
   (or just Enter for the default), then execute **in the current shell**.
9. Tests, full macOS install instructions, private repo.

## Key decisions

- **Language: Python 3.11+.** Best fit for a personal macOS CLI: first-class
  HTTP, filesystem, and TUI libraries; trivial install via `pipx`. (You have
  Python 3.14.)
- **LLM client:** the official `openai` SDK pointed at the local `base_url`.
  Works against LM Studio's OpenAI-compatible server unchanged.
- **Interactive selection:** `questionary` (arrow keys + Enter, sane default).
- **Pretty output:** `rich`.
- **Config:** TOML at `~/.config/command-ai/config.toml`, overridable by env
  vars (`AI_BASE_URL`, `AI_MODEL`, ...) and CLI flags. Precedence:
  CLI flag > env var > config file > built-in default.

### Running "in the current shell"

A child process cannot change its parent shell's `cwd`/env, so a plain
subprocess can't make `cd` persist. We solve this with a thin shell function
`ai()` (installed into `~/.zshrc`) that:

1. calls the Python tool, which does all interaction on **stderr** and writes
   the single chosen command to a temp file;
2. `eval`s that command in the **current** shell (so `cd`, exports, etc.
   persist) and records it in shell history.

If you skip the shell function, the console script still works — it just runs
the command in a subprocess (fine for ffmpeg, find, etc.; `cd` won't persist).

### Filesystem awareness + navigation

- The prompt always includes a compact tree of the current directory
  (depth-limited, count-capped) plus a summary of file extensions present.
- For deeper questions the model can **explore**: it may reply with
  `{"action":"explore","path":"sub/dir"}`; the tool returns that listing and
  re-asks, up to a capped number of hops. This gives real navigation without
  depending on flaky local-model native tool-calling.

### Safety

- The command is **always shown and confirmed** before running.
- Nothing auto-runs unless `--yes` is passed explicitly.
- Each option carries a `danger` rating (low/medium/high); a heuristic also
  flags obviously destructive patterns (`rm -rf`, `dd`, `mkfs`, fork bombs…)
  and requires an extra typed confirmation.

## Module layout

```
src/command_ai/
  __init__.py      version
  __main__.py      python -m command_ai
  config.py        load/merge config (defaults < file < env < flags)
  context.py       gather directory tree + extension summary + os/shell info
  llm.py           prompt building, OpenAI-compatible call, robust JSON parsing
  ui.py            rich rendering + questionary selection (all on stderr)
  executor.py      run-in-subprocess OR write-to-output-file (shell wrapper)
  cli.py           argparse, the explore loop, glue
shell/ai.sh        the `ai` shell function (zsh/bash)
tests/             pytest suite (network + UI fully mocked)
install.sh         venv/pipx install + prints the shell snippet
config.example.toml
README.md          full macOS install instructions
```

## Data contract (model output)

The model must return a single JSON object, one of:

```json
{ "action": "explore", "path": "relative/or/abs/path" }
```
```json
{ "action": "answer",
  "options": [
    { "command": "for f in *.mov; do ffmpeg -i \"$f\" \"${f%.mov}.mp4\"; done",
      "summary": "Convert every .mov in this folder to .mp4",
      "args": [ {"part": "-i \"$f\"", "explains": "input file"},
                {"part": "\"${f%.mov}.mp4\"", "explains": "output name"} ],
      "danger": "low" }
  ] }
```

Parsing is defensive: strip code fences, extract the first balanced `{...}`,
tolerate missing optional fields.

## Test plan

- `config`: defaults, file load, env override, precedence order.
- `context`: depth/count caps, hidden-file handling, extension summary.
- `llm`: prompt includes context+query; JSON parsing of clean/fenced/noisy
  responses; explore vs answer branching. (HTTP client mocked.)
- `executor`: output-file mode writes exactly the command; subprocess mode
  builds the right shell invocation (subprocess mocked); danger heuristic.
- `ui`: option→command mapping, cancel path (questionary mocked).
- `cli`: end-to-end happy path and cancel path (llm + ui mocked).

## Build order

1. Scaffold + plan (this file).
2. Core package (single-author for coherent interfaces).
3. Fan out **in parallel** to subagents: test suite, docs/install, security
   review.
4. Create venv, install, run tests, fix.
5. Commit. Provide commands to create the private GitHub repo.
