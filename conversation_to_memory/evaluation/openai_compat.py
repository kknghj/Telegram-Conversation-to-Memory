"""OpenAI Chat Completions compatibility helpers for multi-model evaluation."""

from __future__ import annotations

from typing import Any


def is_reasoning_family(model: str) -> bool:
    name = (model or "").lower()
    return name.startswith("gpt-5") or "o1" in name or "o3" in name or "o4" in name


def effective_max_output_tokens(model: str, requested: int) -> int:
    """Reasoning models spend completion budget on reasoning tokens too."""
    if is_reasoning_family(model):
        # Keep headroom so JSON content is not truncated to empty.
        return max(requested * 4, 4096)
    return requested


def build_chat_kwargs(
    *,
    model: str,
    messages: list[dict],
    temperature: float | None,
    max_output_tokens: int,
    response_format: dict | None = None,
) -> dict[str, Any]:
    """Build request kwargs compatible with the target model family."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    token_budget = effective_max_output_tokens(model, max_output_tokens)
    if is_reasoning_family(model):
        # GPT-5.x / o-series: max_completion_tokens; temperature often unsupported.
        kwargs["max_completion_tokens"] = token_budget
    else:
        kwargs["max_tokens"] = token_budget
        if temperature is not None:
            kwargs["temperature"] = temperature
    return kwargs


def chat_completion_create(
    client: Any,
    *,
    model: str,
    messages: list[dict],
    temperature: float | None = None,
    max_output_tokens: int = 1200,
    response_format: dict | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Call chat.completions.create with model-compatible kwargs.

    On unsupported-parameter errors, retry once without temperature / with
    max_completion_tokens swap. Never falls back to a different model.
    """
    kwargs = build_chat_kwargs(
        model=model,
        messages=messages,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_format=response_format,
    )
    try:
        response = client.chat.completions.create(**kwargs)
        return response, dict(kwargs)
    except Exception as first_exc:
        message = str(first_exc).lower()
        retry_kwargs = dict(kwargs)
        changed = False
        if "temperature" in message and "temperature" in retry_kwargs:
            retry_kwargs.pop("temperature", None)
            changed = True
        if "max_tokens" in message and "max_tokens" in retry_kwargs:
            retry_kwargs["max_completion_tokens"] = retry_kwargs.pop("max_tokens")
            changed = True
        if "max_completion_tokens" in message and "max_completion_tokens" in retry_kwargs:
            retry_kwargs["max_tokens"] = retry_kwargs.pop("max_completion_tokens")
            changed = True
        if not changed:
            raise
        response = client.chat.completions.create(**retry_kwargs)
        return response, dict(retry_kwargs)


def extract_usage(response: Any) -> tuple[dict[str, Any], Any]:
    """Normalize usage fields; preserve raw usage JSON-compatible dict."""
    usage_obj = getattr(response, "usage", None)
    if usage_obj is None:
        return {
            "input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "reasoning_tokens": None,
            "total_tokens": None,
        }, None

    if hasattr(usage_obj, "model_dump"):
        raw = usage_obj.model_dump()
    elif hasattr(usage_obj, "to_dict"):
        raw = usage_obj.to_dict()
    elif isinstance(usage_obj, dict):
        raw = dict(usage_obj)
    else:
        raw = {
            "prompt_tokens": getattr(usage_obj, "prompt_tokens", None),
            "completion_tokens": getattr(usage_obj, "completion_tokens", None),
            "total_tokens": getattr(usage_obj, "total_tokens", None),
            "input_tokens": getattr(usage_obj, "input_tokens", None),
            "output_tokens": getattr(usage_obj, "output_tokens", None),
        }
        details = getattr(usage_obj, "completion_tokens_details", None) or getattr(
            usage_obj, "output_tokens_details", None
        )
        if details is not None:
            if hasattr(details, "model_dump"):
                raw["completion_tokens_details"] = details.model_dump()
            else:
                raw["completion_tokens_details"] = {
                    "reasoning_tokens": getattr(details, "reasoning_tokens", None),
                }

    prompt_details = raw.get("prompt_tokens_details") or raw.get("input_tokens_details") or {}
    completion_details = (
        raw.get("completion_tokens_details") or raw.get("output_tokens_details") or {}
    )
    if not isinstance(prompt_details, dict):
        prompt_details = {}
    if not isinstance(completion_details, dict):
        completion_details = {}

    input_tokens = raw.get("prompt_tokens")
    if input_tokens is None:
        input_tokens = raw.get("input_tokens")
    output_tokens = raw.get("completion_tokens")
    if output_tokens is None:
        output_tokens = raw.get("output_tokens")

    normalized = {
        "input_tokens": input_tokens,
        "cached_input_tokens": prompt_details.get("cached_tokens"),
        "output_tokens": output_tokens,
        "reasoning_tokens": completion_details.get("reasoning_tokens"),
        "total_tokens": raw.get("total_tokens"),
    }
    return normalized, raw


def classify_api_error(exc: BaseException) -> dict[str, Any]:
    """Classify access errors without falling back to another model."""
    text = str(exc)
    lower = text.lower()
    error_type = "model_access_error"
    category = "unknown"
    if "rate limit" in lower or "429" in lower:
        category = "rate_limit"
    elif "insufficient_quota" in lower or "billing" in lower or "payment" in lower:
        category = "billing"
    elif "403" in lower or "permission" in lower or "not available" in lower or "model_not_found" in lower or "does not exist" in lower or "404" in lower:
        category = "project_permission"
    elif "401" in lower or "invalid api key" in lower or "authentication" in lower:
        category = "authentication"
    elif "expecting value" in lower or "json" in lower or "empty" in lower:
        error_type = "empty_or_invalid_json_response"
        category = "empty_or_invalid_json_response"
    return {
        "error_type": error_type,
        "category": category,
        "message": text[:500],
    }
