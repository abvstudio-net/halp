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
    """Configure and return the module logger based on flags."""
    logger = logging.getLogger("halp")
    # Avoid adding multiple handlers if main() is called multiple times in tests
    if not logger.handlers:
        handler = logging.StreamHandler(stream=sys.stderr)
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    level = logging.WARNING
    if debug:
        level = logging.DEBUG
    elif verbose:
        level = logging.INFO
    logger.setLevel(level)
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

    # Config overrides
    parser.add_argument("-u", "--base_url", help="Override BASE_URL (ignore ~/.halp.env)")
    parser.add_argument("-k", "--api_key", help="Override API_KEY (ignore ~/.halp.env)")
    parser.add_argument("-m", "--model", help="Specify a model to use (overrides DEFAULT_MODEL)")

    # Actions
    parser.add_argument("-l", "--list_models", action="store_true", help="List available models via /v1/models")

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

    # Stub behavior for --yolo
    if args.yolo:
        # TODO: Implement non-interactive execution flow guarded by explicit user
        # approval and safety checks. Consider dry-run, whitelisting, and logging.
        logger.info("--yolo specified. NOTE: This is a stub flag; execution without prompts is not implemented yet.")

    # Placeholder for future functionality
    print("halp is set up. Configuration loaded.")
    if config.get("DEFAULT_MODEL"):
        print(f"Using model: {config['DEFAULT_MODEL']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
