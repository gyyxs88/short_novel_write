from __future__ import annotations

import json

import pytest
import tools.story_idea_pack_llm_builder as llm_builder

from tools.story_idea_pack_llm_builder import (
    LlmConfigError,
    LlmExhaustedError,
    LlmResponseError,
    LlmTransportError,
    build_llm_idea_pack,
    build_llm_idea_pack_with_fallbacks,
    post_json_api,
)


CARD = {
    "card_id": 7,
    "source_mode": "seed_generate",
    "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
    "main_tags": ["Secret Past - 隐秘过去", "Missing Person - 失踪", "First Love - 初恋"],
}


def test_build_llm_idea_pack_supports_chat_completions_provider() -> None:
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
        captured["timeout_seconds"] = timeout_seconds
        captured["extra_headers"] = extra_headers
        return {
            "id": "chatcmpl_123",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "style_reason": "知乎风格更适合这组卡的强冲突表达。",
                                "hook": "她在葬礼结束后收到失踪初恋发来的求救短信。",
                                "core_relationship": "女主与失踪初恋被旧案重新绑回同一条线上。",
                                "main_conflict": "她越想查清失踪真相，越不得不承认自己才是旧案的关键证人。",
                                "reversal_direction": "求救的人未必真是受害者，真正被盯上的也许一直是女主。",
                                "recommended_tags": ["悬疑 / 推理", "失踪", "初恋"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
        }

    pack = build_llm_idea_pack(
        card=CARD,
        style="zhihu",
        provider="openrouter",
        api_mode="chat_completions",
        model="qwen/qwen3.6-plus:free",
        api_key="test-key",
        transport=fake_transport,
    )

    assert pack["generation_mode"] == "llm"
    assert pack["provider_name"] == "openrouter"
    assert pack["api_mode"] == "chat_completions"
    assert pack["style"] == "zhihu"
    assert pack["model_name"] == "qwen/qwen3.6-plus:free"
    assert pack["provider_response_id"] == "chatcmpl_123"
    assert pack["hook"] == "她在葬礼结束后收到失踪初恋发来的求救短信。"

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "qwen/qwen3.6-plus:free"
    assert payload["messages"][0]["role"] == "system"
    assert captured["api_url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_build_llm_idea_pack_supports_responses_mode() -> None:
    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        return {
            "id": "resp_123",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "style_reason": "知乎风格更适合这组卡的强冲突表达。",
                                    "hook": "她在葬礼结束后收到失踪初恋发来的求救短信。",
                                    "core_relationship": "女主与失踪初恋被旧案重新绑回同一条线上。",
                                    "main_conflict": "她越想查清失踪真相，越不得不承认自己才是旧案的关键证人。",
                                    "reversal_direction": "求救的人未必真是受害者，真正被盯上的也许一直是女主。",
                                    "recommended_tags": ["悬疑 / 推理", "失踪", "初恋"],
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        }

    pack = build_llm_idea_pack(
        card=CARD,
        style="zhihu",
        provider="openai",
        api_mode="responses",
        model="gpt-5-mini",
        api_key="test-key",
        transport=fake_transport,
    )

    assert pack["provider_name"] == "openai"
    assert pack["api_mode"] == "responses"
    assert pack["provider_response_id"] == "resp_123"


def test_build_llm_idea_pack_supports_deepseek_json_mode() -> None:
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
            "id": "deepseek_pack_123",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "style_reason": "知乎风格更适合这组卡的强冲突表达。",
                                "hook": "她在葬礼结束后收到失踪初恋发来的求救短信。",
                                "core_relationship": "女主与失踪初恋被旧案重新绑回同一条线上。",
                                "main_conflict": "她越想查清失踪真相，越不得不承认自己才是旧案的关键证人。",
                                "reversal_direction": "求救的人未必真是受害者，真正被盯上的也许一直是女主。",
                                "recommended_tags": ["悬疑 / 推理", "失踪", "初恋"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
        }

    pack = build_llm_idea_pack(
        card=CARD,
        style="zhihu",
        provider="deepseek",
        api_mode="chat_completions",
        model="deepseek-chat",
        api_key="test-key",
        transport=fake_transport,
    )

    assert pack["provider_name"] == "deepseek"
    assert captured["api_url"] == "https://api.deepseek.com/chat/completions"
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["response_format"] == {"type": "json_object"}
    assert request_payload["max_tokens"] == 1200
    assert "stream" not in request_payload


def test_post_json_api_supports_streaming_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeStreamingResponse:
        def __init__(self, lines: list[bytes]) -> None:
            self._lines = iter(lines)

        def readline(self) -> bytes:
            return next(self._lines, b"")

        def __enter__(self) -> "FakeStreamingResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_urlopen(request, timeout: int) -> FakeStreamingResponse:
        assert timeout == 45
        payload = json.loads(request.data.decode("utf-8"))
        assert payload["stream"] is True
        events = [
            {
                "id": "chatcmpl_stream_123",
                "choices": [{"delta": {"content": '{"hook":"流式'}}],
            },
            {
                "id": "chatcmpl_stream_123",
                "choices": [{"delta": {"content": '响应"}'}}],
            },
        ]
        lines = []
        for event in events:
            lines.append(f"data: {json.dumps(event, ensure_ascii=False)}\n".encode("utf-8"))
            lines.append(b"\n")
        lines.append(b"data: [DONE]\n")
        return FakeStreamingResponse(lines)

    monkeypatch.setattr(llm_builder.urllib.request, "urlopen", fake_urlopen)

    response = post_json_api(
        api_url="https://example.com/stream",
        api_key="test-key",
        payload={"stream": True},
        timeout_seconds=45,
    )

    assert response["id"] == "chatcmpl_stream_123"
    assert response["choices"][0]["message"]["content"] == '{"hook":"流式响应"}'


def test_post_json_api_raises_idle_timeout_for_streaming_chat_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTimeoutStreamingResponse:
        def readline(self) -> bytes:
            raise TimeoutError("timed out")

        def __enter__(self) -> "FakeTimeoutStreamingResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_urlopen(request, timeout: int) -> FakeTimeoutStreamingResponse:
        return FakeTimeoutStreamingResponse()

    monkeypatch.setattr(llm_builder.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(LlmTransportError, match="连续 12 秒未收到新的数据块"):
        post_json_api(
            api_url="https://example.com/stream",
            api_key="test-key",
            payload={"stream": True},
            timeout_seconds=12,
        )


def test_post_json_api_falls_back_to_plain_json_when_stream_response_is_not_sse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeJsonResponse:
        def __init__(self, raw_body: bytes) -> None:
            self.headers = {"Content-Type": "application/json; charset=utf-8"}
            self._raw_body = raw_body

        def read(self) -> bytes:
            return self._raw_body

        def __enter__(self) -> "FakeJsonResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    def fake_urlopen(request, timeout: int) -> FakeJsonResponse:
        return FakeJsonResponse(
            json.dumps(
                {
                    "id": "chatcmpl_plain_json_123",
                    "choices": [{"message": {"content": '{"hook":"普通 JSON 回退"}'}}],
                },
                ensure_ascii=False,
            ).encode("utf-8")
        )

    monkeypatch.setattr(llm_builder.urllib.request, "urlopen", fake_urlopen)

    response = post_json_api(
        api_url="https://example.com/plain-json",
        api_key="test-key",
        payload={"stream": True},
        timeout_seconds=45,
    )

    assert response["id"] == "chatcmpl_plain_json_123"
    assert response["choices"][0]["message"]["content"] == '{"hook":"普通 JSON 回退"}'


def test_build_llm_idea_pack_requires_api_key() -> None:
    with pytest.raises(LlmConfigError, match="API Key"):
        build_llm_idea_pack(
            card=CARD,
            style="zhihu",
            provider="openrouter",
            api_mode="chat_completions",
            api_key="",
        )


def test_build_llm_idea_pack_rejects_invalid_llm_response() -> None:
    def fake_transport(
        *,
        api_url: str,
        api_key: str,
        payload: dict,
        timeout_seconds: int,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        return {
            "id": "chatcmpl_invalid",
            "choices": [
                {
                    "message": {
                        "content": "{\"hook\":\"缺字段\"}",
                    }
                }
            ],
        }

    with pytest.raises(LlmResponseError, match="LLM 返回结果缺少必要字段"):
        build_llm_idea_pack(
            card=CARD,
            style="zhihu",
            provider="openrouter",
            api_mode="chat_completions",
            model="qwen/qwen3.6-plus:free",
            api_key="test-key",
            transport=fake_transport,
        )


def test_build_llm_idea_pack_with_fallbacks_uses_next_route_after_failure() -> None:
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
            "id": "chatcmpl_fallback_123",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "style_reason": "第二个模型更稳。",
                                "hook": "她在葬礼结束后收到失踪初恋发来的求救短信。",
                                "core_relationship": "女主与失踪初恋被旧案重新绑回同一条线上。",
                                "main_conflict": "她越想查清失踪真相，越不得不承认自己才是旧案的关键证人。",
                                "reversal_direction": "求救的人未必真是受害者，真正被盯上的也许一直是女主。",
                                "recommended_tags": ["悬疑 / 推理", "失踪", "初恋"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
        }

    pack = build_llm_idea_pack_with_fallbacks(
        card=CARD,
        style="zhihu",
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

    assert pack["model_config_key"] == "route_b"
    assert pack["model_name"] == "model-b"
    assert pack["attempt_count"] == 2
    assert pack["fallback_used"] is True
    assert pack["attempts"][0]["status"] == "failed"
    assert pack["attempts"][1]["status"] == "success"


def test_build_llm_idea_pack_with_fallbacks_raises_agent_fallback_when_all_fail() -> None:
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
        build_llm_idea_pack_with_fallbacks(
            card=CARD,
            style="zhihu",
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
