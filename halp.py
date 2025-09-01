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
import os
import sys
import json
from pathlib import Path
import getpass
import logging
import urllib.request
import urllib.error
from typing import Optional, List

ENV_FILENAME = ".halp.env"
ENV_PATH = Path.home() / ENV_FILENAME
LOG_PATH = Path.home() / "halp.log"

# ===== Colored logging helpers =====
# ANSI color indices
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

def set_color(color: int) -> str:
    return f"\033[1;3{color}m"

LOG_COLORS = {
    logging.DEBUG: set_color(BLUE),
    logging.INFO: set_color(GREEN),
    logging.WARNING: set_color(YELLOW),
    logging.ERROR: set_color(RED),
    logging.CRITICAL: set_color(MAGENTA),
}

class ColoredFormatter(logging.Formatter):
    def format(self, record):
        level_color = LOG_COLORS.get(record.levelno, "")
        record.levelname = f"{level_color}{record.levelname}\033[0m"
        return super().format(record)

def parse_env_file(path: Path) -> dict:
    """Parse a simple KEY=VALUE .env file into a dict.

    Lines starting with '#' or blank lines are ignored.
    Quotes around values are stripped.
    """
    config = {}
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                config[key] = val
    except FileNotFoundError:
        return {}
    return config

def write_env_file(path: Path, data: dict) -> None:
    """Write config to ~/.halp.env with 0600 permissions."""
    lines = []
    for key in ("BASE_URL", "API_KEY", "DEFAULT_MODEL"):
        val = data.get(key, "")
        lines.append(f"{key}={val}")
    content = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(content)
    try:
        os.chmod(path, 0o600)
    except Exception:
        # Best-effort; ignore if platform/filesystem doesn't support
        pass

def setup_logging(verbose: bool = False, debug: bool = False) -> logging.Logger:
    """Configure colored console logging and a file log at ~/halp.log.

    Priority for level:
    - debug=True -> DEBUG
    - elif verbose=True -> INFO
    - else -> INFO (friendly default)
    """
    logger = logging.getLogger("halp")
    logger.propagate = False

    # Reconfigure cleanly each run
    if logger.handlers:
        logger.handlers.clear()

    level = logging.DEBUG if debug else (logging.INFO if verbose or not debug else logging.INFO)
    logger.setLevel(level)

    # Console (colored) to stdout
    if debug:
        log_format = f"%(levelname)s | ({set_color(RED)}%(filename)s\033[0m @ {set_color(YELLOW)}%(lineno)d\033[0m) | %(message)s"
    else:
        log_format = "%(levelname)s | %(message)s"

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(ColoredFormatter(log_format, datefmt="%Y/%m/%d %H:%M.%S"))
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # File (plain) log
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s | %(message)s", datefmt="%Y/%m/%d %H:%M.%S"))
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except Exception:
        # If file logging fails, continue with console-only
        pass

    return logger

def interactive_setup_env(path: Path) -> dict:
    """Prompt user for config values and write ~/.halp.env"""
    print("No configuration found. Let's set up ~/.halp.env")
    default_base = os.environ.get("HALP_BASE_URL", "")
    default_model = os.environ.get("HALP_DEFAULT_MODEL", "")

    base_url = input(f"BASE_URL [{default_base}]: ").strip() or default_base
    api_key = getpass.getpass("API_KEY (input hidden, leave blank if not needed): ").strip()
    default_model = input(f"DEFAULT_MODEL [{default_model}]: ").strip() or default_model

    config = {
        "BASE_URL": base_url,
        "API_KEY": api_key,
        "DEFAULT_MODEL": default_model,
    }
    write_env_file(path, config)
    print(f"Wrote config to {path}")
    return config

def ensure_config(overrides: Optional[dict] = None, force_init: bool = False, logger: Optional[logging.Logger] = None) -> dict:
    """Load config from ~/.halp.env.

    Behavior:
    - If force_init is True: always run interactive setup wizard.
    - If file exists: load and then apply overrides (if provided).
    - If file does not exist and overrides provide values: return overrides without creating a file.
    - Otherwise: run interactive setup to create the file.
    """
    overrides = overrides or {}
    if logger:
        logger.debug(f"ensure_config(force_init={force_init}, overrides_keys={list(overrides.keys())})")

    if force_init:
        base = interactive_setup_env(ENV_PATH)
        # Apply any explicit overrides on top of freshly created config
        base.update({k: v for k, v in overrides.items() if v})
        return base

    if ENV_PATH.exists():
        base = parse_env_file(ENV_PATH)
        base.update({k: v for k, v in overrides.items() if v})
        return base

    # No file: if we have overrides for key fields, don't prompt
    if any(overrides.get(k) for k in ("BASE_URL", "API_KEY", "DEFAULT_MODEL")):
        if logger:
            logger.info("~/.halp.env not found; using provided CLI overrides without creating a file.")
        # Only include known keys
        return {
            "BASE_URL": overrides.get("BASE_URL", ""),
            "API_KEY": overrides.get("API_KEY", ""),
            "DEFAULT_MODEL": overrides.get("DEFAULT_MODEL", ""),
        }

    return interactive_setup_env(ENV_PATH)

