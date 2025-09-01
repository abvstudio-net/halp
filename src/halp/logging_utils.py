"""
Logging utilities with colored output for halp.
"""
from __future__ import annotations

import logging
import sys

# ANSI color indices
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)


def set_color(color: int) -> str:
    return f"\033[1;3{color}m"


LOG_COLORS = {
    logging.DEBUG: set_color(RED),   # DEBUG is red per requirement
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


def setup_logging(enabled: bool = False) -> logging.Logger:
    """Configure logging.

    - If enabled is False: return a logger that emits nothing.
    - If enabled is True: console-only DEBUG logging with colored levels.
    """
    logger = logging.getLogger("halp")
    logger.propagate = False

    # Reconfigure cleanly each run
    if logger.handlers:
        logger.handlers.clear()

    if not enabled:
        # Silent logger
        logger.setLevel(logging.CRITICAL)
        logger.addHandler(logging.NullHandler())
        return logger

    level = logging.DEBUG
    logger.setLevel(level)

    # Verbose format with filename and line number
    log_format = f"%(levelname)s | ({set_color(RED)}%(filename)s\033[0m @ {set_color(YELLOW)}%(lineno)d\033[0m) | %(message)s"

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(ColoredFormatter(log_format, datefmt="%Y/%m/%d %H:%M.%S"))
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    return logger


__all__ = [
    "BLACK",
    "RED",
    "GREEN",
    "YELLOW",
    "BLUE",
    "MAGENTA",
    "CYAN",
    "WHITE",
    "set_color",
    "LOG_COLORS",
    "ColoredFormatter",
    "setup_logging",
]
