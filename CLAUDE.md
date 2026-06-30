# commandai — project notes

Natural-language → shell-command CLI powered by a local/hosted OpenAI-compatible
LLM. The model suggests a command; the user reviews and runs it in their current
shell (via the `ai` shell function in `shell/ai.sh` / `shell/ai.ps1`).

Core modules live in `src/command_ai/`: `cli` (entry point + explore/answer/run
loop), `config`, `context` (directory snapshot + shell history), `llm` (prompt
build + OpenAI-compatible call + parsing), `executor` (run the chosen command +
danger heuristic), `search`, `ui`, `credentials`, `providers`.

## Before pushing: keep docs in sync

When a change touches **CLI flags** (`build_parser` in `cli.py`), **environment
variables** (`_ENV_KEYS` in `config.py`), or **config keys** (`Config` fields),
update `README.md` and `config.example.toml` in the **same** change.

This is enforced mechanically so it can't drift:
- `tests/test_docs.py` fails if any flag / `AI_*` env var / `Config` field is
  undocumented. It runs in the suite and in CI (`.github/workflows/ci.yml`).
- `.githooks/pre-push` runs the suite before a push completes (activated via
  `git config core.hooksPath .githooks`, which the installers set up).

The test only checks that names are *documented*; keep the surrounding prose and
examples accurate yourself. Also update the relevant **Safety** / behavior notes
in `README.md` when you change what the tool actually does.

## Tests

`.venv/bin/pytest` runs everything (network + UI mocked). `tests/test_integration.py`
spawns the real shell where available; `tests/test_security.py` covers the
hardening in `SECURITY_AUDIT.md`.
