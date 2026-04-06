from __future__ import annotations

import json
from typing import Any

from tools.story_idea_pack_llm_builder import (
    DEFAULT_TIMEOUT_SECONDS,
    LlmConfigError,
    LlmExhaustedError,
    LlmResponseError,
    LlmTransportError,
    TransportFn,
    build_provider_chat_completions_options,
    build_direct_route_candidate,
    describe_route,
    extract_chat_output_text,
    extract_responses_output_text,
    normalize_route_candidate,
    post_json_api,
    resolve_api_key_for_route,
    resolve_header_values,
)
from tools.story_plan_builder import (
    build_plan_context,
    normalize_plan_count,
    normalize_pack,
    normalize_target_chapter_count,
    normalize_target_char_range,
)


PLAN_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "plans": {
            "type": "array",
            "minItems": 3,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "variant_label": {"type": "string"},
                    "title": {"type": "string"},
                    "genre_tone": {"type": "string"},
                    "selling_point": {"type": "string"},
                    "protagonist_profile": {"type": "string"},
                    "protagonist_goal": {"type": "string"},
                    "core_relationship": {"type": "string"},
                    "main_conflict": {"type": "string"},
                    "key_turning_point": {"type": "string"},
                    "ending_direction": {"type": "string"},
                    "chapter_rhythm": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "chapter_number": {"type": "integer"},
                                "stage": {"type": "string"},
                                "focus": {"type": "string"},
                                "advance": {"type": "string"},
                                "chapter_hook": {"type": "string"},
                            },
                            "required": [
                                "chapter_number",
                                "stage",
                                "focus",
                                "advance",
                                "chapter_hook",
                            ],
                        },
                    },
                    "writing_brief": {"type": "object"},
                },
                "required": [
                    "variant_label",
                    "title",
                    "genre_tone",
                    "selling_point",
                    "protagonist_profile",
                    "protagonist_goal",
                    "core_relationship",
                    "main_conflict",
                    "key_turning_point",
                    "ending_direction",
                    "chapter_rhythm",
                    "writing_brief",
                ],
            },
        }
    },
    "required": ["plans"],
}
MAX_PLAN_REPAIR_ATTEMPTS = 2


def _normalize_output_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LlmResponseError(f"LLM 返回结果缺少必要字段：{field_name}")
    return value.strip()


def build_story_plan_max_tokens(*, target_chapter_count: int, plan_count: int) -> int:
    return min(6144, max(4096, 768 + target_chapter_count * plan_count * 192))


def build_story_plan_common_prompt(
    *,
    pack: dict[str, Any],
    target_char_range: tuple[int, int],
    target_chapter_count: int,
    plan_count: int,
    repair_error: str | None = None,
) -> str:
    context = build_plan_context(pack)
    repair_block = ""
    if repair_error:
        repair_block = (
            "\n上一版输出不合格，必须整组重写，不要解释。\n"
            f"上一版问题：{repair_error}\n"
            "这次必须优先保证 JSON 合法、plans 数量充足、chapter_rhythm 结构完整。\n"
        )
    return (
        "你是中文短篇小说策划编辑。\n"
        "你当前只负责输出故事方案，不要写正文。\n"
        "输出必须是中文，并且只能返回合法 JSON。\n"
        f"请围绕下面这组已确定创意包，生成 {plan_count} 组差异明显的故事方案。\n"
        "每组方案必须包含：variant_label、title、genre_tone、selling_point、"
        "protagonist_profile、protagonist_goal、core_relationship、main_conflict、"
        "key_turning_point、ending_direction、chapter_rhythm、writing_brief。\n"
        "title 要尽量控制在 6-16 个汉字，不要直接复读钩子原句。\n"
        f"chapter_rhythm 必须恰好包含 {target_chapter_count} 章。\n"
        f"writing_brief 的 target_char_range 必须是 [{target_char_range[0]}, {target_char_range[1]}]。\n"
        f"writing_brief 的 target_chapter_count 必须是 {target_chapter_count}。\n"
        "不同方案之间至少要在冲突推进、关系重心、转折方式或结尾落点上明显不同。\n"
        f"创意包风格：{context['style']}\n"
        f"风格理由：{context['style_reason']}\n"
        f"钩子：{context['hook']}\n"
        f"核心关系：{context['core_relationship']}\n"
        f"主冲突：{context['main_conflict']}\n"
        f"反转方向：{context['reversal_direction']}\n"
        f"推荐标签：{', '.join(context['recommended_tags'])}\n"
        + repair_block
    )