def _models_endpoint(base_url: str) -> str:
    b = (base_url or "").rstrip("/")
    if not b:
        return "/v1/models"
    if b.endswith("/v1"):
        return f"{b}/models"
    return f"{b}/v1/models"

def _chat_completions_endpoint(base_url: str) -> str:
    b = (base_url or "").rstrip("/")
    if not b:
        return "/v1/chat/completions"
    if b.endswith("/v1"):
        return f"{b}/chat/completions"
    return f"{b}/v1/chat/completions"

def list_models_openai(base_url: str, api_key: Optional[str], logger: Optional[logging.Logger] = None, timeout: int = 15) -> List[str]:
    """Query an OpenAI-compatible /v1/models endpoint and return model IDs."""
    url = _models_endpoint(base_url)
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    if logger:
        logger.debug(f"GET {url}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore") if hasattr(e, 'read') else str(e)
        if logger:
            logger.error(f"HTTP {e.code} when listing models: {msg}")
        return []
    except urllib.error.URLError as e:
        if logger:
            logger.error(f"Network error when listing models: {e}")
        return []
    except Exception as e:
        if logger:
            logger.error(f"Failed to parse models response: {e}")
        return []

    models: List[str] = []
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        for m in data["data"]:
            mid = m.get("id") if isinstance(m, dict) else None
            if mid:
                models.append(str(mid))
    elif isinstance(data, list):
        # Some servers may return a list of objects
        for m in data:
            if isinstance(m, dict) and m.get("id"):
                models.append(str(m["id"]))
            elif isinstance(m, str):
                models.append(m)
    else:
        if logger:
            logger.warning("Unexpected models response format.")
    return models

def chat_completion_openai(
    base_url: str,
    api_key: Optional[str],
    model: str,
    prompt: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    logger: Optional[logging.Logger] = None,
    temperature: float = 0.2,
    timeout: int = 60,
) -> Optional[str]:
    """Call an OpenAI-compatible /v1/chat/completions endpoint and return text.

    Provide either a single-turn `prompt` (user role) or a full `messages` history.
    Returns the assistant message content, or None on failure.
    """
    url = _chat_completions_endpoint(base_url)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    msg_list: List[dict]
    if messages is not None:
        msg_list = messages
    else:
        msg_list = [
            {"role": "system", "content": "You are HALP, a helpful command-line assistant."},
            {"role": "user", "content": prompt or ""},
        ]
    body = {
        "model": model,
        "messages": msg_list,
        "temperature": temperature,
        "stream": False,
    }
    data = json.dumps(body).encode("utf-8")
    if logger:
        logger.debug(f"POST {url}")
    try:
        req = urllib.request.Request(url, headers=headers, method="POST", data=data)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore") if hasattr(e, 'read') else str(e)
        if logger:
            logger.error(f"HTTP {e.code} when calling chat completions: {msg}")
        return None
    except urllib.error.URLError as e:
        if logger:
            logger.error(f"Network error when calling chat completions: {e}")
        return None
    except Exception as e:
        if logger:
            logger.error(f"Unexpected error: {e}")
        return None

    # Try to extract the text
    try:
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if choices and len(choices) > 0:
            first = choices[0]
            msg = first.get("message") if isinstance(first, dict) else None
            if msg and isinstance(msg.get("content"), str):
                return msg["content"]
            # Some servers may return delta/content directly
            if isinstance(first.get("text"), str):
                return first["text"]
    except Exception:
        pass
    if logger:
        logger.warning("Unexpected chat completions response format.")
    return None

