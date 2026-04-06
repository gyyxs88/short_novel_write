from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread
from typing import Any, Callable


CLI_PATH = Path(__file__).resolve().parents[2] / "tools" / "story_cli.py"


def run_cli(request: dict, env_overrides: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(CLI_PATH)],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def parse_stdout_json(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def write_source_files(tmp_path: Path) -> Path:
    data_dir = tmp_path / "idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "School Life - 校园生活\nMystery - 旧案悬疑\nModern - 现代\nRomance - 恋爱\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "Missing Person - 失踪\nFirst Love - 初恋\nSecret Past - 隐秘过去\n"
        "Reunion - 重逢\nMisunderstanding - 误会\n",
        encoding="utf-8",
        newline="\n",
    )
    return data_dir


@contextmanager
def serve_mock_responses_api(
    response_payload: dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]
) -> tuple[str, type[BaseHTTPRequestHandler]]:
    class Handler(BaseHTTPRequestHandler):
        last_request: dict | None = None

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            type(self).last_request = json.loads(raw_body)
            payload = response_payload(type(self).last_request) if callable(response_payload) else response_payload
            status_code = 200
            if isinstance(payload, dict) and "_status_code" in payload:
                status_code = int(payload["_status_code"])
                payload = {key: value for key, value in payload.items() if key != "_status_code"}
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1/responses", Handler
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_match_idea_cards_action_returns_deterministic_items(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)
    request = {
        "action": "match_idea_cards",
        "payload": {
            "prompt": "我想写校园初恋和失踪旧案",
            "count": 2,
            "data_dir": str(data_dir),
        },
    }

    first = parse_stdout_json(run_cli(request))
    second = parse_stdout_json(run_cli(request))

    assert first["ok"] is True
    assert first["data"]["items"] == second["data"]["items"]
    assert first["data"]["items"][0]["types"] == ["Mystery - 旧案悬疑", "School Life - 校园生活"]


def test_store_idea_cards_action_creates_batch_and_deduplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    request = {
        "action": "store_idea_cards",
        "payload": {
            "db_path": str(db_path),
            "source_mode": "seed_generate",
            "seed": "seed-a",
            "items": [
                {
                    "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                    "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                }
            ],
        },
    }

    first = parse_stdout_json(run_cli(request))
    second = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-b",
                    "items": [
                        {
                            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
                            "main_tags": ["Secret Past - 隐秘过去", "Missing Person - 失踪", "First Love - 初恋"],
                        }
                    ],
                },
            }
        )
    )

    assert first["ok"] is True
    assert first["data"]["new_card_count"] == 1
    assert second["data"]["existing_card_count"] == 1


def test_build_list_and_update_idea_packs_actions_work_together(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    batch_id = stored["data"]["batch_id"]

    built = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": batch_id,
                    "style": "zhihu",
                },
            }
        )
    )
    listed = parse_stdout_json(
        run_cli(
            {
                "action": "list_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "style": "zhihu",
                    "pack_status": "draft",
                },
            }
        )
    )

    pack_id = listed["data"]["items"][0]["pack_id"]
    updated = parse_stdout_json(
        run_cli(
            {
                "action": "update_idea_pack_status",
                "payload": {
                    "db_path": str(db_path),
                    "pack_id": pack_id,
                    "pack_status": "selected",
                    "review_note": "知乎版更适合当前默认风格",
                },
            }
        )
    )

    assert built["ok"] is True
    assert built["data"]["created_count"] == 1
    assert listed["data"]["items"][0]["style"] == "zhihu"
    assert updated["data"]["pack_status"] == "selected"
    assert updated["data"]["review_note"] == "知乎版更适合当前默认风格"


