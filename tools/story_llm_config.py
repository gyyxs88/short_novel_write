from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.story_idea_repository import resolve_idea_db_path


class AutoClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


VALID_API_MODES = {"chat_completions", "responses"}
LLM_CONFIG_SNAPSHOT_FORMAT_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS llm_providers (
    provider_name TEXT PRIMARY KEY,
    api_key_env TEXT NOT NULL,
    chat_completions_url TEXT NOT NULL,
    responses_url TEXT NOT NULL,
    extra_headers_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_models (
    model_key TEXT PRIMARY KEY,
    provider_name TEXT NOT NULL,
    model_name TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    timeout_seconds INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(provider_name) REFERENCES llm_providers(provider_name)
);

CREATE TABLE IF NOT EXISTS llm_environments (
    environment_name TEXT PRIMARY KEY,
    agent_fallback INTEGER NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS llm_environment_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    environment_name TEXT NOT NULL,
    model_key TEXT NOT NULL,
    route_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(environment_name, model_key),
    UNIQUE(environment_name, route_index),
    FOREIGN KEY(environment_name) REFERENCES llm_environments(environment_name) ON DELETE CASCADE,
    FOREIGN KEY(model_key) REFERENCES llm_models(model_key)
);

CREATE INDEX IF NOT EXISTS idx_llm_models_provider_name ON llm_models(provider_name);
CREATE INDEX IF NOT EXISTS idx_llm_environment_models_environment_name
    ON llm_environment_models(environment_name, route_index);
"""


def resolve_llm_db_path(db_path: str | Path | None = None) -> Path:
    return resolve_idea_db_path(db_path)


def default_llm_config() -> dict[str, dict[str, Any]]:
    return {
        "providers": {},
        "models": {},
        "environments": {},
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


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


def _normalize_model_keys(value: Any, field_name: str = "model_keys") -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} 必须是非空字符串数组。")
    normalized = [_normalize_key(item, field_name) for item in value]
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} 不能包含重复值。")
    return normalized


def _normalize_config_categories(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("config 必须是对象。")
    expected_keys = {"providers", "models", "environments"}
    actual_keys = set(value.keys())
    unexpected_keys = sorted(actual_keys - expected_keys)
    if unexpected_keys:
        raise ValueError(f"config 不支持这些字段：{unexpected_keys}")
    normalized: dict[str, dict[str, Any]] = {}
    for key in ("providers", "models", "environments"):
        category = value.get(key)
        if not isinstance(category, dict):
            raise ValueError(f"config.{key} 必须是对象。")
        normalized[key] = category
    return normalized


def _normalize_provider_record(record_key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("provider 配置必须是对象。")
    normalized_provider_name = _normalize_key(record_key, "providers.key")
    provider_name_in_record = value.get("provider_name", normalized_provider_name)
    if _normalize_key(provider_name_in_record, "providers.provider_name") != normalized_provider_name:
        raise ValueError(f"provider key 与 provider_name 不一致：{record_key}")
    return {
        "provider_name": normalized_provider_name,
        "api_key_env": _normalize_nonempty_string(value.get("api_key_env"), "api_key_env"),
        "chat_completions_url": _normalize_optional_string(
            value.get("chat_completions_url"),
            "chat_completions_url",
        ),
        "responses_url": _normalize_optional_string(value.get("responses_url"), "responses_url"),
        "extra_headers": _normalize_extra_headers(value.get("extra_headers")),
    }


def _normalize_model_record(record_key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("model 配置必须是对象。")
    normalized_model_key = _normalize_key(record_key, "models.key")
    model_key_in_record = value.get("model_key", normalized_model_key)
    if _normalize_key(model_key_in_record, "models.model_key") != normalized_model_key:
        raise ValueError(f"model key 与 model_key 不一致：{record_key}")
    return {
        "model_key": normalized_model_key,
        "provider_name": _normalize_key(value.get("provider_name"), "provider_name"),
        "model_name": _normalize_nonempty_string(value.get("model_name"), "model_name"),
        "api_mode": _normalize_api_mode(value.get("api_mode")),
        "timeout_seconds": _normalize_timeout_seconds(value.get("timeout_seconds")),
    }


def _normalize_environment_record(record_key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("environment 配置必须是对象。")
    normalized_environment_name = _normalize_key(record_key, "environments.key")
    environment_name_in_record = value.get("environment_name", normalized_environment_name)
    if (
        _normalize_key(environment_name_in_record, "environments.environment_name")
        != normalized_environment_name
    ):
        raise ValueError(f"environment key 与 environment_name 不一致：{record_key}")
    agent_fallback = value.get("agent_fallback", True)
    if not isinstance(agent_fallback, bool):
        raise ValueError("agent_fallback 必须是布尔值。")
    return {
        "environment_name": normalized_environment_name,
        "model_keys": _normalize_model_keys(value.get("model_keys")),
        "agent_fallback": agent_fallback,
        "description": _normalize_optional_string(value.get("description"), "description"),
    }


def _normalize_full_config(value: Any) -> dict[str, dict[str, Any]]:
    categories = _normalize_config_categories(value)
    normalized_providers = {
        provider_name: _normalize_provider_record(provider_name, provider_value)
        for provider_name, provider_value in categories["providers"].items()
    }
    normalized_models = {
        model_key: _normalize_model_record(model_key, model_value)
        for model_key, model_value in categories["models"].items()
    }
    normalized_environments = {
        environment_name: _normalize_environment_record(environment_name, environment_value)
        for environment_name, environment_value in categories["environments"].items()
    }

    for model_key, model_record in normalized_models.items():
        provider_name = model_record["provider_name"]
        if provider_name not in normalized_providers:
            raise ValueError(
                f"model_key={model_key} 引用了不存在的 provider_name={provider_name}。"
            )
    for environment_name, environment_record in normalized_environments.items():
        for model_key in environment_record["model_keys"]:
            if model_key not in normalized_models:
                raise ValueError(
                    f"environment_name={environment_name} 引用了不存在的 model_key={model_key}。"
                )

    return {
        "providers": normalized_providers,
        "models": normalized_models,
        "environments": normalized_environments,
    }


def _build_config_counts(config: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        "providers": len(config["providers"]),
        "models": len(config["models"]),
        "environments": len(config["environments"]),
    }


class StoryLlmConfigStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = resolve_llm_db_path(db_path)
        self.initialize()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, factory=AutoClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _row_to_provider(self, row: sqlite3.Row) -> dict[str, Any]:
        extra_headers = json.loads(row["extra_headers_json"])
        if not isinstance(extra_headers, dict):
            raise ValueError("extra_headers_json 必须是对象。")
        return {
            "provider_name": row["provider_name"],
            "api_key_env": row["api_key_env"],
            "chat_completions_url": row["chat_completions_url"],
            "responses_url": row["responses_url"],
            "extra_headers": extra_headers,
        }

    def _row_to_model(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "model_key": row["model_key"],
            "provider_name": row["provider_name"],
            "model_name": row["model_name"],
            "api_mode": row["api_mode"],
            "timeout_seconds": row["timeout_seconds"],
        }

    def _load_environment_model_keys(
        self,
        connection: sqlite3.Connection,
        environment_name: str,
    ) -> list[str]:
        rows = connection.execute(
            """
            SELECT model_key
            FROM llm_environment_models
            WHERE environment_name = ?
            ORDER BY route_index ASC, id ASC
            """,
            (environment_name,),
        ).fetchall()
        return [str(row["model_key"]) for row in rows]

    def _row_to_environment(
        self,
        row: sqlite3.Row,
        *,
        connection: sqlite3.Connection,
    ) -> dict[str, Any]:
        return {
            "environment_name": row["environment_name"],
            "model_keys": self._load_environment_model_keys(connection, row["environment_name"]),
            "agent_fallback": bool(row["agent_fallback"]),
            "description": row["description"],
        }

    def load(self) -> dict[str, dict[str, Any]]:
        config = default_llm_config()
        with self._connect() as connection:
            provider_rows = connection.execute(
                """
                SELECT provider_name, api_key_env, chat_completions_url, responses_url, extra_headers_json
                FROM llm_providers
                ORDER BY provider_name ASC
                """
            ).fetchall()
            for row in provider_rows:
                provider = self._row_to_provider(row)
                config["providers"][provider["provider_name"]] = provider

            model_rows = connection.execute(
                """
                SELECT model_key, provider_name, model_name, api_mode, timeout_seconds
                FROM llm_models
                ORDER BY model_key ASC
                """
            ).fetchall()
            for row in model_rows:
                model = self._row_to_model(row)
                config["models"][model["model_key"]] = model

            environment_rows = connection.execute(
                """
                SELECT environment_name, agent_fallback, description
                FROM llm_environments
                ORDER BY environment_name ASC
                """
            ).fetchall()
            for row in environment_rows:
                environment = self._row_to_environment(row, connection=connection)
                config["environments"][environment["environment_name"]] = environment
        return config

    def get_config(self) -> dict[str, dict[str, Any]]:
        return self.load()

    def export_config_snapshot(self) -> dict[str, Any]:
        config = self.get_config()
        return {
            "format_version": LLM_CONFIG_SNAPSHOT_FORMAT_VERSION,
            "exported_at": utc_now(),
            "config": config,
            "counts": _build_config_counts(config),
        }

    def apply_config_snapshot(self, snapshot: dict[str, Any] | None = None, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        if snapshot is None and config is None:
            raise ValueError("snapshot 和 config 必须至少传一个。")
        if snapshot is not None and config is not None:
            raise ValueError("snapshot 和 config 不能同时传。")

        if snapshot is not None:
            if not isinstance(snapshot, dict):
                raise ValueError("snapshot 必须是对象。")
            format_version = snapshot.get("format_version")
            if format_version is not None and format_version != LLM_CONFIG_SNAPSHOT_FORMAT_VERSION:
                raise ValueError(
                    f"snapshot.format_version 仅支持 {LLM_CONFIG_SNAPSHOT_FORMAT_VERSION}。"
                )
            normalized_config = _normalize_full_config(snapshot.get("config"))
        else:
            normalized_config = _normalize_full_config(config)

        now = utc_now()
        with self._connect() as connection:
            connection.execute("DELETE FROM llm_environment_models")
            connection.execute("DELETE FROM llm_environments")
            connection.execute("DELETE FROM llm_models")
            connection.execute("DELETE FROM llm_providers")

            for provider_name, provider in normalized_config["providers"].items():
                connection.execute(
                    """
                    INSERT INTO llm_providers (
                        provider_name,
                        api_key_env,
                        chat_completions_url,
                        responses_url,
                        extra_headers_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        provider_name,
                        provider["api_key_env"],
                        provider["chat_completions_url"],
                        provider["responses_url"],
                        _json_dumps(provider["extra_headers"]),
                        now,
                        now,
                    ),
                )

            for model_key, model in normalized_config["models"].items():
                connection.execute(
                    """
                    INSERT INTO llm_models (
                        model_key,
                        provider_name,
                        model_name,
                        api_mode,
                        timeout_seconds,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        model_key,
                        model["provider_name"],
                        model["model_name"],
                        model["api_mode"],
                        model["timeout_seconds"],
                        now,
                        now,
                    ),
                )

            for environment_name, environment in normalized_config["environments"].items():
                connection.execute(
                    """
                    INSERT INTO llm_environments (
                        environment_name,
                        agent_fallback,
                        description,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        environment_name,
                        1 if environment["agent_fallback"] else 0,
                        environment["description"],
                        now,
                        now,
                    ),
                )
                for route_index, model_key in enumerate(environment["model_keys"], start=1):
                    connection.execute(
                        """
                        INSERT INTO llm_environment_models (
                            environment_name,
                            model_key,
                            route_index,
                            created_at
                        )
                        VALUES (?, ?, ?, ?)
                        """,
                        (environment_name, model_key, route_index, now),
                    )

        return {
            "applied": True,
            "counts": _build_config_counts(normalized_config),
            "config": normalized_config,
        }

    def list_providers(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT provider_name, api_key_env, chat_completions_url, responses_url, extra_headers_json
                FROM llm_providers
                ORDER BY provider_name ASC
                """
            ).fetchall()
        return [self._row_to_provider(row) for row in rows]

    def get_provider(self, provider_name: str) -> dict[str, Any]:
        normalized_provider_name = _normalize_key(provider_name, "provider_name")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT provider_name, api_key_env, chat_completions_url, responses_url, extra_headers_json
                FROM llm_providers
                WHERE provider_name = ?
                """,
                (normalized_provider_name,),
            ).fetchone()
        if row is None:
            raise ValueError(f"未找到 provider_name={normalized_provider_name} 的供应商配置。")
        return self._row_to_provider(row)

    def list_models(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT model_key, provider_name, model_name, api_mode, timeout_seconds
                FROM llm_models
                ORDER BY model_key ASC
                """
            ).fetchall()
        return [self._row_to_model(row) for row in rows]

    def get_model(self, model_key: str) -> dict[str, Any]:
        normalized_model_key = _normalize_key(model_key, "model_key")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT model_key, provider_name, model_name, api_mode, timeout_seconds
                FROM llm_models
                WHERE model_key = ?
                """,
                (normalized_model_key,),
            ).fetchone()
        if row is None:
            raise ValueError(f"未找到 model_key={normalized_model_key} 的模型配置。")
        return self._row_to_model(row)

    def list_environments(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT environment_name, agent_fallback, description
                FROM llm_environments
                ORDER BY environment_name ASC
                """
            ).fetchall()
            return [self._row_to_environment(row, connection=connection) for row in rows]

    def get_environment(self, environment_name: str) -> dict[str, Any]:
        normalized_environment_name = _normalize_key(environment_name, "environment_name")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT environment_name, agent_fallback, description
                FROM llm_environments
                WHERE environment_name = ?
                """,
                (normalized_environment_name,),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"未找到 environment_name={normalized_environment_name} 的环境配置。"
                )
            return self._row_to_environment(row, connection=connection)

    def delete_provider(self, provider_name: str) -> dict[str, Any]:
        normalized_provider_name = _normalize_key(provider_name, "provider_name")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT provider_name, api_key_env, chat_completions_url, responses_url, extra_headers_json
                FROM llm_providers
                WHERE provider_name = ?
                """,
                (normalized_provider_name,),
            ).fetchone()
            if row is None:
                raise ValueError(f"未找到 provider_name={normalized_provider_name} 的供应商配置。")

            referenced_models = connection.execute(
                """
                SELECT model_key
                FROM llm_models
                WHERE provider_name = ?
                ORDER BY model_key ASC
                """,
                (normalized_provider_name,),
            ).fetchall()
            if referenced_models:
                model_keys = ",".join(str(item["model_key"]) for item in referenced_models)
                raise ValueError(
                    f"无法删除 provider_name={normalized_provider_name} 的供应商配置；"
                    f"仍有模型引用：{model_keys}。请先删除这些模型配置。"
                )

            deleted_provider = self._row_to_provider(row)
            connection.execute(
                """
                DELETE FROM llm_providers
                WHERE provider_name = ?
                """,
                (normalized_provider_name,),
            )
        return {
            "deleted": True,
            "provider": deleted_provider,
        }

    def delete_model(self, model_key: str) -> dict[str, Any]:
        normalized_model_key = _normalize_key(model_key, "model_key")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT model_key, provider_name, model_name, api_mode, timeout_seconds
                FROM llm_models
                WHERE model_key = ?
                """,
                (normalized_model_key,),
            ).fetchone()
            if row is None:
                raise ValueError(f"未找到 model_key={normalized_model_key} 的模型配置。")

            referenced_environments = connection.execute(
                """
                SELECT environment_name
                FROM llm_environment_models
                WHERE model_key = ?
                ORDER BY environment_name ASC, route_index ASC
                """,
                (normalized_model_key,),
            ).fetchall()
            if referenced_environments:
                environment_names = ",".join(
                    str(item["environment_name"]) for item in referenced_environments
                )
                raise ValueError(
                    f"无法删除 model_key={normalized_model_key} 的模型配置；"
                    f"仍被环境引用：{environment_names}。请先更新或删除这些环境配置。"
                )

            deleted_model = self._row_to_model(row)
            connection.execute(
                """
                DELETE FROM llm_models
                WHERE model_key = ?
                """,
                (normalized_model_key,),
            )
        return {
            "deleted": True,
            "model": deleted_model,
        }

    def delete_environment(self, environment_name: str) -> dict[str, Any]:
        normalized_environment_name = _normalize_key(environment_name, "environment_name")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT environment_name, agent_fallback, description
                FROM llm_environments
                WHERE environment_name = ?
                """,
                (normalized_environment_name,),
            ).fetchone()
            if row is None:
                raise ValueError(
                    f"未找到 environment_name={normalized_environment_name} 的环境配置。"
                )

            deleted_environment = self._row_to_environment(row, connection=connection)
            connection.execute(
                """
                DELETE FROM llm_environments
                WHERE environment_name = ?
                """,
                (normalized_environment_name,),
            )
        return {
            "deleted": True,
            "environment": deleted_environment,
        }

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
        now = utc_now()

        with self._connect() as connection:
            existing = connection.execute(
                """
                SELECT provider_name, created_at
                FROM llm_providers
                WHERE provider_name = ?
                """,
                (normalized_provider_name,),
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else now
            connection.execute(
                """
                INSERT INTO llm_providers (
                    provider_name,
                    api_key_env,
                    chat_completions_url,
                    responses_url,
                    extra_headers_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_name) DO UPDATE SET
                    api_key_env = excluded.api_key_env,
                    chat_completions_url = excluded.chat_completions_url,
                    responses_url = excluded.responses_url,
                    extra_headers_json = excluded.extra_headers_json,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_provider_name,
                    normalized_api_key_env,
                    normalized_chat_url,
                    normalized_responses_url,
                    _json_dumps(normalized_extra_headers),
                    created_at,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT provider_name, api_key_env, chat_completions_url, responses_url, extra_headers_json
                FROM llm_providers
                WHERE provider_name = ?
                """,
                (normalized_provider_name,),
            ).fetchone()
        return self._row_to_provider(row)

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
        now = utc_now()

        with self._connect() as connection:
            provider = connection.execute(
                """
                SELECT provider_name
                FROM llm_providers
                WHERE provider_name = ?
                """,
                (normalized_provider_name,),
            ).fetchone()
            if provider is None:
                raise ValueError(f"未找到 provider_name={normalized_provider_name} 的供应商配置。")

            existing = connection.execute(
                """
                SELECT model_key, created_at
                FROM llm_models
                WHERE model_key = ?
                """,
                (normalized_model_key,),
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else now
            connection.execute(
                """
                INSERT INTO llm_models (
                    model_key,
                    provider_name,
                    model_name,
                    api_mode,
                    timeout_seconds,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_key) DO UPDATE SET
                    provider_name = excluded.provider_name,
                    model_name = excluded.model_name,
                    api_mode = excluded.api_mode,
                    timeout_seconds = excluded.timeout_seconds,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_model_key,
                    normalized_provider_name,
                    normalized_model_name,
                    normalized_api_mode,
                    normalized_timeout_seconds,
                    created_at,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT model_key, provider_name, model_name, api_mode, timeout_seconds
                FROM llm_models
                WHERE model_key = ?
                """,
                (normalized_model_key,),
            ).fetchone()
        return self._row_to_model(row)

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
        now = utc_now()

        with self._connect() as connection:
            for model_key in normalized_model_keys:
                model = connection.execute(
                    """
                    SELECT model_key
                    FROM llm_models
                    WHERE model_key = ?
                    """,
                    (model_key,),
                ).fetchone()
                if model is None:
                    raise ValueError(f"未找到 model_key={model_key} 的模型配置。")

            existing = connection.execute(
                """
                SELECT environment_name, created_at
                FROM llm_environments
                WHERE environment_name = ?
                """,
                (normalized_environment_name,),
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else now
            connection.execute(
                """
                INSERT INTO llm_environments (
                    environment_name,
                    agent_fallback,
                    description,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(environment_name) DO UPDATE SET
                    agent_fallback = excluded.agent_fallback,
                    description = excluded.description,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized_environment_name,
                    1 if agent_fallback else 0,
                    normalized_description,
                    created_at,
                    now,
                ),
            )
            connection.execute(
                """
                DELETE FROM llm_environment_models
                WHERE environment_name = ?
                """,
                (normalized_environment_name,),
            )
            for route_index, model_key in enumerate(normalized_model_keys, start=1):
                connection.execute(
                    """
                    INSERT INTO llm_environment_models (
                        environment_name,
                        model_key,
                        route_index,
                        created_at
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (normalized_environment_name, model_key, route_index, now),
                )

            row = connection.execute(
                """
                SELECT environment_name, agent_fallback, description
                FROM llm_environments
                WHERE environment_name = ?
                """,
                (normalized_environment_name,),
            ).fetchone()
            return self._row_to_environment(row, connection=connection)

    def resolve_environment_routes(
        self,
        environment_name: str,
        *,
        model_keys_override: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_environment_name = _normalize_key(environment_name, "environment_name")
        normalized_override = (
            _normalize_model_keys(model_keys_override, "llm_model_keys_override")
            if model_keys_override is not None
            else None
        )
        with self._connect() as connection:
            environment = connection.execute(
                """
                SELECT environment_name, agent_fallback, description
                FROM llm_environments
                WHERE environment_name = ?
                """,
                (normalized_environment_name,),
            ).fetchone()
            if environment is None:
                raise ValueError(f"未找到 environment_name={normalized_environment_name} 的环境配置。")

            route_rows = connection.execute(
                """
                SELECT
                    em.route_index,
                    em.id,
                    m.model_key,
                    m.provider_name,
                    m.model_name,
                    m.api_mode,
                    m.timeout_seconds,
                    p.api_key_env,
                    p.chat_completions_url,
                    p.responses_url,
                    p.extra_headers_json
                FROM llm_environment_models em
                JOIN llm_models m ON m.model_key = em.model_key
                JOIN llm_providers p ON p.provider_name = m.provider_name
                WHERE em.environment_name = ?
                ORDER BY em.route_index ASC, em.id ASC
                """,
                (normalized_environment_name,),
            ).fetchall()

            routes_by_model_key: dict[str, dict[str, Any]] = {}
            ordered_model_keys: list[str] = []
            for row in route_rows:
                api_mode = row["api_mode"]
                api_url = (
                    row["chat_completions_url"]
                    if api_mode == "chat_completions"
                    else row["responses_url"]
                )
                if not isinstance(api_url, str) or not api_url.strip():
                    raise ValueError(
                        f"provider_name={row['provider_name']} 没有为 api_mode={api_mode} 配置可用 URL。"
                    )
                extra_headers = json.loads(row["extra_headers_json"])
                if not isinstance(extra_headers, dict):
                    raise ValueError("extra_headers_json 必须是对象。")
                model_key = str(row["model_key"])
                ordered_model_keys.append(model_key)
                routes_by_model_key[model_key] = {
                    "model_config_key": model_key,
                    "provider_name": row["provider_name"],
                    "api_key_env": row["api_key_env"],
                    "api_mode": api_mode,
                    "model_name": row["model_name"],
                    "api_url": api_url.strip(),
                    "timeout_seconds": row["timeout_seconds"],
                    "header_env_names": extra_headers,
                }

        if normalized_override is not None:
            missing_model_keys = [
                model_key for model_key in normalized_override if model_key not in routes_by_model_key
            ]
            if missing_model_keys:
                raise ValueError(
                    "llm_model_keys_override 只能包含当前环境已绑定的 model_key："
                    + ",".join(missing_model_keys)
                )
            effective_model_keys = normalized_override
        else:
            effective_model_keys = ordered_model_keys

        return {
            "environment_name": environment["environment_name"],
            "agent_fallback": bool(environment["agent_fallback"]),
            "description": environment["description"],
            "routes": [routes_by_model_key[model_key] for model_key in effective_model_keys],
            "model_keys": ordered_model_keys,
            "effective_model_keys": effective_model_keys,
            "override_applied": normalized_override is not None,
        }
