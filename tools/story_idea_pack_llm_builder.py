from __future__ import annotations

import json
import os
import socket
from typing import Any, Callable
import urllib.error
import urllib.request

from tools.story_idea_pack_builder import (
    VALID_STYLES,
    extract_display_label,
    unique_sorted_raw_values,
)
from tools.story_token_usage import (
    build_empty_token_usage,
    extract_token_usage_from_response,
    merge_token_usages,
    normalize_token_usage,
)


DEFAULT_LLM_MODEL = "gpt-5-mini"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_PROVIDER = "openai"
DEFAULT_API_MODE = "chat_completions"
VALID_DIRECT_LLM_PROVIDERS = {"openai", "openrouter", "deepseek"}
VALID_API_MODES = {"chat_completions", "responses"}

DEFAULT_OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_DEEPSEEK_CHAT_COMPLETIONS_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_PROVIDER_HEADER_ENVS = {
    "openrouter": {
        "HTTP-Referer": "OPENROUTER_HTTP_REFERER",
        "X-Title": "OPENROUTER_X_TITLE",
    }
}

STYLE_GUIDANCE = {
    "zhihu": "强调强钩子、强冲突、反转张力和快节奏，可筛选感要强。",
    "douban": "强调关系裂口、情绪余味、人物处境和暧昧留白，但仍要可筛选。",
}

IDEA_PACK_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "style_reason": {"type": "string"},
        "hook": {"type": "string"},
        "core_relationship": {"type": "string"},
        "main_conflict": {"type": "string"},
        "reversal_direction": {"type": "string"},
        "recommended_tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3,
        },
    },
    "required": [
        "style_reason",
        "hook",
        "core_relationship",
        "main_conflict",
        "reversal_direction",
        "recommended_tags",
    ],
}

TransportFn = Callable[..., dict[str, Any]]


class LlmConfigError(ValueError):
    """LLM 配置缺失或非法。"""


class LlmTransportError(RuntimeError):
    """调用上游模型服务失败。"""

    def __init__(self, message: str, *, token_usage: dict[str, int] | None = None) -> None:
        super().__init__(message)
        self.token_usage = normalize_token_usage(token_usage)


class LlmResponseError(RuntimeError):
    """上游返回内容不符合预期。"""

    def __init__(self, message: str, *, token_usage: dict[str, int] | None = None) -> None:
        super().__init__(message)
        self.token_usage = normalize_token_usage(token_usage)