def build_story_plan_responses_payload(
    *,
    pack: dict[str, Any],
    model: str,
    target_char_range: tuple[int, int],
    target_chapter_count: int,
    plan_count: int,
    repair_error: str | None = None,
) -> dict[str, Any]:
    prompt = build_story_plan_common_prompt(
        pack=pack,
        target_char_range=target_char_range,
        target_chapter_count=target_chapter_count,
        plan_count=plan_count,
        repair_error=repair_error,
    )
    return {
        "model": model,
        "instructions": "请严格按照 JSON Schema 返回结果。",
        "input": prompt,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "story_plans",
                "schema": PLAN_JSON_SCHEMA,
                "strict": True,
            }
        },
    }


def build_story_plan_chat_completions_payload(
    *,
    pack: dict[str, Any],
    model: str,
    target_char_range: tuple[int, int],
    target_chapter_count: int,
    plan_count: int,
    repair_error: str | None = None,
) -> dict[str, Any]:
    prompt = build_story_plan_common_prompt(
        pack=pack,
        target_char_range=target_char_range,
        target_chapter_count=target_chapter_count,
        plan_count=plan_count,
        repair_error=repair_error,
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是中文短篇小说策划编辑。"
                    "你必须只返回一个 JSON 对象，不要返回 Markdown 代码块，不要解释。"
                    "顶层字段固定为 plans，plans 是数组。"
                    "每个 plan 都必须带 variant_label、title、genre_tone、selling_point、"
                    "protagonist_profile、protagonist_goal、core_relationship、main_conflict、"
                    "key_turning_point、ending_direction、chapter_rhythm、writing_brief。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n"
                    "请只返回一个 JSON 对象，格式示例："
                    '{"plans":[{"variant_label":"方案一","title":"示例标题","genre_tone":"...","selling_point":"...",'
                    '"protagonist_profile":"...","protagonist_goal":"...","core_relationship":"...","main_conflict":"...",'
                    '"key_turning_point":"...","ending_direction":"...","chapter_rhythm":[{"chapter_number":1,"stage":"...",'
                    '"focus":"...","advance":"...","chapter_hook":"..."}],"writing_brief":{"title":"示例标题","genre_tone":"...",'
                    f'"target_char_range":[{target_char_range[0]},{target_char_range[1]}],"target_chapter_count":{target_chapter_count},'
                    '"protagonist_profile":"...","protagonist_goal":"...","core_relationship":"...","main_conflict":"...",'
                    '"key_turning_point":"...","ending_direction":"..."}}]}'
                ),
            },
        ],
    }