def chat_completion_openai_stream(
    base_url: str,
    api_key: Optional[str],
    model: str,
    prompt: Optional[str] = None,
    messages: Optional[List[dict]] = None,
    logger: Optional[logging.Logger] = None,
    temperature: float = 0.2,
    timeout: int = 60,
):
    """Stream from an OpenAI-compatible /v1/chat/completions endpoint.

    Yields incremental text chunks as they arrive. On error, logs and yields nothing.
    """
    url = _chat_completions_endpoint(base_url)
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    msg_list: List[dict]
    if messages is not None:
        msg_list = messages
    else:
        msg_list = [
            {"role": "system", "content": "You are HALP, a helpful command-line assistant."},
            {"role": "user", "content": prompt or ""},
        ]
    body = {
        "model": model,
        "messages": msg_list,
        "temperature": temperature,
        "stream": True,
    }
    data = json.dumps(body).encode("utf-8")
    if logger:
        logger.debug(f"POST {url} (stream)")
    try:
        req = urllib.request.Request(url, headers=headers, method="POST", data=data)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Iterate Server-Sent Events lines: expect lines starting with "data: " and terminated by blank line
            for raw_line in resp:
                if not raw_line:
                    continue
                try:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not line:
                    continue
                # Ignore SSE comments or other fields
                if line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if data_str == "[DONE]":
                    break
                try:
                    payload = json.loads(data_str)
                except Exception:
                    # Ignore malformed chunks
                    continue
                # Extract chunk text (support both Chat and some provider variants)
                choices = payload.get("choices") if isinstance(payload, dict) else None
                if not choices:
                    continue
                first = choices[0]
                if isinstance(first, dict):
                    delta = first.get("delta")
                    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                        chunk = delta["content"]
                        if chunk:
                            yield chunk
                            continue
                    # Some providers stream via "text" instead of delta/content
                    if isinstance(first.get("text"), str):
                        chunk = first["text"]
                        if chunk:
                            yield chunk
                            continue
            # end for
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="ignore") if hasattr(e, 'read') else str(e)
        if logger:
            logger.error(f"HTTP {e.code} when streaming chat completions: {msg}")
    except urllib.error.URLError as e:
        if logger:
            logger.error(f"Network error when streaming chat completions: {e}")
    except Exception as e:
        if logger:
            logger.error(f"Unexpected streaming error: {e}")

def _read_line_interactive(prompt_text: str = "> ") -> Optional[str]:
    """Read a line from the user even if stdin is not a TTY.

    Tries input() first when stdin is a TTY. Otherwise falls back to /dev/tty.
    Returns None on EOF or error.
    """
    try:
        if sys.stdin.isatty():
            return input(prompt_text)
        # Fallback to /dev/tty for interactive input when stdin is piped
        try:
            with open("/dev/tty", "r") as tty_in, open("/dev/tty", "w") as tty_out:
                tty_out.write(prompt_text)
                tty_out.flush()
                line = tty_in.readline()
                return line.rstrip("\n") if line else None
        except Exception:
            return None
    except EOFError:
        return None

