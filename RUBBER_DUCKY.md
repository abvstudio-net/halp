# RUBBER_DUCKY: halp Developer Onboarding

This document orients a new contributor to the halp CLI: how it works, how it’s organized, and where to extend or clean up. Read top-to-bottom in one sitting.

## What halp is
- __Purpose__: AI assistant for the command line that talks to an OpenAI-compatible API and supports an Agent mode to run tools (e.g., shell commands) with safety controls.
- __Install/Run__: packaged via `pyproject.toml` with console script `halp = halp.cli:main`.

## High-level execution flow
1. __Entry__: `halp.cli:main()` parses CLI flags.
2. __Config__: Loads `~/.halp.env` via `halp.config.ensure_config()` and applies CLI overrides.
3. __Mode__:
   - Chat mode (default): `halp.chat.chat_loop()` streams model output to the terminal.
   - Agent mode (`--agent`): `halp.chat.agent_loop()` runs a ReACT-style loop with JSON tool-calls.
4. __HTTP__: Model interaction over OpenAI-compatible endpoints in `halp.api`.
5. __Tools__: Agent executes actions via registry from `halp.tools` (currently `shell`).

## Repository layout
- `pyproject.toml` — package metadata, entry point
- `src/halp/`
  - `cli.py` — CLI entrypoint and argument parsing
  - `chat.py` — chat loop and agent loop
  - `api.py` — HTTP helpers for `/v1/models` and `/v1/chat/completions` (stream)
  - `config.py` — `.halp.env` read/write, interactive setup
  - `logging_utils.py` — colored logging and helpers
  - `tools.py` — `Tool` base, `ShellTool`, `get_default_toolset()`
  - `ui.py` — TTY-safe `read_line_interactive()` for prompts
  - `VERSION.py`, `__init__.py` — version export

## Key modules and responsibilities
- `halp.cli.main()`
  - Flags: `--env`, `--verbose`, `--debug`, `--init`, `--yolo`, overrides (`--base_url`, `--api_key`, `--model`), actions (`-l/--list_models`), __agent flags__ (`--agent`, `--max_steps`, `--dry_run`, `--unsafe_exec`).
  - Flow: ensure config → optional list models → compute prompt (args/stdin) → choose chat or agent loop.
- `halp.chat.chat_loop()`
  - Maintains `messages` and streams assistant tokens (SSE) with green color.
  - Returns 0 on success, 130 on Ctrl-C, 1 on request failure.
- `halp.chat.agent_loop()`
  - ReACT skeleton with step limit (`max_steps`).
  - Expects the model to emit JSON tool calls or a final object, e.g.:
    - Tool: `{ "tool": "shell", "input": "ls -la" }`
    - Final: `{ "final": "…your answer…" }`
  - Parses JSON from ```json code fences or first `{...}` block.
  - Executes the tool from a registry and appends an `Observation` back to the transcript:
    - Assistant: original reply (for traceability)
    - User: `Observation:\n{"tool": "shell", "result": { ... }}`
- `halp.api`
  - `list_models_openai()` — GET models list.
  - `chat_completion_openai_stream()` — POST to chat completions and yield SSE chunks.
- `halp.tools`
  - `Tool` base class: `run(user_input: str) -> dict` returning `{ok, returncode, stdout, stderr}`.
  - `ShellTool`
    - Safety: regex blocklist (e.g., `rm`, `sudo`, package managers, redirections, etc.).
    - `--dry_run`: returns a simulated result.
    - `--unsafe_exec`: bypasses blocklist with caution.
  - `get_default_toolset(dry_run, unsafe_exec)` returns `{ "shell": ShellTool(...) }`.
- `halp.config`
  - `.halp.env` keys: `BASE_URL`, `API_KEY`, `DEFAULT_MODEL`.
  - Interactive setup supports defaults from `HALP_BASE_URL` and `HALP_DEFAULT_MODEL` env vars.
- `halp.logging_utils`
  - `setup_logging(debug)` sets up colored console logs (DEBUG → red).
- `halp.ui`
  - `read_line_interactive()` uses TTY when stdin is not a TTY, with colorized prompts and safe resets.

## CLI Quickstart
- Help: `halp -h`
- First-time config: `halp --init`
- Print config: `halp --env`  (Note: README currently shows `--print-config`; see Cleanup)
- List models: `halp -l`
- One-off model override: `halp -m <model>`
- Chat mode interactive: `halp`
- Chat mode one reply: `halp -o "Explain pipes in bash"`
- Agent mode (safe): `halp --agent --dry_run "List files in this directory"`
- Agent mode (dangerous; opt-in): `halp --agent --unsafe_exec "Remove temp files"`

## Agent JSON protocols (what the model should emit)
- __Tool call__
  ```json
  { "tool": "shell", "input": "ls -la" }
  ```
- __Final answer__
  ```json
  { "final": "Your concise answer." }
  ```
- The loop returns when a final object is seen, or when `max_steps` is reached.

## Safety model
- Default: cautious. The shell is blocked when inputs match a safety regex.
- `--dry_run`: no commands run; output explains what would have run.
- `--unsafe_exec`: explicitly allow dangerous commands — users must opt in.

## Extending halp
- __Add a new tool__
  - Create a new subclass of `Tool` in `tools.py` with a unique `name`.
  - Implement `run(user_input: str) -> dict`.
  - Register it in `get_default_toolset()` (or introduce a plugin registry).
  - Update the agent prompt to document the new tool name and its expected input format.

## Testing locally
- Ensure env: `~/.halp.env` with `BASE_URL`, `API_KEY`, `DEFAULT_MODEL`.
- Connectivity: `halp -l` should print models.
- Chat smoke test: `echo "hello" | halp -o`
- Agent dry-run: `halp --agent --dry_run -o "What’s in this directory?"`

## Known gaps / cleanup opportunities
- __README flag drift__: README uses `--print-config`; CLI flag is `--env`. Align docs or add an alias.
- __SSE dependency__: `chat_completion_openai_stream()` assumes streaming support. Some providers differ; consider fallback non-streaming path on error.
- __Agent brittleness__: relies on strict JSON emission. Consider structured outputs or tool schema few-shot examples in the system prompt.
- __ShellTool blocklist__: expand/maintain; consider an allowlist mode, path sandboxing, or `cwd` constraints.
- __Error surfaces__: chat loop prints generic failure; propagate brief reason from HTTP layer when safe.
- __Observations format__: currently a simple JSON blob in text; consider a dedicated role or metadata channel when supported.

## Glossary of important symbols
- `chat_loop(base_url, api_key, model, initial_user_prompt, system_prompt, once, logger)`
- `agent_loop(base_url, api_key, model, initial_user_prompt, system_prompt, tools, max_steps, logger)`
- `get_default_toolset(dry_run, unsafe_exec)` → `{ name: Tool }`
- `chat_completion_openai_stream(base_url, api_key, model, messages, ...)` → yields text chunks

— End —
