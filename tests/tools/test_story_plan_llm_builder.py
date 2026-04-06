from __future__ import annotations

import json

import pytest

from tools.story_idea_pack_llm_builder import LlmExhaustedError, LlmResponseError
from tools.story_plan_llm_builder import (
    build_llm_story_plans,
    build_llm_story_plans_with_fallbacks,
)


PACK = {
    "pack_id": 21,
    "source_mode": "seed_generate",
    "style": "zhihu",
    "generation_mode": "llm",
    "style_reason": "知乎风格更适合这组卡的强冲突表达。",
    "hook": "她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
    "core_relationship": "女主与失踪前任、现任未婚夫之间重新形成对立关系。",
    "main_conflict": "她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
    "reversal_direction": "她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
    "recommended_tags": ["悬疑", "婚礼危机", "前任回潮"],
}


def build_mock_plan_payload() -> dict[str, object]:
    return {
        "plans": [
            {
                "variant_label": "真相追猎型",
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
                "writing_brief": {"title": "短信背后的真相"},
            },
            {
                "variant_label": "关系反咬型",
                "title": "前任反咬之后",
                "genre_tone": "情感悬疑并行，关系对撞强。",
                "selling_point": "让前任、未婚夫和女主三方关系互相反咬。",
                "protagonist_profile": "一个想保住体面生活，却被旧关系反复拖回现场的人。",
                "protagonist_goal": "确认谁在利用旧关系把她拖回旧案。",
                "core_relationship": "女主与前任、未婚夫之间的信任同时崩塌。",
                "main_conflict": "她越想保住婚礼，越发现自己才是所有旧账的核心节点。",
                "key_turning_point": "她意识到自己一直保护的人也在主动推动局势。",
                "ending_direction": "真相被摊到台面上，关系没有被修复，只被重新命名。",
                "chapter_rhythm": [
                    {"chapter_number": 1, "stage": "异常闯入", "focus": "前任短信", "advance": "旧关系重启", "chapter_hook": "她第一次动摇婚礼决定。"},
                    {"chapter_number": 2, "stage": "第一轮追查", "focus": "婚礼筹备和旧案并行", "advance": "两条线互相缠绕", "chapter_hook": "她发现前任比她更早知道危险。"},
                    {"chapter_number": 3, "stage": "关系加压", "focus": "未婚夫开始失控", "advance": "三方关系被拉到台面", "chapter_hook": "她第一次怀疑未婚夫不是保护者。"},
                    {"chapter_number": 4, "stage": "中段偏转", "focus": "她一直保护错了人", "advance": "认知被彻底推翻", "chapter_hook": "她意识到自己也是这场局的一部分。"},
                    {"chapter_number": 5, "stage": "总爆点前夜", "focus": "关系全面崩盘", "advance": "真相只剩最后一层", "chapter_hook": "她必须决定最后站到谁那一边。"},
                    {"chapter_number": 6, "stage": "回收落点", "focus": "婚礼停止", "advance": "旧关系被重新命名", "chapter_hook": "她没有回到过去，也没有继续原样往前。"},
                ],
                "writing_brief": {"title": "前任反咬之后"},
            },
            {
                "variant_label": "局中局设伏型",
                "title": "婚礼局中局",
                "genre_tone": "设局与反设局并行，章尾持续留钩。",
                "selling_point": "把婚礼写成明面舞台，把旧案写成里层杀招。",
                "protagonist_profile": "一个被拖回旧局后开始反向设局的人。",
                "protagonist_goal": "利用对手误判反向设局。",
                "core_relationship": "女主和前任互相试探，但真正对位关系直到中后段才揭开。",
                "main_conflict": "她既要查清真相，又要抢在对手收网前把自己改写成棋手。",
                "key_turning_point": "她发现自己早年埋下的一个细节，正是对手今天敢设局的底牌。",
                "ending_direction": "主角公开真相并完成反咬，但必须亲手切断一段再也回不去的关系。",
                "chapter_rhythm": [
                    {"chapter_number": 1, "stage": "异常闯入", "focus": "短信把她拖回现场", "advance": "她决定先装作不知情", "chapter_hook": "她意识到有人在等她入局。"},
                    {"chapter_number": 2, "stage": "第一轮追查", "focus": "婚礼名单与旧案交叉", "advance": "主角故意放出假动作", "chapter_hook": "她第一次摸到对手的节奏。"},
                    {"chapter_number": 3, "stage": "关系加压", "focus": "前任和未婚夫都在逼她表态", "advance": "她开始双线试探", "chapter_hook": "她发现自己不是唯一一个在演戏的人。"},
                    {"chapter_number": 4, "stage": "中段偏转", "focus": "她自己埋下的细节反噬回来", "advance": "计划被迫改写", "chapter_hook": "她终于明白对手为什么敢赌她会回来。"},
                    {"chapter_number": 5, "stage": "总爆点前夜", "focus": "反设局正式启动", "advance": "所有线索开始汇拢", "chapter_hook": "她知道再往前一步就必须舍掉一个人。"},
                    {"chapter_number": 6, "stage": "回收落点", "focus": "反咬完成", "advance": "局被当众翻面", "chapter_hook": "她赢下真相，却永远失去一段关系。"},
                ],
                "writing_brief": {"title": "婚礼局中局"},
            },
            {
                "variant_label": "代价救赎型",
                "title": "婚礼之后",
                "genre_tone": "高代价抉择驱动，情绪爆点和真相回收并行。",
                "selling_point": "把婚礼保不保得住，写成比真相本身更痛的选择。",
                "protagonist_profile": "一个必须在真相和体面生活之间做选择的人。",
                "protagonist_goal": "在真相和体面生活之间完成止损。",
                "core_relationship": "女主与前任、未婚夫之间的纠葛被代价一步步外化。",
                "main_conflict": "她每往前一步，都要先决定愿意失去什么。",
                "key_turning_point": "只有主动放弃眼前最重要的一段关系，她才有机会逼幕后现身。",
                "ending_direction": "她赢下真相，输掉眼前的体面与安全感，但完成了真正的止损。",
                "chapter_rhythm": [
                    {"chapter_number": 1, "stage": "异常闯入", "focus": "婚礼前夜短信", "advance": "主角的体面生活出现裂口", "chapter_hook": "她发现自己再装作没看到已经不可能。"},
                    {"chapter_number": 2, "stage": "第一轮追查", "focus": "她开始追短信来源", "advance": "旧关系和现实关系同时施压", "chapter_hook": "她第一次意识到婚礼可能根本办不成。"},
                    {"chapter_number": 3, "stage": "关系加压", "focus": "她试图两边都保住", "advance": "代价开始具体化", "chapter_hook": "她发现自己最怕失去的东西正在先失去她。"},
                    {"chapter_number": 4, "stage": "中段偏转", "focus": "必须主动放弃一段关系", "advance": "主角目标被迫重订", "chapter_hook": "她知道真正的损失现在才开始。"},
                    {"chapter_number": 5, "stage": "总爆点前夜", "focus": "她用代价逼幕后现身", "advance": "真相和情绪一起翻面", "chapter_hook": "她第一次觉得自己可能真的赢不了。"},
                    {"chapter_number": 6, "stage": "回收落点", "focus": "止损完成", "advance": "她保住了自己，却失去原本以为最重要的生活", "chapter_hook": "真相终于被说出来，但婚礼已经没有意义。"},
                ],
                "writing_brief": {"title": "婚礼之后"},
            },
        ]
    }