def test_evaluate_and_list_pack_evaluations_actions_work_together(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    built = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "style": "zhihu",
                },
            }
        )
    )
    evaluated = parse_stdout_json(
        run_cli(
            {
                "action": "evaluate_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                },
            }
        )
    )
    listed = parse_stdout_json(
        run_cli(
            {
                "action": "list_idea_pack_evaluations",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                },
            }
        )
    )

    assert built["ok"] is True
    assert evaluated["ok"] is True
    assert evaluated["data"]["created_count"] == 1
    assert evaluated["data"]["updated_count"] == 0
    assert evaluated["data"]["items"][0]["total_score"] >= 1
    assert listed["data"]["count"] == 1
    assert listed["data"]["items"][0]["pack"]["style"] == "zhihu"
    assert listed["data"]["items"][0]["recommendation"] in {"priority_select", "shortlist", "rework"}


def test_list_idea_cards_action_returns_batch_items(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )

    listed = parse_stdout_json(
        run_cli(
            {
                "action": "list_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                },
            }
        )
    )

    assert listed["ok"] is True
    assert listed["data"]["count"] == 1
    assert listed["data"]["items"][0]["types"] == ["Mystery - 悬疑 / 推理", "Modern - 现代"]


def test_build_idea_packs_action_supports_card_ids(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "prompt_match",
                    "user_prompt": "我想写校园初恋和失踪旧案",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    card_id = stored["data"]["items"][0]["card_id"]

    built = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "card_ids": [card_id],
                    "style": "zhihu",
                },
            }
        )
    )

    assert built["ok"] is True
    assert built["data"]["created_count"] == 1
    assert built["data"]["items"][0]["card_id"] == card_id


