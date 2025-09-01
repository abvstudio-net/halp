"""
Configuration management for halp (.env handling and setup).
"""
from __future__ import annotations

import os
import getpass
import logging
from pathlib import Path
from typing import Optional

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


def ensure_config(
    overrides: Optional[dict] = None,
    force_init: bool = False,
    logger: Optional[logging.Logger] = None,
) -> dict:
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
            logger.debug("~/.halp.env not found; using provided CLI overrides without creating a file.")
        # Only include known keys
        return {
            "BASE_URL": overrides.get("BASE_URL", ""),
            "API_KEY": overrides.get("API_KEY", ""),
            "DEFAULT_MODEL": overrides.get("DEFAULT_MODEL", ""),
        }

    return interactive_setup_env(ENV_PATH)


__all__ = [
    "ENV_FILENAME",
    "ENV_PATH",
    "parse_env_file",
    "write_env_file",
    "interactive_setup_env",
    "ensure_config",
]
