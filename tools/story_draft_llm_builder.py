from __future__ import annotations

import json
import math
import re
from typing import Any

from tools.story_draft_builder import normalize_story_payload
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
from tools.story_structure_checker import count_content_chars
from tools.story_token_usage import (
    build_empty_token_usage,
    extract_token_usage_from_response,
    merge_token_usages,
    normalize_token_usage,
)


SUMMARY_CHAR_RANGE = (50, 120)
MAX_DRAFT_REPAIR_ATTEMPTS = 2
LONG_DRAFT_SEGMENT_MIN_CHARS = 10000
LONG_DRAFT_SEGMENT_MAX_CHARS = 12000
MIN_CHAPTER_BODY_CHARS = 500
STYLE_CHAPTER_MAX_SLACK = {
    "zhihu": 1800,
    "douban": 1600,
}
SUMMARY_MAX_OVERFLOW_FLOOR = 5
SUMMARY_MAX_OVERFLOW_CAP = 20
TOTAL_MAX_OVERFLOW_FLOOR = 100
TOTAL_MAX_OVERFLOW_CAP = 300
CHAPTER_MAX_OVERFLOW_FLOOR = 300
CHAPTER_MAX_OVERFLOW_CAP = 800
PROMPT_FIELD_LIMITS = {
    "genre_tone": 48,
    "selling_point": 80,
    "protagonist_profile": 72,
    "protagonist_goal": 72,
    "core_relationship": 96,
    "main_conflict": 96,
    "key_turning_point": 80,
    "ending_direction": 72,
    "summary_guidance": 88,
    "chapter_stage": 14,
    "chapter_focus": 32,
    "chapter_advance": 32,
    "chapter_hook": 28,
}
STYLE_DRAFT_GUIDANCE = {
    "zhihu": [
        "知乎风格优先把危险、代价和反转压到前台，推进要快，不要绕远。",
        "每章都要让冲突升级或认知翻面，不能只做背景说明。",
    ],
    "douban": [
        "豆瓣风格要把情绪落在具体场景、动作、停顿、对话和回忆触发上，不要空泛抒情。",
        "每章至少写出一个完整场景和一段有效对话，让关系变化真实发生，而不是一句话概括过去。",
    ],
}

DRAFT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "chapter_number": {"type": "integer"},
                    "content": {"type": "string"},
                },
                "required": ["chapter_number", "content"],
            },
        },
    },
    "required": ["summary", "chapters"],
}

SUMMARY_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
    },
    "required": ["summary"],
}

CHAPTER_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "chapter_number": {"type": "integer"},
        "content": {"type": "string"},
    },
    "required": ["chapter_number", "content"],
}


def _normalize_output_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LlmResponseError(f"LLM 返回结果缺少必要字段：{field_name}")
    return value.strip()


def parse_llm_json_object(raw_text: str) -> dict[str, Any]:
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
    return parsed


def extract_plain_text_candidate(raw_text: str) -> str:
    candidate_text = raw_text.strip()
    if candidate_text.startswith("```"):
        lines = candidate_text.splitlines()
        if len(lines) >= 3:
            candidate_text = "\n".join(lines[1:-1]).strip()

    candidate_text = re.sub(r"^\s*(summary|content)\s*[:：]\s*", "", candidate_text, flags=re.IGNORECASE)
    candidate_text = re.sub(r"^\s*第\s*[0-9一二三四五六七八九十]+\s*章\s*[:：]?\s*", "", candidate_text)
    candidate_text = re.sub(r"^\s*###\s*[0-9]+\s*", "", candidate_text)
    candidate_text = candidate_text.strip()
    if not candidate_text:
        raise LlmResponseError("LLM 返回结果缺少可用文本内容。")
    return candidate_text


def normalize_story_draft_summary(summary_text: str, *, min_chars: int, max_chars: int) -> tuple[str, int]:
    normalized = re.sub(r"\s+", " ", summary_text).strip()
    summary_chars = count_content_chars(normalized)
    return normalized, summary_chars


def normalize_story_draft_chapter_content(content: str, *, min_chars: int, max_chars: int) -> tuple[str, int]:
    normalized = content.strip().replace("\r\n", "\n").replace("\r", "\n")
    chapter_chars = count_content_chars(normalized)
    return normalized, chapter_chars