def test_build_idea_packs_action_supports_llm_generation_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )

    mock_response = {
        "id": "chatcmpl_cli_123",
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

    with serve_mock_responses_api(mock_response) as (api_url, handler):
        env_overrides = {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_CHAT_COMPLETIONS_URL": api_url,
        }
        built = parse_stdout_json(
            run_cli(
                {
                    "action": "build_idea_packs",
                    "payload": {
                        "db_path": str(db_path),
                        "batch_id": stored["data"]["batch_id"],
                        "style": "zhihu",
                        "generation_mode": "llm",
                        "provider": "openrouter",
                        "api_mode": "chat_completions",
                        "model": "qwen/qwen3.6-plus:free",
                    },
                },
                env_overrides=env_overrides,
            )
        )
        listed = parse_stdout_json(
            run_cli(
                {
                    "action": "list_idea_packs",
                    "payload": {
                        "db_path": str(db_path),
                        "style": "zhihu",
                        "generation_mode": "llm",
                        "provider_name": "openrouter",
                        "model_name": "qwen/qwen3.6-plus:free",
                    },
                },
                env_overrides=env_overrides,
            )
        )

    assert built["ok"] is True
    assert built["data"]["generation_mode"] == "llm"
    assert built["data"]["provider_name"] == "openrouter"
    assert built["data"]["api_mode"] == "chat_completions"
    assert built["data"]["model_name"] == "qwen/qwen3.6-plus:free"
    assert built["data"]["created_count"] == 1
    assert listed["data"]["count"] == 1
    assert listed["data"]["items"][0]["generation_mode"] == "llm"
    assert listed["data"]["items"][0]["provider_name"] == "openrouter"
    assert listed["data"]["items"][0]["model_name"] == "qwen/qwen3.6-plus:free"
    assert handler.last_request is not None
    assert handler.last_request["model"] == "qwen/qwen3.6-plus:free"


def test_build_idea_packs_action_supports_llm_environment_fallback(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    llm_config_path = tmp_path / "llm_config.json"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )

    parse_stdout_json(
        run_cli(
            {
                "action": "upsert_llm_provider",
                "payload": {
                    "llm_config_path": str(llm_config_path),
                    "provider_name": "openrouter",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "chat_completions_url": "https://example.com/placeholder",
                },
            }
        )
    )
    parse_stdout_json(
        run_cli(
            {
                "action": "upsert_llm_model",
                "payload": {
                    "llm_config_path": str(llm_config_path),
                    "model_key": "route_a",
                    "provider_name": "openrouter",
                    "model_name": "model-a",
                    "api_mode": "chat_completions",
                },
            }
        )
    )
    parse_stdout_json(
        run_cli(
            {
                "action": "upsert_llm_model",
                "payload": {
                    "llm_config_path": str(llm_config_path),
                    "model_key": "route_b",
                    "provider_name": "openrouter",
                    "model_name": "model-b",
                    "api_mode": "chat_completions",
                },
            }
        )
    )
    parse_stdout_json(
        run_cli(
            {
                "action": "upsert_llm_environment",
                "payload": {
                    "llm_config_path": str(llm_config_path),
                    "environment_name": "idea_pack_default",
                    "model_keys": ["route_a", "route_b"],
                    "agent_fallback": True,
                },
            }
        )
    )

    def response_factory(request_payload: dict[str, Any]) -> dict[str, Any]:
        if request_payload["model"] == "model-a":
            return {
                "_status_code": 500,
                "error": {"message": "route_a failed"},
            }
        return {
            "id": "chatcmpl_env_123",
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

    with serve_mock_responses_api(response_factory) as (api_url, handler):
        provider_response = parse_stdout_json(
            run_cli(
                {
                    "action": "upsert_llm_provider",
                    "payload": {
                        "llm_config_path": str(llm_config_path),
                        "provider_name": "openrouter",
                        "api_key_env": "OPENROUTER_API_KEY",
                        "chat_completions_url": api_url,
                    },
                }
            )
        )
        built = parse_stdout_json(
            run_cli(
                {
                    "action": "build_idea_packs",
                    "payload": {
                        "db_path": str(db_path),
                        "llm_config_path": str(llm_config_path),
                        "batch_id": stored["data"]["batch_id"],
                        "style": "zhihu",
                        "generation_mode": "llm",
                        "llm_environment": "idea_pack_default",
                    },
                },
                env_overrides={"OPENROUTER_API_KEY": "test-key"},
            )
        )

    assert provider_response["ok"] is True
    assert built["ok"] is True
    assert built["data"]["llm_environment"] == "idea_pack_default"
    assert built["data"]["fallback_used_count"] == 1
    assert built["data"]["used_model_config_keys"] == ["route_b"]
    assert built["data"]["items"][0]["model_name"] == "model-b"
    assert built["data"]["items"][0]["model_config_key"] == "route_b"
    assert built["data"]["items"][0]["fallback_used"] is True
    assert built["data"]["items"][0]["attempt_count"] == 2
    assert built["data"]["items"][0]["attempts"][0]["status"] == "failed"
    assert built["data"]["items"][0]["attempts"][1]["status"] == "success"
    assert handler.last_request is not None
    assert handler.last_request["model"] == "model-b"


def test_build_idea_packs_action_returns_agent_fallback_required_when_environment_exhausted(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    llm_config_path = tmp_path / "llm_config.json"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    parse_stdout_json(
        run_cli(
            {
                "action": "upsert_llm_provider",
                "payload": {
                    "llm_config_path": str(llm_config_path),
                    "provider_name": "openrouter",
                    "api_key_env": "OPENROUTER_API_KEY",
                    "chat_completions_url": "https://example.com/placeholder",
                },
            }
        )
    )
    parse_stdout_json(
        run_cli(
            {
                "action": "upsert_llm_model",
                "payload": {
                    "llm_config_path": str(llm_config_path),
                    "model_key": "route_a",
                    "provider_name": "openrouter",
                    "model_name": "model-a",
                    "api_mode": "chat_completions",
                },
            }
        )
    )
    parse_stdout_json(
        run_cli(
            {
                "action": "upsert_llm_environment",
                "payload": {
                    "llm_config_path": str(llm_config_path),
                    "environment_name": "idea_pack_default",
                    "model_keys": ["route_a"],
                    "agent_fallback": True,
                },
            }
        )
    )

    def response_factory(request_payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "_status_code": 500,
            "error": {"message": f"{request_payload['model']} failed"},
        }

    with serve_mock_responses_api(response_factory) as (api_url, _handler):
        parse_stdout_json(
            run_cli(
                {
                    "action": "upsert_llm_provider",
                    "payload": {
                        "llm_config_path": str(llm_config_path),
                        "provider_name": "openrouter",
                        "api_key_env": "OPENROUTER_API_KEY",
                        "chat_completions_url": api_url,
                    },
                }
            )
        )
        result = run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "llm_config_path": str(llm_config_path),
                    "batch_id": stored["data"]["batch_id"],
                    "style": "zhihu",
                    "generation_mode": "llm",
                    "llm_environment": "idea_pack_default",
                },
            },
            env_overrides={"OPENROUTER_API_KEY": "test-key"},
        )

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "AGENT_FALLBACK_REQUIRED"
    assert len(response["error"]["details"]["attempts"]) == 1


