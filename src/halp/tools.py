"""
Tooling interfaces and implementations for the halp agent.

Provides a minimal Tool base and a ShellTool with safety gating and interactive confirmation.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Dict, Optional

from .ui import read_line_interactive
from .logging_utils import YELLOW, set_color


class ToolExecutionError(Exception):
    pass


@dataclass
class Tool:
    name: str
    description: str

    def run(self, user_input: str) -> Dict[str, object]:
        """Execute the tool.
        Must return a dict with keys: ok (bool), returncode (int), stdout (str), stderr (str).
        """
        raise NotImplementedError


class ShellTool(Tool):
    def __init__(self, unsafe_exec: bool = False):
        super().__init__(
            name="shell",
            description=(
                "Execute shell commands on the local system. Input is a single string. "
                "Use responsibly. Commands will require confirmation unless --unsafe_exec is set. "
                "Absolute policy: 'sudo' is never allowed in tool calls."
            ),
        )
        self.unsafe_exec = unsafe_exec
        # Simple safety blocklist (best-effort; not exhaustive)
        self._blocklist = [
            r"\brm\b",
            r"\bsudo\b",
            r"\bchown\b",
            r"\bchmod\b",
            r"\bdd\b",
            r"\bmkfs\b",
            r">\s*\S",  # redirection
            r">>\s*\S",
            r"\bshutdown\b|\breboot\b|\bhalt\b",
            r"\bkill\b",
            r"\bmount\b|\bumount\b",
            r"\bsystemctl\b",
            r"\bapt(-get)?\b|\byum\b|\bdnf\b|\bpacman\b",
            r"\bpip\b\s+install\b|\bpython\b\s+-m\s+pip\s+install\b",
            r"\bdocker\b|\bpodman\b|\bkubectl\b",
            r"curl\s*\|\s*sh|wget\s*\|\s*sh",
            r"\bgit\b\s+push\b|\bgit\b\s+reset\b|\bgit\b\s+clean\b",
        ]
        self._block_re = re.compile("|".join(self._blocklist), re.IGNORECASE)

    def run(self, user_input: str) -> Dict[str, object]:
        cmd = user_input.strip()
        if not cmd:
            return {"ok": False, "returncode": 2, "stdout": "", "stderr": "Empty command"}
        # Hard block: never allow sudo regardless of unsafe_exec
        if re.search(r"\bsudo\b", cmd, re.IGNORECASE):
            return {
                "ok": False,
                "returncode": 13,
                "stdout": "",
                "stderr": (
                    "Blocked by policy: 'sudo' is not allowed in tool calls. "
                    "Provide guidance to the user instead."
                ),
            }
        # Confirmation flow: if unsafe_exec is not set, ask the user to confirm before executing
        is_potentially_unsafe = bool(self._block_re.search(cmd))
        if not self.unsafe_exec:
            warn = " [WARNING: potentially unsafe]" if is_potentially_unsafe else ""
            yellow = set_color(YELLOW)
            reset = "\033[0m"
            prompt = (
                f"Approve shell command? [y/N]{warn}\n"
                f"  {yellow}{cmd}{reset}\n"
                f"-> "
            )
            ans = read_line_interactive(prompt)
            if ans is None:
                return {
                    "ok": False,
                    "returncode": 4,
                    "stdout": "",
                    "stderr": (
                        "Command not executed: interactive confirmation required but no TTY available."
                    ),
                }
            if ans.strip().lower() not in {"y", "yes"}:
                return {
                    "ok": False,
                    "returncode": 5,
                    "stdout": "",
                    "stderr": "Command not executed: user declined.",
                }
        try:
            # Always echo the command being executed in yellow so the user can see it
            try:
                yellow = set_color(YELLOW)
                reset = "\033[0m"
                sys.stdout.write(f"{yellow}{cmd}{reset}\n")
                sys.stdout.flush()
            except Exception:
                pass

            # Use shell=True to allow pipelines and operators users expect
            proc = subprocess.run(
                cmd,
                shell=True,
                text=True,
                capture_output=True,
                cwd=os.getcwd(),
            )
            # Echo outputs to user immediately
            if proc.stdout:
                try:
                    sys.stdout.write(proc.stdout)
                    sys.stdout.flush()
                except Exception:
                    pass
            if proc.stderr:
                try:
                    sys.stderr.write(proc.stderr)
                    sys.stderr.flush()
                except Exception:
                    pass
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout or "",
                "stderr": proc.stderr or "",
            }
        except Exception as e:
            return {
                "ok": False,
                "returncode": 1,
                "stdout": "",
                "stderr": f"Execution error: {e}",
            }


def get_default_toolset(unsafe_exec: bool = False) -> Dict[str, Tool]:
    """Return the default tool registry keyed by tool name."""
    return {
        "shell": ShellTool(unsafe_exec=unsafe_exec),
    }


__all__ = [
    "Tool",
    "ShellTool",
    "ToolExecutionError",
    "get_default_toolset",
]
