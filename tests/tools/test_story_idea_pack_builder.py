from __future__ import annotations

import pytest

from tools.story_idea_pack_builder import build_deterministic_idea_pack


CARD = {
    "card_id": 7,
    "source_mode": "seed_generate",
    "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
    "main_tags": ["Secret Past - 隐秘过去", "Missing Person - 失踪", "First Love - 初恋"],
}


def test_build_deterministic_idea_pack_returns_expected_zhihu_shape() -> None:
    pack = build_deterministic_idea_pack(card=CARD, style="zhihu")

    assert pack["source_mode"] == "seed_generate"
    assert pack["style"] == "zhihu"
    assert pack["generation_mode"] == "deterministic"
    assert pack["model_config_key"] == ""
    assert pack["style_reason"] == "这组卡更适合强钩子、强冲突、快节奏的知乎式整理。"
    assert pack["hook"] == "一条和“失踪”有关的线索，突然把主角拖回“悬疑 / 推理”和“现代”交叠的局面里。"
    assert pack["core_relationship"] == "主角与那个牵出“初恋”旧账的人，重新站到了彼此试探的位置。"
    assert pack["main_conflict"] == "为了查清“失踪”背后的真相，主角必须先面对“隐秘过去”带来的代价。"
    assert pack["reversal_direction"] == "表面上需要解决的是“失踪”，真正被掀开的却是“隐秘过去”埋下的旧账。"
    assert pack["recommended_tags"] == ["悬疑 / 推理", "失踪", "初恋"]


def test_build_deterministic_idea_pack_returns_distinct_douban_output() -> None:
    pack = build_deterministic_idea_pack(card=CARD, style="douban")

    assert pack["style"] == "douban"
    assert pack["style_reason"] == "这组卡更适合从关系裂口和情绪余味切入，整理成豆瓣式表达。"
    assert pack["hook"] == "一段被“初恋”重新牵动的关系，让主角又回到“悬疑 / 推理”和“现代”交错的生活缝隙里。"
    assert pack["main_conflict"] == "主角想维持眼前的平静，但“隐秘过去”不断逼她承认这段关系早已变形。"


def test_build_deterministic_idea_pack_is_stable_when_card_order_changes() -> None:
    first = build_deterministic_idea_pack(card=CARD, style="zhihu")
    second = build_deterministic_idea_pack(
        card={
            "card_id": 7,
            "source_mode": "seed_generate",
            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
            "main_tags": ["First Love - 初恋", "Missing Person - 失踪", "Secret Past - 隐秘过去"],
        },
        style="zhihu",
    )

    assert first == second


def test_build_deterministic_idea_pack_rejects_invalid_style() -> None:
    with pytest.raises(ValueError, match="style 仅支持 zhihu 或 douban。"):
        build_deterministic_idea_pack(card=CARD, style="weibo")


def test_build_deterministic_idea_pack_rejects_non_dict_card() -> None:
    with pytest.raises(ValueError, match="card 必须是对象。"):
        build_deterministic_idea_pack(card=["not-a-dict"], style="zhihu")


def test_build_deterministic_idea_pack_avoids_duplicate_recommended_tags() -> None:
    pack = build_deterministic_idea_pack(
        card={
            "card_id": 9,
            "source_mode": "seed_generate",
            "types": ["Modern - 现代", "Romance - 恋爱"],
            "main_tags": ["First Love - 初恋", "Reunion - 重逢", "Misunderstanding - 误会"],
        },
        style="zhihu",
    )

    assert len(pack["recommended_tags"]) == len(set(pack["recommended_tags"]))


def test_build_deterministic_idea_pack_normalizes_source_cards_to_unique_values() -> None:
    pack = build_deterministic_idea_pack(
        card={
            "card_id": 10,
            "source_mode": "seed_generate",
            "types": [
                "Modern - 现代",
                "Mystery - 悬疑 / 推理",
                "Modern - 现代",
            ],
            "main_tags": [
                "Secret Past - 隐秘过去",
                "Missing Person - 失踪",
                "First Love - 初恋",
                "First Love - 初恋",
            ],
        },
        style="zhihu",
    )

    assert pack["source_cards"]["types"] == ["Modern - 现代", "Mystery - 悬疑 / 推理"]
    assert pack["source_cards"]["main_tags"] == [
        "First Love - 初恋",
        "Missing Person - 失踪",
        "Secret Past - 隐秘过去",
    ]