def test_build_list_and_update_story_plans_actions_work_together(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    built_pack = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "style": "zhihu",
                },
            }
        )
    )
    built_plans = parse_stdout_json(
        run_cli(
            {
                "action": "build_story_plans",
                "payload": {
                    "db_path": str(db_path),
                    "pack_ids": [built_pack["data"]["items"][0]["pack_id"]],
                    "target_char_range": [5000, 8000],
                    "target_chapter_count": 6,
                    "plan_count": 4,
                },
            }
        )
    )
    listed = parse_stdout_json(
        run_cli(
            {
                "action": "list_story_plans",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "plan_status": "draft",
                },
            }
        )
    )

    plan_id = listed["data"]["items"][0]["plan_id"]
    updated = parse_stdout_json(
        run_cli(
            {
                "action": "update_story_plan_status",
                "payload": {
                    "db_path": str(db_path),
                    "plan_id": plan_id,
                    "plan_status": "selected",
                    "review_note": "这一版最适合进入正文阶段",
                },
            }
        )
    )

    assert built_plans["ok"] is True
    assert built_plans["data"]["created_count"] == 4
    assert listed["data"]["count"] == 4
    assert listed["data"]["items"][0]["writing_brief"]["target_char_range"] == [5000, 8000]
    assert listed["data"]["items"][0]["writing_brief"]["target_chapter_count"] == 6
    assert updated["data"]["plan_status"] == "selected"
    assert updated["data"]["review_note"] == "这一版最适合进入正文阶段"


def test_build_story_plans_action_uses_style_default_target_range_when_omitted(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    built_pack = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "style": "zhihu",
                },
            }
        )
    )
    built_plans = parse_stdout_json(
        run_cli(
            {
                "action": "build_story_plans",
                "payload": {
                    "db_path": str(db_path),
                    "pack_ids": [built_pack["data"]["items"][0]["pack_id"]],
                },
            }
        )
    )
    listed = parse_stdout_json(
        run_cli(
            {
                "action": "list_story_plans",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "plan_status": "draft",
                },
            }
        )
    )

    assert built_plans["ok"] is True
    assert built_plans["data"]["target_char_range"] == [10000, 30000]
    assert listed["data"]["items"][0]["writing_brief"]["target_char_range"] == [10000, 30000]


def test_build_story_plans_action_supports_llm_generation_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    built_pack = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "style": "zhihu",
                },
            }
        )
    )
    plan_response_payload = {
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

    with serve_mock_responses_api(
        {
            "id": "chatcmpl_plan_cli_123",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(plan_response_payload, ensure_ascii=False),
                    }
                }
            ],
        }
    ) as (api_url, handler):
        env_overrides = {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_CHAT_COMPLETIONS_URL": api_url,
        }
        built_plans = parse_stdout_json(
            run_cli(
                {
                    "action": "build_story_plans",
                    "payload": {
                        "db_path": str(db_path),
                        "pack_ids": [built_pack["data"]["items"][0]["pack_id"]],
                        "generation_mode": "llm",
                        "provider": "openrouter",
                        "api_mode": "chat_completions",
                        "model": "qwen/qwen3.6-plus:free",
                        "target_char_range": [5000, 8000],
                        "target_chapter_count": 6,
                        "plan_count": 4,
                    },
                },
                env_overrides=env_overrides,
            )
        )
        listed = parse_stdout_json(
            run_cli(
                {
                    "action": "list_story_plans",
                    "payload": {
                        "db_path": str(db_path),
                        "pack_ids": [built_pack["data"]["items"][0]["pack_id"]],
                        "generation_mode": "llm",
                        "provider_name": "openrouter",
                        "model_name": "qwen/qwen3.6-plus:free",
                    },
                }
            )
        )

    assert built_plans["ok"] is True
    assert built_plans["data"]["generation_mode"] == "llm"
    assert built_plans["data"]["provider_name"] == "openrouter"
    assert built_plans["data"]["api_mode"] == "chat_completions"
    assert built_plans["data"]["model_name"] == "qwen/qwen3.6-plus:free"
    assert built_plans["data"]["created_count"] == 4
    assert listed["data"]["count"] == 4
    assert listed["data"]["items"][0]["generation_mode"] == "llm"
    assert listed["data"]["items"][0]["writing_brief"]["target_chapter_count"] == 6
    assert handler.last_request is not None
    assert handler.last_request["model"] == "qwen/qwen3.6-plus:free"


