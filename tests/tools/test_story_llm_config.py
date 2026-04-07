from __future__ import annotations

from pathlib import Path

from tools.story_llm_config import StoryLlmConfigStore


def test_config_store_upserts_and_resolves_environment_routes(tmp_path: Path) -> None:
    store = StoryLlmConfigStore(tmp_path / "story_ideas.sqlite3")

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


def test_config_store_delete_environment_model_and_provider(tmp_path: Path) -> None:
    store = StoryLlmConfigStore(tmp_path / "story_ideas.sqlite3")
    store.upsert_provider(
        provider_name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        chat_completions_url="https://openrouter.ai/api/v1/chat/completions",
    )
    store.upsert_model(
        model_key="openrouter_free_qwen",
        provider_name="openrouter",
        model_name="qwen/qwen3.6-plus:free",
    )
    store.upsert_environment(
        environment_name="idea_pack_default",
        model_keys=["openrouter_free_qwen"],
    )

    deleted_environment = store.delete_environment("idea_pack_default")
    deleted_model = store.delete_model("openrouter_free_qwen")
    deleted_provider = store.delete_provider("openrouter")
    config = store.get_config()

    assert deleted_environment["deleted"] is True
    assert deleted_environment["environment"]["environment_name"] == "idea_pack_default"
    assert deleted_model["deleted"] is True
    assert deleted_model["model"]["model_key"] == "openrouter_free_qwen"
    assert deleted_provider["deleted"] is True
    assert deleted_provider["provider"]["provider_name"] == "openrouter"
    assert config == {
        "providers": {},
        "models": {},
        "environments": {},
    }


def test_delete_model_requires_environment_cleanup_first(tmp_path: Path) -> None:
    store = StoryLlmConfigStore(tmp_path / "story_ideas.sqlite3")
    store.upsert_provider(
        provider_name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        chat_completions_url="https://openrouter.ai/api/v1/chat/completions",
    )
    store.upsert_model(
        model_key="openrouter_free_qwen",
        provider_name="openrouter",
        model_name="qwen/qwen3.6-plus:free",
    )
    store.upsert_environment(
        environment_name="idea_pack_default",
        model_keys=["openrouter_free_qwen"],
    )

    try:
        store.delete_model("openrouter_free_qwen")
    except ValueError as exc:
        assert "仍被环境引用：idea_pack_default" in str(exc)
    else:
        raise AssertionError("delete_model 应该在模型仍被环境引用时失败。")


def test_delete_provider_requires_model_cleanup_first(tmp_path: Path) -> None:
    store = StoryLlmConfigStore(tmp_path / "story_ideas.sqlite3")
    store.upsert_provider(
        provider_name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        chat_completions_url="https://openrouter.ai/api/v1/chat/completions",
    )
    store.upsert_model(
        model_key="openrouter_free_qwen",
        provider_name="openrouter",
        model_name="qwen/qwen3.6-plus:free",
    )

    try:
        store.delete_provider("openrouter")
    except ValueError as exc:
        assert "仍有模型引用：openrouter_free_qwen" in str(exc)
    else:
        raise AssertionError("delete_provider 应该在供应商仍被模型引用时失败。")


def test_config_store_lists_gets_and_resolves_override_order(tmp_path: Path) -> None:
    store = StoryLlmConfigStore(tmp_path / "story_ideas.sqlite3")
    store.upsert_provider(
        provider_name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        chat_completions_url="https://openrouter.ai/api/v1/chat/completions",
    )
    store.upsert_model(
        model_key="route_a",
        provider_name="openrouter",
        model_name="model-a",
    )
    store.upsert_model(
        model_key="route_b",
        provider_name="openrouter",
        model_name="model-b",
    )
    store.upsert_environment(
        environment_name="draft_default",
        model_keys=["route_a", "route_b"],
        description="正文默认环境",
    )

    providers = store.list_providers()
    models = store.list_models()
    environments = store.list_environments()
    provider = store.get_provider("openrouter")
    model = store.get_model("route_b")
    environment = store.get_environment("draft_default")
    resolved = store.resolve_environment_routes(
        "draft_default",
        model_keys_override=["route_b", "route_a"],
    )

    assert [item["provider_name"] for item in providers] == ["openrouter"]
    assert [item["model_key"] for item in models] == ["route_a", "route_b"]
    assert [item["environment_name"] for item in environments] == ["draft_default"]
    assert provider["provider_name"] == "openrouter"
    assert model["model_key"] == "route_b"
    assert environment["model_keys"] == ["route_a", "route_b"]
    assert resolved["model_keys"] == ["route_a", "route_b"]
    assert resolved["effective_model_keys"] == ["route_b", "route_a"]
    assert resolved["override_applied"] is True
    assert [item["model_config_key"] for item in resolved["routes"]] == ["route_b", "route_a"]


def test_config_store_exports_and_applies_snapshot_roundtrip(tmp_path: Path) -> None:
    source_store = StoryLlmConfigStore(tmp_path / "source.sqlite3")
    target_store = StoryLlmConfigStore(tmp_path / "target.sqlite3")

    source_store.upsert_provider(
        provider_name="openrouter",
        api_key_env="OPENROUTER_API_KEY",
        chat_completions_url="https://openrouter.ai/api/v1/chat/completions",
        extra_headers={"HTTP-Referer": "OPENROUTER_HTTP_REFERER"},
    )
    source_store.upsert_model(
        model_key="route_a",
        provider_name="openrouter",
        model_name="model-a",
        api_mode="chat_completions",
        timeout_seconds=45,
    )
    source_store.upsert_environment(
        environment_name="idea_pack_default",
        model_keys=["route_a"],
        agent_fallback=True,
        description="创意包环境",
    )

    snapshot = source_store.export_config_snapshot()
    applied = target_store.apply_config_snapshot(snapshot)
    target_config = target_store.get_config()
    resolved = target_store.resolve_environment_routes("idea_pack_default")

    assert snapshot["format_version"] == 1
    assert snapshot["counts"] == {"providers": 1, "models": 1, "environments": 1}
    assert applied["applied"] is True
    assert applied["counts"] == {"providers": 1, "models": 1, "environments": 1}
    assert target_config == snapshot["config"]
    assert resolved["effective_model_keys"] == ["route_a"]
    assert resolved["routes"][0]["model_name"] == "model-a"
