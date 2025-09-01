"""
User interaction helpers for halp (TTY-safe input and prompts).
"""
from __future__ import annotations

import sys
from typing import Optional

from .logging_utils import BLUE, MAGENTA, set_color


def read_line_interactive(prompt_text: str = "> ") -> Optional[str]:
    """Read a line from the user even if stdin is not a TTY.

    Tries input() first when stdin is a TTY. Otherwise falls back to /dev/tty.
    Returns None on EOF or error.
    """
    try:
        if sys.stdin.isatty():
            blue = set_color(BLUE)
            purple = set_color(MAGENTA)
            reset = "\033[0m"
            try:
                line = input(f"{blue}{prompt_text}{purple}")
            finally:
                try:
                    # Ensure terminal color resets even on interrupt
                    sys.stdout.write(reset)
                    sys.stdout.flush()
                except Exception:
                    pass
            return line
        # Fallback to /dev/tty for interactive input when stdin is piped
        try:
            blue = set_color(BLUE)
            purple = set_color(MAGENTA)
            reset = "\033[0m"
            with open("/dev/tty", "r") as tty_in, open("/dev/tty", "w") as tty_out:
                tty_out.write(f"{blue}{prompt_text}{purple}")
                tty_out.flush()
                line = tty_in.readline()
                try:
                    tty_out.write(reset)
                    tty_out.flush()
                except Exception:
                    pass
                return line.rstrip("\n") if line else None
        except Exception:
            return None
    except EOFError:
        return None


# Backward-compat alias
_read_line_interactive = read_line_interactive

__all__ = ["read_line_interactive", "_read_line_interactive"]