class LlmExhaustedError(RuntimeError):
    """候选模型链路全部失败。"""

    def __init__(
        self,
        message: str,
        *,
        attempts: list[dict[str, Any]],
        agent_fallback_required: bool,
        token_usage: dict[str, int] | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.agent_fallback_required = agent_fallback_required
        self.token_usage = normalize_token_usage(token_usage)


def _read_windows_user_env(name: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - 非 Windows 环境
        return None

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
    except OSError:
        return None

    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def resolve_env_value(name: str) -> str | None:
    if name in os.environ:
        env_value = os.environ.get(name)
        if isinstance(env_value, str) and env_value.strip():
            return env_value.strip()
        return None
    return _read_windows_user_env(name)


def normalize_model_name(model: str | None = None) -> str:
    if model is None:
        return DEFAULT_LLM_MODEL
    if not isinstance(model, str) or not model.strip():
        raise LlmConfigError("model 必须是非空字符串。")
    return model.strip()


def normalize_timeout_seconds(timeout_seconds: int) -> int:
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 1:
        raise LlmConfigError("timeout_seconds 必须是大于等于 1 的整数。")
    return timeout_seconds


def normalize_direct_provider_name(provider: str | None = None) -> str:
    if provider is None:
        return DEFAULT_PROVIDER
    if not isinstance(provider, str) or not provider.strip():
        raise LlmConfigError("provider 必须是非空字符串。")
    normalized = provider.strip().lower()
    if normalized not in VALID_DIRECT_LLM_PROVIDERS:
        raise LlmConfigError(f"provider 仅支持：{sorted(VALID_DIRECT_LLM_PROVIDERS)}")
    return normalized


def normalize_provider_name(value: Any, field_name: str = "provider_name") -> str:
    if not isinstance(value, str) or not value.strip():
        raise LlmConfigError(f"{field_name} 必须是非空字符串。")
    return value.strip().lower()


def normalize_optional_key(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LlmConfigError(f"{field_name} 必须是字符串。")
    return value.strip()


def normalize_api_mode(api_mode: str | None = None) -> str:
    if api_mode is None:
        return DEFAULT_API_MODE
    if not isinstance(api_mode, str) or not api_mode.strip():
        raise LlmConfigError("api_mode 必须是非空字符串。")
    normalized = api_mode.strip().lower()
    if normalized not in VALID_API_MODES:
        raise LlmConfigError(f"api_mode 仅支持：{sorted(VALID_API_MODES)}")
    return normalized


def build_style_prompt(style: str) -> str:
    if style not in VALID_STYLES:
        raise ValueError("style 仅支持 zhihu 或 douban。")
    return STYLE_GUIDANCE[style]


def resolve_api_key(*, provider: str, api_key: str | None = None) -> str:
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()

    preferred_names: list[str]
    if provider == "openrouter":
        preferred_names = ["LLM_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"]
    elif provider == "deepseek":
        preferred_names = ["LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"]
    else:
        preferred_names = ["LLM_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"]

    for name in preferred_names:
        value = resolve_env_value(name)
        if value:
            return value

    raise LlmConfigError("缺少可用的 API Key 环境变量。请设置 LLM_API_KEY、OPENAI_API_KEY 或 OPENROUTER_API_KEY。")


def resolve_api_url(
    *,
    provider: str,
    api_mode: str,
    api_url: str | None = None,
) -> str:
    if isinstance(api_url, str) and api_url.strip():
        return api_url.strip()

    env_names: list[str]
    default_url: str
    if api_mode == "responses":
        env_names = ["LLM_RESPONSES_URL", "OPENAI_RESPONSES_URL"]
        default_url = DEFAULT_OPENAI_RESPONSES_URL
    elif provider == "openrouter":
        env_names = ["LLM_CHAT_COMPLETIONS_URL", "OPENROUTER_CHAT_COMPLETIONS_URL"]
        default_url = DEFAULT_OPENROUTER_CHAT_COMPLETIONS_URL
    elif provider == "deepseek":
        env_names = ["LLM_CHAT_COMPLETIONS_URL", "DEEPSEEK_CHAT_COMPLETIONS_URL"]
        default_url = DEFAULT_DEEPSEEK_CHAT_COMPLETIONS_URL
    else:
        env_names = ["LLM_CHAT_COMPLETIONS_URL", "OPENAI_CHAT_COMPLETIONS_URL"]
        default_url = DEFAULT_OPENAI_CHAT_COMPLETIONS_URL

    for name in env_names:
        value = resolve_env_value(name)
        if value:
            return value
    return default_url


def build_common_prompt(*, style: str, type_labels: list[str], tag_labels: list[str]) -> str:
    return (
        "你是中文短篇故事创意编辑。\n"
        "你当前只负责输出可筛选创意包，不要输出标题、章节节奏、结尾方案或正文。\n"
        "输出必须是中文，并且只能返回符合 JSON Schema 的内容。\n"
        "recommended_tags 必须恰好给出 3 个短标签。\n"
        f"目标风格：{style}\n"
        f"风格要求：{build_style_prompt(style)}\n"
        f"类型：{', '.join(type_labels)}\n"
        f"主标签：{', '.join(tag_labels)}\n"
        "请基于这组卡生成一个可筛选创意包。"
    )


def build_responses_payload(
    *,
    style: str,
    model: str,
    type_labels: list[str],
    tag_labels: list[str],
) -> dict[str, Any]:
    prompt = build_common_prompt(style=style, type_labels=type_labels, tag_labels=tag_labels)
    return {
        "model": model,
        "instructions": "请严格按照 JSON Schema 返回结果。",
        "input": prompt,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "idea_pack",
                "schema": IDEA_PACK_JSON_SCHEMA,
                "strict": True,
            }
        },
    }


def build_chat_completions_payload(
    *,
    style: str,
    model: str,
    type_labels: list[str],
    tag_labels: list[str],
) -> dict[str, Any]:
    prompt = build_common_prompt(style=style, type_labels=type_labels, tag_labels=tag_labels)
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是中文短篇故事创意编辑。"
                    "你必须只返回一个 JSON 对象，不要返回 Markdown 代码块，不要解释，不要补充说明。"
                    "固定字段必须是：style_reason、hook、core_relationship、main_conflict、reversal_direction、recommended_tags。"
                    "recommended_tags 必须是恰好 3 个字符串。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n"
                    "请只返回一个 JSON 对象，格式示例："
                    '{"style_reason":"...","hook":"...","core_relationship":"...","main_conflict":"...","reversal_direction":"...","recommended_tags":["...","...","..."]}'
                ),
            },
        ],
    }


