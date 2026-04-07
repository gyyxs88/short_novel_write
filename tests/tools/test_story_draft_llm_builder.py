from __future__ import annotations

import json

import pytest

from tools.story_draft_llm_builder import (
    build_llm_story_draft,
    build_llm_story_draft_with_fallbacks,
)
from tools.story_idea_pack_llm_builder import LlmExhaustedError, LlmResponseError
from tools.story_payload_builder import build_story_payload
from tools.story_structure_checker import count_content_chars


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


def build_long_summary() -> str:
    return (
        "婚礼前夜，失踪前任忽然用旧号码发来求救短信，说真正想让女主闭嘴的人一直躲在她最信任的关系里，"
        "她必须在天亮前拆穿旧案和婚约背后的双重骗局。"
    )


def build_exact_length_summary(char_count: int) -> str:
    return "概" * char_count


def build_exact_length_content(char_count: int) -> str:
    return "文" * char_count


def build_long_chapter_content(chapter_number: int) -> str:
    sentence = (
        f"第{chapter_number}章里，女主被迫顺着旧短信追到新的现场，"
        "一边处理眼前不断失控的婚礼安排，一边拆解前任、未婚夫和旧案之间互相套住的谎话，"
        "每往前一步都要付出更具体的代价，也让她更清楚自己已经回不到原来的安全位置。"
    )
    return "".join(sentence for _ in range(9))


def build_mock_draft_payload() -> dict[str, object]:
    return {
        "summary": build_long_summary(),
        "chapters": [
            {"chapter_number": 1, "content": build_long_chapter_content(1)},
            {"chapter_number": 2, "content": build_long_chapter_content(2)},
            {"chapter_number": 3, "content": build_long_chapter_content(3)},
            {"chapter_number": 4, "content": build_long_chapter_content(4)},
            {"chapter_number": 5, "content": build_long_chapter_content(5)},
            {"chapter_number": 6, "content": build_long_chapter_content(6)},
        ],
    }


def build_valid_draft_payload_with_summary_length(summary_chars: int) -> dict[str, object]:
    return {
        "summary": build_exact_length_summary(summary_chars),
        "chapters": [
            {"chapter_number": 1, "content": build_long_chapter_content(1)},
            {"chapter_number": 2, "content": build_long_chapter_content(2)},
            {"chapter_number": 3, "content": build_long_chapter_content(3)},
            {"chapter_number": 4, "content": build_long_chapter_content(4)},
            {"chapter_number": 5, "content": build_long_chapter_content(5)},
            {"chapter_number": 6, "content": build_long_chapter_content(6)},
        ],
    }


def build_short_invalid_draft_payload() -> dict[str, object]:
    return {
        "summary": build_exact_length_summary(120),
        "chapters": [
            {"chapter_number": 1, "content": "第一章很短。"},
            {"chapter_number": 2, "content": "第二章也很短。"},
            {"chapter_number": 3, "content": "第三章还是很短。"},
            {"chapter_number": 4, "content": "第四章依旧很短。"},
            {"chapter_number": 5, "content": "第五章继续很短。"},
            {"chapter_number": 6, "content": "第六章仍然很短。"},
        ],
    }


def build_overlong_non_segmented_draft_payload() -> dict[str, object]:
    return {
        "summary": build_exact_length_summary(100),
        "chapters": [
            {"chapter_number": 1, "content": build_exact_length_content(1600)},
            {"chapter_number": 2, "content": build_exact_length_content(1600)},
            {"chapter_number": 3, "content": build_exact_length_content(1600)},
            {"chapter_number": 4, "content": build_exact_length_content(1600)},
            {"chapter_number": 5, "content": build_exact_length_content(1600)},
            {"chapter_number": 6, "content": build_exact_length_content(1600)},
        ],
    }


def build_long_segmented_payload() -> dict[str, object]:
    long_plan = json.loads(json.dumps(PLAN, ensure_ascii=False))
    long_plan["writing_brief"]["target_char_range"] = [10000, 20000]
    return build_story_payload(plan=long_plan)