def calculate_small_overflow_allowance(
    max_chars: int,
    *,
    floor: int,
    cap: int,
) -> int:
    return max(floor, min(cap, max(1, max_chars // 10)))


def compact_prompt_text(value: Any, max_chars: int) -> str:
    if not isinstance(value, str):
        return ""
    normalized = " ".join(value.strip().split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def should_use_segmented_draft_generation(payload: dict[str, Any]) -> bool:
    normalized_payload = normalize_story_payload(payload)
    total_min, total_max = normalized_payload["target_char_range"]
    return total_min >= LONG_DRAFT_SEGMENT_MIN_CHARS or total_max > LONG_DRAFT_SEGMENT_MAX_CHARS


def build_story_draft_constraints(payload: dict[str, Any]) -> dict[str, int]:
    normalized_payload = normalize_story_payload(payload)
    summary_min, summary_max = SUMMARY_CHAR_RANGE
    total_min, total_max = normalized_payload["target_char_range"]
    body_min = max(1, total_min - summary_max)
    body_max = max(body_min, total_max - summary_min)
    per_chapter_target = max(MIN_CHAPTER_BODY_CHARS, body_min // normalized_payload["target_chapter_count"])
    return {
        "summary_min": summary_min,
        "summary_max": summary_max,
        "total_min": total_min,
        "total_max": total_max,
        "body_min": body_min,
        "body_max": body_max,
        "per_chapter_target": per_chapter_target,
    }


def build_story_draft_prompt_fields(payload: dict[str, Any]) -> dict[str, str]:
    normalized_payload = normalize_story_payload(payload)
    return {
        "genre_tone": compact_prompt_text(
            normalized_payload["genre_tone"],
            PROMPT_FIELD_LIMITS["genre_tone"],
        ),
        "selling_point": compact_prompt_text(
            normalized_payload["selling_point"],
            PROMPT_FIELD_LIMITS["selling_point"],
        ),
        "protagonist_profile": compact_prompt_text(
            normalized_payload["protagonist_profile"],
            PROMPT_FIELD_LIMITS["protagonist_profile"],
        ),
        "protagonist_goal": compact_prompt_text(
            normalized_payload["protagonist_goal"],
            PROMPT_FIELD_LIMITS["protagonist_goal"],
        ),
        "core_relationship": compact_prompt_text(
            normalized_payload["core_relationship"],
            PROMPT_FIELD_LIMITS["core_relationship"],
        ),
        "main_conflict": compact_prompt_text(
            normalized_payload["main_conflict"],
            PROMPT_FIELD_LIMITS["main_conflict"],
        ),
        "key_turning_point": compact_prompt_text(
            normalized_payload["key_turning_point"],
            PROMPT_FIELD_LIMITS["key_turning_point"],
        ),
        "ending_direction": compact_prompt_text(
            normalized_payload["ending_direction"],
            PROMPT_FIELD_LIMITS["ending_direction"],
        ),
        "summary_guidance": compact_prompt_text(
            normalized_payload["summary_guidance"],
            PROMPT_FIELD_LIMITS["summary_guidance"],
        ),
    }


def build_story_draft_chapter_lines(payload: dict[str, Any]) -> list[str]:
    normalized_payload = normalize_story_payload(payload)
    lines: list[str] = []
    for item in normalized_payload["chapter_blueprints"]:
        lines.append(
            (
                f"第{item['chapter_number']}章："
                f"阶段={compact_prompt_text(item['stage'], PROMPT_FIELD_LIMITS['chapter_stage'])}；"
                f"焦点={compact_prompt_text(item['focus'], PROMPT_FIELD_LIMITS['chapter_focus'])}；"
                f"推进={compact_prompt_text(item['advance'], PROMPT_FIELD_LIMITS['chapter_advance'])}；"
                f"章尾={compact_prompt_text(item['chapter_hook'], PROMPT_FIELD_LIMITS['chapter_hook'])}"
            )
        )
    return lines


def build_story_draft_existing_chapter_lines(existing_draft: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for chapter in existing_draft["chapters"]:
        lines.append(
            "\n".join(
                [
                    f"第{chapter['chapter_number']}章当前版本：",
                    chapter["content"],
                ]
            )
        )
    return lines


def summarize_existing_chapter_content(content: str, *, max_chars: int = 80) -> str:
    normalized = " ".join(content.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def build_previous_chapter_recap_lines(existing_chapters: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for chapter in existing_chapters:
        chapter_chars = count_content_chars(chapter["content"])
        lines.append(
            f"第{chapter['chapter_number']}章已完成（{chapter_chars}字）："
            f"{summarize_existing_chapter_content(chapter['content'])}"
        )
    return lines


def build_story_draft_output_from_parts(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    provider_response_id: str,
    summary_text: str,
    chapters: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_payload = normalize_story_payload(payload)
    constraints = build_story_draft_constraints(normalized_payload)
    normalized_summary_text, summary_char_count = normalize_story_draft_summary(
        summary_text,
        min_chars=constraints["summary_min"],
        max_chars=constraints["summary_max"],
    )

    markdown_parts = [
        f"# {normalized_payload['title']}",
        "",
        "## 简介",
        "",
        normalized_summary_text,
        "",
        "## 正文",
        "",
    ]
    normalized_chapters: list[dict[str, Any]] = []
    for expected_index, raw_chapter in enumerate(chapters, start=1):
        if not isinstance(raw_chapter, dict):
            raise LlmResponseError("chapters 里的每一项都必须是对象。")
        chapter_number = raw_chapter.get("chapter_number")
        if chapter_number != expected_index:
            raise LlmResponseError("chapter_number 必须从 1 开始连续递增。")
        content = _normalize_output_string(raw_chapter.get("content"), "chapters.content")
        normalized_chapters.append(
            {
                "chapter_number": chapter_number,
                "content": content,
            }
        )
        markdown_parts.extend(
            [
                f"### {chapter_number}",
                "",
                content,
                "",
            ]
        )

    body_char_count = sum(count_content_chars(item["content"]) for item in normalized_chapters)
    content_markdown = "\n".join(markdown_parts).strip() + "\n"
    return {
        "title": normalized_payload["title"],
        "summary_text": normalized_summary_text,
        "summary_char_count": summary_char_count,
        "chapters": normalized_chapters,
        "content_markdown": content_markdown,
        "body_char_count": body_char_count,
        "generation_mode": "llm",
        "provider_name": route["provider_name"],
        "api_mode": route["api_mode"],
        "model_name": route["model_name"],
        "model_config_key": route["model_config_key"],
        "provider_response_id": provider_response_id,
    }


def build_story_draft_chapter_targets(
    payload: dict[str, Any],
    *,
    summary_text: str,
    existing_chapters: list[dict[str, Any]],
) -> dict[str, int]:
    normalized_payload = normalize_story_payload(payload)
    constraints = build_story_draft_constraints(normalized_payload)
    _, summary_char_count = validate_story_draft_summary_text(
        payload=normalized_payload,
        summary_text=summary_text,
    )
    written_body_chars = sum(count_content_chars(item["content"]) for item in existing_chapters)
    remaining_chapter_count = normalized_payload["target_chapter_count"] - len(existing_chapters)
    if remaining_chapter_count < 1:
        raise LlmResponseError("当前没有可生成的剩余章节。")

    actual_body_min = max(0, constraints["total_min"] - summary_char_count)
    actual_body_max = max(actual_body_min, constraints["total_max"] - summary_char_count)
    remaining_body_min = max(0, actual_body_min - written_body_chars)
    remaining_body_max = max(remaining_body_min, actual_body_max - written_body_chars)
    chapter_min = max(MIN_CHAPTER_BODY_CHARS, math.ceil(remaining_body_min / remaining_chapter_count))
    average_chapter_max = max(chapter_min, math.ceil(remaining_body_max / remaining_chapter_count))
    future_chapter_count = max(0, remaining_chapter_count - 1)
    future_reserved_min = MIN_CHAPTER_BODY_CHARS * future_chapter_count
    style_slack = STYLE_CHAPTER_MAX_SLACK.get(normalized_payload["style"], 1200)
    chapter_max = min(
        remaining_body_max,
        max(
            chapter_min,
            average_chapter_max + style_slack,
        ),
    )
    if future_chapter_count > 0:
        chapter_max = min(
            chapter_max,
            max(chapter_min, remaining_body_max - future_reserved_min),
        )
    chapter_hard_max = min(
        remaining_body_max,
        max(
            chapter_max,
            average_chapter_max + style_slack * 2,
        ),
    )
    if future_chapter_count > 0:
        chapter_hard_max = min(
            chapter_hard_max,
            max(chapter_max, remaining_body_max - future_reserved_min),
        )
    chapter_target = max(chapter_min, min(average_chapter_max, math.ceil((chapter_min + chapter_max) / 2)))
    return {
        "written_body_chars": written_body_chars,
        "summary_char_count": summary_char_count,
        "remaining_body_min": remaining_body_min,
        "remaining_body_max": remaining_body_max,
        "remaining_chapter_count": remaining_chapter_count,
        "chapter_min": chapter_min,
        "chapter_max": chapter_max,
        "chapter_hard_max": chapter_hard_max,
        "chapter_target": chapter_target,
        "average_chapter_max": average_chapter_max,
    }


def build_story_draft_expansion_prompt(
    payload: dict[str, Any],
    *,
    repair_error: str,
    existing_draft: dict[str, Any],
) -> str:
    normalized_payload = normalize_story_payload(payload)
    constraints = build_story_draft_constraints(normalized_payload)
    prompt_fields = build_story_draft_prompt_fields(normalized_payload)
    style_rules = STYLE_DRAFT_GUIDANCE.get(normalized_payload["style"], [])
    return (
        "你正在修订一篇已经成形但不合格的中文短篇小说。\n"
        "不要换故事，不要改标题，不要减少章节，只能在现有基础上补强和重写。\n"
        f"标题固定为：{normalized_payload['title']}\n"
        f"题材氛围：{prompt_fields['genre_tone']}\n"
        f"主角目标：{prompt_fields['protagonist_goal']}\n"
        f"核心关系：{prompt_fields['core_relationship']}\n"
        f"主冲突：{prompt_fields['main_conflict']}\n"
        f"关键转折：{prompt_fields['key_turning_point']}\n"
        f"结尾落点：{prompt_fields['ending_direction']}\n"
        f"当前问题：{repair_error}\n"
        "修订硬约束：\n"
        f"- summary 必须控制在 {constraints['summary_min']}-{constraints['summary_max']} 字。\n"
        f"- 简介和正文总字数必须控制在 {constraints['total_min']}-{constraints['total_max']} 字。\n"
        f"- 仅正文部分至少 {constraints['body_min']} 字，最多 {constraints['body_max']} 字。\n"
        f"- 共 {normalized_payload['target_chapter_count']} 章，每章都要扩成完整场景，尽量接近 {constraints['per_chapter_target']} 字以上。\n"
        "修订要求：\n"
        "- 优先保留现有故事方向和章节顺序，不要另起炉灶。\n"
        "- 如果 summary 超长就压缩 summary；如果正文过短就重点扩写 chapters，不要把字数浪费在解释上。\n"
        "- 每章都要补足场景、动作、对话、心理和结果，不要只加概述句。\n"
        "- 只返回完整的新 JSON 对象，不要解释。\n"
        + "\n".join(f"- {rule}" for rule in style_rules)
        + "\n章节节奏：\n"
        + "\n".join(build_story_draft_chapter_lines(normalized_payload))
        + "\n当前草稿：\n"
        + f"summary={existing_draft['summary_text']}\n"
        + "\n".join(build_story_draft_existing_chapter_lines(existing_draft))
        + "\n请返回完整的新 summary 和完整的新 chapters。"
    )


def build_story_draft_common_prompt(
    payload: dict[str, Any],
    *,
    repair_error: str | None = None,
    existing_draft: dict[str, Any] | None = None,
) -> str:
    normalized_payload = normalize_story_payload(payload)
    constraints = build_story_draft_constraints(normalized_payload)
    prompt_fields = build_story_draft_prompt_fields(normalized_payload)
    chapter_lines = build_story_draft_chapter_lines(normalized_payload)
    if existing_draft is not None and repair_error:
        return build_story_draft_expansion_prompt(
            normalized_payload,
            repair_error=repair_error,
            existing_draft=existing_draft,
        )
    repair_block = ""
    if repair_error:
        repair_block = (
            "\n上一版输出不合格，必须整篇重写，不要解释。\n"
            f"上一版问题：{repair_error}\n"
            "这次必须优先修正长度约束和 JSON 结构约束。\n"
        )
        if "简介字数不符合要求" in repair_error:
            repair_block += (
                f"- 这次先把 summary 压缩到 {constraints['summary_min']}-{constraints['summary_max']} 字，"
                "只保留危险、代价、关系和转折影子，不要写成长简介。\n"
            )
        if "正文总字数不符合要求" in repair_error:
            repair_block += (
                f"- 这次不要继续拉长 summary，重点扩写 chapters，把正文至少写到 {constraints['body_min']} 字。"
                "每章都补足场景、动作、对话、心理和结果，不要用概述偷字数。\n"
            )
    style_rules = STYLE_DRAFT_GUIDANCE.get(normalized_payload["style"], [])

    return (
        "你是中文短篇小说作者。\n"
        "请根据下面的稳定写作 payload，输出一篇完整 Markdown 成稿所需的 JSON 内容。\n"
        "不要改标题，不要省略章节，不要输出 Markdown 代码块。\n"
        f"标题固定为：{normalized_payload['title']}\n"
        f"题材氛围：{prompt_fields['genre_tone']}\n"
        f"卖点：{prompt_fields['selling_point']}\n"
        f"目标字数范围：{normalized_payload['target_char_range'][0]}-{normalized_payload['target_char_range'][1]}\n"
        f"目标章节数：{normalized_payload['target_chapter_count']}\n"
        f"主角画像：{prompt_fields['protagonist_profile']}\n"
        f"主角目标：{prompt_fields['protagonist_goal']}\n"
        f"核心关系：{prompt_fields['core_relationship']}\n"
        f"主冲突：{prompt_fields['main_conflict']}\n"
        f"关键转折：{prompt_fields['key_turning_point']}\n"
        f"结尾落点：{prompt_fields['ending_direction']}\n"
        f"简介要求：{prompt_fields['summary_guidance']}\n"
        "硬性长度约束：\n"
        f"- summary 必须控制在 {constraints['summary_min']}-{constraints['summary_max']} 字。\n"
        f"- 简介和正文总字数必须控制在 {constraints['total_min']}-{constraints['total_max']} 字。\n"
        f"- 仅正文部分至少 {constraints['body_min']} 字，最多 {constraints['body_max']} 字。\n"
        f"- 共 {normalized_payload['target_chapter_count']} 章，每章都必须写成完整场景，尽量接近 {constraints['per_chapter_target']} 字以上，不要用几句话草草带过。\n"
        "输出约束：\n"
        "- summary 只写一段，不要分点，不要解释创作思路。\n"
        "- chapters 里的每章都必须是完整叙事，不要写提纲，不要写“这一章”“接下来”“下面进入”等元提示句。\n"
        "- 不要把写作规则、章节节奏、objective、tension 直接抄进正文。\n"
        "- 如果长度吃紧，优先压缩 summary，不要压缩正文。\n"
        "- 每章至少写出 2-3 个连续叙事段落，让事件推进真正发生。\n"
        + "\n".join(f"- {rule}" for rule in style_rules)
        + "\n章节节奏：\n"
        + "\n".join(chapter_lines)
        + "\n写作规则：\n"
        + "\n".join(f"- {rule}" for rule in normalized_payload.get("writing_rules", []))
        + repair_block
        + "\n请返回 summary 和 chapters。"
    )


def build_story_draft_summary_prompt(
    payload: dict[str, Any],
    *,
    repair_error: str | None = None,
) -> str:
    normalized_payload = normalize_story_payload(payload)
    constraints = build_story_draft_constraints(normalized_payload)
    prompt_fields = build_story_draft_prompt_fields(normalized_payload)
    style_rules = STYLE_DRAFT_GUIDANCE.get(normalized_payload["style"], [])
    repair_block = ""
    if repair_error:
        repair_block = (
            "\n上一版 summary 不合格，必须重写，不要解释。\n"
            f"上一版问题：{repair_error}\n"
            f"- 这次一定把 summary 控制在 {constraints['summary_min']}-{constraints['summary_max']} 字。\n"
            "- 不要写成长梗概，不要把章节节奏提前泄露完。\n"
        )
    return (
        "你是中文短篇小说作者。\n"
        "你当前只负责写这篇故事的简介 summary，不要写正文，不要写章节。\n"
        f"标题固定为：{normalized_payload['title']}\n"
        f"题材氛围：{prompt_fields['genre_tone']}\n"
        f"卖点：{prompt_fields['selling_point']}\n"
        f"主角画像：{prompt_fields['protagonist_profile']}\n"
        f"主角目标：{prompt_fields['protagonist_goal']}\n"
        f"核心关系：{prompt_fields['core_relationship']}\n"
        f"主冲突：{prompt_fields['main_conflict']}\n"
        f"关键转折：{prompt_fields['key_turning_point']}\n"
        f"结尾落点：{prompt_fields['ending_direction']}\n"
        f"简介要求：{prompt_fields['summary_guidance']}\n"
        f"summary 必须控制在 {constraints['summary_min']}-{constraints['summary_max']} 字。\n"
        "- summary 只写一段，不要分点，不要解释，不要带“简介：”前缀。\n"
        "- 如果信息很多，优先保留危险、代价、关系和转折影子，不要把细节展开成梗概。\n"
        + "\n".join(f"- {rule}" for rule in style_rules)
        + repair_block
        + "\n请只返回包含 summary 字段的 JSON 对象。"
    )


def build_story_draft_chapter_prompt(
    payload: dict[str, Any],
    *,
    summary_text: str,
    chapter_number: int,
    existing_chapters: list[dict[str, Any]],
    repair_error: str | None = None,
    existing_chapter_text: str | None = None,
) -> str:
    normalized_payload = normalize_story_payload(payload)
    prompt_fields = build_story_draft_prompt_fields(normalized_payload)
    chapter_blueprint = normalized_payload["chapter_blueprints"][chapter_number - 1]
    chapter_targets = build_story_draft_chapter_targets(
        normalized_payload,
        summary_text=summary_text,
        existing_chapters=existing_chapters,
    )
    style_rules = STYLE_DRAFT_GUIDANCE.get(normalized_payload["style"], [])
    repair_block = ""
    if repair_error:
        repair_block = (
            "\n上一版本章不合格，必须只重写当前章节，不要解释。\n"
            f"上一版问题：{repair_error}\n"
        )
        if "字数不符合要求" in repair_error:
            repair_block += (
                "- 如果本章偏短，就补足场景、动作、对话、心理和结果，让事件真正推进。\n"
                "- 如果本章偏长，就删掉重复回顾、空泛解释和无效抒情，只保留有效冲突、动作和关系变化。\n"
            )
        if existing_chapter_text:
            repair_block += (
                "上一版本章内容：\n"
                f"{existing_chapter_text}\n"
            )

    previous_chapter_lines = build_previous_chapter_recap_lines(existing_chapters)
    future_chapter_lines = build_story_draft_chapter_lines(normalized_payload)[chapter_number - 1 :]
    return (
        "你是中文短篇小说作者。\n"
        "你当前只负责写一章正文，不要写简介，不要写其他章节。\n"
        f"标题固定为：{normalized_payload['title']}\n"
        f"题材氛围：{prompt_fields['genre_tone']}\n"
        f"卖点：{prompt_fields['selling_point']}\n"
        f"主角画像：{prompt_fields['protagonist_profile']}\n"
        f"主角目标：{prompt_fields['protagonist_goal']}\n"
        f"核心关系：{prompt_fields['core_relationship']}\n"
        f"主冲突：{prompt_fields['main_conflict']}\n"
        f"关键转折：{prompt_fields['key_turning_point']}\n"
        f"结尾落点：{prompt_fields['ending_direction']}\n"
        f"全篇 summary：{summary_text}\n"
        f"当前要写第{chapter_number}章。\n"
        f"本章阶段：{chapter_blueprint['stage']}\n"
        f"本章焦点：{chapter_blueprint['focus']}\n"
        f"本章推进：{chapter_blueprint['advance']}\n"
        f"本章章尾：{chapter_blueprint['chapter_hook']}\n"
        f"本章目标：{chapter_blueprint['objective']}\n"
        f"本章张力：{chapter_blueprint['tension']}\n"
        "长度约束：\n"
        f"- 当前已完成正文 {chapter_targets['written_body_chars']} 字。\n"
        f"- 剩余正文总预算 {chapter_targets['remaining_body_min']}-{chapter_targets['remaining_body_max']} 字。\n"
        f"- 包含当前章在内，还剩 {chapter_targets['remaining_chapter_count']} 章。\n"
        f"- 第{chapter_number}章建议控制在 {chapter_targets['chapter_min']}-{chapter_targets['chapter_max']} 字，尽量接近 {chapter_targets['chapter_target']} 字。\n"
        f"- 平均预算上限约为 {chapter_targets['average_chapter_max']} 字，允许首章或爆点章略长，但不能把后续章节的篇幅全部挤没。\n"
        "- 当前章必须写成完整叙事，不要写提纲，不要写“这一章”“接下来”等元提示句。\n"
        "- 当前章至少写出 3-5 个连续叙事段落，让事件、动作、对话、心理和结果真实发生。\n"
        "- 如果篇幅吃紧，优先压缩解释和复述，不要牺牲场景推进。\n"
        + "\n".join(f"- {rule}" for rule in style_rules)
        + ("\n已完成章节：\n" + "\n".join(previous_chapter_lines) if previous_chapter_lines else "")
        + "\n后续章节节奏：\n"
        + "\n".join(future_chapter_lines)
        + "\n写作规则：\n"
        + "\n".join(f"- {rule}" for rule in normalized_payload.get("writing_rules", []))
        + repair_block
        + f"\n请只返回包含 chapter_number 和 content 的 JSON 对象，chapter_number 固定为 {chapter_number}。"
    )


def build_story_draft_summary_responses_payload(
    *,
    payload: dict[str, Any],
    model: str,
    repair_error: str | None = None,
) -> dict[str, Any]:
    prompt = build_story_draft_summary_prompt(
        payload,
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
                "name": "story_draft_summary",
                "schema": SUMMARY_JSON_SCHEMA,
                "strict": True,
            }
        },
    }


def build_story_draft_summary_chat_completions_payload(
    *,
    payload: dict[str, Any],
    model: str,
    repair_error: str | None = None,
) -> dict[str, Any]:
    prompt = build_story_draft_summary_prompt(
        payload,
        repair_error=repair_error,
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是中文短篇小说作者。"
                    "你必须只返回一个 JSON 对象，不要解释，不要返回 Markdown 代码块。"
                    "顶层字段固定为 summary。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n"
                    '请只返回一个 JSON 对象，格式示例：{"summary":"..."}'
                ),
            },
        ],
    }


def build_story_draft_chapter_responses_payload(
    *,
    payload: dict[str, Any],
    model: str,
    summary_text: str,
    chapter_number: int,
    existing_chapters: list[dict[str, Any]],
    repair_error: str | None = None,
    existing_chapter_text: str | None = None,
) -> dict[str, Any]:
    prompt = build_story_draft_chapter_prompt(
        payload,
        summary_text=summary_text,
        chapter_number=chapter_number,
        existing_chapters=existing_chapters,
        repair_error=repair_error,
        existing_chapter_text=existing_chapter_text,
    )
    return {
        "model": model,
        "instructions": "请严格按照 JSON Schema 返回结果。",
        "input": prompt,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "story_draft_chapter",
                "schema": CHAPTER_JSON_SCHEMA,
                "strict": True,
            }
        },
    }


def build_story_draft_chapter_chat_completions_payload(
    *,
    payload: dict[str, Any],
    model: str,
    summary_text: str,
    chapter_number: int,
    existing_chapters: list[dict[str, Any]],
    repair_error: str | None = None,
    existing_chapter_text: str | None = None,
) -> dict[str, Any]:
    prompt = build_story_draft_chapter_prompt(
        payload,
        summary_text=summary_text,
        chapter_number=chapter_number,
        existing_chapters=existing_chapters,
        repair_error=repair_error,
        existing_chapter_text=existing_chapter_text,
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是中文短篇小说作者。"
                    "你必须只返回一个 JSON 对象，不要解释，不要返回 Markdown 代码块。"
                    "顶层字段固定为 chapter_number 和 content。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n"
                    f'请只返回一个 JSON 对象，格式示例：{{"chapter_number":{chapter_number},"content":"..."}}'
                ),
            },
        ],
    }


