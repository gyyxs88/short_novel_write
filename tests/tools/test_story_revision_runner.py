from tools.story_revision_runner import revise_story_draft_deterministic
from tools.story_span_judge import apply_llm_judge_to_changed_spans
from tools.story_style_profile import get_builtin_style_profile


AI_ISH_STORY = """# 回声里的婚礼

## 简介

婚礼前夜，她收到一条旧号码发来的短信。短信没有解释太多，只说那一刻别相信任何人。

## 正文

### 1

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。

### 2

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。

### 3

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。
"""


RISKY_DIALOGUE_STORY = """# 夜谈

## 简介

她在重逢后的夜里终于问出埋了很多年的问题。

## 正文

### 1

她感到痛苦，也感到不安。

“你后悔吗？”陈默问。

“我后悔的是，浪费了十五年时间。”她说。
"""


REVIEW_DIALOGUE_STORY = """# 夜谈

## 简介

她在重逢后的夜里终于问出埋了很多年的问题。

## 正文

### 1

她感到痛苦，也感到不安。

“她感到难过，也感到压抑。”陈默说。
"""


REMINDER_ONLY_STORY = """# 回楼

## 简介

她回到旧楼取走最后一只箱子，却在门口重新看见那个本该消失的人。

## 正文

### 1

走廊灯泡坏了一半，她把箱子放到墙边，抬手去敲门。门一开，对方眼神闪过一丝迟疑，又很快把笑意压了回去。

### 2

她没有马上进门，只用鞋尖碰了一下门槛。对方让开半步，话里带着试探意味，像是还在等她先把旧账提出来。

### 3

她侧身进屋，手背擦过门框上的灰。桌上那只杯子还有热气，这次重逢不是她想象中的平静叙旧，而是把没说完的话重新顶到了面前。
"""


def test_revise_story_draft_deterministic_runs_revision_rounds() -> None:
    result = revise_story_draft_deterministic(
        content_markdown=AI_ISH_STORY,
        style="zhihu",
        profile=get_builtin_style_profile("zhihu_tight_hook"),
        revision_modes=["remove_ai_phrases", "concretize_emotion", "compress_exposition"],
        max_rounds=2,
        max_spans_per_round=2,
    )

    assert result["generation_mode"] == "deterministic"
    assert result["round_count"] >= 1
    assert len(result["rounds"]) == result["round_count"]
    assert result["after_content_markdown"] != AI_ISH_STORY
    assert result["initial_issue_count"] >= result["final_issue_count"]
    assert result["final_overall_score"] >= result["initial_overall_score"]
    assert result["rounds"][0]["changed_span_count"] >= 1
    assert result["stop_reason"] in {
        "max_rounds_reached",
        "no_issues_remaining",
        "no_rewrite_targets",
        "no_changes_applied",
    }


def test_revise_story_draft_deterministic_keeps_agent_review_queue_from_span_judge() -> None:
    def fake_span_judge(**kwargs: object) -> dict[str, object]:
        rewrite_result = kwargs["rewrite_result"]
        assert isinstance(rewrite_result, dict)
        changed_spans = rewrite_result["changed_spans"]
        assert isinstance(changed_spans, list)
        judge_items = []
        for index, span in enumerate(changed_spans):
            assert isinstance(span, dict)
            decision = "review" if index == 1 else "accept"
            judge_items.append(
                {
                    "target_index": span["target_index"],
                    "decision": decision,
                    "reason": "第二个片段改交给 agent 复核。" if decision == "review" else "普通片段可以直接接受。",
                    "agent_review_required": decision == "review",
                }
            )
        return apply_llm_judge_to_changed_spans(
            before_content_markdown=str(kwargs["before_content_markdown"]),
            rewrite_result=rewrite_result,
            judge_result={
                "generation_mode": "llm",
                "provider_name": "mock",
                "api_mode": "chat_completions",
                "model_name": "mock-judge",
                "model_config_key": "mock_judge",
                "provider_response_id": "judge_mock_1",
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                "judge_items": judge_items,
                "accepted_candidate_count": sum(1 for item in judge_items if item["decision"] == "accept"),
                "rejected_candidate_count": 0,
                "review_candidate_count": sum(1 for item in judge_items if item["decision"] == "review"),
                "agent_review_required_count": sum(1 for item in judge_items if item["agent_review_required"]),
            },
        )

    result = revise_story_draft_deterministic(
        content_markdown=AI_ISH_STORY,
        style="zhihu",
        profile=get_builtin_style_profile("zhihu_tight_hook"),
        revision_modes=["remove_ai_phrases", "concretize_emotion"],
        max_rounds=1,
        max_spans_per_round=2,
        span_judge_fn=fake_span_judge,
    )

    assert result["round_count"] == 1
    assert result["after_content_markdown"] != AI_ISH_STORY
    assert result["rounds"][0]["review_metadata"]["agent_review_required_count"] >= 1


def test_revise_story_draft_deterministic_does_not_treat_reminder_only_signals_as_rewrite_targets() -> None:
    result = revise_story_draft_deterministic(
        content_markdown=REMINDER_ONLY_STORY,
        style="douban",
        profile=get_builtin_style_profile("douban_subtle_scene"),
        revision_modes=["remove_ai_phrases", "concretize_emotion", "compress_exposition"],
        max_rounds=1,
        max_spans_per_round=2,
    )

    assert result["round_count"] == 0
    assert result["stop_reason"] == "no_issues_remaining"
    assert result["initial_analysis_report"]["risk_signal_count"] >= 2
    assert result["initial_issue_count"] == 0
    assert result["after_content_markdown"] == REMINDER_ONLY_STORY