def test_build_story_payloads_and_drafts_actions_work_together(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    built_pack = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "style": "zhihu",
                },
            }
        )
    )
    built_plans = parse_stdout_json(
        run_cli(
            {
                "action": "build_story_plans",
                "payload": {
                    "db_path": str(db_path),
                    "pack_ids": [built_pack["data"]["items"][0]["pack_id"]],
                    "target_char_range": [5000, 8000],
                    "target_chapter_count": 6,
                    "plan_count": 4,
                },
            }
        )
    )
    built_payloads = parse_stdout_json(
        run_cli(
            {
                "action": "build_story_payloads",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                },
            }
        )
    )
    listed_payloads = parse_stdout_json(
        run_cli(
            {
                "action": "list_story_payloads",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                },
            }
        )
    )
    built_drafts = parse_stdout_json(
        run_cli(
            {
                "action": "build_story_drafts",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                },
            }
        )
    )
    listed_drafts = parse_stdout_json(
        run_cli(
            {
                "action": "list_story_drafts",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "draft_status": "draft",
                },
            }
        )
    )
    updated_draft = parse_stdout_json(
        run_cli(
            {
                "action": "update_story_draft_status",
                "payload": {
                    "db_path": str(db_path),
                    "draft_id": listed_drafts["data"]["items"][0]["draft_id"],
                    "draft_status": "selected",
                    "review_note": "这版正文可继续修订",
                },
            }
        )
    )

    assert built_plans["data"]["created_count"] == 4
    assert built_payloads["data"]["created_count"] == 4
    assert listed_payloads["data"]["count"] == 4
    assert built_drafts["data"]["created_count"] == 4
    assert listed_drafts["data"]["count"] == 4
    assert "## 简介" in listed_drafts["data"]["items"][0]["content_markdown"]
    assert "## 正文" in listed_drafts["data"]["items"][0]["content_markdown"]
    assert updated_draft["data"]["draft_status"] == "selected"
    assert updated_draft["data"]["review_note"] == "这版正文可继续修订"