def build_story_draft_responses_payload(
    *,
    payload: dict[str, Any],
    model: str,
    repair_error: str | None = None,
    existing_draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = build_story_draft_common_prompt(
        payload,
        repair_error=repair_error,
        existing_draft=existing_draft,
    )
    return {
        "model": model,
        "instructions": "请严格按照 JSON Schema 返回结果。",
        "input": prompt,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "story_draft",
                "schema": DRAFT_JSON_SCHEMA,
                "strict": True,
            }
        },
    }


def build_story_draft_chat_completions_payload(
    *,
    payload: dict[str, Any],
    model: str,
    repair_error: str | None = None,
    existing_draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prompt = build_story_draft_common_prompt(
        payload,
        repair_error=repair_error,
        existing_draft=existing_draft,
    )
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是中文短篇小说作者。"
                    "你必须只返回一个 JSON 对象，不要解释，不要返回 Markdown 代码块。"
                    "顶层字段固定为 summary 和 chapters。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"{prompt}\n"
                    "请只返回一个 JSON 对象，格式示例："
                    '{"summary":"...","chapters":[{"chapter_number":1,"content":"..."},{"chapter_number":2,"content":"..."}]}'
                ),
            },
        ],
    }


def validate_story_draft_summary_text(
    *,
    payload: dict[str, Any],
    summary_text: str,
) -> tuple[str, int]:
    normalized_payload = normalize_story_payload(payload)
    constraints = build_story_draft_constraints(normalized_payload)
    normalized_summary_text, summary_char_count = normalize_story_draft_summary(
        _normalize_output_string(summary_text, "summary"),
        min_chars=constraints["summary_min"],
        max_chars=constraints["summary_max"],
    )
    max_summary_with_overflow = constraints["summary_max"] + calculate_small_overflow_allowance(
        constraints["summary_max"],
        floor=SUMMARY_MAX_OVERFLOW_FLOOR,
        cap=SUMMARY_MAX_OVERFLOW_CAP,
    )
    if summary_char_count < constraints["summary_min"] or summary_char_count > max_summary_with_overflow:
        raise LlmResponseError(
            f"简介字数不符合要求，当前为 {summary_char_count} 字，应在 "
            f"{constraints['summary_min']}-{max_summary_with_overflow} 字之间。"
        )
    return normalized_summary_text, summary_char_count


