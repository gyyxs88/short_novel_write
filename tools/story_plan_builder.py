from __future__ import annotations

from typing import Any


DEFAULT_TARGET_CHAR_RANGES = {
    "zhihu": (10000, 30000),
    "douban": (10000, 20000),
}
DEFAULT_TARGET_CHAPTER_COUNT = 6
DEFAULT_PLAN_COUNT = 4
VALID_PLAN_COUNTS = {3, 4}
VALID_PLAN_STYLES = {"zhihu", "douban"}

TITLE_MOTIFS = (
    "短信",
    "电话",
    "婚礼",
    "葬礼",
    "失踪",
    "遗书",
    "遗嘱",
    "旧案",
    "火灾",
    "监控",
    "名单",
    "录音",
    "医院",
    "直播",
    "保险箱",
    "钥匙",
    "门外",
    "停尸房",
    "定位",
)
RELATIONSHIP_MOTIFS = (
    "前任",
    "初恋",
    "夫妻",
    "恋人",
    "未婚夫",
    "未婚妻",
    "白月光",
    "母女",
    "父女",
    "姐妹",
    "兄弟",
    "搭档",
    "家族",
    "闺蜜",
    "恩人",
)

PLAN_VARIANTS = {
    "zhihu": [
        {
            "variant_key": "truth_hunt",
            "variant_label": "真相追猎型",
            "genre_tone": "现代悬疑反转，快节奏推进，信息差强压迫。",
        },
        {
            "variant_key": "relationship_backfire",
            "variant_label": "关系反咬型",
            "genre_tone": "情感悬疑并行，关系对撞强，推进里不断翻旧账。",
        },
        {
            "variant_key": "nested_trap",
            "variant_label": "局中局设伏型",
            "genre_tone": "设局与反设局并行，节奏密，章尾持续留钩。",
        },
        {
            "variant_key": "sacrifice_redemption",
            "variant_label": "代价救赎型",
            "genre_tone": "高代价抉择驱动，情绪爆点和真相回收并行。",
        },
    ],
    "douban": [
        {
            "variant_key": "emotion_revisit",
            "variant_label": "旧关系回潮型",
            "genre_tone": "关系悬疑与现实情绪并行，推进克制但持续绷紧。",
        },
        {
            "variant_key": "life_crack",
            "variant_label": "生活裂口型",
            "genre_tone": "从日常缝隙切入，缓慢揭开处境和选择的代价。",
        },
        {
            "variant_key": "late_truth",
            "variant_label": "迟到真相型",
            "genre_tone": "情绪余味重，认知翻转晚到，但落点扎实。",
        },
        {
            "variant_key": "silent_betrayal",
            "variant_label": "沉默背叛型",
            "genre_tone": "关系内耗与现实压力叠加，转折更偏钝痛感。",
        },
    ],
}


def normalize_plan_style(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("style 必须是非空字符串。")
    normalized = value.strip()
    if normalized not in VALID_PLAN_STYLES:
        raise ValueError("style 仅支持 zhihu 或 douban。")
    return normalized


def resolve_default_target_char_range(style: str) -> tuple[int, int]:
    normalized_style = normalize_plan_style(style)
    return DEFAULT_TARGET_CHAR_RANGES[normalized_style]


def normalize_target_char_range(value: Any = None, *, style: str | None = None) -> tuple[int, int]:
    if value is None:
        if style is None:
            raise ValueError("未显式传 target_char_range 时，必须提供 style。")
        return resolve_default_target_char_range(style)
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    ):
        raise ValueError("target_char_range 必须是两个整数构成的数组。")
    minimum, maximum = value
    if minimum < 1000 or maximum < minimum:
        raise ValueError("target_char_range 必须满足最小值大于等于 1000，且最大值不小于最小值。")
    return minimum, maximum


def normalize_target_chapter_count(value: Any = None) -> int:
    if value is None:
        return DEFAULT_TARGET_CHAPTER_COUNT
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("target_chapter_count 必须是整数。")
    if value < 4 or value > 12:
        raise ValueError("target_chapter_count 仅支持 4-12。")
    return value


def normalize_plan_count(value: Any = None) -> int:
    if value is None:
        return DEFAULT_PLAN_COUNT
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("plan_count 必须是整数。")
    if value not in VALID_PLAN_COUNTS:
        raise ValueError(f"plan_count 仅支持：{sorted(VALID_PLAN_COUNTS)}")
    return value


def normalize_pack_text(pack: dict[str, Any], field_name: str) -> str:
    value = pack.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pack.{field_name} 必须是非空字符串。")
    return value.strip()