def parse_story_plans_output(
    *,
    raw_text: str,
    pack: dict[str, Any],
    route: dict[str, Any],
    target_char_range: tuple[int, int],
    target_chapter_count: int,
    plan_count: int,
    provider_response_id: str,
) -> list[dict[str, Any]]:
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
    raw_plans = parsed.get("plans")
    if not isinstance(raw_plans, list) or len(raw_plans) < plan_count:
        raise LlmResponseError("LLM 返回的 plans 数量不足。")

    context = build_plan_context(pack)
    normalized_plans: list[dict[str, Any]] = []
    for variant_index, raw_plan in enumerate(raw_plans[:plan_count], start=1):
        if not isinstance(raw_plan, dict):
            raise LlmResponseError("plans 里的每一项都必须是对象。")
        variant_label = _normalize_output_string(raw_plan.get("variant_label"), "variant_label")
        title = _normalize_output_string(raw_plan.get("title"), "title")
        genre_tone = _normalize_output_string(raw_plan.get("genre_tone"), "genre_tone")
        selling_point = _normalize_output_string(raw_plan.get("selling_point"), "selling_point")
        protagonist_profile = _normalize_output_string(
            raw_plan.get("protagonist_profile"),
            "protagonist_profile",
        )
        protagonist_goal = _normalize_output_string(
            raw_plan.get("protagonist_goal"),
            "protagonist_goal",
        )
        core_relationship = _normalize_output_string(
            raw_plan.get("core_relationship"),
            "core_relationship",
        )
        main_conflict = _normalize_output_string(raw_plan.get("main_conflict"), "main_conflict")
        key_turning_point = _normalize_output_string(
            raw_plan.get("key_turning_point"),
            "key_turning_point",
        )
        ending_direction = _normalize_output_string(
            raw_plan.get("ending_direction"),
            "ending_direction",
        )

        chapter_rhythm = raw_plan.get("chapter_rhythm")
        if not isinstance(chapter_rhythm, list) or len(chapter_rhythm) < target_chapter_count:
            raise LlmResponseError("chapter_rhythm 数量不足。")
        normalized_rhythm: list[dict[str, Any]] = []
        for chapter_index, beat in enumerate(chapter_rhythm[:target_chapter_count], start=1):
            if not isinstance(beat, dict):
                raise LlmResponseError("chapter_rhythm 里的每一项都必须是对象。")
            normalized_rhythm.append(
                {
                    "chapter_number": chapter_index,
                    "stage": _normalize_output_string(beat.get("stage"), "chapter_rhythm.stage"),
                    "focus": _normalize_output_string(beat.get("focus"), "chapter_rhythm.focus"),
                    "advance": _normalize_output_string(beat.get("advance"), "chapter_rhythm.advance"),
                    "chapter_hook": _normalize_output_string(
                        beat.get("chapter_hook"),
                        "chapter_rhythm.chapter_hook",
                    ),
                }
            )

        writing_brief = raw_plan.get("writing_brief")
        if not isinstance(writing_brief, dict):
            raise LlmResponseError("LLM 返回结果缺少必要字段：writing_brief")

        normalized_plans.append(
            {
                "pack_id": context["pack_id"],
                "source_mode": context["source_mode"],
                "style": context["style"],
                "variant_index": variant_index,
                "variant_key": f"llm_variant_{variant_index}",
                "variant_label": variant_label,
                "generation_mode": "llm",
                "provider_name": route["provider_name"],
                "api_mode": route["api_mode"],
                "model_name": route["model_name"],
                "model_config_key": route["model_config_key"],
                "provider_response_id": provider_response_id,
                "title": title,
                "genre_tone": genre_tone,
                "selling_point": selling_point,
                "protagonist_profile": protagonist_profile,
                "protagonist_goal": protagonist_goal,
                "core_relationship": core_relationship,
                "main_conflict": main_conflict,
                "key_turning_point": key_turning_point,
                "ending_direction": ending_direction,
                "chapter_rhythm": normalized_rhythm,
                "writing_brief": {
                    "title": title,
                    "genre_tone": genre_tone,
                    "target_char_range": [target_char_range[0], target_char_range[1]],
                    "target_chapter_count": target_chapter_count,
                    "protagonist_profile": protagonist_profile,
                    "protagonist_goal": protagonist_goal,
                    "core_relationship": core_relationship,
                    "main_conflict": main_conflict,
                    "key_turning_point": key_turning_point,
                    "ending_direction": ending_direction,
                },
            }
        )

    return normalized_plans


