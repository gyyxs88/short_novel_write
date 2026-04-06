from __future__ import annotations

from typing import Any


RELATION_KEYWORDS = ("恋", "婚", "前任", "青梅", "重逢", "误会", "搭档", "朋友", "姐妹", "师徒")
CONFLICT_KEYWORDS = ("失踪", "谋杀", "秘密", "真相", "背叛", "旧案", "过去", "调查", "绑架", "复仇")
VALID_STYLES = {"zhihu", "douban"}


def extract_display_label(raw_value: str) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError("卡组字段里的每一项都必须是非空字符串。")
    if " - " in raw_value:
        return raw_value.split(" - ", 1)[1].strip()
    return raw_value.strip()


def unique_sorted_labels(values: list[str], field_name: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field_name} 必须是非空字符串数组。")
    return sorted({extract_display_label(value) for value in values})


def unique_sorted_raw_values(values: list[str], field_name: str) -> list[str]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{field_name} 必须是非空字符串数组。")
    normalized_values: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} 里的每一项都必须是非空字符串。")
        normalized_values.add(value.strip())
    return sorted(normalized_values)


def first_matching_label(labels: list[str], keywords: tuple[str, ...]) -> str | None:
    for label in labels:
        if any(keyword in label for keyword in keywords):
            return label
    return None


def first_remaining_label(labels: list[str], excluded: set[str]) -> str:
    for label in labels:
        if label not in excluded:
            return label
    return labels[0]


def normalize_card_field(card: dict[str, Any], field_name: str) -> list[str]:
    value = card.get(field_name)
    return unique_sorted_labels(value, field_name)


def build_deterministic_idea_pack(*, card: dict[str, Any], style: str) -> dict[str, Any]:
    if style not in VALID_STYLES:
        raise ValueError("style 仅支持 zhihu 或 douban。")
    if not isinstance(card, dict):
        raise ValueError("card 必须是对象。")

    source_mode = card.get("source_mode")
    if not isinstance(source_mode, str) or not source_mode.strip():
        raise ValueError("card.source_mode 必须是非空字符串。")

    raw_types = card.get("types")
    raw_main_tags = card.get("main_tags")
    source_types = unique_sorted_raw_values(raw_types, "types")
    source_main_tags = unique_sorted_raw_values(raw_main_tags, "main_tags")
    if len(source_types) != 2:
        raise ValueError("card.types 需要恰好 2 个有效类型。")
    if len(source_main_tags) != 3:
        raise ValueError("card.main_tags 需要恰好 3 个有效主标签。")

    type_labels = normalize_card_field(card, "types")
    tag_labels = normalize_card_field(card, "main_tags")
    if len(type_labels) < 2:
        raise ValueError("card.types 至少需要 2 个有效类型。")
    if len(tag_labels) < 3:
        raise ValueError("card.main_tags 至少需要 3 个有效主标签。")

    relation_label = first_matching_label(tag_labels, RELATION_KEYWORDS) or tag_labels[0]
    conflict_label = first_matching_label(tag_labels, CONFLICT_KEYWORDS)
    if conflict_label is None or conflict_label == relation_label:
        conflict_label = first_remaining_label(tag_labels, {relation_label})
    secondary_label = first_remaining_label(tag_labels, {relation_label, conflict_label})
    primary_type = type_labels[0]
    secondary_type = type_labels[1] if len(type_labels) > 1 else type_labels[0]

    if style == "zhihu":
        return {
            "source_mode": source_mode.strip(),
            "style": "zhihu",
            "generation_mode": "deterministic",
            "provider_name": "",
            "api_mode": "",
            "model_name": "",
            "model_config_key": "",
            "provider_response_id": "",
            "style_reason": "这组卡更适合强钩子、强冲突、快节奏的知乎式整理。",
            "hook": f"一条和“{conflict_label}”有关的线索，突然把主角拖回“{primary_type}”和“{secondary_type}”交叠的局面里。",
            "core_relationship": f"主角与那个牵出“{relation_label}”旧账的人，重新站到了彼此试探的位置。",
            "main_conflict": f"为了查清“{conflict_label}”背后的真相，主角必须先面对“{secondary_label}”带来的代价。",
            "reversal_direction": f"表面上需要解决的是“{conflict_label}”，真正被掀开的却是“{secondary_label}”埋下的旧账。",
            "recommended_tags": [primary_type, conflict_label, relation_label],
            "source_cards": {
                "types": source_types,
                "main_tags": source_main_tags,
            },
        }

    return {
        "source_mode": source_mode.strip(),
        "style": "douban",
        "generation_mode": "deterministic",
        "provider_name": "",
        "api_mode": "",
        "model_name": "",
        "model_config_key": "",
        "provider_response_id": "",
        "style_reason": "这组卡更适合从关系裂口和情绪余味切入，整理成豆瓣式表达。",
        "hook": f"一段被“{relation_label}”重新牵动的关系，让主角又回到“{primary_type}”和“{secondary_type}”交错的生活缝隙里。",
        "core_relationship": f"主角和那个牵出“{relation_label}”旧事的人，在靠近与回避之间反复拉扯。",
        "main_conflict": f"主角想维持眼前的平静，但“{secondary_label}”不断逼她承认这段关系早已变形。",
        "reversal_direction": f"真正改变她的未必是“{conflict_label}”本身，而是“{relation_label}”让旧情绪重新有了名字。",
        "recommended_tags": [secondary_type, relation_label, secondary_label],
        "source_cards": {
            "types": source_types,
            "main_tags": source_main_tags,
        },
    }
