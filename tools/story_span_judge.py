from __future__ import annotations

import json
from typing import Any

from tools.story_draft_llm_builder import parse_llm_json_object
from tools.story_idea_pack_llm_builder import (
    DEFAULT_TIMEOUT_SECONDS,
    LlmConfigError,
    LlmExhaustedError,
    LlmResponseError,
    LlmTransportError,
    TransportFn,
    build_chat_message_content,
    build_direct_route_candidate,
    build_provider_chat_completions_options,
    describe_route,
    extract_chat_output_text,
    extract_responses_output_text,
    normalize_route_candidate,
    post_json_api,
    resolve_api_key_for_route,
    resolve_header_values,
)
from tools.story_span_rewriter import apply_changed_spans
from tools.story_token_usage import (
    build_empty_token_usage,
    extract_token_usage_from_response,
    merge_token_usages,
    normalize_token_usage,
)


VALID_SPAN_JUDGE_DECISIONS = {"accept", "reject", "review"}
SPAN_JUDGE_MAX_TOKENS = 1200
SPAN_CONTEXT_WINDOW = 60
DEFAULT_REVIEW_REASON = "LLM 未返回该片段的明确判定。"

SPAN_JUDGE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target_index": {"type": "integer"},
                    "decision": {
                        "type": "string",
                        "enum": ["accept", "reject", "review"],
                    },
                    "reason": {"type": "string"},
                    "agent_review_required": {"type": "boolean"},
                },
                "required": ["target_index", "decision", "reason", "agent_review_required"],
            },
        }
    },
    "required": ["items"],
}


def extract_span_context(
    content_markdown: str,
    *,
    start_offset: int,
    end_offset: int,
    window: int = SPAN_CONTEXT_WINDOW,
) -> str:
    safe_start = max(0, start_offset - window)
    safe_end = min(len(content_markdown), end_offset + window)
    return content_markdown[safe_start:safe_end].strip()


def build_span_judge_candidates(
    *,
    before_content_markdown: str,
    changed_spans: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for span in changed_spans:
        before_excerpt = extract_span_context(
            before_content_markdown,
            start_offset=int(span["start_offset"]),
            end_offset=int(span["end_offset"]),
        )
        after_excerpt = before_excerpt.replace(
            str(span["original_text"]),
            str(span["rewritten_text"]),
            1,
        )
        if after_excerpt == before_excerpt:
            after_excerpt = str(span["rewritten_text"])
        candidates.append(
            {
                "target_index": int(span["target_index"]),
                "issue_code": str(span["issue_code"]),
                "chapter_number": span.get("chapter_number"),
                "requested_rewrite_modes": list(span.get("requested_rewrite_modes", [])),
                "applied_rewrite_modes": list(span.get("applied_rewrite_modes", [])),
                "risk_flags": list(span.get("risk_flags", [])),
                "before_span": str(span["original_text"]),
                "after_span": str(span["rewritten_text"]),
                "before_excerpt": before_excerpt,
                "after_excerpt": after_excerpt,
            }
        )
    return candidates


def build_story_span_judge_common_prompt(
    *,
    style: str,
    changed_spans: list[dict[str, Any]],
    before_content_markdown: str,
) -> str:
    candidates = build_span_judge_candidates(
        before_content_markdown=before_content_markdown,
        changed_spans=changed_spans,
    )
    serialized_candidates = json.dumps(candidates, ensure_ascii=False, indent=2)
    return (
        "你是中文小说修订复核员。你的任务不是继续润色，而是判断每个改写片段是否应该被接受。\n"
        f"当前风格：{style or '未指定'}\n"
        "判定标准：\n"
        "1. accept：改写更自然、更准确，没有病句、错插、语义跑偏或人物口吻失真。\n"
        "2. reject：改写明显变差，出现病句、语义错误、对白被破坏、人物说话方式被改坏等问题。\n"
        "3. review：你不能稳定判断，或者这个片段风险较高，需要 agent 再读一遍。\n"
        "4. risk_flags 只是提醒，不是自动否决条件；只有在内容真的变差时才 reject。\n"
        "5. 只返回 JSON，不要输出额外说明。\n\n"
        "待判定片段如下：\n"
        f"{serialized_candidates}\n\n"
        "请返回 JSON 对象，格式必须是："
        '{"items":[{"target_index":1,"decision":"accept","reason":"...","agent_review_required":false}]}'
    )


def build_story_span_judge_responses_payload(
    *,
    model: str,
    style: str,
    changed_spans: list[dict[str, Any]],
    before_content_markdown: str,
) -> dict[str, Any]:
    prompt = build_story_span_judge_common_prompt(
        style=style,
        changed_spans=changed_spans,
        before_content_markdown=before_content_markdown,
    )
    return {
        "model": model,
        "instructions": "请严格按照 JSON Schema 返回结果。",
        "input": prompt,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "story_span_judgements",
                "schema": SPAN_JUDGE_JSON_SCHEMA,
                "strict": True,
            }
        },
    }