def build_llm_story_plans_from_route(
    *,
    pack: dict[str, Any],
    route: dict[str, Any],
    target_char_range: list[int] | tuple[int, int] | None = None,
    target_chapter_count: int | None = None,
    plan_count: int | None = None,
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    normalized_pack = normalize_pack(pack)
    normalized_target_char_range = normalize_target_char_range(
        list(target_char_range) if isinstance(target_char_range, tuple) else target_char_range,
        style=normalized_pack["style"],
    )
    normalized_target_chapter_count = normalize_target_chapter_count(target_chapter_count)
    normalized_plan_count = normalize_plan_count(plan_count)
    normalized_route = normalize_route_candidate(route)
    resolved_api_key = resolve_api_key_for_route(normalized_route)
    extra_headers = resolve_header_values(normalized_route["header_env_names"])

    last_error: LlmResponseError | None = None
    for _repair_attempt_index in range(MAX_PLAN_REPAIR_ATTEMPTS + 1):
        if normalized_route["api_mode"] == "responses":
            request_payload = build_story_plan_responses_payload(
                pack=pack,
                model=normalized_route["model_name"],
                target_char_range=normalized_target_char_range,
                target_chapter_count=normalized_target_chapter_count,
                plan_count=normalized_plan_count,
                repair_error=str(last_error) if last_error else None,
            )
        else:
            request_payload = build_story_plan_chat_completions_payload(
                pack=pack,
                model=normalized_route["model_name"],
                target_char_range=normalized_target_char_range,
                target_chapter_count=normalized_target_chapter_count,
                plan_count=normalized_plan_count,
                repair_error=str(last_error) if last_error else None,
            )
            request_payload.update(
                build_provider_chat_completions_options(
                    route=normalized_route,
                    max_tokens=build_story_plan_max_tokens(
                        target_chapter_count=normalized_target_chapter_count,
                        plan_count=normalized_plan_count,
                    ),
                    stream=True,
                )
            )

        response_payload = transport(
            api_url=normalized_route["api_url"],
            api_key=resolved_api_key,
            payload=request_payload,
            timeout_seconds=normalized_route.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS),
            extra_headers=extra_headers,
        )
        if normalized_route["api_mode"] == "responses":
            output_text = extract_responses_output_text(response_payload)
        else:
            output_text = extract_chat_output_text(response_payload)

        try:
            return {
                "plans": parse_story_plans_output(
                    raw_text=output_text,
                    pack=pack,
                    route=normalized_route,
                    target_char_range=normalized_target_char_range,
                    target_chapter_count=normalized_target_chapter_count,
                    plan_count=normalized_plan_count,
                    provider_response_id=str(response_payload.get("id", "")).strip(),
                )
            }
        except LlmResponseError as exc:
            last_error = exc
            continue

    if last_error is None:
        raise LlmResponseError("LLM 方案生成失败。")
    raise last_error


def build_llm_story_plans_with_fallbacks(
    *,
    pack: dict[str, Any],
    routes: list[dict[str, Any]],
    target_char_range: list[int] | tuple[int, int] | None = None,
    target_chapter_count: int | None = None,
    plan_count: int | None = None,
    agent_fallback: bool = False,
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    if not isinstance(routes, list) or not routes:
        raise LlmConfigError("routes 必须是非空对象数组。")
    if not isinstance(agent_fallback, bool):
        raise LlmConfigError("agent_fallback 必须是布尔值。")

    attempts: list[dict[str, Any]] = []
    for index, route in enumerate(routes, start=1):
        route_snapshot = describe_route(route)
        try:
            built = build_llm_story_plans_from_route(
                pack=pack,
                route=route,
                target_char_range=target_char_range,
                target_chapter_count=target_chapter_count,
                plan_count=plan_count,
                transport=transport,
            )
            success_attempt = {
                "attempt_index": index,
                **route_snapshot,
                "status": "success",
            }
            built["attempt_count"] = len(attempts) + 1
            built["fallback_used"] = len(attempts) > 0
            built["attempts"] = [*attempts, success_attempt]
            return built
        except (LlmConfigError, LlmTransportError, LlmResponseError) as exc:
            attempts.append(
                {
                    "attempt_index": index,
                    **route_snapshot,
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )

    message = "候选 LLM 模型全部失败。"
    if agent_fallback:
        message += " 请由 agent 兜底。"
    raise LlmExhaustedError(
        message,
        attempts=attempts,
        agent_fallback_required=agent_fallback,
    )


def build_llm_story_plans(
    *,
    pack: dict[str, Any],
    model: str | None = None,
    provider: str | None = None,
    api_mode: str | None = None,
    api_key: str | None = None,
    api_url: str | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    target_char_range: list[int] | tuple[int, int] | None = None,
    target_chapter_count: int | None = None,
    plan_count: int | None = None,
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
    built = build_llm_story_plans_from_route(
        pack=pack,
        route=route,
        target_char_range=target_char_range,
        target_chapter_count=target_chapter_count,
        plan_count=plan_count,
        transport=transport,
    )
    built["attempt_count"] = 1
    built["fallback_used"] = False
    built["attempts"] = [
        {
            "attempt_index": 1,
            "model_config_key": route.get("model_config_key", ""),
            "provider_name": route["provider_name"],
            "api_mode": route["api_mode"],
            "model_name": route["model_name"],
            "status": "success",
        }
    ]
    return built
