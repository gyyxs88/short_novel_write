from __future__ import annotations

from typing import Any


DEFAULT_EVALUATION_MODE = "deterministic"
DEFAULT_EVALUATOR_NAME = "heuristic_v1"
VALID_EVALUATION_MODES = {"deterministic"}
VALID_RECOMMENDATIONS = {"priority_select", "shortlist", "rework"}

HOOK_SIGNAL_KEYWORDS = (
    "失踪",
    "短信",
    "电话",
    "葬礼",
    "婚礼",
    "血",
    "真相",
    "秘密",
    "门外",
    "尸体",
    "绑架",
    "威胁",
)
CONFLICT_GOAL_KEYWORDS = ("必须", "不得不", "想", "要", "决定", "查清", "阻止", "保护", "证明")
CONFLICT_COST_KEYWORDS = ("代价", "风险", "暴露", "失去", "牺牲", "后果", "追杀", "毁掉", "灭口")
RELATIONSHIP_KEYWORDS = (
    "前任",
    "初恋",
    "夫妻",
    "恋人",
    "婚约",
    "母女",
    "父女",
    "父子",
    "姐妹",
    "兄弟",
    "搭档",
    "恩人",
    "白月光",
    "家族",
)
REVERSAL_KEYWORDS = ("其实", "原来", "真正", "不是", "而是", "未必", "反而", "才是", "真凶", "局中局")
DOUBAN_STYLE_KEYWORDS = ("关系", "情绪", "沉默", "余味", "裂口", "拉扯", "平静", "生活", "回避", "名字")


def clamp_score(value: int, minimum: int = 1, maximum: int = 10) -> int:
    return max(minimum, min(maximum, value))


def count_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword in text)


def normalize_text_field(pack: dict[str, Any], field_name: str) -> str:
    value = pack.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pack.{field_name} 必须是非空字符串。")
    return value.strip()


def normalize_string_list_field(pack: dict[str, Any], field_name: str) -> list[str]:
    value = pack.get(field_name)
    if not isinstance(value, list) or not value:
        raise ValueError(f"pack.{field_name} 必须是非空字符串数组。")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"pack.{field_name} 里的每一项都必须是非空字符串。")
        normalized.append(item.strip())
    return normalized


def score_hook_strength(hook: str) -> int:
    score = 3
    if 18 <= len(hook) <= 80:
        score += 2
    elif len(hook) >= 12:
        score += 1
    score += min(3, count_hits(hook, HOOK_SIGNAL_KEYWORDS))
    if any(marker in hook for marker in ("？", "!", "！", "《", "“", "”", "：")):
        score += 1
    if any(marker in hook for marker in ("却", "竟", "但", "然而", "原来", "不是")):
        score += 1
    return clamp_score(score)


def score_conflict_clarity(main_conflict: str) -> int:
    score = 3
    if len(main_conflict) >= 24:
        score += 2
    elif len(main_conflict) >= 16:
        score += 1
    score += min(2, count_hits(main_conflict, CONFLICT_GOAL_KEYWORDS))
    score += min(2, count_hits(main_conflict, CONFLICT_COST_KEYWORDS))
    if any(marker in main_conflict for marker in ("同时", "却", "而", "否则", "一边", "另一边")):
        score += 1
    return clamp_score(score)


def score_relationship_tension(core_relationship: str, main_conflict: str) -> int:
    score = 3
    score += min(3, count_hits(core_relationship, RELATIONSHIP_KEYWORDS))
    if any(marker in core_relationship for marker in ("对立", "试探", "拉扯", "绑回", "靠近", "回避")):
        score += 2
    if any(marker in main_conflict for marker in ("关系", "信任", "背叛", "隐瞒", "旧账")):
        score += 1
    return clamp_score(score)


def score_reversal_expandability(reversal_direction: str) -> int:
    score = 3
    if len(reversal_direction) >= 20:
        score += 2
    elif len(reversal_direction) >= 12:
        score += 1
    score += min(3, count_hits(reversal_direction, REVERSAL_KEYWORDS))
    if any(marker in reversal_direction for marker in ("表面上", "真正", "其实", "局", "身份", "证据")):
        score += 1
    return clamp_score(score)


def score_style_fit(style: str, hook: str, core_relationship: str, main_conflict: str, reversal_direction: str) -> int:
    if style not in {"zhihu", "douban"}:
        raise ValueError("style 仅支持 zhihu 或 douban。")

    if style == "zhihu":
        score = 4
        score += min(2, count_hits(hook + main_conflict, HOOK_SIGNAL_KEYWORDS))
        score += min(2, count_hits(reversal_direction, REVERSAL_KEYWORDS))
        if any(marker in main_conflict for marker in ("必须", "不得不", "代价", "暴露")):
            score += 1
        if any(marker in hook for marker in ("短信", "电话", "婚礼", "葬礼", "门外")):
            score += 1
        return clamp_score(score)

    score = 4
    score += min(2, count_hits(core_relationship + main_conflict, RELATIONSHIP_KEYWORDS))
    score += min(2, count_hits(core_relationship + main_conflict + reversal_direction, DOUBAN_STYLE_KEYWORDS))
    if any(marker in core_relationship for marker in ("拉扯", "回避", "靠近", "旧事")):
        score += 1
    if any(marker in main_conflict for marker in ("平静", "关系", "情绪", "承认")):
        score += 1
    return clamp_score(score)