def validate_story_draft_chapter_content(
    *,
    payload: dict[str, Any],
    summary_text: str,
    chapter_number: int,
    existing_chapters: list[dict[str, Any]],
    content: str,
) -> tuple[str, int]:
    normalized_payload = normalize_story_payload(payload)
    if chapter_number < 1 or chapter_number > normalized_payload["target_chapter_count"]:
        raise LlmResponseError("chapter_number 超出目标章节范围。")

    chapter_targets = build_story_draft_chapter_targets(
        normalized_payload,
        summary_text=summary_text,
        existing_chapters=existing_chapters,
    )
    normalized_content, chapter_char_count = normalize_story_draft_chapter_content(
        _normalize_output_string(content, "content"),
        min_chars=chapter_targets["chapter_min"],
        max_chars=chapter_targets["chapter_hard_max"],
    )
    # 正文阶段优先卡下限，避免因模型写得偏长而整章作废。
    if chapter_char_count < chapter_targets["chapter_min"]:
        raise LlmResponseError(
            f"第{chapter_number}章字数不足，当前为 {chapter_char_count} 字，应不少于 "
            f"{chapter_targets['chapter_min']} 字。"
        )
    return normalized_content, chapter_char_count


def parse_story_draft_summary_candidate(
    *,
    raw_text: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        parsed = parse_llm_json_object(raw_text)
        summary_source = parsed.get("summary")
    except LlmResponseError:
        summary_source = extract_plain_text_candidate(raw_text)
    summary_text, summary_char_count = validate_story_draft_summary_text(
        payload=payload,
        summary_text=summary_source,
    )
    return {
        "summary_text": summary_text,
        "summary_char_count": summary_char_count,
    }


def parse_story_draft_chapter_candidate(
    *,
    raw_text: str,
    payload: dict[str, Any],
    summary_text: str,
    chapter_number: int,
    existing_chapters: list[dict[str, Any]],
) -> dict[str, Any]:
    try:
        parsed = parse_llm_json_object(raw_text)
        parsed_chapter_number = parsed.get("chapter_number")
        if parsed_chapter_number != chapter_number:
            raise LlmResponseError(f"chapter_number 必须等于 {chapter_number}。")
        content_source = parsed.get("content")
    except LlmResponseError:
        content_source = extract_plain_text_candidate(raw_text)
    content, chapter_char_count = validate_story_draft_chapter_content(
        payload=payload,
        summary_text=summary_text,
        chapter_number=chapter_number,
        existing_chapters=existing_chapters,
        content=content_source,
    )
    return {
        "chapter_number": chapter_number,
        "content": content,
        "chapter_char_count": chapter_char_count,
    }


def validate_story_draft_lengths(
    *,
    payload: dict[str, Any],
    summary_text: str,
    chapters: list[dict[str, Any]],
) -> tuple[int, int]:
    normalized_payload = normalize_story_payload(payload)
    constraints = build_story_draft_constraints(normalized_payload)
    summary_chars = count_content_chars(summary_text)
    max_summary_with_overflow = constraints["summary_max"] + calculate_small_overflow_allowance(
        constraints["summary_max"],
        floor=SUMMARY_MAX_OVERFLOW_FLOOR,
        cap=SUMMARY_MAX_OVERFLOW_CAP,
    )
    if summary_chars < constraints["summary_min"] or summary_chars > max_summary_with_overflow:
        raise LlmResponseError(
            f"简介字数不符合要求，当前为 {summary_chars} 字，应在 "
            f"{constraints['summary_min']}-{max_summary_with_overflow} 字之间。"
        )

    body_char_count = sum(count_content_chars(item["content"]) for item in chapters)
    total_chars = summary_chars + body_char_count
    if total_chars < constraints["total_min"]:
        raise LlmResponseError(
            f"正文总字数不足，当前总字数为 {total_chars} 字，"
            f"其中正文为 {body_char_count} 字，应不少于 {constraints['total_min']} 字。"
        )
    return summary_chars, body_char_count


def parse_story_draft_candidate(
    *,
    raw_text: str,
    payload: dict[str, Any],
    route: dict[str, Any],
    provider_response_id: str,
) -> dict[str, Any]:
    normalized_payload = normalize_story_payload(payload)
    parsed = parse_llm_json_object(raw_text)
    chapters = parsed.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != normalized_payload["target_chapter_count"]:
        raise LlmResponseError("chapters 数量必须与目标章节数一致。")
    summary_text, summary_char_count = validate_story_draft_summary_text(
        payload=normalized_payload,
        summary_text=parsed.get("summary"),
    )

    normalized_chapters: list[dict[str, Any]] = []
    markdown_parts = [
        f"# {normalized_payload['title']}",
        "",
        "## 简介",
        "",
        summary_text,
        "",
        "## 正文",
        "",
    ]
    for expected_index, raw_chapter in enumerate(chapters, start=1):
        if not isinstance(raw_chapter, dict):
            raise LlmResponseError("chapters 里的每一项都必须是对象。")
        chapter_number = raw_chapter.get("chapter_number")
        if chapter_number != expected_index:
            raise LlmResponseError("chapter_number 必须从 1 开始连续递增。")
        content = _normalize_output_string(raw_chapter.get("content"), "chapters.content")
        normalized_chapters.append(
            {
                "chapter_number": chapter_number,
                "content": content,
            }
        )
        markdown_parts.extend(
            [
                f"### {chapter_number}",
                "",
                content,
                "",
            ]
        )

    body_char_count = sum(count_content_chars(item["content"]) for item in normalized_chapters)
    content_markdown = "\n".join(markdown_parts).strip() + "\n"
    return {
        "title": normalized_payload["title"],
        "summary_text": summary_text,
        "summary_char_count": summary_char_count,
        "chapters": normalized_chapters,
        "content_markdown": content_markdown,
        "body_char_count": body_char_count,
        "generation_mode": "llm",
        "provider_name": route["provider_name"],
        "api_mode": route["api_mode"],
        "model_name": route["model_name"],
        "model_config_key": route["model_config_key"],
        "provider_response_id": provider_response_id,
    }


def validate_story_draft_candidate(
    *,
    payload: dict[str, Any],
    candidate: dict[str, Any],
) -> None:
    validate_story_draft_lengths(
        payload=payload,
        summary_text=candidate["summary_text"],
        chapters=candidate["chapters"],
    )


def parse_story_draft_output(
    *,
    raw_text: str,
    payload: dict[str, Any],
    route: dict[str, Any],
    provider_response_id: str,
) -> dict[str, Any]:
    candidate = parse_story_draft_candidate(
        raw_text=raw_text,
        payload=payload,
        route=route,
        provider_response_id=provider_response_id,
    )
    validate_story_draft_candidate(payload=payload, candidate=candidate)
    return candidate


def request_story_draft_summary_output_text(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    transport: TransportFn,
    repair_error: str | None = None,
) -> tuple[dict[str, Any], str]:
    normalized_route = normalize_route_candidate(route)
    resolved_api_key = resolve_api_key_for_route(normalized_route)
    extra_headers = resolve_header_values(normalized_route["header_env_names"])

    if normalized_route["api_mode"] == "responses":
        request_payload = build_story_draft_summary_responses_payload(
            payload=payload,
            model=normalized_route["model_name"],
            repair_error=repair_error,
        )
    else:
        request_payload = build_story_draft_summary_chat_completions_payload(
            payload=payload,
            model=normalized_route["model_name"],
            repair_error=repair_error,
        )
        request_payload.update(
            build_provider_chat_completions_options(
                route=normalized_route,
                max_tokens=512,
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
    return response_payload, output_text


def request_story_draft_chapter_output_text(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    summary_text: str,
    chapter_number: int,
    existing_chapters: list[dict[str, Any]],
    transport: TransportFn,
    repair_error: str | None = None,
    existing_chapter_text: str | None = None,
) -> tuple[dict[str, Any], str]:
    normalized_route = normalize_route_candidate(route)
    resolved_api_key = resolve_api_key_for_route(normalized_route)
    extra_headers = resolve_header_values(normalized_route["header_env_names"])
    chapter_targets = build_story_draft_chapter_targets(
        payload,
        summary_text=summary_text,
        existing_chapters=existing_chapters,
    )

    if normalized_route["api_mode"] == "responses":
        request_payload = build_story_draft_chapter_responses_payload(
            payload=payload,
            model=normalized_route["model_name"],
            summary_text=summary_text,
            chapter_number=chapter_number,
            existing_chapters=existing_chapters,
            repair_error=repair_error,
            existing_chapter_text=existing_chapter_text,
        )
    else:
        request_payload = build_story_draft_chapter_chat_completions_payload(
            payload=payload,
            model=normalized_route["model_name"],
            summary_text=summary_text,
            chapter_number=chapter_number,
            existing_chapters=existing_chapters,
            repair_error=repair_error,
            existing_chapter_text=existing_chapter_text,
        )
        request_payload.update(
            build_provider_chat_completions_options(
                route=normalized_route,
                max_tokens=min(
                    8192,
                    max(2048, chapter_targets["chapter_max"] + 512),
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
    return response_payload, output_text


def request_story_draft_output_text(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    transport: TransportFn,
    repair_error: str | None = None,
    existing_draft: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    normalized_route = normalize_route_candidate(route)
    resolved_api_key = resolve_api_key_for_route(normalized_route)
    extra_headers = resolve_header_values(normalized_route["header_env_names"])
    normalized_payload = normalize_story_payload(payload)

    if normalized_route["api_mode"] == "responses":
        request_payload = build_story_draft_responses_payload(
            payload=payload,
            model=normalized_route["model_name"],
            repair_error=repair_error,
            existing_draft=existing_draft,
        )
    else:
        request_payload = build_story_draft_chat_completions_payload(
            payload=payload,
            model=normalized_route["model_name"],
            repair_error=repair_error,
            existing_draft=existing_draft,
        )
        request_payload.update(
            build_provider_chat_completions_options(
                route=normalized_route,
                max_tokens=min(
                    8192,
                    max(4096, normalized_payload["target_char_range"][1] + 512),
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
    return response_payload, output_text


def build_llm_story_draft_summary_from_route(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    transport: TransportFn,
) -> tuple[dict[str, Any], str, int, dict[str, int]]:
    normalized_route = normalize_route_candidate(route)
    last_error: LlmResponseError | None = None
    total_token_usage = build_empty_token_usage()
    for repair_attempt_index in range(MAX_DRAFT_REPAIR_ATTEMPTS + 1):
        response_payload, output_text = request_story_draft_summary_output_text(
            payload=payload,
            route=normalized_route,
            transport=transport,
            repair_error=str(last_error) if last_error else None,
        )
        total_token_usage = merge_token_usages(
            total_token_usage,
            extract_token_usage_from_response(response_payload),
        )
        try:
            summary_candidate = parse_story_draft_summary_candidate(
                raw_text=output_text,
                payload=payload,
            )
            return (
                summary_candidate,
                str(response_payload.get("id", "")).strip(),
                repair_attempt_index,
                total_token_usage,
            )
        except LlmResponseError as exc:
            last_error = LlmResponseError(str(exc), token_usage=total_token_usage)
            continue

    if last_error is None:
        raise LlmResponseError("LLM 简介生成失败。", token_usage=total_token_usage)
    raise last_error


def build_llm_story_draft_chapter_from_route(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    summary_text: str,
    chapter_number: int,
    existing_chapters: list[dict[str, Any]],
    transport: TransportFn,
) -> tuple[dict[str, Any], str, int, dict[str, int]]:
    normalized_route = normalize_route_candidate(route)
    last_error: LlmResponseError | None = None
    last_chapter_text: str | None = None
    total_token_usage = build_empty_token_usage()
    for repair_attempt_index in range(MAX_DRAFT_REPAIR_ATTEMPTS + 1):
        response_payload, output_text = request_story_draft_chapter_output_text(
            payload=payload,
            route=normalized_route,
            summary_text=summary_text,
            chapter_number=chapter_number,
            existing_chapters=existing_chapters,
            transport=transport,
            repair_error=str(last_error) if last_error else None,
            existing_chapter_text=last_chapter_text if last_error is not None else None,
        )
        total_token_usage = merge_token_usages(
            total_token_usage,
            extract_token_usage_from_response(response_payload),
        )
        try:
            chapter_candidate = parse_story_draft_chapter_candidate(
                raw_text=output_text,
                payload=payload,
                summary_text=summary_text,
                chapter_number=chapter_number,
                existing_chapters=existing_chapters,
            )
            return (
                chapter_candidate,
                str(response_payload.get("id", "")).strip(),
                repair_attempt_index,
                total_token_usage,
            )
        except LlmResponseError as exc:
            last_error = LlmResponseError(str(exc), token_usage=total_token_usage)
            try:
                parsed = parse_llm_json_object(output_text)
                raw_content = parsed.get("content")
                if isinstance(raw_content, str) and raw_content.strip():
                    last_chapter_text = raw_content.strip()
                    continue
            except LlmResponseError:
                pass
            if isinstance(output_text, str) and output_text.strip():
                last_chapter_text = output_text.strip()
            continue

    if last_error is None:
        raise LlmResponseError(f"LLM 第{chapter_number}章生成失败。", token_usage=total_token_usage)
    raise last_error


def build_segmented_llm_story_draft_from_route(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    normalized_route = normalize_route_candidate(route)
    normalized_payload = normalize_story_payload(payload)

    summary_candidate, summary_response_id, summary_repair_attempt_count, summary_token_usage = (
        build_llm_story_draft_summary_from_route(
            payload=normalized_payload,
            route=normalized_route,
            transport=transport,
        )
    )

    chapters: list[dict[str, Any]] = []
    provider_response_ids: list[str] = []
    if summary_response_id:
        provider_response_ids.append(summary_response_id)
    segment_attempts = [
        {
            "segment_type": "summary",
            "repair_attempt_count": summary_repair_attempt_count,
            "token_usage": normalize_token_usage(summary_token_usage),
        }
    ]
    total_repair_attempt_count = summary_repair_attempt_count
    total_token_usage = summary_token_usage

    for chapter_number in range(1, normalized_payload["target_chapter_count"] + 1):
        chapter_candidate, chapter_response_id, chapter_repair_attempt_count, chapter_token_usage = (
            build_llm_story_draft_chapter_from_route(
                payload=normalized_payload,
                route=normalized_route,
                summary_text=summary_candidate["summary_text"],
                chapter_number=chapter_number,
                existing_chapters=chapters,
                transport=transport,
            )
        )
        chapters.append(
            {
                "chapter_number": chapter_candidate["chapter_number"],
                "content": chapter_candidate["content"],
            }
        )
        if chapter_response_id:
            provider_response_ids.append(chapter_response_id)
        segment_attempts.append(
            {
                "segment_type": "chapter",
                "chapter_number": chapter_number,
                "repair_attempt_count": chapter_repair_attempt_count,
                "chapter_char_count": chapter_candidate["chapter_char_count"],
                "token_usage": normalize_token_usage(chapter_token_usage),
            }
        )
        total_repair_attempt_count += chapter_repair_attempt_count
        total_token_usage = merge_token_usages(total_token_usage, chapter_token_usage)

    draft = build_story_draft_output_from_parts(
        payload=normalized_payload,
        route=normalized_route,
        provider_response_id=",".join(provider_response_ids),
        summary_text=summary_candidate["summary_text"],
        chapters=chapters,
    )
    validate_story_draft_candidate(payload=normalized_payload, candidate=draft)
    draft["repair_attempt_used"] = total_repair_attempt_count > 0
    draft["repair_attempt_count"] = total_repair_attempt_count
    draft["segmented_generation"] = True
    draft["provider_response_ids"] = provider_response_ids
    draft["segment_count"] = len(segment_attempts)
    draft["segment_attempts"] = segment_attempts
    draft["token_usage"] = total_token_usage
    return draft


def build_llm_story_draft_from_route(
    *,
    payload: dict[str, Any],
    route: dict[str, Any],
    transport: TransportFn = post_json_api,
) -> dict[str, Any]:
    normalized_route = normalize_route_candidate(route)
    if should_use_segmented_draft_generation(payload):
        return build_segmented_llm_story_draft_from_route(
            payload=payload,
            route=normalized_route,
            transport=transport,
        )

    last_error: LlmResponseError | None = None
    last_candidate: dict[str, Any] | None = None
    total_token_usage = build_empty_token_usage()
    for repair_attempt_index in range(MAX_DRAFT_REPAIR_ATTEMPTS + 1):
        response_payload, output_text = request_story_draft_output_text(
            payload=payload,
            route=normalized_route,
            transport=transport,
            repair_error=str(last_error) if last_error else None,
            existing_draft=last_candidate if last_error is not None else None,
        )
        total_token_usage = merge_token_usages(
            total_token_usage,
            extract_token_usage_from_response(response_payload),
        )
        try:
            draft = parse_story_draft_candidate(
                raw_text=output_text,
                payload=payload,
                route=normalized_route,
                provider_response_id=str(response_payload.get("id", "")).strip(),
            )
            last_candidate = draft
            validate_story_draft_candidate(payload=payload, candidate=draft)
            draft["repair_attempt_used"] = repair_attempt_index > 0
            draft["repair_attempt_count"] = repair_attempt_index
            draft["token_usage"] = total_token_usage
            return draft
        except LlmResponseError as exc:
            last_error = LlmResponseError(str(exc), token_usage=total_token_usage)
            continue

    if last_error is None:
        raise LlmResponseError("LLM 正文生成失败。", token_usage=total_token_usage)
    raise last_error


def build_llm_story_draft_with_fallbacks(
    *,
    payload: dict[str, Any],
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
            draft = build_llm_story_draft_from_route(
                payload=payload,
                route=route,
                transport=transport,
            )
            current_token_usage = draft.get("token_usage", {})
            total_token_usage = merge_token_usages(total_token_usage, current_token_usage)
            success_attempt = {
                "attempt_index": index,
                **route_snapshot,
                "status": "success",
                "token_usage": normalize_token_usage(current_token_usage),
            }
            draft["attempt_count"] = len(attempts) + 1
            draft["fallback_used"] = len(attempts) > 0
            draft["attempts"] = [*attempts, success_attempt]
            draft["token_usage"] = total_token_usage
            return draft
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


def build_llm_story_draft(
    *,
    payload: dict[str, Any],
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
    draft = build_llm_story_draft_from_route(
        payload=payload,
        route=route,
        transport=transport,
    )
    draft["attempt_count"] = 1
    draft["fallback_used"] = False
    draft["attempts"] = [
        {
            "attempt_index": 1,
            "model_config_key": route.get("model_config_key", ""),
            "provider_name": route["provider_name"],
            "api_mode": route["api_mode"],
            "model_name": route["model_name"],
            "status": "success",
        }
    ]
    return draft
