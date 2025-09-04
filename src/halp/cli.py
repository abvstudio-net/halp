#!/usr/bin/env python3
"""
halp - AI assistance for the command line.

This CLI uses a simple .env file at ~/.halp.env for configuration with keys:
- BASE_URL: OpenAI-compatible base URL (e.g., https://api.openai.com)
- API_KEY: API key for the provider
- DEFAULT_MODEL: Default model to use

You can override these at runtime via flags, and list available models from an
OpenAI-compatible endpoint using --list_models.
"""

import argparse
import sys
import json
import os
import platform
import getpass

from . import __version__
from .logging_utils import setup_logging as setup_logging_new
from .config import ensure_config as ensure_config_new
from .api import list_models_openai as list_models_openai_new
from .chat import chat_loop as chat_loop_new
from .chat import agent_loop as agent_loop_new
from .tools import get_default_toolset

def main(argv=None) -> int:  # new modular entrypoint (overrides legacy main above)
    parser = argparse.ArgumentParser(
        prog="halp",
        description=(__doc__ or "AI assistance for the command line.").strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # General flags
    parser.add_argument("--version", "-v", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--env", action="store_true", help="Print the loaded environment configuration and exit")
    parser.add_argument("--verbose", action="store_true", help="Use a normal, not-terse assistant system prompt")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging to console")
    parser.add_argument("--init", action="store_true", help="Run interactive setup wizard, even if ~/.halp.env exists")
    parser.add_argument(
        "--quick",
        "-q",
        action="store_true",
        help="Run a single agent episode (tools allowed) and exit after the final reply",
    )

    # Config overrides
    parser.add_argument("-u", "--base_url", help="Override BASE_URL (ignore ~/.halp.env)")
    parser.add_argument("-k", "--api_key", help="Override API_KEY (ignore ~/.halp.env)")
    parser.add_argument("-m", "--model", help="Specify a model to use (overrides DEFAULT_MODEL)")

    # Actions
    parser.add_argument("-l", "--list_models", action="store_true", help="List available models via /v1/models")

    # Agent mode (default)
    parser.add_argument("--max_steps", type=int, default=10, help="Max agent steps before stopping")
    parser.add_argument(
        "--unsafe_exec",
        action="store_true",
        help="Auto-execute shell commands without confirmation (DANGEROUS)",
    )

    # Prompt to send to the model (positional). If omitted, halp prints status or reads from stdin when piped.
    parser.add_argument("prompt", nargs="*", help="Prompt to send to the model (use quotes)")

    args = parser.parse_args(argv)

    logger = setup_logging_new(enabled=args.debug)

    overrides = {
        "BASE_URL": args.base_url,
        "API_KEY": args.api_key,
        "DEFAULT_MODEL": args.model,
    }
    try:
        config = ensure_config_new(overrides=overrides, force_init=args.init, logger=logger)
    except KeyboardInterrupt:
        if logger:
            logger.debug("Interrupted by user (Ctrl-C) during setup.")
        return 130

    # After ensure_config, apply model override explicitly again to be safe
    if args.model:
        config["DEFAULT_MODEL"] = args.model

    if args.env:
        print(json.dumps(config, indent=2))
        return 0

    if args.list_models:
        try:
            base_url = config.get("BASE_URL", "")
            api_key = config.get("API_KEY", "")
            if not base_url:
                print("Error: BASE_URL is required to list models. Provide via ~/.halp.env or --base_url.", file=sys.stderr)
                return 2
            models = list_models_openai_new(base_url=base_url, api_key=api_key, logger=logger)
            if not models:
                print("No models found or request failed.", file=sys.stderr)
                return 1
            for m in models:
                print(m)
            return 0
        except KeyboardInterrupt:
            if logger:
                logger.debug("Interrupted by user (Ctrl-C) while listing models.")
            return 130

    # Determine initial prompt from args or stdin; if none, start interactive and ask
    prompt_text = None
    unsafe_exec_flag = args.unsafe_exec
    if args.prompt:
        prompt_text = " ".join(args.prompt).strip()
        # "yolo" directive at start enables auto-execution and is stripped from the prompt
        if prompt_text.lower().startswith("yolo"):
            parts = prompt_text.split(None, 1)
            if parts and parts[0].lower() == "yolo":
                unsafe_exec_flag = True
                prompt_text = parts[1] if len(parts) > 1 else ""
    elif not sys.stdin.isatty():
        try:
            prompt_text = sys.stdin.read().strip()
        except KeyboardInterrupt:
            # Graceful exit if Ctrl-C while reading from piped stdin
            return 130
        except Exception:
            prompt_text = None
        # Detect leading "yolo" directive in piped input
        if prompt_text and prompt_text.lower().startswith("yolo"):
            parts = prompt_text.split(None, 1)
            if parts and parts[0].lower() == "yolo":
                unsafe_exec_flag = True
                prompt_text = parts[1] if len(parts) > 1 else ""

    base_url = config.get("BASE_URL", "")
    api_key = config.get("API_KEY", "")
    model = config.get("DEFAULT_MODEL", "")
    if not base_url or not model:
        print("Error: BASE_URL and DEFAULT_MODEL are required. Set them in ~/.halp.env or via CLI overrides.", file=sys.stderr)
        return 2

    # Select system prompt based on verbosity (default: terse)
    if args.verbose:
        system_prompt = (
            "You are HALP, a helpful command-line assistant. Be helpful but concise. "
            "Use tools when necessary."
        )
    else:
        system_prompt = "You are HALP, a helpful command-line assistant. Be terse and concise."

    # Build agent system prompt with environment grounding and tools
    tools = get_default_toolset(unsafe_exec=unsafe_exec_flag)
    env_overview = (
        f"OS={platform.system()} {platform.release()} ({platform.machine()}), "
        f"Python={platform.python_version()}, Shell={os.environ.get('SHELL', '')}, "
        f"CWD={os.getcwd()}"
    )
    # User and directory context
    try:
        user_name = getpass.getuser()
    except Exception:
        user_name = os.environ.get("USER", "unknown")
    home_dir = os.path.expanduser("~")
    cwd = os.getcwd()
    # Current directory listing (limit to 30 entries to keep prompt bounded)
    try:
        entries = []
        for name in sorted(os.listdir(cwd))[:30]:
            p = os.path.join(cwd, name)
            suffix = "/" if os.path.isdir(p) else ""
            entries.append(name + suffix)
        cwd_list = "  ".join(entries) if entries else "<empty>"
    except Exception:
        cwd_list = "<error listing directory>"
    # Shell history tail (prefer HISTFILE, else ~/.zsh_history or ~/.bash_history)
    hist_candidates = []
    if os.environ.get("HISTFILE"):
        hist_candidates.append(os.environ.get("HISTFILE"))
    hist_candidates += [
        os.path.join(home_dir, ".zsh_history"),
        os.path.join(home_dir, ".bash_history"),
    ]
    history_file = None
    for hp in hist_candidates:
        try:
            if hp and os.path.isfile(hp):
                history_file = hp
                break
        except Exception:
            continue
    history_tail = []
    if history_file:
        try:
            with open(history_file, "r", encoding="utf-8", errors="ignore") as hf:
                lines = hf.read().splitlines()
                # zsh may include metadata like ": 1697003895:0;cmd"; keep raw for transparency
                history_tail = lines[-50:]
        except Exception:
            history_tail = []
    history_block = ("\n".join(history_tail)) if history_tail else "<no history available>"
    tool_desc = "\n".join([f"- {t.name}: {t.description}" for t in tools.values()])
    agent_chunks = []
    agent_chunks.append(
        "You are HALP Agent. You can decide to think and act using tools to help the user.\n"
    )
    agent_chunks.append(
        "When you need to act, emit ONLY a JSON object with keys 'tool' and 'input', e.g.\n"
        '{"tool": "shell", "input": "ls -la"}.\n'
    )
    agent_chunks.append(
        "Never include extra commentary around tool JSON. No code fences. No prose.\n"
    )
    agent_chunks.append(
        "After executing a tool, you will receive an 'Observation'. Use it to decide the next step.\n"
    )
    agent_chunks.append(
        "If you have a final answer for the user, emit ONLY {\"final\": \"...\"}. No extra text.\n"
    )
    agent_chunks.append(
        "Policy: NEVER use 'sudo' in any tool call. If elevated privileges are needed, do NOT call tools; instead, emit ONLY a final answer that explains the exact sudo command the user can run manually.\n"
    )
    agent_chunks.append(
        "Policy: NEVER install or upgrade software in any tool call. Do not invoke package managers or installers (e.g., apt, apt-get, yum, dnf, pacman, zypper, apk, brew, port, choco, scoop) or language/runtime installers (e.g., pip/pip3 install, conda/mamba install, npm/yarn/pnpm, gem, cargo, go install). Avoid shell-install patterns (e.g., curl | bash, wget | sh, bash <(curl ...)). If installation appears required, do NOT call tools; instead, emit ONLY a final answer describing the exact commands the user can run manually.\n"
    )
    agent_chunks.append(
        "Do not modify package repositories or system configuration (e.g., add-apt-repository, editing sources, apt-key/rpm --import).\n"
    )
    agent_chunks.append(
        "If your previous reply had malformed tool JSON or a blocked command (e.g., contained 'sudo'), re-emit a corrected tool JSON without sudo, or provide a final answer. Do not include anything besides the JSON object.\n"
    )
    agent_chunks.append(
        "Tool calls that execute CLI commands will be presented for user confirmation unless --unsafe_exec is set, in which case they auto-execute.\n"
    )
    agent_chunks.append(
        "Avoid destructive commands. Prefer read-only queries unless explicitly requested. Even with auto-execution, 'sudo' remains disallowed.\n"
    )
    agent_chunks.append(
        "The user may also type 'yolo' as the first word of their prompt to enable auto-execution for this session. The word 'yolo' is a directive and should be stripped from the task.\n"
    )
    agent_chunks.append(f"\nEnvironment:\n{env_overview}\n")
    agent_chunks.append(f"User: {user_name} (home={home_dir})\n")
    agent_chunks.append(f"\nCWD listing (max 200):\n{cwd_list}\n")
    if history_file:
        agent_chunks.append(
            f"\nShell history (last 50 lines from {history_file}):\n{history_block}\n"
        )
    else:
        agent_chunks.append("\nShell history: <none found>\n")
    agent_chunks.append(f"\nTools available:\n{tool_desc}\n")
    if not args.verbose:
        agent_chunks.append("Be terse and concise.\n")
    agent_system_prompt = "".join(agent_chunks)

    # Start quick (single-episode agent) or full agent loop (default)
    try:
        if args.quick:
            return agent_loop_new(
                base_url=base_url,
                api_key=api_key,
                model=model,
                initial_user_prompt=prompt_text,
                system_prompt=agent_system_prompt,
                tools=tools,
                max_steps=args.max_steps,
                logger=logger,
                continue_conversation=False,
            )
        else:
            return agent_loop_new(
                base_url=base_url,
                api_key=api_key,
                model=model,
                initial_user_prompt=prompt_text,
                system_prompt=agent_system_prompt,
                tools=tools,
                max_steps=args.max_steps,
                logger=logger,
            )
    except KeyboardInterrupt:
        # Ensure clean exit if Ctrl-C bubbles up for any reason
        try:
            reset = "\033[0m"
            print(f"{reset}")
        except Exception:
            pass
        if logger:
            logger.debug("Interrupted by user (Ctrl-C).")
        return 130

if __name__ == "__main__":
    sys.exit(main())