def score_plan_readiness(
    hook: str,
    core_relationship: str,
    main_conflict: str,
    reversal_direction: str,
    recommended_tags: list[str],
) -> int:
    score = 3
    if len(recommended_tags) == 3:
        score += 1
    if len(hook) >= 16:
        score += 1
    if len(core_relationship) >= 14:
        score += 1
    if len(main_conflict) >= 20:
        score += 2
    if len(reversal_direction) >= 16:
        score += 1
    if any(marker in main_conflict for marker in ("必须", "查清", "决定", "保护", "阻止")):
        score += 1
    return clamp_score(score)


def build_recommendation(total_score: int) -> str:
    if total_score >= 52:
        return "priority_select"
    if total_score >= 42:
        return "shortlist"
    return "rework"


def build_summary(style: str, generation_mode: str, total_score: int, recommendation: str) -> str:
    if recommendation == "priority_select":
        return f"{style} / {generation_mode} 版本整体完成度较高，可以优先进入方案阶段。"
    if recommendation == "shortlist":
        return f"{style} / {generation_mode} 版本具备筛选价值，建议进入 shortlist 再做人工复核。"
    return f"{style} / {generation_mode} 版本有基础可用性，但进入方案阶段前仍建议先重写或补强。"


def build_strengths(scores: dict[str, int]) -> list[str]:
    labels = {
        "hook_strength_score": "钩子强度",
        "conflict_clarity_score": "冲突清晰度",
        "relationship_tension_score": "关系张力",
        "reversal_expandability_score": "反转可展开性",
        "style_fit_score": "风格贴合度",
        "plan_readiness_score": "可方案化程度",
    }
    sorted_items = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    strengths: list[str] = []
    for field_name, score in sorted_items[:2]:
        if score >= 8:
            strengths.append(f"{labels[field_name]}较强")
    if not strengths:
        strengths.append("整体结构完整，可作为继续改写的基础")
    return strengths


def build_risks(scores: dict[str, int]) -> list[str]:
    labels = {
        "hook_strength_score": "钩子强度",
        "conflict_clarity_score": "冲突清晰度",
        "relationship_tension_score": "关系张力",
        "reversal_expandability_score": "反转可展开性",
        "style_fit_score": "风格贴合度",
        "plan_readiness_score": "可方案化程度",
    }
    sorted_items = sorted(scores.items(), key=lambda item: (item[1], item[0]))
    risks: list[str] = []
    for field_name, score in sorted_items[:2]:
        if score <= 6:
            risks.append(f"{labels[field_name]}偏弱，建议重点补强")
    if not risks:
        risks.append("暂无明显短板，但仍建议人工复核细节表达")
    return risks


def evaluate_deterministic_idea_pack(pack: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(pack, dict):
        raise ValueError("pack 必须是对象。")

    pack_id = pack.get("pack_id")
    if isinstance(pack_id, bool) or not isinstance(pack_id, int):
        raise ValueError("pack.pack_id 必须是整数。")

    style = normalize_text_field(pack, "style")
    generation_mode = normalize_text_field(pack, "generation_mode")
    hook = normalize_text_field(pack, "hook")
    core_relationship = normalize_text_field(pack, "core_relationship")
    main_conflict = normalize_text_field(pack, "main_conflict")
    reversal_direction = normalize_text_field(pack, "reversal_direction")
    recommended_tags = normalize_string_list_field(pack, "recommended_tags")

    scores = {
        "hook_strength_score": score_hook_strength(hook),
        "conflict_clarity_score": score_conflict_clarity(main_conflict),
        "relationship_tension_score": score_relationship_tension(core_relationship, main_conflict),
        "reversal_expandability_score": score_reversal_expandability(reversal_direction),
        "style_fit_score": score_style_fit(style, hook, core_relationship, main_conflict, reversal_direction),
        "plan_readiness_score": score_plan_readiness(
            hook,
            core_relationship,
            main_conflict,
            reversal_direction,
            recommended_tags,
        ),
    }
    total_score = sum(scores.values())
    recommendation = build_recommendation(total_score)

    return {
        "pack_id": pack_id,
        "evaluation_mode": DEFAULT_EVALUATION_MODE,
        "evaluator_name": DEFAULT_EVALUATOR_NAME,
        "total_score": total_score,
        **scores,
        "recommendation": recommendation,
        "summary": build_summary(style, generation_mode, total_score, recommendation),
        "strengths": build_strengths(scores),
        "risks": build_risks(scores),
    }
