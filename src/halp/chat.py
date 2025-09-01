"""
Chat loop orchestration for halp.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from typing import Dict, List, Optional

from .api import chat_completion_openai_stream
from .logging_utils import GREEN, set_color
from .ui import read_line_interactive


def chat_loop(
    base_url: str,
    api_key: Optional[str],
    model: str,
    initial_user_prompt: Optional[str],
    system_prompt: str,
    once: bool,
    logger: Optional[logging.Logger] = None,
) -> int:
    """Interactive chat loop. Returns process exit code."""
    messages: List[dict] = [
        {"role": "system", "content": system_prompt}
    ]

    # If an initial prompt is provided, use it; otherwise ask the user.
    if initial_user_prompt:
        messages.append({"role": "user", "content": initial_user_prompt})
    else:
        try:
            user_msg = read_line_interactive("How can I halp? |  ")
        except KeyboardInterrupt:
            # Graceful exit if Ctrl-C during initial prompt
            try:
                reset = "\033[0m"
                print(f"{reset}")
            except Exception:
                pass
            if logger:
                logger.debug("Interrupted by user (Ctrl-C).")
            return 130
        if not user_msg:
            return 0
        messages.append({"role": "user", "content": user_msg})

    while True:
        try:
            if logger:
                logger.debug("Sending request to model…")
            # Stream tokens to stdout with bright green color, while accumulating the full reply
            green = set_color(GREEN)
            reset = "\033[0m"
            print(f"{green}", end="", flush=True)
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
            print()  # Extra vertical space after assistant reply
            if not parts and logger:
                logger.debug("No stream chunks received.")
            reply = "".join(parts)
            if not reply:
                print("Request failed. See logs for details.", file=sys.stderr)
                return 1
            # Append assistant message to history
            messages.append({"role": "assistant", "content": reply})

            if once:
                return 0

            # Next user turn
            user_msg = read_line_interactive("How can I halp? |  ")
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
                logger.debug("Interrupted by user (Ctrl-C).")
            return 130


def _extract_json_objects(text: str) -> List[dict]:
    """Best-effort extractor for JSON objects in model output.

    - Prefer fenced ```json blocks.
    - Fallback to first balanced-looking { ... } object in the text.
    """
    objs: List[dict] = []
    # Prefer code-fenced JSON
    for m in re.finditer(r"```json\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE):
        try:
            obj = json.loads(m.group(1))
            objs.append(obj)
        except Exception:
            continue
    if objs:
        return objs
    # Fallback: find first {..} blob (non-greedy) and try to parse
    m = re.search(r"\{[\s\S]*?\}", text)
    if m:
        try:
            obj = json.loads(m.group(0))
            objs.append(obj)
        except Exception:
            pass
    return objs


def agent_loop(
    base_url: str,
    api_key: Optional[str],
    model: str,
    initial_user_prompt: Optional[str],
    system_prompt: str,
    tools: Dict[str, object],
    max_steps: int = 10,
    logger: Optional[logging.Logger] = None,
) -> int:
    """ReACT-style agent loop.

    The model should emit JSON tool calls like:
    {"tool": "shell", "input": "ls -la"}
    To finish, it may either produce a normal final answer (no tool JSON), or:
    {"final": "<final answer>"}
    """
    messages: List[dict] = [
        {"role": "system", "content": system_prompt}
    ]

    # Seed with initial user input or ask
    if initial_user_prompt:
        messages.append({"role": "user", "content": initial_user_prompt})
    else:
        try:
            user_msg = read_line_interactive("How can I halp? |  ")
        except KeyboardInterrupt:
            try:
                reset = "\033[0m"
                print(f"{reset}")
            except Exception:
                pass
            if logger:
                logger.debug("Interrupted by user (Ctrl-C).")
            return 130
        if not user_msg:
            return 0
        messages.append({"role": "user", "content": user_msg})

    for step in range(1, max_steps + 1):
        if logger:
            logger.debug(f"Agent step {step}/{max_steps}: requesting model")
        # Get a full assistant message without streaming to console
        parts: List[str] = []
        for chunk in chat_completion_openai_stream(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=messages,
            logger=logger,
        ):
            parts.append(chunk)
        reply = "".join(parts).strip()
        if not reply:
            print("Request failed. See logs for details.", file=sys.stderr)
            return 1
        if logger:
            logger.debug(f"Assistant reply chars={len(reply)}")

        # Try to parse for tool call or final
        objs = _extract_json_objects(reply)
        tool_obj = None
        final_obj = None
        for obj in objs:
            if isinstance(obj, dict) and "final" in obj:
                final_obj = obj
                break
            if isinstance(obj, dict) and obj.get("tool") and ("input" in obj or "args" in obj):
                tool_obj = obj
                break

        if final_obj is not None:
            # Final message
            final_text = str(final_obj.get("final", "")).strip()
            print(final_text)
            return 0

        if tool_obj is None:
            # No tool: treat whole reply as final answer
            print(reply)
            return 0

        # Found a tool call
        tool_name = str(tool_obj.get("tool")).strip()
        tool_input = tool_obj.get("input")
        if tool_input is None:
            tool_input = tool_obj.get("args")
        if not isinstance(tool_input, str):
            tool_input = json.dumps(tool_input)

        if logger:
            logger.debug(f"Tool call: {tool_name} -> {tool_input}")
        tool = tools.get(tool_name)
        if not tool:
            observation = {
                "ok": False,
                "error": f"Unknown tool: {tool_name}",
            }
        else:
            try:
                observation = tool.run(tool_input)
            except Exception as e:
                observation = {"ok": False, "error": f"Tool execution error: {e}"}

        # Append to transcript as an observation for the model
        obs_text = json.dumps({"tool": tool_name, "result": observation})
        messages.append({"role": "assistant", "content": reply})
        messages.append({"role": "user", "content": f"Observation:\n{obs_text}"})

    print("Agent reached max steps without finishing.", file=sys.stderr)
    return 1