def build_provider_chat_completions_options(
    *,
    route: dict[str, Any],
    max_tokens: int | None = None,
    stream: bool = False,
) -> dict[str, Any]:
    normalized_route = normalize_route_candidate(route)
    if normalized_route["api_mode"] != "chat_completions":
        return {}

    options: dict[str, Any] = {}
    if stream:
        options["stream"] = True
        if normalized_route["provider_name"] in {"openai", "openrouter"}:
            options["stream_options"] = {"include_usage": True}
    if normalized_route["provider_name"] == "deepseek":
        options["response_format"] = {"type": "json_object"}
        if max_tokens is not None:
            options["max_tokens"] = max_tokens
    return options


def _extract_stream_delta_text(choice: dict[str, Any]) -> str:
    delta = choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
            return "".join(parts)
    return ""


def _read_streaming_chat_completions_response(
    response: Any,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    provider_response_id = ""
    content_parts: list[str] = []
    token_usage_payload: dict[str, Any] | None = None

    while True:
        try:
            raw_line = response.readline()
        except (TimeoutError, socket.timeout) as exc:
            raise LlmTransportError(
                f"模型接口流式读取超时：连续 {timeout_seconds} 秒未收到新的数据块。"
            ) from exc

        if not raw_line:
            break

        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue

        data_line = line[5:].strip()
        if not data_line:
            continue
        if data_line == "[DONE]":
            break

        try:
            event_payload = json.loads(data_line)
        except json.JSONDecodeError as exc:
            raise LlmResponseError("模型接口返回了非法流式 JSON 数据。") from exc

        if not isinstance(event_payload, dict):
            continue

        if not provider_response_id:
            response_id = event_payload.get("id")
            if isinstance(response_id, str) and response_id.strip():
                provider_response_id = response_id.strip()

        usage_payload = event_payload.get("usage")
        if isinstance(usage_payload, dict):
            token_usage_payload = usage_payload

        choices = event_payload.get("choices")
        if not isinstance(choices, list) or not choices:
            continue
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            continue

        delta_text = _extract_stream_delta_text(first_choice)
        if delta_text:
            content_parts.append(delta_text)

    output_text = "".join(content_parts).strip()
    if not output_text:
        raise LlmResponseError("流式 chat/completions 响应里没有可用内容。")

    response_payload = {
        "id": provider_response_id,
        "choices": [
            {
                "message": {
                    "content": output_text,
                }
            }
        ],
    }
    if token_usage_payload is not None:
        response_payload["usage"] = token_usage_payload
    return response_payload


def _is_event_stream_response(response: Any) -> bool:
    headers = getattr(response, "headers", None)
    if headers is None:
        return True
    content_type = ""
    if hasattr(headers, "get"):
        content_type = headers.get("Content-Type", "")
    elif isinstance(headers, dict):
        content_type = str(headers.get("Content-Type", ""))
    if not isinstance(content_type, str) or not content_type.strip():
        return True
    return "text/event-stream" in content_type.lower()


def post_json_api(
    *,
    api_url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json; charset=utf-8",
    }
    if extra_headers:
        headers.update(extra_headers)

    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if payload.get("stream") is True and _is_event_stream_response(response):
                return _read_streaming_chat_completions_response(
                    response,
                    timeout_seconds=timeout_seconds,
                )
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            error_body = exc.read().decode("utf-8", errors="replace")
        except OSError:
            error_body = str(exc)
        raise LlmTransportError(f"模型接口返回 HTTP {exc.code}：{error_body}") from exc
    except urllib.error.URLError as exc:
        raise LlmTransportError(f"模型接口调用失败：{exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        if payload.get("stream") is True:
            raise LlmTransportError(
                f"模型接口流式读取超时：连续 {timeout_seconds} 秒未收到新的数据块。"
            ) from exc
        raise LlmTransportError(f"模型接口读取超时：{timeout_seconds} 秒内未返回完整响应。") from exc

    try:
        response_payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise LlmResponseError("模型接口返回了非法 JSON。") from exc
    if not isinstance(response_payload, dict):
        raise LlmResponseError("模型接口返回体必须是 JSON 对象。")
    return response_payload


def resolve_header_values(header_env_names: dict[str, str]) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for header_name, env_name in header_env_names.items():
        env_value = resolve_env_value(env_name)
        if env_value:
            resolved[header_name] = env_value
    return resolved


def extract_responses_output_text(response_payload: dict[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output_items = response_payload.get("output")
    if not isinstance(output_items, list):
        raise LlmResponseError("LLM 响应里缺少 output 内容。")

    for item in output_items:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content_item in content_items:
            if not isinstance(content_item, dict):
                continue
            text = content_item.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise LlmResponseError("无法从 Responses 响应中提取文本内容。")


def extract_chat_output_text(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmResponseError("chat/completions 响应里缺少 choices。")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LlmResponseError("chat/completions 响应缺少 message。")
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    raise LlmResponseError("无法从 chat/completions 响应中提取文本内容。")


def _normalize_output_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LlmResponseError(f"LLM 返回结果缺少必要字段：{field_name}")
    return value.strip()


def normalize_recommended_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise LlmResponseError("LLM 返回结果缺少必要字段：recommended_tags")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise LlmResponseError("recommended_tags 里的每一项都必须是非空字符串。")
        normalized_item = item.strip()
        if normalized_item in seen:
            continue
        seen.add(normalized_item)
        normalized.append(normalized_item)
    if len(normalized) != 3:
        raise LlmResponseError("recommended_tags 必须恰好包含 3 个去重后的标签。")
    return normalized


def parse_idea_pack_output(raw_text: str) -> dict[str, Any]:
    candidate_text = raw_text.strip()
    if candidate_text.startswith("```"):
        lines = candidate_text.splitlines()
        if len(lines) >= 3:
            candidate_text = "\n".join(lines[1:-1]).strip()

    try:
        parsed = json.loads(candidate_text)
    except json.JSONDecodeError as exc:
        start = candidate_text.find("{")
        end = candidate_text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LlmResponseError("LLM 返回的文本不是合法 JSON。") from exc
        try:
            parsed = json.loads(candidate_text[start : end + 1])
        except json.JSONDecodeError as inner_exc:
            raise LlmResponseError("LLM 返回的文本不是合法 JSON。") from inner_exc
    if not isinstance(parsed, dict):
        raise LlmResponseError("LLM 返回结果必须是 JSON 对象。")
    return {
        "style_reason": _normalize_output_string(parsed.get("style_reason"), "style_reason"),
        "hook": _normalize_output_string(parsed.get("hook"), "hook"),
        "core_relationship": _normalize_output_string(parsed.get("core_relationship"), "core_relationship"),
        "main_conflict": _normalize_output_string(parsed.get("main_conflict"), "main_conflict"),
        "reversal_direction": _normalize_output_string(parsed.get("reversal_direction"), "reversal_direction"),
        "recommended_tags": normalize_recommended_tags(parsed.get("recommended_tags")),
    }


def validate_build_inputs(card: dict[str, Any], style: str) -> dict[str, Any]:
    if style not in VALID_STYLES:
        raise ValueError("style 仅支持 zhihu 或 douban。")
    if not isinstance(card, dict):
        raise ValueError("card 必须是对象。")

    source_mode = card.get("source_mode")
    if not isinstance(source_mode, str) or not source_mode.strip():
        raise ValueError("card.source_mode 必须是非空字符串。")

    source_types = unique_sorted_raw_values(card.get("types"), "types")
    source_main_tags = unique_sorted_raw_values(card.get("main_tags"), "main_tags")
    if len(source_types) != 2:
        raise ValueError("card.types 需要恰好 2 个有效类型。")
    if len(source_main_tags) != 3:
        raise ValueError("card.main_tags 需要恰好 3 个有效主标签。")

    return {
        "source_mode": source_mode.strip(),
        "source_types": source_types,
        "source_main_tags": source_main_tags,
    }


def normalize_route_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise LlmConfigError("route candidate 必须是对象。")

    provider_name = normalize_provider_name(candidate.get("provider_name"), "provider_name")
    api_mode = normalize_api_mode(candidate.get("api_mode"))
    model_name = normalize_model_name(candidate.get("model_name"))
    api_url = normalize_optional_key(candidate.get("api_url"), "api_url")
    if not api_url:
        raise LlmConfigError("api_url 必须是非空字符串。")
    timeout_seconds = normalize_timeout_seconds(
        candidate.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    )
    model_config_key = normalize_optional_key(candidate.get("model_config_key"), "model_config_key")
    api_key = normalize_optional_key(candidate.get("api_key"), "api_key")
    api_key_env = normalize_optional_key(candidate.get("api_key_env"), "api_key_env")

    header_env_names = candidate.get("header_env_names", {})
    if not isinstance(header_env_names, dict):
        raise LlmConfigError("header_env_names 必须是对象。")
    normalized_header_env_names: dict[str, str] = {}
    for header_name, env_name in header_env_names.items():
        normalized_header_name = normalize_optional_key(header_name, "header_env_names.header_name")
        normalized_env_name = normalize_optional_key(env_name, "header_env_names.env_name")
        if not normalized_header_name or not normalized_env_name:
            raise LlmConfigError("header_env_names 里的键和值都必须是非空字符串。")
        normalized_header_env_names[normalized_header_name] = normalized_env_name

    if provider_name == "openrouter" and api_mode == "responses":
        raise LlmConfigError("openrouter 当前仅支持 chat_completions 模式。")

    return {
        "model_config_key": model_config_key,
        "provider_name": provider_name,
        "api_mode": api_mode,
        "model_name": model_name,
        "api_url": api_url,
        "timeout_seconds": timeout_seconds,
        "api_key": api_key,
        "api_key_env": api_key_env,
        "header_env_names": normalized_header_env_names,
    }


def build_direct_route_candidate(
    *,
    model: str | None = None,
    provider: str | None = None,
    api_mode: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    resolved_provider = normalize_direct_provider_name(provider)
    resolved_api_mode = normalize_api_mode(api_mode)
    return normalize_route_candidate(
        {
            "provider_name": resolved_provider,
            "api_mode": resolved_api_mode,
            "model_name": normalize_model_name(model),
            "api_url": resolve_api_url(
                provider=resolved_provider,
                api_mode=resolved_api_mode,
                api_url=api_url,
            ),
            "timeout_seconds": timeout_seconds,
            "api_key": normalize_optional_key(api_key, "api_key"),
            "api_key_env": "",
            "header_env_names": dict(DEFAULT_PROVIDER_HEADER_ENVS.get(resolved_provider, {})),
        }
    )


def resolve_api_key_for_route(route: dict[str, Any]) -> str:
    explicit_api_key = route.get("api_key", "")
    if explicit_api_key:
        return explicit_api_key

    api_key_env = route.get("api_key_env", "")
    if api_key_env:
        env_value = resolve_env_value(api_key_env)
        if env_value:
            return env_value
        raise LlmConfigError(f"环境变量 {api_key_env} 未配置有效 API Key。")

    return resolve_api_key(provider=route["provider_name"], api_key=None)


def build_llm_idea_pack_from_route(
    *,
    card: dict[str, Any],
    style: str,
    route: dict[str, Any],
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    card_context = validate_build_inputs(card, style)
    normalized_route = normalize_route_candidate(route)
    resolved_api_key = resolve_api_key_for_route(normalized_route)
    extra_headers = resolve_header_values(normalized_route["header_env_names"])

    type_labels = [extract_display_label(value) for value in card_context["source_types"]]
    tag_labels = [extract_display_label(value) for value in card_context["source_main_tags"]]
    if normalized_route["api_mode"] == "responses":
        request_payload = build_responses_payload(
            style=style,
            model=normalized_route["model_name"],
            type_labels=type_labels,
            tag_labels=tag_labels,
        )
    else:
        request_payload = build_chat_completions_payload(
            style=style,
            model=normalized_route["model_name"],
            type_labels=type_labels,
            tag_labels=tag_labels,
        )
        request_payload.update(
            build_provider_chat_completions_options(
                route=normalized_route,
                max_tokens=1200,
            )
        )

    response_payload = transport(
        api_url=normalized_route["api_url"],
        api_key=resolved_api_key,
        payload=request_payload,
        timeout_seconds=normalized_route["timeout_seconds"],
        extra_headers=extra_headers,
    )
    token_usage = extract_token_usage_from_response(response_payload)

    if normalized_route["api_mode"] == "responses":
        output_text = extract_responses_output_text(response_payload)
    else:
        output_text = extract_chat_output_text(response_payload)
    try:
        output_payload = parse_idea_pack_output(output_text)
    except LlmResponseError as exc:
        raise LlmResponseError(str(exc), token_usage=token_usage) from exc

    return {
        "source_mode": card_context["source_mode"],
        "style": style,
        "generation_mode": "llm",
        "provider_name": normalized_route["provider_name"],
        "api_mode": normalized_route["api_mode"],
        "model_name": normalized_route["model_name"],
        "model_config_key": normalized_route["model_config_key"],
        "provider_response_id": str(response_payload.get("id", "")).strip(),
        "style_reason": output_payload["style_reason"],
        "hook": output_payload["hook"],
        "core_relationship": output_payload["core_relationship"],
        "main_conflict": output_payload["main_conflict"],
        "reversal_direction": output_payload["reversal_direction"],
        "recommended_tags": output_payload["recommended_tags"],
        "source_cards": {
            "types": card_context["source_types"],
            "main_tags": card_context["source_main_tags"],
        },
        "token_usage": token_usage,
    }


def describe_route(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_config_key": normalize_optional_key(route.get("model_config_key"), "model_config_key"),
        "provider_name": normalize_optional_key(route.get("provider_name"), "provider_name"),
        "api_mode": normalize_optional_key(route.get("api_mode"), "api_mode"),
        "model_name": normalize_optional_key(route.get("model_name"), "model_name"),
    }


def build_llm_idea_pack_with_fallbacks(
    *,
    card: dict[str, Any],
    style: str,
    routes: list[dict[str, Any]],
    agent_fallback: bool = False,
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    validate_build_inputs(card, style)
    if not isinstance(routes, list) or not routes:
        raise LlmConfigError("routes 必须是非空对象数组。")
    if not isinstance(agent_fallback, bool):
        raise LlmConfigError("agent_fallback 必须是布尔值。")

    attempts: list[dict[str, Any]] = []
    total_token_usage = build_empty_token_usage()
    for index, route in enumerate(routes, start=1):
        route_snapshot = describe_route(route)
        try:
            pack = build_llm_idea_pack_from_route(
                card=card,
                style=style,
                route=route,
                transport=transport,
            )
            current_token_usage = pack.get("token_usage", {})
            total_token_usage = merge_token_usages(total_token_usage, current_token_usage)
            success_attempt = {
                "attempt_index": index,
                **route_snapshot,
                "status": "success",
                "token_usage": normalize_token_usage(current_token_usage),
            }
            all_attempts = [*attempts, success_attempt]
            pack["attempt_count"] = len(all_attempts)
            pack["fallback_used"] = len(attempts) > 0
            pack["attempts"] = all_attempts
            pack["token_usage"] = total_token_usage
            return pack
        except (LlmConfigError, LlmTransportError, LlmResponseError) as exc:
            current_token_usage = getattr(exc, "token_usage", {})
            total_token_usage = merge_token_usages(total_token_usage, current_token_usage)
            attempts.append(
                {
                    "attempt_index": index,
                    **route_snapshot,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "token_usage": normalize_token_usage(current_token_usage),
                }
            )

    message = "候选 LLM 模型全部失败。"
    if agent_fallback:
        message += " 请由 agent 兜底。"
    raise LlmExhaustedError(
        message,
        attempts=attempts,
        agent_fallback_required=agent_fallback,
        token_usage=total_token_usage,
    )


def build_llm_idea_pack(
    *,
    card: dict[str, Any],
    style: str,
    model: str | None = None,
    provider: str | None = None,
    api_mode: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    route = build_direct_route_candidate(
        model=model,
        provider=provider,
        api_mode=api_mode,
        api_key=api_key,
        api_url=api_url,
        timeout_seconds=timeout_seconds,
    )
    pack = build_llm_idea_pack_from_route(
        card=card,
        style=style,
        route=route,
        transport=transport,
    )
    pack["attempt_count"] = 1
    pack["fallback_used"] = False
    pack["attempts"] = [
        {
            "attempt_index": 1,
            "model_config_key": pack.get("model_config_key", ""),
            "provider_name": pack["provider_name"],
            "api_mode": pack["api_mode"],
            "model_name": pack["model_name"],
            "status": "success",
        }
    ]
    return pack