def chat_loop(
    base_url: str,
    api_key: Optional[str],
    model: str,
    initial_user_prompt: Optional[str],
    once: bool,
    stream: bool,
    logger: Optional[logging.Logger] = None,
) -> int:
    """Interactive chat loop. Returns process exit code."""
    messages: List[dict] = [
        {"role": "system", "content": "You are HALP, a helpful command-line assistant."}
    ]

    # If an initial prompt is provided, use it; otherwise ask the user.
    if initial_user_prompt:
        messages.append({"role": "user", "content": initial_user_prompt})
    else:
        user_msg = _read_line_interactive("How can I halp? |  ")
        if not user_msg:
            return 0
        messages.append({"role": "user", "content": user_msg})

    while True:
        try:
            if logger:
                logger.info("Sending request to model…")
            reply: Optional[str] = None
            if stream:
                # Stream tokens to stdout with color, while accumulating the full reply
                cyan = set_color(CYAN)
                reset = "\033[0m"
                print(f"{cyan}", end="", flush=True)
                parts: List[str] = []
                for chunk in chat_completion_openai_stream(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    logger=logger,
                ):
                    parts.append(chunk)
                    print(chunk, end="", flush=True)
                print(f"{reset}")
                if not parts:
                    # Some providers may ignore stream=True and return a JSON payload instead.
                    # Fallback to non-streaming request to maintain compatibility.
                    if logger:
                        logger.warning("No stream chunks received; falling back to non-streaming response.")
                    reply = chat_completion_openai(
                        base_url=base_url,
                        api_key=api_key,
                        model=model,
                        messages=messages,
                        logger=logger,
                    )
                    if reply:
                        # Print reply in color to match streaming UX
                        print(f"{cyan}{reply}{reset}")
                else:
                    reply = "".join(parts)
            else:
                reply = chat_completion_openai(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    messages=messages,
                    logger=logger,
                )
            if not reply:
                print("Request failed. See logs for details.", file=sys.stderr)
                return 1
            # Append assistant message to history; only print here for non-streaming path
            messages.append({"role": "assistant", "content": reply})
            if not stream:
                cyan = set_color(CYAN)
                reset = "\033[0m"
                print(f"{cyan}{reply}{reset}")

            if once:
                return 0

            # Next user turn
            user_msg = _read_line_interactive("How can I halp? |  ")
            if user_msg is None:
                # EOF (Ctrl-D) or error -> end session
                return 0
            if user_msg.strip() in {"/exit", "/quit", "/q"}:
                return 0
            if user_msg.strip() == "":
                # Ignore empty lines
                continue
            messages.append({"role": "user", "content": user_msg})
        except KeyboardInterrupt:
            # Reset terminal colors if we started streaming, log, and exit with 130
            try:
                reset = "\033[0m"
                print(f"{reset}")
            except Exception:
                pass
            if logger:
                logger.info("Interrupted by user (Ctrl-C).")
            return 130

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="halp",
        description=(__doc__ or "AI assistance for the command line.").strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # General flags
    parser.add_argument("--print-config", action="store_true", help="Print the loaded configuration and exit")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging (implies --verbose)")
    parser.add_argument("--init", action="store_true", help="Run interactive setup wizard, even if ~/.halp.env exists")
    # TODO: --yolo should cause any suggested command to run without prior user approval.
    # IMPORTANT: This is security-sensitive and must only be implemented with
    # explicit user consent and strong safeguards. For now, it is a stub only.
    parser.add_argument("--yolo", action="store_true", help="Run suggested commands without prompting [stub, not implemented]")
    parser.add_argument("--once", "-o", action="store_true", dest="once", help="Exit after a single assistant reply and quit")
    parser.add_argument("--no-stream", action="store_true", dest="no_stream", help="Disable token streaming; return full responses")

    # Config overrides
    parser.add_argument("-u", "--base_url", help="Override BASE_URL (ignore ~/.halp.env)")
    parser.add_argument("-k", "--api_key", help="Override API_KEY (ignore ~/.halp.env)")
    parser.add_argument("-m", "--model", help="Specify a model to use (overrides DEFAULT_MODEL)")

    # Actions
    parser.add_argument("-l", "--list_models", action="store_true", help="List available models via /v1/models")

    # Prompt to send to the model (positional). If omitted, halp prints status or reads from stdin when piped.
    parser.add_argument("prompt", nargs="*", help="Prompt to send to the model (use quotes)")

    args = parser.parse_args(argv)

    logger = setup_logging(verbose=args.verbose or args.debug, debug=args.debug)

    overrides = {
        "BASE_URL": args.base_url,
        "API_KEY": args.api_key,
        "DEFAULT_MODEL": args.model,
    }
    config = ensure_config(overrides=overrides, force_init=args.init, logger=logger)

    # After ensure_config, apply model override explicitly again to be safe
    if args.model:
        config["DEFAULT_MODEL"] = args.model

    if args.print_config:
        print(json.dumps(config, indent=2))
        return 0

    if args.list_models:
        base_url = config.get("BASE_URL", "")
        api_key = config.get("API_KEY", "")
        if not base_url:
            print("Error: BASE_URL is required to list models. Provide via ~/.halp.env or --base_url.", file=sys.stderr)
            return 2
        models = list_models_openai(base_url=base_url, api_key=api_key, logger=logger)
        if not models:
            print("No models found or request failed.", file=sys.stderr)
            return 1
        for m in models:
            print(m)
        return 0

    # Determine initial prompt from args or stdin; if none, start interactive and ask
    prompt_text = None
    if args.prompt:
        prompt_text = " ".join(args.prompt).strip()
    elif not sys.stdin.isatty():
        try:
            prompt_text = sys.stdin.read().strip()
        except Exception:
            prompt_text = None

    base_url = config.get("BASE_URL", "")
    api_key = config.get("API_KEY", "")
    model = config.get("DEFAULT_MODEL", "")
    if not base_url or not model:
        print("Error: BASE_URL and DEFAULT_MODEL are required. Set them in ~/.halp.env or via CLI overrides.", file=sys.stderr)
        return 2

    # Start chat loop (default: persistent). Use --once/-o to exit after one reply.
    return chat_loop(
        base_url=base_url,
        api_key=api_key,
        model=model,
        initial_user_prompt=prompt_text,
        once=args.once,
        stream=(not args.no_stream),
        logger=logger,
    )

    # Stub behavior for --yolo
    if args.yolo:
        # TODO: Implement non-interactive execution flow guarded by explicit user
        # approval and safety checks. Consider dry-run, whitelisting, and logging.
        logger.info("--yolo specified. NOTE: This is a stub flag; execution without prompts is not implemented yet.")

    # (Unreachable in normal flow since chat_loop returns)
    return 0

if __name__ == "__main__":
    sys.exit(main())