def test_build_llm_story_plans_supports_chat_completions_provider() -> None:
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
        captured["api_key"] = api_key
        captured["payload"] = payload
        return {
            "id": "chatcmpl_plan_123",
            "choices": [{"message": {"content": json.dumps(build_mock_plan_payload(), ensure_ascii=False)}}],
        }

    built = build_llm_story_plans(
        pack=PACK,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert len(built["plans"]) == 4
    assert built["plans"][0]["generation_mode"] == "llm"
    assert built["plans"][0]["provider_name"] == "openrouter"
    assert built["plans"][0]["model_name"] == "qwen/qwen3.6-plus:free"
    assert built["plans"][0]["provider_response_id"] == "chatcmpl_plan_123"
    assert built["plans"][0]["writing_brief"]["target_char_range"] == [10000, 30000]
    assert captured["api_url"] == "https://openrouter.ai/api/v1/chat/completions"
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["stream"] is True


def test_build_llm_story_plans_supports_responses_mode() -> None:
    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        return {
            "id": "resp_plan_123",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(build_mock_plan_payload(), ensure_ascii=False),
                        }
                    ],
                }
            ],
        }

    built = build_llm_story_plans(
        pack=PACK,
        provider="openai",
        api_mode="responses",
        model="gpt-5-mini",
        api_key="test-key",
        transport=fake_transport,
        target_chapter_count=6,
        plan_count=4,
    )

    assert len(built["plans"]) == 4
    assert built["plans"][0]["provider_response_id"] == "resp_plan_123"
    assert built["plans"][0]["api_mode"] == "responses"