def normalize_pack_tags(pack: dict[str, Any], field_name: str) -> list[str]:
    value = pack.get(field_name)
    if not isinstance(value, list) or len(value) < 3:
        raise ValueError(f"pack.{field_name} 必须至少包含 3 个标签。")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"pack.{field_name} 里的每一项都必须是非空字符串。")
        normalized.append(item.strip())
    return normalized


def normalize_pack(pack: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(pack, dict):
        raise ValueError("pack 必须是对象。")
    pack_id = pack.get("pack_id")
    if isinstance(pack_id, bool) or not isinstance(pack_id, int):
        raise ValueError("pack.pack_id 必须是整数。")
    style = normalize_plan_style(pack.get("style"))

    return {
        "pack_id": pack_id,
        "source_mode": normalize_pack_text(pack, "source_mode"),
        "style": style,
        "generation_mode": normalize_pack_text(pack, "generation_mode"),
        "hook": normalize_pack_text(pack, "hook"),
        "style_reason": normalize_pack_text(pack, "style_reason"),
        "core_relationship": normalize_pack_text(pack, "core_relationship"),
        "main_conflict": normalize_pack_text(pack, "main_conflict"),
        "reversal_direction": normalize_pack_text(pack, "reversal_direction"),
        "recommended_tags": normalize_pack_tags(pack, "recommended_tags"),
    }


def extract_keywords(text: str, keywords: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if keyword in text and keyword not in hits:
            hits.append(keyword)
    return hits


def build_plan_context(pack: dict[str, Any]) -> dict[str, Any]:
    normalized_pack = normalize_pack(pack)
    hook = normalized_pack["hook"]
    core_relationship = normalized_pack["core_relationship"]
    main_conflict = normalized_pack["main_conflict"]
    reversal_direction = normalized_pack["reversal_direction"]

    motif_hits = extract_keywords(
        " ".join([hook, main_conflict, reversal_direction]),
        TITLE_MOTIFS,
    )
    relation_hits = extract_keywords(core_relationship, RELATIONSHIP_MOTIFS)
    recommended_tags = normalized_pack["recommended_tags"]

    primary_motif = motif_hits[0] if motif_hits else recommended_tags[0]
    secondary_motif = motif_hits[1] if len(motif_hits) > 1 else recommended_tags[1]
    relationship_motif = relation_hits[0] if relation_hits else recommended_tags[2]
    protagonist_profile = (
        f"一个被“{primary_motif}”重新拖回旧局、不得不亲手拆解真相的人"
        if normalized_pack["style"] == "zhihu"
        else f"一个试图维持体面生活，却被“{primary_motif}”再次撕开旧伤的人"
    )

    return {
        **normalized_pack,
        "primary_motif": primary_motif,
        "secondary_motif": secondary_motif,
        "relationship_motif": relationship_motif,
        "protagonist_profile": protagonist_profile,
    }


def build_title(context: dict[str, Any], variant_key: str, variant_index: int) -> str:
    primary_motif = context["primary_motif"]
    secondary_motif = context["secondary_motif"]
    relationship_motif = context["relationship_motif"]

    if variant_key == "truth_hunt":
        return f"{primary_motif}背后的真相"
    if variant_key == "relationship_backfire":
        return f"{relationship_motif}反咬之后"
    if variant_key == "nested_trap":
        return f"{primary_motif}局中局"
    if variant_key == "sacrifice_redemption":
        return f"{secondary_motif}之后"
    if variant_key == "emotion_revisit":
        return f"{relationship_motif}回来以后"
    if variant_key == "life_crack":
        return f"{primary_motif}撕开的生活"
    if variant_key == "late_truth":
        return f"{secondary_motif}迟到的答案"
    if variant_key == "silent_betrayal":
        return f"{relationship_motif}里的沉默"
    return f"{primary_motif}计划{variant_index}"


def build_selling_point(context: dict[str, Any], variant_key: str) -> str:
    if variant_key in {"truth_hunt", "late_truth"}:
        return f"用“{context['primary_motif']}”做强入口，把{context['main_conflict']}一路追到真相翻面。"
    if variant_key in {"relationship_backfire", "emotion_revisit", "silent_betrayal"}:
        return f"把“{context['core_relationship']}”推到无法回避的位置，让关系本身成为剧情引擎。"
    if variant_key == "nested_trap":
        return f"让主角在{context['main_conflict']}里反向设局，把{context['reversal_direction']}做成连环翻面。"
    return f"用“{context['primary_motif']}”带出高代价抉择，让真相回收和情绪落点一起成立。"


def build_protagonist_goal(context: dict[str, Any], variant_key: str) -> str:
    if variant_key == "truth_hunt":
        return f"查清“{context['primary_motif']}”背后的操盘逻辑，并在真相公开前保住自己。"
    if variant_key == "relationship_backfire":
        return f"在不彻底毁掉现有关系前，确认谁在利用“{context['relationship_motif']}”把她拖回旧局。"
    if variant_key == "nested_trap":
        return f"利用对手误判她仍被蒙在鼓里的时间差，主动反设一局。"
    if variant_key == "sacrifice_redemption":
        return f"在真相和体面生活之间做出选择，争取把代价控制在自己能承担的范围内。"
    if variant_key == "emotion_revisit":
        return f"弄清旧关系为什么会在“{context['primary_motif']}”出现后重新失衡。"
    if variant_key == "life_crack":
        return f"在不让生活全面崩塌的前提下，确认“{context['primary_motif']}”撕开的裂口究竟通向哪里。"
    if variant_key == "late_truth":
        return f"追到那个总被推迟一步的答案，弄清谁在故意让她慢半拍。"
    return f"承认并拆开关系里的沉默与背叛，避免自己继续被旧局消耗。"


def build_key_turning_point(context: dict[str, Any], variant_key: str) -> str:
    if variant_key in {"truth_hunt", "late_truth"}:
        return "主角发现最可靠的一条证据，其实是有人故意递到她手里的诱饵。"
    if variant_key in {"relationship_backfire", "silent_betrayal"}:
        return "她意识到自己一直保护的人并不只是受害者，对方也在主动推动局势。"
    if variant_key == "nested_trap":
        return "她发现自己早年埋下的一个细节，正是对手今天敢设局的底牌。"
    if variant_key == "sacrifice_redemption":
        return "只有主动放弃眼前最重要的一段关系，她才有机会逼幕后现身。"
    if variant_key == "emotion_revisit":
        return "她以为回来的只是旧人，真正回来的是当年没被说出口的责任。"
    return "她终于明白真正压垮生活的不是事件本身，而是所有人共同维持的沉默。"


def build_ending_direction(context: dict[str, Any], variant_key: str) -> str:
    if variant_key in {"truth_hunt", "nested_trap"}:
        return "主角公开真相并完成反咬，但必须亲手切断一段再也回不去的关系。"
    if variant_key in {"relationship_backfire", "silent_betrayal"}:
        return "真相被摊到台面上，关系没有被修复，只被重新命名。"
    if variant_key == "sacrifice_redemption":
        return "她赢下真相，输掉眼前的体面与安全感，但完成了真正的止损。"
    if variant_key == "emotion_revisit":
        return "她没有回到过去，但终于能把过去放回它该在的位置。"
    return "答案来得很晚，却足够让她重新决定今后要和谁、以什么方式继续生活。"


def build_variant_conflict(context: dict[str, Any], variant_key: str) -> str:
    if variant_key == "nested_trap":
        return f"{context['main_conflict']}，同时她还得抢在对手收网前，把自己改写成棋手。"
    if variant_key in {"relationship_backfire", "silent_betrayal"}:
        return f"{context['main_conflict']}，而最危险的阻力恰恰来自她最难放手的人。"
    if variant_key == "sacrifice_redemption":
        return f"{context['main_conflict']}，她每往前一步，都要先决定愿意失去什么。"
    return context["main_conflict"]


def build_variant_relationship(context: dict[str, Any], variant_key: str) -> str:
    if variant_key in {"relationship_backfire", "emotion_revisit", "silent_betrayal"}:
        return f"{context['core_relationship']}，而且彼此都在隐瞒真正想保护的东西。"
    if variant_key == "nested_trap":
        return f"{context['core_relationship']}，但两人真正的对位关系直到中后段才会被揭开。"
    return context["core_relationship"]


def build_chapter_rhythm(
    *,
    context: dict[str, Any],
    variant_label: str,
    key_turning_point: str,
    ending_direction: str,
    target_chapter_count: int,
) -> list[dict[str, Any]]:
    beats: list[dict[str, str]] = []
    for chapter_number in range(1, target_chapter_count + 1):
        if chapter_number == 1:
            stage = "异常闯入"
            focus = context["hook"]
            advance = "主角立下短期目标，故事核心问题被明确抛出。"
            chapter_hook = f"她意识到这件事和“{context['primary_motif']}”绝不是巧合。"
        elif chapter_number == 2:
            stage = "第一轮追查"
            focus = f"围绕“{context['primary_motif']}”追出第一条有效线索。"
            advance = f"{context['core_relationship']}开始真正施压。"
            chapter_hook = "她第一次发现自己被人提前一步布局。"
        elif chapter_number < target_chapter_count // 2:
            stage = "关系加压"
            focus = f"{context['main_conflict']}被外化成具体阻力。"
            advance = f"“{variant_label}”的推进方向开始显形。"
            chapter_hook = "一条旧信息把她推向更危险的位置。"
        elif chapter_number == target_chapter_count // 2:
            stage = "中段偏转"
            focus = key_turning_point
            advance = "主角的认知被改写，原先的目标需要重订。"
            chapter_hook = "她开始怀疑自己看到的所有证据都有第二层解释。"
        elif chapter_number < target_chapter_count - 1:
            stage = "反向布局"
            focus = "主角试图掌控节奏，开始反设局或主动切断关系。"
            advance = f"{context['reversal_direction']}被拆出更多结构。"
            chapter_hook = "真正的代价第一次落到她自己身上。"
        elif chapter_number == target_chapter_count - 1:
            stage = "总爆点前夜"
            focus = key_turning_point
            advance = "所有隐藏关系和旧账在这一章汇拢。"
            chapter_hook = "她终于确认最后该相信谁、该舍弃谁。"
        else:
            stage = "回收落点"
            focus = ending_direction
            advance = "核心冲突被正面解决，人物关系完成最后命名。"
            chapter_hook = "尾章不再留悬念，而是把情绪和代价落地。"

        beats.append(
            {
                "chapter_number": chapter_number,
                "stage": stage,
                "focus": focus,
                "advance": advance,
                "chapter_hook": chapter_hook,
            }
        )
    return beats


def build_writing_brief(
    *,
    title: str,
    genre_tone: str,
    protagonist_profile: str,
    protagonist_goal: str,
    core_relationship: str,
    main_conflict: str,
    key_turning_point: str,
    ending_direction: str,
    target_char_range: tuple[int, int],
    target_chapter_count: int,
) -> dict[str, Any]:
    return {
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
    }


def build_deterministic_story_plans(
    *,
    pack: dict[str, Any],
    target_char_range: list[int] | tuple[int, int] | None = None,
    target_chapter_count: int | None = None,
    plan_count: int | None = None,
) -> list[dict[str, Any]]:
    context = build_plan_context(pack)
    normalized_target_char_range = normalize_target_char_range(
        list(target_char_range) if isinstance(target_char_range, tuple) else target_char_range,
        style=context["style"],
    )
    normalized_target_chapter_count = normalize_target_chapter_count(target_chapter_count)
    normalized_plan_count = normalize_plan_count(plan_count)
    variants = PLAN_VARIANTS[context["style"]][:normalized_plan_count]

    plans: list[dict[str, Any]] = []
    for variant_index, variant in enumerate(variants, start=1):
        title = build_title(context, variant["variant_key"], variant_index)
        protagonist_goal = build_protagonist_goal(context, variant["variant_key"])
        core_relationship = build_variant_relationship(context, variant["variant_key"])
        main_conflict = build_variant_conflict(context, variant["variant_key"])
        key_turning_point = build_key_turning_point(context, variant["variant_key"])
        ending_direction = build_ending_direction(context, variant["variant_key"])
        chapter_rhythm = build_chapter_rhythm(
            context=context,
            variant_label=variant["variant_label"],
            key_turning_point=key_turning_point,
            ending_direction=ending_direction,
            target_chapter_count=normalized_target_chapter_count,
        )
        genre_tone = variant["genre_tone"]
        writing_brief = build_writing_brief(
            title=title,
            genre_tone=genre_tone,
            protagonist_profile=context["protagonist_profile"],
            protagonist_goal=protagonist_goal,
            core_relationship=core_relationship,
            main_conflict=main_conflict,
            key_turning_point=key_turning_point,
            ending_direction=ending_direction,
            target_char_range=normalized_target_char_range,
            target_chapter_count=normalized_target_chapter_count,
        )
        plans.append(
            {
                "pack_id": context["pack_id"],
                "source_mode": context["source_mode"],
                "style": context["style"],
                "variant_index": variant_index,
                "variant_key": variant["variant_key"],
                "variant_label": variant["variant_label"],
                "generation_mode": "deterministic",
                "provider_name": "",
                "api_mode": "",
                "model_name": "",
                "model_config_key": "",
                "provider_response_id": "",
                "title": title,
                "genre_tone": genre_tone,
                "selling_point": build_selling_point(context, variant["variant_key"]),
                "protagonist_profile": context["protagonist_profile"],
                "protagonist_goal": protagonist_goal,
                "core_relationship": core_relationship,
                "main_conflict": main_conflict,
                "key_turning_point": key_turning_point,
                "ending_direction": ending_direction,
                "chapter_rhythm": chapter_rhythm,
                "writing_brief": writing_brief,
            }
        )
    return plans
