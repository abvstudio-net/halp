"""
HTTP API helpers for OpenAI-compatible endpoints.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import List, Optional


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


def list_models_openai(
    base_url: str,
    api_key: Optional[str],
    logger: Optional[logging.Logger] = None,
    timeout: int = 15,
) -> List[str]:
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
            logger.debug(f"HTTP {e.code} when listing models: {msg}")
        return []
    except urllib.error.URLError as e:
        if logger:
            logger.debug(f"Network error when listing models: {e}")
        return []
    except Exception as e:
        if logger:
            logger.debug(f"Failed to parse models response: {e}")
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
            logger.debug("Unexpected models response format.")
    return models


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
            logger.debug(f"HTTP {e.code} when streaming chat completions: {msg}")
    except urllib.error.URLError as e:
        if logger:
            logger.debug(f"Network error when streaming chat completions: {e}")
    except Exception as e:
        if logger:
            logger.debug(f"Unexpected streaming error: {e}")


__all__ = [
    "list_models_openai",
    "chat_completion_openai_stream",
]
