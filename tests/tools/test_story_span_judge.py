import json

from tools.story_span_judge import (
    apply_llm_judge_to_changed_spans,
    build_llm_story_span_judgement,
)


def test_build_llm_story_span_judgement_supports_chat_completions_provider() -> None:
    changed_spans = [
        {
            "target_index": 0,
            "issue_code": "abstract_emotion",
            "chapter_number": 1,
            "start_offset": 0,
            "end_offset": 11,
            "original_text": "她感到痛苦，也感到不安。",
            "rewritten_text": "她攥紧手指，后背一下绷住，连呼吸都乱了。",
            "requested_rewrite_modes": ["concretize_emotion"],
            "applied_rewrite_modes": ["concretize_emotion"],
            "evidence": {"matched_term": "痛苦"},
            "risk_flags": [],
        }
    ]
    captured: dict[str, object] = {}

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        captured["api_url"] = api_url
        captured["payload"] = payload
        return {
            "id": "judge_chatcmpl_123",
            "usage": {"prompt_tokens": 111, "completion_tokens": 222, "total_tokens": 333},
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "items": [
                                    {
                                        "target_index": 0,
                                        "decision": "accept",
                                        "reason": "动作化改写更具体，也没有破坏语义。",
                                        "agent_review_required": False,
                                    }
                                ]
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
        }

    judged = build_llm_story_span_judgement(
        before_content_markdown="她感到痛苦，也感到不安。",
        changed_spans=changed_spans,
        style="zhihu",
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert judged["provider_name"] == "openrouter"
    assert judged["api_mode"] == "chat_completions"
    assert judged["provider_response_id"] == "judge_chatcmpl_123"
    assert judged["accepted_candidate_count"] == 1
    assert judged["judge_items"][0]["decision"] == "accept"
    assert judged["token_usage"] == {"prompt_tokens": 111, "completion_tokens": 222, "total_tokens": 333}
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["messages"][0]["role"] == "system"
    assert request_payload["messages"][1]["role"] == "user"


def test_apply_llm_judge_to_changed_spans_filters_review_items() -> None:
    before_content_markdown = "甲。乙。"
    rewrite_result = {
        "generation_mode": "deterministic",
        "style": "zhihu",
        "changed_spans": [
            {
                "target_index": 0,
                "issue_code": "ai_ism",
                "chapter_number": 1,
                "start_offset": 0,
                "end_offset": 2,
                "original_text": "甲。",
                "rewritten_text": "甲改。",
                "requested_rewrite_modes": ["remove_ai_phrases"],
                "applied_rewrite_modes": ["remove_ai_phrases"],
                "evidence": {},
                "risk_flags": [],
                "revision_reason": "按 remove_ai_phrases 处理 ai_ism。",
            },
            {
                "target_index": 1,
                "issue_code": "abstract_emotion",
                "chapter_number": 1,
                "start_offset": 2,
                "end_offset": 4,
                "original_text": "乙。",
                "rewritten_text": "乙改。",
                "requested_rewrite_modes": ["concretize_emotion"],
                "applied_rewrite_modes": ["concretize_emotion"],
                "evidence": {},
                "risk_flags": ["dialogue_fragment"],
                "revision_reason": "按 concretize_emotion 处理 abstract_emotion。",
            },
        ],
        "changed_span_count": 2,
        "risk_alerts": [{"target_index": 1, "risk_flags": ["dialogue_fragment"]}],
        "risk_alert_count": 1,
        "after_content_markdown": "甲改。乙改。",
        "revision_summary": "本次共改写 2 个片段。",
    }
    judge_result = {
        "generation_mode": "llm",
        "provider_name": "mock",
        "api_mode": "chat_completions",
        "model_name": "mock-judge",
        "model_config_key": "mock_judge",
        "provider_response_id": "judge_mock_2",
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        "judge_items": [
            {
                "target_index": 0,
                "decision": "accept",
                "reason": "第一处改写自然。",
                "agent_review_required": False,
            },
            {
                "target_index": 1,
                "decision": "review",
                "reason": "对白片段风险高，改交给 agent 复核。",
                "agent_review_required": True,
            },
        ],
        "accepted_candidate_count": 1,
        "rejected_candidate_count": 0,
        "review_candidate_count": 1,
        "agent_review_required_count": 1,
    }

    applied = apply_llm_judge_to_changed_spans(
        before_content_markdown=before_content_markdown,
        rewrite_result=rewrite_result,
        judge_result=judge_result,
    )

    assert applied["changed_span_count"] == 1
    assert applied["after_content_markdown"] == "甲改。乙。"
    assert applied["changed_spans"][0]["judge_decision"] == "accept"
    assert applied["review_metadata"]["agent_review_required_count"] == 1
    assert applied["review_metadata"]["agent_review_required_spans"][0]["judge_decision"] == "review"