def build_story_span_judge_chat_completions_payload(
    *,
    model: str,
    style: str,
    changed_spans: list[dict[str, Any]],
    before_content_markdown: str,
) -> dict[str, Any]:
    prompt = build_story_span_judge_common_prompt(
        style=style,
        changed_spans=changed_spans,
        before_content_markdown=before_content_markdown,
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": build_chat_message_content(
                    "你是严格的中文小说修订评审，只负责接受、拒绝或转交复核。"
                ),
            },
            {
                "role": "user",
                "content": build_chat_message_content(prompt),
            },
        ],
    }


def normalize_span_judge_item(
    item: dict[str, Any],
    *,
    span_lookup: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise LlmResponseError("LLM 判定结果 items 里的每一项都必须是对象。")
    raw_target_index = item.get("target_index")
    if isinstance(raw_target_index, bool) or not isinstance(raw_target_index, int):
        raise LlmResponseError("LLM 判定结果缺少合法的 target_index。")
    if raw_target_index not in span_lookup:
        raise LlmResponseError(f"LLM 判定结果包含未知的 target_index={raw_target_index}。")
    raw_decision = item.get("decision")
    if not isinstance(raw_decision, str) or raw_decision.strip() not in VALID_SPAN_JUDGE_DECISIONS:
        raise LlmResponseError("LLM 判定结果 decision 必须是 accept/reject/review 之一。")
    reason = item.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise LlmResponseError("LLM 判定结果 reason 必须是非空字符串。")
    agent_review_required = item.get("agent_review_required")
    if not isinstance(agent_review_required, bool):
        raise LlmResponseError("LLM 判定结果 agent_review_required 必须是布尔值。")

    span = span_lookup[raw_target_index]
    return {
        "target_index": raw_target_index,
        "issue_code": span["issue_code"],
        "chapter_number": span.get("chapter_number"),
        "decision": raw_decision.strip(),
        "reason": reason.strip(),
        "agent_review_required": agent_review_required or raw_decision.strip() == "review",
        "risk_flags": list(span.get("risk_flags", [])),
        "before_span": span["original_text"],
        "after_span": span["rewritten_text"],
    }


def parse_story_span_judge_output(
    *,
    raw_text: str,
    changed_spans: list[dict[str, Any]],
    route: dict[str, Any],
    provider_response_id: str,
) -> dict[str, Any]:
    parsed = parse_llm_json_object(raw_text)
    raw_items = parsed.get("items")
    if not isinstance(raw_items, list):
        raise LlmResponseError("LLM 判定结果缺少 items 数组。")

    span_lookup = {
        int(span["target_index"]): span
        for span in changed_spans
    }
    normalized_items: list[dict[str, Any]] = []
    for item in raw_items:
        normalized_items.append(
            normalize_span_judge_item(item, span_lookup=span_lookup)
        )

    existing_indexes = {item["target_index"] for item in normalized_items}
    for target_index, span in span_lookup.items():
        if target_index in existing_indexes:
            continue
        normalized_items.append(
            {
                "target_index": target_index,
                "issue_code": span["issue_code"],
                "chapter_number": span.get("chapter_number"),
                "decision": "review",
                "reason": DEFAULT_REVIEW_REASON,
                "agent_review_required": True,
                "risk_flags": list(span.get("risk_flags", [])),
                "before_span": span["original_text"],
                "after_span": span["rewritten_text"],
            }
        )

    normalized_items.sort(key=lambda item: item["target_index"])
    accepted_count = sum(1 for item in normalized_items if item["decision"] == "accept")
    rejected_count = sum(1 for item in normalized_items if item["decision"] == "reject")
    review_count = sum(1 for item in normalized_items if item["decision"] == "review")
    agent_review_required_count = sum(1 for item in normalized_items if item["agent_review_required"])

    return {
        "generation_mode": "llm",
        "provider_name": route["provider_name"],
        "api_mode": route["api_mode"],
        "model_name": route["model_name"],
        "model_config_key": route.get("model_config_key", ""),
        "provider_response_id": provider_response_id,
        "judge_items": normalized_items,
        "accepted_candidate_count": accepted_count,
        "rejected_candidate_count": rejected_count,
        "review_candidate_count": review_count,
        "agent_review_required_count": agent_review_required_count,
    }


def build_llm_story_span_judgement_from_route(
    *,
    before_content_markdown: str,
    changed_spans: list[dict[str, Any]],
    style: str,
    route: dict[str, Any],
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    if not isinstance(changed_spans, list) or not changed_spans:
        raise LlmConfigError("changed_spans 必须是非空数组。")

    normalized_route = normalize_route_candidate(route)
    resolved_api_key = resolve_api_key_for_route(normalized_route)
    extra_headers = resolve_header_values(normalized_route["header_env_names"])

    if normalized_route["api_mode"] == "responses":
        request_payload = build_story_span_judge_responses_payload(
            model=normalized_route["model_name"],
            style=style,
            changed_spans=changed_spans,
            before_content_markdown=before_content_markdown,
        )
    else:
        request_payload = build_story_span_judge_chat_completions_payload(
            model=normalized_route["model_name"],
            style=style,
            changed_spans=changed_spans,
            before_content_markdown=before_content_markdown,
        )
        request_payload.update(
            build_provider_chat_completions_options(
                route=normalized_route,
                max_tokens=SPAN_JUDGE_MAX_TOKENS,
                stream=False,
            )
        )

    response_payload = transport(
        api_url=normalized_route["api_url"],
        api_key=resolved_api_key,
        payload=request_payload,
        timeout_seconds=normalized_route.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
        extra_headers=extra_headers,
    )
    token_usage = extract_token_usage_from_response(response_payload)
    if normalized_route["api_mode"] == "responses":
        output_text = extract_responses_output_text(response_payload)
    else:
        output_text = extract_chat_output_text(response_payload)

    judged = parse_story_span_judge_output(
        raw_text=output_text,
        changed_spans=changed_spans,
        route=normalized_route,
        provider_response_id=str(response_payload.get("id", "")).strip(),
    )
    judged["token_usage"] = token_usage
    return judged


def build_llm_story_span_judgement_with_fallbacks(
    *,
    before_content_markdown: str,
    changed_spans: list[dict[str, Any]],
    style: str,
    routes: list[dict[str, Any]],
    agent_fallback: bool = False,
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    if not isinstance(routes, list) or not routes:
        raise LlmConfigError("routes 必须是非空对象数组。")
    if not isinstance(agent_fallback, bool):
        raise LlmConfigError("agent_fallback 必须是布尔值。")

    attempts: list[dict[str, Any]] = []
    total_token_usage = build_empty_token_usage()
    for index, route in enumerate(routes, start=1):
        route_snapshot = describe_route(route)
        try:
            judged = build_llm_story_span_judgement_from_route(
                before_content_markdown=before_content_markdown,
                changed_spans=changed_spans,
                style=style,
                route=route,
                transport=transport,
            )
            current_token_usage = judged.get("token_usage", {})
            total_token_usage = merge_token_usages(total_token_usage, current_token_usage)
            success_attempt = {
                "attempt_index": index,
                **route_snapshot,
                "status": "success",
                "token_usage": normalize_token_usage(current_token_usage),
            }
            judged["attempt_count"] = len(attempts) + 1
            judged["fallback_used"] = len(attempts) > 0
            judged["attempts"] = [*attempts, success_attempt]
            judged["token_usage"] = total_token_usage
            return judged
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

    message = "候选 LLM 判定模型全部失败。"
    if agent_fallback:
        message += " 请由 agent 兜底复核。"
    raise LlmExhaustedError(
        message,
        attempts=attempts,
        agent_fallback_required=agent_fallback,
        token_usage=total_token_usage,
    )


def build_llm_story_span_judgement(
    *,
    before_content_markdown: str,
    changed_spans: list[dict[str, Any]],
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
    judged = build_llm_story_span_judgement_from_route(
        before_content_markdown=before_content_markdown,
        changed_spans=changed_spans,
        style=style,
        route=route,
        transport=transport,
    )
    judged["attempt_count"] = 1
    judged["fallback_used"] = False
    judged["attempts"] = [
        {
            "attempt_index": 1,
            **describe_route(route),
            "status": "success",
            "token_usage": normalize_token_usage(judged.get("token_usage", {})),
        }
    ]
    return judged


def apply_llm_judge_to_changed_spans(
    *,
    before_content_markdown: str,
    rewrite_result: dict[str, Any],
    judge_result: dict[str, Any],
) -> dict[str, Any]:
    changed_spans = list(rewrite_result.get("changed_spans", []))
    judge_items = judge_result.get("judge_items", [])
    if not isinstance(judge_items, list):
        raise ValueError("judge_result.judge_items 必须是数组。")

    judge_lookup = {
        int(item["target_index"]): item
        for item in judge_items
        if isinstance(item, dict) and isinstance(item.get("target_index"), int)
    }
    accepted_spans: list[dict[str, Any]] = []
    rejected_spans: list[dict[str, Any]] = []
    review_spans: list[dict[str, Any]] = []
    candidate_spans: list[dict[str, Any]] = []
    for span in changed_spans:
        judge_item = judge_lookup.get(int(span["target_index"]))
        if judge_item is None:
            judge_item = {
                "decision": "review",
                "reason": DEFAULT_REVIEW_REASON,
                "agent_review_required": True,
            }
        annotated_span = {
            **span,
            "judge_decision": judge_item["decision"],
            "judge_reason": judge_item["reason"],
            "agent_review_required": bool(judge_item.get("agent_review_required", False)),
        }
        candidate_spans.append(annotated_span)
        if judge_item["decision"] == "accept":
            accepted_spans.append(annotated_span)
        elif judge_item["decision"] == "reject":
            rejected_spans.append(annotated_span)
        else:
            review_spans.append(annotated_span)

    after_content_markdown = (
        apply_changed_spans(before_content_markdown, accepted_spans)
        if accepted_spans
        else before_content_markdown
    )
    review_metadata = {
        "risk_alerts": list(rewrite_result.get("risk_alerts", [])),
        "risk_alert_count": int(rewrite_result.get("risk_alert_count", 0) or 0),
        "candidate_changed_span_count": len(candidate_spans),
        "candidate_changed_spans": candidate_spans,
        "accepted_candidate_count": len(accepted_spans),
        "rejected_candidate_count": len(rejected_spans),
        "agent_review_required_count": len(review_spans),
        "rejected_changed_spans": rejected_spans,
        "agent_review_required_spans": review_spans,
        "llm_judge": judge_result,
    }
    summary = (
        f"{rewrite_result['revision_summary']} "
        f"LLM 判定接受 {len(accepted_spans)} 个，拒绝 {len(rejected_spans)} 个，"
        f"转交 agent 复核 {len(review_spans)} 个。"
    ).strip()
    return {
        **rewrite_result,
        "changed_spans": accepted_spans,
        "changed_span_count": len(accepted_spans),
        "after_content_markdown": after_content_markdown,
        "review_metadata": review_metadata,
        "revision_summary": summary,
    }