def test_build_story_drafts_action_supports_llm_generation_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )
    built_pack = parse_stdout_json(
        run_cli(
            {
                "action": "build_idea_packs",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                    "style": "zhihu",
                },
            }
        )
    )
    parse_stdout_json(
        run_cli(
            {
                "action": "build_story_plans",
                "payload": {
                    "db_path": str(db_path),
                    "pack_ids": [built_pack["data"]["items"][0]["pack_id"]],
                    "target_char_range": [5000, 8000],
                    "target_chapter_count": 6,
                    "plan_count": 4,
                },
            }
        )
    )
    built_payloads = parse_stdout_json(
        run_cli(
            {
                "action": "build_story_payloads",
                "payload": {
                    "db_path": str(db_path),
                    "batch_id": stored["data"]["batch_id"],
                },
            }
        )
    )

    summary_text = (
        "婚礼前夜，失踪前任忽然用旧号码发来求救短信，说真正想让女主闭嘴的人一直躲在她最信任的关系里，"
        "她必须在天亮前拆穿旧案和婚约背后的双重骗局。"
    )
    chapter_template = (
        "女主被迫顺着旧短信追到新的现场，一边处理不断失控的婚礼安排，"
        "一边拆解前任、未婚夫和旧案之间互相套住的谎话，"
        "每往前一步都要付出更具体的代价，也让她更清楚自己已经回不到原来的安全位置。"
    )
    draft_response_payload = {
        "summary": summary_text,
        "chapters": [
            {"chapter_number": 1, "content": chapter_template * 10},
            {"chapter_number": 2, "content": chapter_template * 10},
            {"chapter_number": 3, "content": chapter_template * 10},
            {"chapter_number": 4, "content": chapter_template * 10},
            {"chapter_number": 5, "content": chapter_template * 10},
            {"chapter_number": 6, "content": chapter_template * 10},
        ],
    }

    with serve_mock_responses_api(
        {
            "id": "chatcmpl_draft_cli_123",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(draft_response_payload, ensure_ascii=False),
                    }
                }
            ],
        }
    ) as (api_url, handler):
        env_overrides = {
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_CHAT_COMPLETIONS_URL": api_url,
        }
        built_drafts = parse_stdout_json(
            run_cli(
                {
                    "action": "build_story_drafts",
                    "payload": {
                        "db_path": str(db_path),
                        "payload_ids": [built_payloads["data"]["items"][0]["payload_id"]],
                        "generation_mode": "llm",
                        "provider": "openrouter",
                        "api_mode": "chat_completions",
                        "model": "qwen/qwen3.6-plus:free",
                    },
                },
                env_overrides=env_overrides,
            )
        )
        listed = parse_stdout_json(
            run_cli(
                {
                    "action": "list_story_drafts",
                    "payload": {
                        "db_path": str(db_path),
                        "payload_ids": [built_payloads["data"]["items"][0]["payload_id"]],
                        "generation_mode": "llm",
                        "provider_name": "openrouter",
                        "model_name": "qwen/qwen3.6-plus:free",
                    },
                }
            )
        )

    assert built_drafts["ok"] is True
    assert built_drafts["data"]["generation_mode"] == "llm"
    assert built_drafts["data"]["provider_name"] == "openrouter"
    assert built_drafts["data"]["model_name"] == "qwen/qwen3.6-plus:free"
    assert built_drafts["data"]["created_count"] == 1
    assert listed["data"]["count"] == 1
    assert listed["data"]["items"][0]["generation_mode"] == "llm"
    assert "## 正文" in listed["data"]["items"][0]["content_markdown"]
    assert handler.last_request is not None
    assert handler.last_request["model"] == "qwen/qwen3.6-plus:free"


def test_build_idea_packs_action_rejects_invalid_style(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    result = run_cli(
        {
            "action": "build_idea_packs",
            "payload": {
                "db_path": str(db_path),
                "batch_id": 1,
                "style": "weibo",
            },
        }
    )

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"


def test_store_idea_cards_action_rejects_invalid_db_path_type() -> None:
    result = run_cli(
        {
            "action": "store_idea_cards",
            "payload": {
                "db_path": 123,
                "source_mode": "seed_generate",
                "seed": "seed-a",
                "items": [
                    {
                        "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                        "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                    }
                ],
            },
        }
    )

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"


def test_build_idea_packs_action_llm_requires_api_key(tmp_path: Path) -> None:
    db_path = tmp_path / "story_ideas.sqlite3"
    stored = parse_stdout_json(
        run_cli(
            {
                "action": "store_idea_cards",
                "payload": {
                    "db_path": str(db_path),
                    "source_mode": "seed_generate",
                    "seed": "seed-a",
                    "items": [
                        {
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            }
        )
    )

    result = run_cli(
        {
            "action": "build_idea_packs",
            "payload": {
                "db_path": str(db_path),
                "batch_id": stored["data"]["batch_id"],
                "style": "zhihu",
                "generation_mode": "llm",
            },
        },
        env_overrides={
            "LLM_API_KEY": "",
            "OPENAI_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "OPENAI_CHAT_COMPLETIONS_URL": "",
            "OPENAI_RESPONSES_URL": "",
        },
    )

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "MISSING_CONFIG"
