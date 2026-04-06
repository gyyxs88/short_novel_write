from __future__ import annotations

import pytest

from tools.story_plan_builder import build_deterministic_story_plans


ZHIHU_PACK = {
    "pack_id": 11,
    "source_mode": "seed_generate",
    "style": "zhihu",
    "generation_mode": "deterministic",
    "style_reason": "这组卡更适合强钩子、强冲突、快节奏的知乎式整理。",
    "hook": "她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
    "core_relationship": "女主与失踪前任、现任未婚夫之间重新形成对立关系。",
    "main_conflict": "她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
    "reversal_direction": "她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
    "recommended_tags": ["悬疑", "婚礼危机", "前任回潮"],
}

DOUBAN_PACK = {
    "pack_id": 12,
    "source_mode": "prompt_match",
    "style": "douban",
    "generation_mode": "llm",
    "style_reason": "这组卡更适合从关系裂口和余味切入。",
    "hook": "她和多年不见的初恋在母亲葬礼后重逢，才发现彼此都还记得那场没被说开的火灾。",
    "core_relationship": "她和初恋在沉默、愧疚和迟到解释之间重新靠近。",
    "main_conflict": "她想让生活继续往前走，但旧事不断逼她承认自己一直靠误解维持体面。",
    "reversal_direction": "真正迟到的不是答案，而是她终于肯承认自己当年也参与了那场沉默。",
    "recommended_tags": ["重逢", "葬礼", "旧事"],
}


def test_build_deterministic_story_plans_returns_four_complete_variants() -> None:
    plans = build_deterministic_story_plans(pack=ZHIHU_PACK)

    assert len(plans) == 4
    assert [item["variant_key"] for item in plans] == [
        "truth_hunt",
        "relationship_backfire",
        "nested_trap",
        "sacrifice_redemption",
    ]
    assert plans[0]["title"] == "短信背后的真相"
    assert plans[1]["title"] == "前任反咬之后"
    assert plans[0]["generation_mode"] == "deterministic"
    assert plans[0]["writing_brief"]["target_char_range"] == [10000, 30000]
    assert plans[0]["writing_brief"]["target_chapter_count"] == 6
    assert len(plans[0]["chapter_rhythm"]) == 6
    assert plans[0]["chapter_rhythm"][0]["chapter_number"] == 1
    assert plans[0]["chapter_rhythm"][-1]["chapter_number"] == 6
    assert plans[0]["writing_brief"]["title"] == plans[0]["title"]


def test_build_deterministic_story_plans_uses_douban_default_target_range() -> None:
    plans = build_deterministic_story_plans(pack=DOUBAN_PACK)

    assert len(plans) == 4
    assert plans[0]["writing_brief"]["target_char_range"] == [10000, 20000]
    assert plans[0]["writing_brief"]["target_chapter_count"] == 6


def test_build_deterministic_story_plans_supports_douban_and_custom_sizes() -> None:
    plans = build_deterministic_story_plans(
        pack=DOUBAN_PACK,
        target_char_range=[8000, 12000],
        target_chapter_count=8,
        plan_count=3,
    )

    assert len(plans) == 3
    assert [item["variant_key"] for item in plans] == [
        "emotion_revisit",
        "life_crack",
        "late_truth",
    ]
    assert plans[0]["style"] == "douban"
    assert plans[0]["variant_label"] == "旧关系回潮型"
    assert plans[0]["writing_brief"]["target_char_range"] == [8000, 12000]
    assert plans[0]["writing_brief"]["target_chapter_count"] == 8
    assert len(plans[0]["chapter_rhythm"]) == 8


def test_build_deterministic_story_plans_rejects_invalid_plan_count() -> None:
    with pytest.raises(ValueError, match="plan_count 仅支持"):
        build_deterministic_story_plans(pack=ZHIHU_PACK, plan_count=2)
