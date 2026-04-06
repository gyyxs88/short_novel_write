from __future__ import annotations

import pytest

from tools.story_payload_builder import build_story_payload


PLAN = {
    "plan_id": 31,
    "pack_id": 11,
    "source_mode": "seed_generate",
    "style": "zhihu",
    "variant_index": 1,
    "variant_key": "truth_hunt",
    "variant_label": "真相追猎型",
    "generation_mode": "deterministic",
    "provider_name": "",
    "api_mode": "",
    "model_name": "",
    "model_config_key": "",
    "provider_response_id": "",
    "title": "短信背后的真相",
    "genre_tone": "现代悬疑反转，快节奏推进。",
    "selling_point": "用婚礼倒计时压迫感推动真相翻面。",
    "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
    "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
    "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
    "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
    "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
    "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
    "chapter_rhythm": [
        {"chapter_number": 1, "stage": "异常闯入", "focus": "短信到来", "advance": "主角被迫回头追查", "chapter_hook": "她意识到这条短信不是恶作剧。"},
        {"chapter_number": 2, "stage": "第一轮追查", "focus": "婚礼线索", "advance": "前任和未婚夫同时施压", "chapter_hook": "她第一次发现自己被人提前一步布局。"},
        {"chapter_number": 3, "stage": "关系加压", "focus": "旧案旧情叠加", "advance": "关系被迫公开对撞", "chapter_hook": "她发现最危险的人并不在明处。"},
        {"chapter_number": 4, "stage": "中段偏转", "focus": "短信是诱饵", "advance": "主角认知被改写", "chapter_hook": "她开始怀疑自己看到的所有证据都有第二层解释。"},
        {"chapter_number": 5, "stage": "总爆点前夜", "focus": "主角主动反设局", "advance": "所有隐藏关系汇拢", "chapter_hook": "她终于确认最后该相信谁、该舍弃谁。"},
        {"chapter_number": 6, "stage": "回收落点", "focus": "真相公开", "advance": "核心冲突被解决", "chapter_hook": "尾章把代价和关系一起落地。"},
    ],
    "writing_brief": {
        "title": "短信背后的真相",
        "genre_tone": "现代悬疑反转，快节奏推进。",
        "target_char_range": [5000, 8000],
        "target_chapter_count": 6,
        "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
        "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
        "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
        "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
        "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
        "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
    },
}


def test_build_story_payload_returns_complete_payload() -> None:
    payload = build_story_payload(plan=PLAN)

    assert payload["plan_id"] == 31
    assert payload["title"] == "短信背后的真相"
    assert payload["target_char_range"] == [5000, 8000]
    assert payload["target_chapter_count"] == 6
    assert len(payload["chapter_blueprints"]) == 6
    assert payload["chapter_blueprints"][0]["objective"]
    assert payload["summary_guidance"]
    assert payload["source_plan"]["variant_key"] == "truth_hunt"
    assert len(payload["writing_rules"]) >= 3


def test_build_story_payload_rejects_invalid_plan() -> None:
    with pytest.raises(ValueError, match="plan.title 必须是非空字符串"):
        build_story_payload(
            plan={
                **PLAN,
                "title": "",
            }
        )
