from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_LLM_CONFIG_PATH = Path("outputs/idea_pipeline/llm_config.json")
VALID_API_MODES = {"chat_completions", "responses"}


def resolve_llm_config_path(config_path: str | Path | None = None) -> Path:
    if config_path is not None:
        return Path(config_path)
    return Path(__file__).resolve().parents[1] / DEFAULT_LLM_CONFIG_PATH


def default_llm_config() -> dict[str, dict[str, Any]]:
    return {
        "providers": {},
        "models": {},
        "environments": {},
    }


def _normalize_key(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip().lower()


def _normalize_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip()


def _normalize_optional_string(value: Any, field_name: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} 必须是字符串。")
    return value.strip()


def _normalize_timeout_seconds(value: Any) -> int:
    if value is None:
        return 60
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("timeout_seconds 必须是大于等于 1 的整数。")
    return value


def _normalize_api_mode(value: Any) -> str:
    normalized = _normalize_key(value, "api_mode")
    if normalized not in VALID_API_MODES:
        raise ValueError(f"api_mode 仅支持：{sorted(VALID_API_MODES)}")
    return normalized


def _normalize_extra_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("extra_headers 必须是对象。")
    normalized: dict[str, str] = {}
    for header_name, env_name in value.items():
        normalized_header_name = _normalize_nonempty_string(header_name, "extra_headers.header_name")
        normalized_env_name = _normalize_nonempty_string(env_name, "extra_headers.env_name")
        normalized[normalized_header_name] = normalized_env_name
    return normalized


def _normalize_model_keys(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("model_keys 必须是非空字符串数组。")
    return [_normalize_key(item, "model_keys") for item in value]


class StoryLlmConfigStore:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self.config_path = resolve_llm_config_path(config_path)
        self.initialize()

    def initialize(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists():
            self.save(default_llm_config())

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.config_path.exists():
            return default_llm_config()
        raw_text = self.config_path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return default_llm_config()
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            raise ValueError("LLM 配置文件必须是 JSON 对象。")
        config = default_llm_config()
        for section_name in config:
            section_value = data.get(section_name, {})
            if not isinstance(section_value, dict):
                raise ValueError(f"LLM 配置的 {section_name} 必须是对象。")
            config[section_name] = section_value
        return config

    def save(self, config: dict[str, dict[str, Any]]) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def get_config(self) -> dict[str, dict[str, Any]]:
        return self.load()

    def upsert_provider(
        self,
        *,
        provider_name: str,
        api_key_env: str,
        chat_completions_url: str | None = None,
        responses_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        normalized_provider_name = _normalize_key(provider_name, "provider_name")
        normalized_api_key_env = _normalize_nonempty_string(api_key_env, "api_key_env")
        normalized_chat_url = _normalize_optional_string(chat_completions_url, "chat_completions_url")
        normalized_responses_url = _normalize_optional_string(responses_url, "responses_url")
        if not normalized_chat_url and not normalized_responses_url:
            raise ValueError("chat_completions_url 和 responses_url 至少要配置一个。")
        normalized_extra_headers = _normalize_extra_headers(extra_headers)

        config = self.load()
        provider = {
            "provider_name": normalized_provider_name,
            "api_key_env": normalized_api_key_env,
            "chat_completions_url": normalized_chat_url,
            "responses_url": normalized_responses_url,
            "extra_headers": normalized_extra_headers,
        }
        config["providers"][normalized_provider_name] = provider
        self.save(config)
        return provider

    def upsert_model(
        self,
        *,
        model_key: str,
        provider_name: str,
        model_name: str,
        api_mode: str = "chat_completions",
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        normalized_model_key = _normalize_key(model_key, "model_key")
        normalized_provider_name = _normalize_key(provider_name, "provider_name")
        normalized_model_name = _normalize_nonempty_string(model_name, "model_name")
        normalized_api_mode = _normalize_api_mode(api_mode)
        normalized_timeout_seconds = _normalize_timeout_seconds(timeout_seconds)

        config = self.load()
        if normalized_provider_name not in config["providers"]:
            raise ValueError(f"未找到 provider_name={normalized_provider_name} 的供应商配置。")

        model = {
            "model_key": normalized_model_key,
            "provider_name": normalized_provider_name,
            "model_name": normalized_model_name,
            "api_mode": normalized_api_mode,
            "timeout_seconds": normalized_timeout_seconds,
        }
        config["models"][normalized_model_key] = model
        self.save(config)
        return model

    def upsert_environment(
        self,
        *,
        environment_name: str,
        model_keys: list[str],
        agent_fallback: bool = True,
        description: str = "",
    ) -> dict[str, Any]:
        normalized_environment_name = _normalize_key(environment_name, "environment_name")
        normalized_model_keys = _normalize_model_keys(model_keys)
        if not isinstance(agent_fallback, bool):
            raise ValueError("agent_fallback 必须是布尔值。")
        normalized_description = _normalize_optional_string(description, "description")

        config = self.load()
        for model_key in normalized_model_keys:
            if model_key not in config["models"]:
                raise ValueError(f"未找到 model_key={model_key} 的模型配置。")

        environment = {
            "environment_name": normalized_environment_name,
            "model_keys": normalized_model_keys,
            "agent_fallback": agent_fallback,
            "description": normalized_description,
        }
        config["environments"][normalized_environment_name] = environment
        self.save(config)
        return environment

    def resolve_environment_routes(self, environment_name: str) -> dict[str, Any]:
        normalized_environment_name = _normalize_key(environment_name, "environment_name")
        config = self.load()
        environment = config["environments"].get(normalized_environment_name)
        if not isinstance(environment, dict):
            raise ValueError(f"未找到 environment_name={normalized_environment_name} 的环境配置。")

        routes: list[dict[str, Any]] = []
        for model_key in environment["model_keys"]:
            model = config["models"].get(model_key)
            if not isinstance(model, dict):
                raise ValueError(f"环境 {normalized_environment_name} 引用了不存在的 model_key={model_key}。")
            provider_name = model["provider_name"]
            provider = config["providers"].get(provider_name)
            if not isinstance(provider, dict):
                raise ValueError(
                    f"模型 {model_key} 引用了不存在的 provider_name={provider_name}。"
                )

            api_mode = model["api_mode"]
            if api_mode == "chat_completions":
                api_url = provider.get("chat_completions_url", "")
            else:
                api_url = provider.get("responses_url", "")
            if not isinstance(api_url, str) or not api_url.strip():
                raise ValueError(
                    f"provider_name={provider_name} 没有为 api_mode={api_mode} 配置可用 URL。"
                )

            routes.append(
                {
                    "model_config_key": model["model_key"],
                    "provider_name": provider["provider_name"],
                    "api_key_env": provider["api_key_env"],
                    "api_mode": api_mode,
                    "model_name": model["model_name"],
                    "api_url": api_url.strip(),
                    "timeout_seconds": model["timeout_seconds"],
                    "header_env_names": dict(provider.get("extra_headers", {})),
                }
            )

        return {
            "environment_name": environment["environment_name"],
            "agent_fallback": bool(environment["agent_fallback"]),
            "description": environment.get("description", ""),
            "routes": routes,
        }
