from __future__ import annotations

from pathlib import Path

from tools.story_llm_config import StoryLlmConfigStore


def test_config_store_upserts_and_resolves_environment_routes(tmp_path: Path) -> None:
    store = StoryLlmConfigStore(tmp_path / "llm_config.json")

    provider = store.upsert_provider(
        provider_name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        chat_completions_url="https://openrouter.ai/api/v1/chat/completions",
        extra_headers={
            "HTTP-Referer": "OPENROUTER_HTTP_REFERER",
            "X-Title": "OPENROUTER_X_TITLE",
        },
    )
    model = store.upsert_model(
        model_key="openrouter_free_qwen",
        provider_name="openrouter",
        model_name="qwen/qwen3.6-plus:free",
        api_mode="chat_completions",
        timeout_seconds=45,
    )
    environment = store.upsert_environment(
        environment_name="idea_pack_default",
        model_keys=["openrouter_free_qwen"],
        agent_fallback=True,
        description="默认创意包环境",
    )
    resolved = store.resolve_environment_routes("idea_pack_default")

    assert provider["provider_name"] == "openrouter"
    assert model["model_key"] == "openrouter_free_qwen"
    assert environment["environment_name"] == "idea_pack_default"
    assert resolved["environment_name"] == "idea_pack_default"
    assert resolved["agent_fallback"] is True
    assert len(resolved["routes"]) == 1
    assert resolved["routes"][0]["provider_name"] == "openrouter"
    assert resolved["routes"][0]["model_name"] == "qwen/qwen3.6-plus:free"
    assert resolved["routes"][0]["model_config_key"] == "openrouter_free_qwen"
    assert resolved["routes"][0]["header_env_names"]["HTTP-Referer"] == "OPENROUTER_HTTP_REFERER"