def test_build_llm_story_plans_supports_deepseek_json_mode() -> None:
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
            "id": "deepseek_plan_123",
            "choices": [{"message": {"content": json.dumps(build_mock_plan_payload(), ensure_ascii=False)}}],
        }

    built = build_llm_story_plans(
        pack=PACK,
        provider="deepseek",
        api_mode="chat_completions",
        model="deepseek-chat",
        api_key="test-key",
        transport=fake_transport,
    )

    assert len(built["plans"]) == 4
    assert built["plans"][0]["provider_name"] == "deepseek"
    assert captured["api_url"] == "https://api.deepseek.com/chat/completions"
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["stream"] is True
    assert request_payload["response_format"] == {"type": "json_object"}
    assert request_payload["max_tokens"] == 5376


def test_build_llm_story_plans_rejects_invalid_output() -> None:
    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        return {
            "id": "chatcmpl_invalid_plan",
            "choices": [{"message": {"content": "{\"plans\":[]}"}},],
        }

    with pytest.raises(LlmResponseError, match="plans 数量不足"):
        build_llm_story_plans(
            pack=PACK,
            provider="openrouter",
            api_mode="chat_completions",
            model="qwen/qwen3.6-plus:free",
            api_key="test-key",
            transport=fake_transport,
        )


def test_build_llm_story_plans_retries_once_when_output_is_invalid_json() -> None:
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
        if call_count["value"] == 1:
            content = '{"plans": ['
        else:
            content = json.dumps(build_mock_plan_payload(), ensure_ascii=False)
        return {
            "id": f"chatcmpl_plan_retry_{call_count['value']}",
            "choices": [{"message": {"content": content}}],
        }

    built = build_llm_story_plans(
        pack=PACK,
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert call_count["value"] == 2
    assert len(built["plans"]) == 4
    assert "上一版问题" not in prompts[0]
    assert "上一版问题" in prompts[1]


def test_build_llm_story_plans_with_fallbacks_uses_next_route_after_failure() -> None:
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
            "id": "chatcmpl_plan_fallback",
            "choices": [{"message": {"content": json.dumps(build_mock_plan_payload(), ensure_ascii=False)}}],
        }

    built = build_llm_story_plans_with_fallbacks(
        pack=PACK,
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

    assert len(built["plans"]) == 4
    assert built["plans"][0]["model_config_key"] == "route_b"
    assert built["attempt_count"] == 2
    assert built["fallback_used"] is True
    assert built["attempts"][0]["status"] == "failed"
    assert built["attempts"][1]["status"] == "success"


def test_build_llm_story_plans_with_fallbacks_raises_agent_fallback_when_all_fail() -> None:
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
        build_llm_story_plans_with_fallbacks(
            pack=PACK,
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
