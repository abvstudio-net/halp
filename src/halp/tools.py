"""
Tooling interfaces and implementations for the halp agent.

Provides a minimal Tool base and a ShellTool with dry-run and safety gating.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Dict, Optional

from .ui import read_line_interactive


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
    def __init__(self, dry_run: bool = False, unsafe_exec: bool = False):
        super().__init__(
            name="shell",
            description=(
                "Execute shell commands on the local system. Input is a single string. "
                "Use responsibly. Commands will require confirmation unless --unsafe_exec is set."
            ),
        )
        self.dry_run = dry_run
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
        if self.dry_run:
            return {
                "ok": True,
                "returncode": 0,
                "stdout": f"DRY RUN: would execute -> {cmd}",
                "stderr": "",
            }
        # Confirmation flow: if unsafe_exec is not set, ask the user to confirm before executing
        is_potentially_unsafe = bool(self._block_re.search(cmd))
        if not self.unsafe_exec:
            warn = " [WARNING: potentially unsafe]" if is_potentially_unsafe else ""
            prompt = (
                f"Approve shell command? [y/N]{warn}\n"
                f"  {cmd}\n"
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
            # Use shell=True to allow pipelines and operators users expect
            proc = subprocess.run(
                cmd,
                shell=True,
                text=True,
                capture_output=True,
                cwd=os.getcwd(),
            )
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


def get_default_toolset(dry_run: bool = False, unsafe_exec: bool = False) -> Dict[str, Tool]:
    """Return the default tool registry keyed by tool name."""
    return {
        "shell": ShellTool(dry_run=dry_run, unsafe_exec=unsafe_exec),
    }


__all__ = [
    "Tool",
    "ShellTool",
    "ToolExecutionError",
    "get_default_toolset",
]
