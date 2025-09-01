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
from .logging_utils import GREEN, YELLOW, RED, set_color
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
    """Extract JSON objects from arbitrary text robustly.

    This implementation scans the text, tracks string/escape state, and
    collects balanced {...} objects while ignoring braces inside strings.
    """
    objs: List[dict] = []

    in_string = False
    escape = False
    depth = 0
    start_idx: Optional[int] = None

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                # Current char is escaped; consume and reset escape
                escape = False
            else:
                if ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            continue

        # Not in a string
        if ch == '"':
            in_string = True
            continue
        if ch == '{':
            if depth == 0:
                start_idx = i
            depth += 1
            continue
        if ch == '}' and depth > 0:
            depth -= 1
            if depth == 0 and start_idx is not None:
                candidate = text[start_idx : i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        objs.append(obj)
                except Exception:
                    pass
                start_idx = None

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
    continue_conversation: bool = True,
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
        # Detect leading "yolo" directive to enable auto-execution and strip it from the prompt
        yolo = False
        if user_msg and user_msg.strip():
            parts = user_msg.strip().split(None, 1)
            if parts and parts[0].lower() == "yolo":
                yolo = True
                user_msg = parts[1] if len(parts) > 1 else ""
        if yolo:
            try:
                for t in tools.values():
                    if hasattr(t, "unsafe_exec"):
                        setattr(t, "unsafe_exec", True)
                if logger:
                    logger.debug("'yolo' directive detected: enabling unsafe_exec for tools")
            except Exception:
                pass
        messages.append({"role": "user", "content": user_msg})

    while True:
        restart_episode = False
        for step in range(1, max_steps + 1):
            if logger:
                logger.debug(f"Agent step {step}/{max_steps}: requesting model")
            # Get a full assistant message without streaming to console (avoid exposing tool JSON)
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
                # Final message (print in green)
                final_text = str(final_obj.get("final", "")).strip()
                try:
                    green = set_color(GREEN)
                    reset = "\033[0m"
                    print(f"{green}{final_text}{reset}")
                except Exception:
                    print(final_text)
                if not continue_conversation:
                    return 0
                # Next user turn
                user_msg = read_line_interactive("How can I halp? |  ")
                if user_msg is None or user_msg.strip() in {"/exit", "/quit", "/q"}:
                    return 0
                if user_msg.strip() == "":
                    return 0
                messages.append({"role": "user", "content": user_msg})
                restart_episode = True
                break

            if tool_obj is None:
                # No tool parsed. If the reply appears to attempt a tool call (malformed JSON), ask to try again.
                looks_like_tool = (
                    '```json' in reply
                    or '"tool"' in reply
                    or re.search(r"\{[^}]*\"tool\"", reply) is not None
                )
                if looks_like_tool:
                    # Inform the user visually about the malformed tool JSON and that we are retrying
                    try:
                        red = set_color(RED)
                        yellow = set_color(YELLOW)
                        reset = "\033[0m"
                        print(f"{red}<MALFORMED TOOL CALL - RETRYING>{reset}")
                        print(f"{yellow}{reply}{reset}")
                    except Exception:
                        print("<MALFORMED TOOL CALL - RETRYING>")
                        print(reply)
                    if logger:
                        logger.debug("Malformed tool JSON detected; asking model to re-emit valid JSON")
                    messages.append({"role": "assistant", "content": reply})
                    messages.append({
                        "role": "user",
                        "content": (
                            "Observation:\n"
                            + json.dumps({
                                "error": "Malformed tool JSON. Emit ONLY a JSON object like {\"tool\": \"shell\", \"input\": \"...\"} or a final {\"final\": \"...\"}. No extra text."})
                        ),
                    })
                    continue
                # Otherwise, treat whole reply as final answer (print in green)
                try:
                    green = set_color(GREEN)
                    reset = "\033[0m"
                    print(f"{green}{reply}{reset}")
                except Exception:
                    print(reply)
                if not continue_conversation:
                    return 0
                user_msg = read_line_interactive("How can I halp? |  ")
                if user_msg is None or user_msg.strip() in {"/exit", "/quit", "/q"}:
                    return 0
                if user_msg.strip() == "":
                    return 0
                messages.append({"role": "user", "content": user_msg})
                restart_episode = True
                break

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
                # Pre-check: never allow sudo; instruct model to try again without sudo
                if tool_name == "shell" and re.search(r"\bsudo\b", tool_input or "", re.IGNORECASE):
                    observation = {
                        "ok": False,
                        "returncode": 13,
                        "stdout": "",
                        "stderr": "Blocked by policy: 'sudo' is not allowed in tool calls. Recommend the sudo command to the user instead, or retry without sudo.",
                    }
                else:
                    try:
                        observation = tool.run(tool_input)
                    except Exception as e:
                        observation = {"ok": False, "error": f"Tool execution error: {e}"}
            if logger:
                try:
                    rc = observation.get("returncode") if isinstance(observation, dict) else None
                    ok = observation.get("ok") if isinstance(observation, dict) else None
                    logger.debug(f"Tool observation: ok={ok}, returncode={rc}")
                except Exception:
                    logger.debug("Tool observation logged.")

            # Append to transcript as an observation for the model
            obs_text = json.dumps({"tool": tool_name, "result": observation})
            messages.append({"role": "assistant", "content": reply})
            messages.append({"role": "user", "content": f"Observation:\n{obs_text}"})

        if restart_episode:
            continue
        print("Agent reached max steps without finishing.", file=sys.stderr)
        return 1
