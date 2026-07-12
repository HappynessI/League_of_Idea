"""LLM calling layer — every model call goes through here.

Uses Mozilla.ai's **any-llm** (NOT litellm), which dispatches to each provider's
official SDK. Model ids use the ``provider:model`` form, e.g.::

    openai:gpt-4o
    anthropic:claude-sonnet-4-6

Keys are read from the environment (loaded from ``.env`` by ``cli.py``).
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from .usage import UsageTracker


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
    max_retries: int = 2,
    usage_tracker: UsageTracker | None = None,
) -> str:
    """Return the model's text completion for a single prompt."""
    completion = _load_any_llm()
    provider, model_id = _split_model_ref(model)
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    if usage_tracker is not None:
        usage_tracker.before_call()

    for attempt in range(max_retries + 1):
        try:
            resp = completion(
                model=model_id,
                provider=provider,
                messages=messages,
                temperature=temperature,
            )
            break
        except Exception as exc:  # pragma: no cover - network/provider errors
            if attempt >= max_retries:
                raise LLMError(
                    f"LLM call failed for model {model!r} after "
                    f"{max_retries + 1} attempts: {exc}"
                ) from exc
            time.sleep(2**attempt)

    if usage_tracker is not None:
        prompt_tokens, completion_tokens = _extract_usage(resp)
        usage_tracker.record(prompt_tokens, completion_tokens, model=model)
    return _extract_text(resp)


def _split_model_ref(model: str) -> tuple[str, str]:
    """Accept current ``provider:model`` and legacy ``provider/model`` refs."""
    if ":" in model:
        provider, model_id = model.split(":", 1)
    elif "/" in model:
        provider, model_id = model.split("/", 1)
    else:
        raise LLMError(
            f"Model {model!r} must include a provider, for example "
            "'openai:gpt-4o-mini'."
        )
    if not provider.strip() or not model_id.strip():
        raise LLMError(f"Invalid model reference: {model!r}")
    return provider.strip(), model_id.strip()


def _extract_text(resp: Any) -> str:
    """Pull the assistant text out of an OpenAI-style response object/dict."""
    try:
        if isinstance(resp, dict):
            return resp["choices"][0]["message"]["content"]
        return resp.choices[0].message.content
    except Exception as exc:  # pragma: no cover
        raise LLMError(f"Could not parse LLM response: {resp!r}") from exc


def _extract_usage(resp: Any) -> tuple[int, int]:
    """Extract common OpenAI-style usage fields, defaulting to zero if absent."""
    usage = resp.get("usage") if isinstance(resp, dict) else getattr(resp, "usage", None)
    if usage is None:
        return 0, 0

    def get_value(*names: str) -> int:
        for name in names:
            value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if value is not None:
                return int(value)
        return 0

    return (
        get_value("prompt_tokens", "input_tokens"),
        get_value("completion_tokens", "output_tokens"),
    )


def complete_json(
    model: str,
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.3,
    usage_tracker: UsageTracker | None = None,
) -> Any:
    """Call the model and parse its reply as JSON.

    Provider-agnostic structured output: we ask for JSON in the prompt and
    tolerate fenced ```json blocks.
    """
    text = complete(
        model,
        prompt,
        system=system,
        temperature=temperature,
        usage_tracker=usage_tracker,
    )
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
