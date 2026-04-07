from __future__ import annotations

from typing import Any


def _coerce_non_negative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    return 0


def build_empty_token_usage() -> dict[str, int]:
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }


def normalize_token_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return build_empty_token_usage()

    prompt_tokens = _coerce_non_negative_int(value.get("prompt_tokens", value.get("input_tokens", 0)))
    completion_tokens = _coerce_non_negative_int(
        value.get("completion_tokens", value.get("output_tokens", 0))
    )
    total_tokens = _coerce_non_negative_int(value.get("total_tokens", 0))
    if total_tokens == 0 and (prompt_tokens > 0 or completion_tokens > 0):
        total_tokens = prompt_tokens + completion_tokens

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def merge_token_usages(*values: Any) -> dict[str, int]:
    merged = build_empty_token_usage()
    for value in values:
        normalized = normalize_token_usage(value)
        merged["prompt_tokens"] += normalized["prompt_tokens"]
        merged["completion_tokens"] += normalized["completion_tokens"]
        merged["total_tokens"] += normalized["total_tokens"]
    return merged


def has_token_usage(value: Any) -> bool:
    normalized = normalize_token_usage(value)
    return any(normalized.values())


def extract_token_usage_from_response(response_payload: dict[str, Any]) -> dict[str, int]:
    if not isinstance(response_payload, dict):
        return build_empty_token_usage()
    return normalize_token_usage(response_payload.get("usage", {}))