def build_douban_long_segmented_payload() -> dict[str, object]:
    long_plan = json.loads(json.dumps(PLAN, ensure_ascii=False))
    long_plan["style"] = "douban"
    long_plan["writing_brief"]["target_char_range"] = [10000, 20000]
    return build_story_payload(plan=long_plan)


def build_segmented_summary() -> str:
    return build_exact_length_summary(80)


def build_segmented_chapter_content(chapter_number: int) -> str:
    return f"第{chapter_number}章，" + ("冲突推进与关系反转。" * 200)


def test_build_llm_story_draft_supports_chat_completions_provider() -> None:
    payload = build_story_payload(plan=PLAN)
    captured: dict[str, object] = {}

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        captured["payload"] = payload
        return {
            "id": "chatcmpl_draft_123",
            "usage": {"prompt_tokens": 300, "completion_tokens": 900, "total_tokens": 1200},
            "choices": [{"message": {"content": json.dumps(build_mock_draft_payload(), ensure_ascii=False)}}],
        }

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert built["generation_mode"] == "llm"
    assert built["provider_name"] == "openrouter"
    assert built["model_name"] == "qwen/qwen3.6-plus:free"
    assert built["provider_response_id"] == "chatcmpl_draft_123"
    assert built["token_usage"] == {"prompt_tokens": 300, "completion_tokens": 900, "total_tokens": 1200}
    assert "## 正文" in built["content_markdown"]
    assert built["body_char_count"] >= 6
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["messages"][0]["role"] == "system"
    assert request_payload["stream"] is True


def test_build_llm_story_draft_rejects_invalid_output() -> None:
    payload = build_story_payload(plan=PLAN)

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        return {
            "id": "chatcmpl_invalid_draft",
            "choices": [{"message": {"content": "{\"summary\":\"只有简介\",\"chapters\":[]}"}},],
        }

    with pytest.raises(LlmResponseError, match="chapters 数量必须与目标章节数一致"):
        build_llm_story_draft(
            payload=payload,
            provider="openrouter",
            api_mode="chat_completions",
            model="qwen/qwen3.6-plus:free",
            api_key="test-key",
            transport=fake_transport,
        )


def test_build_llm_story_draft_supports_deepseek_json_mode() -> None:
    payload = build_story_payload(plan=PLAN)
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
            "id": "deepseek_draft_123",
            "choices": [{"message": {"content": json.dumps(build_mock_draft_payload(), ensure_ascii=False)}}],
        }

    built = build_llm_story_draft(
        payload=payload,
        provider="deepseek",
        api_mode="chat_completions",
        model="deepseek-chat",
        api_key="test-key",
        transport=fake_transport,
    )

    assert built["provider_name"] == "deepseek"
    assert captured["api_url"] == "https://api.deepseek.com/chat/completions"
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["stream"] is True
    assert request_payload["response_format"] == {"type": "json_object"}
    assert request_payload["max_tokens"] == 8192


def test_build_llm_story_draft_with_fallbacks_uses_next_route_after_failure() -> None:
    payload = build_story_payload(plan=PLAN)
    call_count = {"value": 0}

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        call_count["value"] += 1
        if call_count["value"] == 1:
            raise LlmResponseError("首个模型返回坏数据")
        return {
            "id": "chatcmpl_draft_fallback",
            "choices": [{"message": {"content": json.dumps(build_mock_draft_payload(), ensure_ascii=False)}}],
        }

    built = build_llm_story_draft_with_fallbacks(
        payload=payload,
        routes=[
            {
                "model_config_key": "route_a",
                "provider_name": "openrouter",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "model_name": "model-a",
                "api_url": "https://example.com/a",
            },
            {
                "model_config_key": "route_b",
                "provider_name": "openrouter",
                "api_key": "test-key",
                "api_mode": "chat_completions",
                "model_name": "model-b",
                "api_url": "https://example.com/b",
            },
        ],
        agent_fallback=True,
        transport=fake_transport,
    )

    assert built["model_config_key"] == "route_b"
    assert built["attempt_count"] == 2
    assert built["fallback_used"] is True
    assert built["attempts"][0]["status"] == "failed"
    assert built["attempts"][1]["status"] == "success"


