from __future__ import annotations

from typing import Any


VALID_STYLES = {"zhihu", "douban"}

COMMON_WRITING_RULES = [
    "默认先写简介，再写正文。",
    "开头前几段尽快进入异常、冲突或悬念。",
    "每章都要推进事件、关系或认知，不要原地抒情。",
    "中段至少出现一次有效偏转。",
    "最后一章要回应主冲突，不写成断头文。",
]


def _normalize_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip()


def _normalize_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} 必须是整数。")
    return value


def _normalize_target_char_range(value: Any) -> list[int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    ):
        raise ValueError("writing_brief.target_char_range 必须是两个整数构成的数组。")
    return [value[0], value[1]]


def _normalize_chapter_rhythm(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("plan.chapter_rhythm 必须是非空数组。")
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("plan.chapter_rhythm 里的每一项都必须是对象。")
        chapter_number = _normalize_int(item.get("chapter_number"), "chapter_rhythm.chapter_number")
        normalized.append(
            {
                "chapter_number": chapter_number,
                "stage": _normalize_string(item.get("stage"), "chapter_rhythm.stage"),
                "focus": _normalize_string(item.get("focus"), "chapter_rhythm.focus"),
                "advance": _normalize_string(item.get("advance"), "chapter_rhythm.advance"),
                "chapter_hook": _normalize_string(
                    item.get("chapter_hook"),
                    "chapter_rhythm.chapter_hook",
                ),
            }
        )
    return normalized


def normalize_story_plan(plan: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("plan 必须是对象。")
    plan_id = _normalize_int(plan.get("plan_id"), "plan.plan_id")
    style = _normalize_string(plan.get("style"), "plan.style")
    if style not in VALID_STYLES:
        raise ValueError("plan.style 仅支持 zhihu 或 douban。")
    writing_brief = plan.get("writing_brief")
    if not isinstance(writing_brief, dict):
        raise ValueError("plan.writing_brief 必须是对象。")

    return {
        "plan_id": plan_id,
        "pack_id": _normalize_int(plan.get("pack_id"), "plan.pack_id"),
        "source_mode": _normalize_string(plan.get("source_mode"), "plan.source_mode"),
        "style": style,
        "variant_index": _normalize_int(plan.get("variant_index"), "plan.variant_index"),
        "variant_key": _normalize_string(plan.get("variant_key"), "plan.variant_key"),
        "variant_label": _normalize_string(plan.get("variant_label"), "plan.variant_label"),
        "generation_mode": _normalize_string(plan.get("generation_mode"), "plan.generation_mode"),
        "provider_name": str(plan.get("provider_name", "")).strip(),
        "api_mode": str(plan.get("api_mode", "")).strip(),
        "model_name": str(plan.get("model_name", "")).strip(),
        "model_config_key": str(plan.get("model_config_key", "")).strip(),
        "provider_response_id": str(plan.get("provider_response_id", "")).strip(),
        "title": _normalize_string(plan.get("title"), "plan.title"),
        "genre_tone": _normalize_string(plan.get("genre_tone"), "plan.genre_tone"),
        "selling_point": _normalize_string(plan.get("selling_point"), "plan.selling_point"),
        "protagonist_profile": _normalize_string(
            plan.get("protagonist_profile"),
            "plan.protagonist_profile",
        ),
        "protagonist_goal": _normalize_string(plan.get("protagonist_goal"), "plan.protagonist_goal"),
        "core_relationship": _normalize_string(
            plan.get("core_relationship"),
            "plan.core_relationship",
        ),
        "main_conflict": _normalize_string(plan.get("main_conflict"), "plan.main_conflict"),
        "key_turning_point": _normalize_string(
            plan.get("key_turning_point"),
            "plan.key_turning_point",
        ),
        "ending_direction": _normalize_string(plan.get("ending_direction"), "plan.ending_direction"),
        "chapter_rhythm": _normalize_chapter_rhythm(plan.get("chapter_rhythm")),
        "target_char_range": _normalize_target_char_range(writing_brief.get("target_char_range")),
        "target_chapter_count": _normalize_int(
            writing_brief.get("target_chapter_count"),
            "writing_brief.target_chapter_count",
        ),
    }


def build_summary_guidance(plan: dict[str, Any]) -> str:
    if plan["style"] == "zhihu":
        return (
            f"简介要从“{plan['main_conflict']}”里直接抛出危险、代价和倒计时感，"
            f"并把“{plan['key_turning_point']}”的影子提前埋进去。"
        )
    return (
        f"简介要从“{plan['core_relationship']}”里写出关系裂口和迟到情绪，"
        f"同时让“{plan['ending_direction']}”的余味在开头就隐约出现。"
    )


def build_chapter_blueprints(plan: dict[str, Any]) -> list[dict[str, Any]]:
    blueprints: list[dict[str, Any]] = []
    total_chapters = plan["target_chapter_count"]
    for beat in plan["chapter_rhythm"]:
        chapter_number = beat["chapter_number"]
        if chapter_number == 1:
            objective = f"把主角拖入“{plan['main_conflict']}”，让异常无法再被忽视。"
        elif chapter_number == total_chapters:
            objective = f"回收“{plan['ending_direction']}”，让主冲突真正落地。"
        elif chapter_number == max(2, total_chapters // 2):
            objective = f"完成“{plan['key_turning_point']}”，让认知或关系发生偏转。"
        else:
            objective = f"围绕“{beat['focus']}”推进事件，并把“{beat['advance']}”外化成具体局面。"

        if plan["style"] == "zhihu":
            tension = f"章节里要持续强化“{plan['main_conflict']}”的风险与倒计时。"
        else:
            tension = f"章节里要持续强化“{plan['core_relationship']}”的情绪拉扯和生活裂口。"

        blueprints.append(
            {
                **beat,
                "objective": objective,
                "tension": tension,
            }
        )
    return blueprints


def build_story_payload(*, plan: dict[str, Any]) -> dict[str, Any]:
    normalized_plan = normalize_story_plan(plan)
    return {
        "plan_id": normalized_plan["plan_id"],
        "source_mode": normalized_plan["source_mode"],
        "style": normalized_plan["style"],
        "title": normalized_plan["title"],
        "genre_tone": normalized_plan["genre_tone"],
        "selling_point": normalized_plan["selling_point"],
        "target_char_range": normalized_plan["target_char_range"],
        "target_chapter_count": normalized_plan["target_chapter_count"],
        "protagonist_profile": normalized_plan["protagonist_profile"],
        "protagonist_goal": normalized_plan["protagonist_goal"],
        "core_relationship": normalized_plan["core_relationship"],
        "main_conflict": normalized_plan["main_conflict"],
        "key_turning_point": normalized_plan["key_turning_point"],
        "ending_direction": normalized_plan["ending_direction"],
        "summary_guidance": build_summary_guidance(normalized_plan),
        "chapter_blueprints": build_chapter_blueprints(normalized_plan),
        "writing_rules": list(COMMON_WRITING_RULES),
        "source_plan": {
            "pack_id": normalized_plan["pack_id"],
            "variant_index": normalized_plan["variant_index"],
            "variant_key": normalized_plan["variant_key"],
            "variant_label": normalized_plan["variant_label"],
            "generation_mode": normalized_plan["generation_mode"],
            "provider_name": normalized_plan["provider_name"],
            "api_mode": normalized_plan["api_mode"],
            "model_name": normalized_plan["model_name"],
            "model_config_key": normalized_plan["model_config_key"],
            "provider_response_id": normalized_plan["provider_response_id"],
        },
    }
