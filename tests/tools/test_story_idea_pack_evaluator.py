from __future__ import annotations

from tools.story_idea_pack_evaluator import evaluate_deterministic_idea_pack


PACK = {
    "pack_id": 11,
    "style": "zhihu",
    "generation_mode": "llm",
    "hook": "她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
    "core_relationship": "女主与失踪前任、现任未婚夫之间重新形成对立关系。",
    "main_conflict": "她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
    "reversal_direction": "她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
    "recommended_tags": ["悬疑", "婚礼危机", "前任回潮"],
}


def test_evaluate_deterministic_idea_pack_returns_structured_scores() -> None:
    evaluation = evaluate_deterministic_idea_pack(PACK)

    assert evaluation["pack_id"] == 11
    assert evaluation["evaluation_mode"] == "deterministic"
    assert evaluation["evaluator_name"] == "heuristic_v1"
    assert 6 <= evaluation["hook_strength_score"] <= 10
    assert 6 <= evaluation["conflict_clarity_score"] <= 10
    assert 6 <= evaluation["reversal_expandability_score"] <= 10
    assert evaluation["total_score"] == (
        evaluation["hook_strength_score"]
        + evaluation["conflict_clarity_score"]
        + evaluation["relationship_tension_score"]
        + evaluation["reversal_expandability_score"]
        + evaluation["style_fit_score"]
        + evaluation["plan_readiness_score"]
    )
    assert evaluation["recommendation"] in {"priority_select", "shortlist", "rework"}
    assert evaluation["strengths"]
    assert evaluation["risks"]