def test_build_llm_story_draft_with_fallbacks_raises_agent_fallback_when_all_fail() -> None:
    payload = build_story_payload(plan=PLAN)

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        raise LlmResponseError("一直失败")

    with pytest.raises(LlmExhaustedError, match="请由 agent 兜底"):
        build_llm_story_draft_with_fallbacks(
            payload=payload,
            routes=[
                {
                    "model_config_key": "route_a",
                    "provider_name": "openrouter",
                    "api_key": "test-key",
                    "api_mode": "chat_completions",
                    "model_name": "model-a",
                    "api_url": "https://example.com/a",
                }
            ],
            agent_fallback=True,
            transport=fake_transport,
        )


def test_build_llm_story_draft_retries_once_when_length_constraints_fail() -> None:
    payload = build_story_payload(plan=PLAN)
    call_count = {"value": 0}
    prompts: list[str] = []

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        call_count["value"] += 1
        prompts.append(payload["messages"][1]["content"])
        response_body = (
            build_short_invalid_draft_payload()
            if call_count["value"] == 1
            else build_mock_draft_payload()
        )
        return {
            "id": f"chatcmpl_retry_{call_count['value']}",
            "choices": [{"message": {"content": json.dumps(response_body, ensure_ascii=False)}}],
        }

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert call_count["value"] == 2
    assert built["repair_attempt_used"] is True
    assert built["provider_response_id"] == "chatcmpl_retry_2"
    assert built["body_char_count"] >= 4880
    assert "当前草稿" not in prompts[0]
    assert "当前草稿" in prompts[1]
    assert "第一章很短。" in prompts[1]


def test_build_llm_story_draft_accepts_small_summary_overflow_without_trimming() -> None:
    payload = build_story_payload(plan=PLAN)
    call_count = {"value": 0}
    first_response = build_valid_draft_payload_with_summary_length(125)

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        call_count["value"] += 1
        return {
            "id": "chatcmpl_small_summary_overflow",
            "choices": [{"message": {"content": json.dumps(first_response, ensure_ascii=False)}}],
        }

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert call_count["value"] == 1
    assert built["repair_attempt_used"] is False
    assert built["summary_char_count"] == 125
    assert built["summary_text"] == build_exact_length_summary(125)
    assert "## 简介" in built["content_markdown"]


def test_build_llm_story_draft_accepts_overlong_total_when_minimum_is_met() -> None:
    payload = build_story_payload(plan=PLAN)
    call_count = {"value": 0}

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        call_count["value"] += 1
        return {
            "id": "chatcmpl_overlong_total",
            "choices": [{"message": {"content": json.dumps(build_overlong_non_segmented_draft_payload(), ensure_ascii=False)}}],
        }

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert call_count["value"] == 1
    assert built["repair_attempt_used"] is False
    assert built["summary_char_count"] == 100
    assert built["body_char_count"] == 9600


def test_build_llm_story_draft_retries_large_summary_overflow() -> None:
    payload = build_story_payload(plan=PLAN)
    call_count = {"value": 0}

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        call_count["value"] += 1
        response_body = (
            build_valid_draft_payload_with_summary_length(140)
            if call_count["value"] == 1
            else build_mock_draft_payload()
        )
        return {
            "id": f"chatcmpl_large_summary_overflow_{call_count['value']}",
            "choices": [{"message": {"content": json.dumps(response_body, ensure_ascii=False)}}],
        }

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert call_count["value"] == 2
    assert built["repair_attempt_used"] is True
    assert built["summary_char_count"] <= 132


