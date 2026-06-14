"""LLM calling layer — every model call goes through here.

Uses Mozilla.ai's **any-llm** (NOT litellm), which dispatches to each provider's
official SDK. Model ids use the ``provider/model`` form, e.g.::

    openai/gpt-4o
    anthropic/claude-sonnet-4-6

Keys are read from the environment (loaded from ``.env`` by ``cli.py``).
"""

from __future__ import annotations

import json
import re
from typing import Any


class LLMError(RuntimeError):
    pass


def _load_any_llm():
    try:
        from any_llm import completion  # type: ignore
    except Exception as exc:  # pragma: no cover - import guard
        raise LLMError(
            "any-llm is not installed. Install it with:\n"
            "    pip install 'any-llm-sdk[openai,anthropic]'\n"
            f"(original import error: {exc})"
        ) from exc
    return completion


def complete(
    model: str,
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.8,
) -> str:
    """Return the model's text completion for a single prompt."""
    completion = _load_any_llm()
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        resp = completion(model=model, messages=messages, temperature=temperature)
    except Exception as exc:  # pragma: no cover - network/provider errors
        raise LLMError(f"LLM call failed for model {model!r}: {exc}") from exc

    return _extract_text(resp)


def _extract_text(resp: Any) -> str:
    """Pull the assistant text out of an OpenAI-style response object/dict."""
    try:
        if isinstance(resp, dict):
            return resp["choices"][0]["message"]["content"]
        return resp.choices[0].message.content
    except Exception as exc:  # pragma: no cover
        raise LLMError(f"Could not parse LLM response: {resp!r}") from exc


def complete_json(
    model: str,
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.3,
) -> Any:
    """Call the model and parse its reply as JSON.

    Provider-agnostic structured output: we ask for JSON in the prompt and
    tolerate fenced ```json blocks.
    """
    text = complete(model, prompt, system=system, temperature=temperature)
    return _parse_json(text)


def _parse_json(text: str) -> Any:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fall back to the first {...} or [...] block.
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise LLMError(f"Model did not return valid JSON:\n{text}")