def test_build_llm_story_draft_uses_segmented_generation_for_long_targets() -> None:
    payload = build_long_segmented_payload()
    prompts: list[str] = []
    response_ids: list[str] = []

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        prompt = payload["messages"][1]["content"]
        prompts.append(prompt)
        assert payload["stream"] is True
        if "你当前只负责写这篇故事的简介 summary" in prompt:
            response_ids.append("seg_summary_1")
            return {
                "id": "seg_summary_1",
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                "choices": [{"message": {"content": json.dumps({"summary": build_segmented_summary()}, ensure_ascii=False)}}],
            }

        for chapter_number in range(1, 7):
            if f"当前要写第{chapter_number}章" in prompt:
                response_id = f"seg_chapter_{chapter_number}"
                response_ids.append(response_id)
                return {
                    "id": response_id,
                    "usage": {"prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300},
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "chapter_number": chapter_number,
                                        "content": build_segmented_chapter_content(chapter_number),
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                }

        raise AssertionError(f"未识别的 prompt：{prompt}")

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert len(prompts) == 7
    assert built["segmented_generation"] is True
    assert built["segment_count"] == 7
    assert built["repair_attempt_used"] is False
    assert built["repair_attempt_count"] == 0
    assert built["summary_char_count"] == 80
    assert 9880 <= built["body_char_count"] <= 19950
    assert built["provider_response_ids"] == response_ids
    assert built["provider_response_id"] == ",".join(response_ids)
    assert built["token_usage"] == {"prompt_tokens": 620, "completion_tokens": 1210, "total_tokens": 1830}
    assert "你当前只负责写这篇故事的简介 summary" in prompts[0]
    assert "当前要写第1章" in prompts[1]
    assert "当前要写第6章" in prompts[6]


def test_build_llm_story_draft_allows_segmented_first_chapter_to_exceed_soft_budget() -> None:
    payload = build_douban_long_segmented_payload()
    prompts: list[str] = []

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        prompt = payload["messages"][1]["content"]
        prompts.append(prompt)
        if "你当前只负责写这篇故事的简介 summary" in prompt:
            return {
                "id": "seg_summary_budget",
                "choices": [{"message": {"content": json.dumps({"summary": build_segmented_summary()}, ensure_ascii=False)}}],
            }

        for chapter_number in range(1, 7):
            if f"当前要写第{chapter_number}章" in prompt:
                chapter_length = 5200 if chapter_number == 1 else 1800
                return {
                    "id": f"seg_budget_{chapter_number}",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "chapter_number": chapter_number,
                                        "content": build_exact_length_content(chapter_length),
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                }

        raise AssertionError(f"未识别的 prompt：{prompt}")

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert built["segmented_generation"] is True
    assert built["repair_attempt_used"] is False
    assert built["body_char_count"] == 14200
    assert "当前要写第1章" in prompts[1]
    assert "建议控制在 1654-4920 字" in prompts[1]
    assert "平均预算上限约为 3320 字" in prompts[1]


def test_build_llm_story_draft_accepts_segmented_chapter_small_overflow_without_trimming() -> None:
    payload = build_douban_long_segmented_payload()

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        prompt = payload["messages"][1]["content"]
        if "你当前只负责写这篇故事的简介 summary" in prompt:
            return {
                "id": "seg_summary_trim",
                "choices": [{"message": {"content": json.dumps({"summary": build_segmented_summary()}, ensure_ascii=False)}}],
            }

        for chapter_number in range(1, 7):
            if f"当前要写第{chapter_number}章" in prompt:
                chapter_length = 7000 if chapter_number == 1 else 1800
                return {
                    "id": f"seg_trim_{chapter_number}",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "chapter_number": chapter_number,
                                        "content": build_exact_length_content(chapter_length),
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                }

        raise AssertionError(f"未识别的 prompt：{prompt}")

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert built["segmented_generation"] is True
    assert built["repair_attempt_used"] is False
    assert count_content_chars(built["chapters"][0]["content"]) == 7000
    assert built["body_char_count"] == 16000


def test_build_llm_story_draft_accepts_plain_text_segmented_chapter_output() -> None:
    payload = build_douban_long_segmented_payload()

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        prompt = payload["messages"][1]["content"]
        if "你当前只负责写这篇故事的简介 summary" in prompt:
            return {
                "id": "seg_summary_plain_text",
                "choices": [{"message": {"content": json.dumps({"summary": build_segmented_summary()}, ensure_ascii=False)}}],
            }

        for chapter_number in range(1, 7):
            if f"当前要写第{chapter_number}章" in prompt:
                return {
                    "id": f"seg_plain_text_{chapter_number}",
                    "choices": [
                        {
                            "message": {
                                "content": f"第{chapter_number}章：{build_exact_length_content(1800)}"
                            }
                        }
                    ],
                }

        raise AssertionError(f"未识别的 prompt：{prompt}")

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert built["segmented_generation"] is True
    assert built["repair_attempt_used"] is False
    assert len(built["chapters"]) == 6
    assert built["body_char_count"] == 10800


def test_build_llm_story_draft_accepts_segmented_overlong_chapter_when_total_is_enough() -> None:
    payload = build_douban_long_segmented_payload()

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        prompt = payload["messages"][1]["content"]
        if "你当前只负责写这篇故事的简介 summary" in prompt:
            return {
                "id": "seg_summary_large_chapter",
                "choices": [{"message": {"content": json.dumps({"summary": build_segmented_summary()}, ensure_ascii=False)}}],
            }

        for chapter_number in range(1, 7):
            if f"当前要写第{chapter_number}章" in prompt:
                chapter_length = 9000 if chapter_number == 1 else 1500
                return {
                    "id": f"seg_large_chapter_{chapter_number}",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "chapter_number": chapter_number,
                                        "content": build_exact_length_content(chapter_length),
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                }

        raise AssertionError(f"未识别的 prompt：{prompt}")

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert built["segmented_generation"] is True
    assert built["repair_attempt_used"] is False
    assert count_content_chars(built["chapters"][0]["content"]) == 9000
    assert built["body_char_count"] == 16500


def test_build_llm_story_draft_retries_segmented_chapter_when_invalid() -> None:
    payload = build_long_segmented_payload()
    prompts: list[str] = []
    chapter_one_call_count = {"value": 0}

    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        prompt = payload["messages"][1]["content"]
        prompts.append(prompt)
        if "你当前只负责写这篇故事的简介 summary" in prompt:
            return {
                "id": "seg_summary_retry",
                "choices": [{"message": {"content": json.dumps({"summary": build_segmented_summary()}, ensure_ascii=False)}}],
            }

        if "当前要写第1章" in prompt:
            chapter_one_call_count["value"] += 1
            if chapter_one_call_count["value"] == 1:
                return {
                    "id": "seg_chapter_1_invalid",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"chapter_number": 1, "content": "太短了。"},
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                }
            return {
                "id": "seg_chapter_1_retry",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"chapter_number": 1, "content": build_segmented_chapter_content(1)},
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
            }

        for chapter_number in range(2, 7):
            if f"当前要写第{chapter_number}章" in prompt:
                return {
                    "id": f"seg_chapter_{chapter_number}",
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "chapter_number": chapter_number,
                                        "content": build_segmented_chapter_content(chapter_number),
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                }

        raise AssertionError(f"未识别的 prompt：{prompt}")

    built = build_llm_story_draft(
        payload=payload,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert chapter_one_call_count["value"] == 2
    assert built["segmented_generation"] is True
    assert built["repair_attempt_used"] is True
    assert built["repair_attempt_count"] == 1
    assert built["segment_attempts"][1]["segment_type"] == "chapter"
    assert built["segment_attempts"][1]["chapter_number"] == 1
    assert built["segment_attempts"][1]["repair_attempt_count"] == 1
    assert "上一版本章不合格" in prompts[2]
    assert "太短了。" in prompts[2]
