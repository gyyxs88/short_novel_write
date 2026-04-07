from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.story_output_writer import write_story_markdown
from tools.story_idea_pack_evaluator import (
    DEFAULT_EVALUATION_MODE,
    evaluate_deterministic_idea_pack,
)
from tools.story_idea_pack_builder import build_deterministic_idea_pack
from tools.story_idea_pack_llm_builder import (
    DEFAULT_LLM_MODEL,
    DEFAULT_PROVIDER,
    DEFAULT_API_MODE,
    LlmConfigError,
    LlmExhaustedError,
    LlmResponseError,
    LlmTransportError,
    build_llm_idea_pack,
    build_llm_idea_pack_with_fallbacks,
)
from tools.story_llm_config import StoryLlmConfigStore
from tools.story_idea_prompt_matcher import match_idea_cards_from_prompt
from tools.story_idea_repository import StoryIdeaRepository
from tools.story_idea_seed_generator import generate_idea_seed_batch
from tools.story_payload_builder import build_story_payload
from tools.story_draft_builder import build_story_markdown_from_payload
from tools.story_draft_llm_builder import (
    build_llm_story_draft,
    build_llm_story_draft_with_fallbacks,
)
from tools.story_archive_manager import ArchiveError, archive_run
from tools.story_plan_builder import (
    build_deterministic_story_plans,
    normalize_plan_count as normalize_story_plan_count,
    normalize_target_chapter_count as normalize_story_target_chapter_count,
    normalize_target_char_range as normalize_story_target_char_range,
    resolve_default_target_char_range as resolve_default_story_target_char_range,
)
from tools.story_plan_llm_builder import (
    build_llm_story_plans,
    build_llm_story_plans_with_fallbacks,
)
from tools.story_quality_checker import check_story_quality_markdown
from tools.story_structure_checker import check_story_markdown
from tools.story_token_usage import (
    build_empty_token_usage,
    has_token_usage,
    merge_token_usages,
    normalize_token_usage,
)


SUPPORTED_ACTIONS = {
    "save",
    "check_structure",
    "check_quality",
    "inspect",
    "generate_ideas",
    "match_idea_cards",
    "store_idea_cards",
    "build_idea_packs",
    "evaluate_idea_packs",
    "build_story_plans",
    "build_story_payloads",
    "build_story_drafts",
    "get_llm_config",
    "export_llm_config",
    "apply_llm_config",
    "list_llm_providers",
    "list_llm_models",
    "list_llm_environments",
    "get_llm_provider",
    "get_llm_model",
    "get_llm_environment",
    "upsert_llm_provider",
    "upsert_llm_model",
    "upsert_llm_environment",
    "delete_llm_provider",
    "delete_llm_model",
    "delete_llm_environment",
    "list_idea_cards",
    "list_idea_packs",
    "list_idea_pack_evaluations",
    "list_story_plans",
    "list_story_payloads",
    "list_story_drafts",
    "update_idea_pack_status",
    "update_story_plan_status",
    "update_story_draft_status",
    "archive_run",
}


class CliRequestError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        action: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.action = action
        self.details = details or {}


def build_success_response(action: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "action": action,
        "data": data,
    }


def build_error_response(
    code: str,
    message: str,
    action: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = {
        "ok": False,
        "action": action,
        "error": {
            "code": code,
            "message": message,
        },
    }
    if details:
        response["error"]["details"] = details
    return response


def append_token_usage_details(
    details: dict[str, Any] | None,
    token_usage: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_details = dict(details or {})
    normalized_token_usage = normalize_token_usage(token_usage)
    if has_token_usage(normalized_token_usage):
        normalized_details["token_usage"] = normalized_token_usage
    return normalized_details


def read_request() -> dict[str, Any]:
    raw_bytes = sys.stdin.buffer.read()
    try:
        raw_input = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        fallback_encoding = sys.stdin.encoding or "utf-8"
        raw_input = raw_bytes.decode(fallback_encoding)

    try:
        request = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        raise CliRequestError("INVALID_JSON", f"请求不是合法 JSON：{exc.msg}") from exc

    if not isinstance(request, dict):
        raise CliRequestError("INVALID_REQUEST", "请求体必须是 JSON 对象。")
    return request


def validate_request(request: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    action = request.get("action")
    payload = request.get("payload")

    if not isinstance(action, str) or not action.strip():
        raise CliRequestError("INVALID_REQUEST", "action 必填且必须是字符串。")
    if action not in SUPPORTED_ACTIONS:
        raise CliRequestError("UNKNOWN_ACTION", f"不支持的 action：{action}", action=action)
    if not isinstance(payload, dict):
        raise CliRequestError("INVALID_REQUEST", "payload 必填且必须是对象。", action=action)

    return action, payload


def normalize_range(
    value: Any,
    field_name: str,
    action: str,
) -> tuple[int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    ):
        raise CliRequestError(
            "INVALID_REQUEST",
            f"{field_name} 必须是两个整数构成的数组。",
            action=action,
        )
    return value[0], value[1]


def ensure_string_field(
    payload: dict[str, Any],
    field_name: str,
    action: str,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise CliRequestError(
            "INVALID_REQUEST",
            f"{field_name} 必填且必须是非空字符串。",
            action=action,
        )
    return value


def ensure_optional_positive_int(
    payload: dict[str, Any],
    field_name: str,
    action: str,
    default: int,
) -> int:
    value = payload.get(field_name)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise CliRequestError(
            "INVALID_REQUEST",
            f"{field_name} 必须是大于等于 1 的整数。",
            action=action,
        )
    return value


def ensure_optional_string(
    payload: dict[str, Any],
    field_name: str,
    action: str,
) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CliRequestError(
            "INVALID_REQUEST",
            f"{field_name} 必须是非空字符串。",
            action=action,
        )
    return value


def ensure_optional_path_string(
    payload: dict[str, Any],
    field_name: str,
    action: str,
) -> str | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CliRequestError(
            "INVALID_REQUEST",
            f"{field_name} 必须是非空字符串。",
            action=action,
        )
    return value


def ensure_optional_string_list(
    payload: dict[str, Any],
    field_name: str,
    action: str,
) -> list[str] | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise CliRequestError(
            "INVALID_REQUEST",
            f"{field_name} 必须是非空字符串数组。",
            action=action,
        )
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CliRequestError(
                "INVALID_REQUEST",
                f"{field_name} 必须是非空字符串数组。",
                action=action,
            )
        normalized.append(item.strip())
    if len(set(normalized)) != len(normalized):
        raise CliRequestError(
            "INVALID_REQUEST",
            f"{field_name} 不能包含重复值。",
            action=action,
        )
    return normalized


def get_repository(payload: dict[str, Any], action: str) -> StoryIdeaRepository:
    db_path = payload.get("db_path")
    if db_path is not None and (not isinstance(db_path, str) or not db_path.strip()):
        raise CliRequestError("INVALID_REQUEST", "db_path 必须是非空字符串。", action=action)
    return StoryIdeaRepository(db_path)


def get_llm_config_store(payload: dict[str, Any], action: str) -> StoryLlmConfigStore:
    llm_config_path = payload.get("llm_config_path")
    if llm_config_path is not None:
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_config_path 已废弃；LLM 配置现已统一存储在 db_path 对应的 SQLite 里。",
            action=action,
        )
    db_path = payload.get("db_path")
    if db_path is not None and (not isinstance(db_path, str) or not db_path.strip()):
        raise CliRequestError("INVALID_REQUEST", "db_path 必须是非空字符串。", action=action)
    return StoryLlmConfigStore(db_path)


def resolve_llm_environment_config(
    payload: dict[str, Any],
    action: str,
    *,
    llm_environment: str | None,
    llm_model_keys_override: list[str] | None = None,
) -> tuple[StoryLlmConfigStore | None, dict[str, Any] | None, list[str] | None]:
    if llm_environment is None:
        return None, None, None
    store = get_llm_config_store(payload, action)
    environment_config = store.resolve_environment_routes(
        llm_environment,
        model_keys_override=llm_model_keys_override,
    )
    return store, environment_config, llm_model_keys_override


def resolve_content_input(payload: dict[str, Any], action: str) -> str:
    content = payload.get("content")
    file_path = payload.get("file_path")

    has_content = isinstance(content, str) and bool(content.strip())
    has_file_path = isinstance(file_path, str) and bool(file_path.strip())

    if has_content == has_file_path:
        raise CliRequestError(
            "INVALID_INPUT_SOURCE",
            "content 和 file_path 必须且只能传一个。",
            action=action,
        )

    if has_content:
        return content

    target_file = Path(file_path)
    if not target_file.exists():
        raise CliRequestError(
            "FILE_NOT_FOUND",
            f"文件不存在：{target_file}",
            action=action,
        )

    try:
        return target_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliRequestError(
            "IO_ERROR",
            f"读取文件失败：{target_file}",
            action=action,
        ) from exc


def handle_save(payload: dict[str, Any], action: str) -> dict[str, Any]:
    title = ensure_string_field(payload, "title", action)
    content = ensure_string_field(payload, "content", action)
    output_dir = payload.get("output_dir")
    suffix = payload.get("suffix", ".md")

    if output_dir is not None and not isinstance(output_dir, str):
        raise CliRequestError("INVALID_REQUEST", "output_dir 必须是字符串。", action=action)
    if not isinstance(suffix, str) or not suffix.strip():
        raise CliRequestError("INVALID_REQUEST", "suffix 必须是非空字符串。", action=action)

    try:
        result = write_story_markdown(
            title=title,
            content=content,
            output_dir=output_dir,
            suffix=suffix,
        )
    except OSError as exc:
        raise CliRequestError("IO_ERROR", f"写入文件失败：{exc}", action=action) from exc

    return {
        "output_dir": str(result.output_dir),
        "output_path": str(result.output_path),
        "directory_created": result.directory_created,
    }


def handle_check_structure(payload: dict[str, Any], action: str) -> dict[str, Any]:
    content = resolve_content_input(payload, action)
    target_char_range = normalize_range(payload.get("target_char_range"), "target_char_range", action)
    summary_char_range = normalize_range(
        payload.get("summary_char_range"),
        "summary_char_range",
        action,
    )
    report = check_story_markdown(
        content,
        target_char_range=target_char_range,
        summary_char_range=summary_char_range or (50, 120),
    )
    return {
        "is_valid": report.is_valid,
        "title": report.title,
        "summary_chars": report.summary_chars,
        "body_chars": report.body_chars,
        "chapter_numbers": report.chapter_numbers,
        "issues": report.issues,
    }


def handle_check_quality(payload: dict[str, Any], action: str) -> dict[str, Any]:
    content = resolve_content_input(payload, action)
    report = check_story_quality_markdown(content)
    return {
        "is_passable": report.is_passable,
        "title": report.title,
        "opening_signal_hits": report.opening_signal_hits,
        "middle_signal_hits": report.middle_signal_hits,
        "ending_signal_hits": report.ending_signal_hits,
        "chapter_char_counts": report.chapter_char_counts,
        "title_overlap_chars": report.title_overlap_chars,
        "issues": report.issues,
        "suggestions": report.suggestions,
    }


def handle_inspect(payload: dict[str, Any], action: str) -> dict[str, Any]:
    structure_data = handle_check_structure(payload, action)
    quality_data = handle_check_quality(payload, action)
    return {
        "overall_ok": structure_data["is_valid"] and quality_data["is_passable"],
        "structure": structure_data,
        "quality": quality_data,
    }


def handle_generate_ideas(payload: dict[str, Any], action: str) -> dict[str, Any]:
    count = ensure_optional_positive_int(payload, "count", action, default=3)
    seed = ensure_optional_string(payload, "seed", action)
    data_dir = ensure_optional_path_string(payload, "data_dir", action)

    try:
        batch = generate_idea_seed_batch(count=count, seed=seed, data_dir=data_dir)
    except FileNotFoundError as exc:
        missing_path = getattr(exc, "filename", None) or str(exc)
        raise CliRequestError("FILE_NOT_FOUND", f"文件不存在：{missing_path}", action=action) from exc
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc

    return {
        "seed": batch.seed,
        "count": len(batch.items),
        "items": [
            {
                "id": item.id,
                "types": item.types,
                "main_tags": item.main_tags,
            }
            for item in batch.items
        ],
    }


def handle_match_idea_cards(payload: dict[str, Any], action: str) -> dict[str, Any]:
    prompt = ensure_string_field(payload, "prompt", action)
    count = ensure_optional_positive_int(payload, "count", action, default=3)
    data_dir = ensure_optional_path_string(payload, "data_dir", action)

    try:
        batch = match_idea_cards_from_prompt(prompt=prompt, count=count, data_dir=data_dir)
    except FileNotFoundError as exc:
        missing_path = getattr(exc, "filename", None) or str(exc)
        raise CliRequestError("FILE_NOT_FOUND", f"文件不存在：{missing_path}", action=action) from exc
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc

    return {
        "prompt": batch.prompt,
        "count": len(batch.items),
        "items": [
            {
                "id": item.id,
                "types": item.types,
                "main_tags": item.main_tags,
            }
            for item in batch.items
        ],
    }


def handle_store_idea_cards(payload: dict[str, Any], action: str) -> dict[str, Any]:
    source_mode = ensure_string_field(payload, "source_mode", action)
    seed = ensure_optional_string(payload, "seed", action)
    user_prompt = ensure_optional_string(payload, "user_prompt", action)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise CliRequestError("INVALID_REQUEST", "items 必须是非空数组。", action=action)

    try:
        repository = get_repository(payload, action)
        return repository.store_idea_cards(
            source_mode=source_mode,
            seed=seed,
            user_prompt=user_prompt,
            items=items,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_build_idea_packs(payload: dict[str, Any], action: str) -> dict[str, Any]:
    style = ensure_string_field(payload, "style", action)
    if style not in {"zhihu", "douban"}:
        raise CliRequestError("INVALID_REQUEST", "style 仅支持 zhihu 或 douban。", action=action)
    generation_mode = payload.get("generation_mode", "deterministic")
    if not isinstance(generation_mode, str) or generation_mode not in {"deterministic", "llm"}:
        raise CliRequestError(
            "INVALID_REQUEST",
            "generation_mode 仅支持 deterministic 或 llm。",
            action=action,
        )
    model = ensure_optional_string(payload, "model", action)
    provider = ensure_optional_string(payload, "provider", action)
    api_mode = ensure_optional_string(payload, "api_mode", action)
    llm_environment = ensure_optional_string(payload, "llm_environment", action)
    llm_model_keys_override = ensure_optional_string_list(payload, "llm_model_keys_override", action)
    batch_id = payload.get("batch_id")
    card_ids = payload.get("card_ids")
    if (batch_id is None) == (card_ids is None):
        raise CliRequestError(
            "INVALID_REQUEST",
            "batch_id 和 card_ids 必须且只能传一个。",
            action=action,
        )
    if card_ids is not None:
        if (
            not isinstance(card_ids, list)
            or not card_ids
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in card_ids)
        ):
            raise CliRequestError("INVALID_REQUEST", "card_ids 必须是非空整数数组。", action=action)

    if llm_environment is not None and any(value is not None for value in (model, provider, api_mode)):
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_environment 和 provider/model/api_mode 不能混用。",
            action=action,
        )
    if llm_environment is not None and generation_mode != "llm":
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_environment 只能和 generation_mode=llm 一起使用。",
            action=action,
        )
    if llm_model_keys_override is not None and llm_environment is None:
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_model_keys_override 只能和 llm_environment 一起使用。",
            action=action,
        )
    if llm_model_keys_override is not None and generation_mode != "llm":
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_model_keys_override 只能和 generation_mode=llm 一起使用。",
            action=action,
        )

    try:
        repository = get_repository(payload, action)
        _llm_config_store, environment_config, llm_model_keys_override = resolve_llm_environment_config(
            payload,
            action,
            llm_environment=llm_environment,
            llm_model_keys_override=llm_model_keys_override,
        )
        cards = repository.get_cards_for_build(batch_id=batch_id, card_ids=card_ids)
        created_count = 0
        existing_count = 0
        if llm_environment is not None:
            resolved_model_name = ""
            resolved_provider_name = ""
            resolved_api_mode = ""
        else:
            resolved_model_name = model or (DEFAULT_LLM_MODEL if generation_mode == "llm" else "")
            resolved_provider_name = provider or (DEFAULT_PROVIDER if generation_mode == "llm" else "")
            resolved_api_mode = api_mode or (DEFAULT_API_MODE if generation_mode == "llm" else "")
        used_model_config_keys: list[str] = []
        fallback_used_count = 0
        total_token_usage = build_empty_token_usage()
        items: list[dict[str, Any]] = []
        for card in cards:
            if generation_mode == "llm":
                if llm_environment is not None:
                    built_pack = build_llm_idea_pack_with_fallbacks(
                        card=card,
                        style=style,
                        routes=environment_config["routes"],
                        agent_fallback=environment_config["agent_fallback"],
                    )
                else:
                    built_pack = build_llm_idea_pack(
                        card=card,
                        style=style,
                        model=model,
                        provider=provider,
                        api_mode=api_mode,
                    )
            else:
                built_pack = build_deterministic_idea_pack(card=card, style=style)
            if built_pack.get("model_name"):
                resolved_model_name = built_pack["model_name"]
            if built_pack.get("provider_name") is not None:
                resolved_provider_name = built_pack.get("provider_name", "")
            if built_pack.get("api_mode") is not None:
                resolved_api_mode = built_pack.get("api_mode", "")
            if built_pack.get("model_config_key"):
                model_config_key = built_pack["model_config_key"]
                if model_config_key not in used_model_config_keys:
                    used_model_config_keys.append(model_config_key)
            if built_pack.get("fallback_used"):
                fallback_used_count += 1
            current_token_usage = built_pack.get("token_usage", {})
            total_token_usage = merge_token_usages(total_token_usage, current_token_usage)
            stored_pack = repository.upsert_idea_pack(
                card_id=card["card_id"],
                source_mode=built_pack["source_mode"],
                style=built_pack["style"],
                generation_mode=built_pack["generation_mode"],
                provider_name=built_pack.get("provider_name", ""),
                api_mode=built_pack.get("api_mode", ""),
                model_name=built_pack.get("model_name", ""),
                model_config_key=built_pack.get("model_config_key", ""),
                provider_response_id=built_pack.get("provider_response_id", ""),
                token_usage=current_token_usage,
                style_reason=built_pack["style_reason"],
                hook=built_pack["hook"],
                core_relationship=built_pack["core_relationship"],
                main_conflict=built_pack["main_conflict"],
                reversal_direction=built_pack["reversal_direction"],
                recommended_tags=built_pack["recommended_tags"],
                source_cards=built_pack["source_cards"],
            )
            if stored_pack["status"] == "created":
                created_count += 1
            else:
                existing_count += 1
            items.append(
                {
                    "pack_id": stored_pack["pack_id"],
                    "card_id": card["card_id"],
                    "idea_id": f"idea-pack-{stored_pack['pack_id']:06d}",
                    "status": stored_pack["status"],
                    "generation_mode": stored_pack["generation_mode"],
                    "provider_name": stored_pack.get("provider_name", ""),
                    "api_mode": stored_pack.get("api_mode", ""),
                    "model_name": stored_pack.get("model_name", ""),
                    "model_config_key": stored_pack.get("model_config_key", ""),
                    "attempt_count": built_pack.get("attempt_count", 1),
                    "fallback_used": bool(built_pack.get("fallback_used", False)),
                    "attempts": built_pack.get("attempts", []),
                    "token_usage": normalize_token_usage(current_token_usage),
                }
            )
        return {
            "style": style,
            "generation_mode": generation_mode,
            "provider_name": resolved_provider_name,
            "api_mode": resolved_api_mode,
            "model_name": resolved_model_name,
            "llm_environment": llm_environment or "",
            "effective_llm_model_keys": environment_config["effective_model_keys"] if environment_config else [],
            "llm_model_keys_override": llm_model_keys_override or [],
            "used_model_config_keys": used_model_config_keys,
            "fallback_used_count": fallback_used_count,
            "created_count": created_count,
            "existing_count": existing_count,
            "token_usage": total_token_usage,
            "items": items,
        }
    except LlmConfigError as exc:
        raise CliRequestError("MISSING_CONFIG", str(exc), action=action) from exc
    except LlmExhaustedError as exc:
        error_code = "AGENT_FALLBACK_REQUIRED" if exc.agent_fallback_required else "UPSTREAM_ERROR"
        raise CliRequestError(
            error_code,
            str(exc),
            action=action,
            details=append_token_usage_details({"attempts": exc.attempts}, exc.token_usage),
        ) from exc
    except LlmTransportError as exc:
        raise CliRequestError(
            "UPSTREAM_ERROR",
            str(exc),
            action=action,
            details=append_token_usage_details(None, getattr(exc, "token_usage", {})),
        ) from exc
    except LlmResponseError as exc:
        raise CliRequestError(
            "UPSTREAM_ERROR",
            str(exc),
            action=action,
            details=append_token_usage_details(None, exc.token_usage),
        ) from exc
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_get_llm_config(payload: dict[str, Any], action: str) -> dict[str, Any]:
    try:
        store = get_llm_config_store(payload, action)
        return store.get_config()
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_export_llm_config(payload: dict[str, Any], action: str) -> dict[str, Any]:
    try:
        store = get_llm_config_store(payload, action)
        snapshot = store.export_config_snapshot()
        return {
            "snapshot": snapshot,
            "counts": snapshot["counts"],
        }
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_apply_llm_config(payload: dict[str, Any], action: str) -> dict[str, Any]:
    snapshot = payload.get("snapshot")
    config = payload.get("config")
    try:
        store = get_llm_config_store(payload, action)
        return store.apply_config_snapshot(snapshot, config=config)
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_list_llm_providers(payload: dict[str, Any], action: str) -> dict[str, Any]:
    try:
        store = get_llm_config_store(payload, action)
        items = store.list_providers()
        return {"items": items, "count": len(items)}
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_list_llm_models(payload: dict[str, Any], action: str) -> dict[str, Any]:
    try:
        store = get_llm_config_store(payload, action)
        items = store.list_models()
        return {"items": items, "count": len(items)}
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_list_llm_environments(payload: dict[str, Any], action: str) -> dict[str, Any]:
    try:
        store = get_llm_config_store(payload, action)
        items = store.list_environments()
        return {"items": items, "count": len(items)}
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_get_llm_provider(payload: dict[str, Any], action: str) -> dict[str, Any]:
    provider_name = ensure_string_field(payload, "provider_name", action)
    try:
        store = get_llm_config_store(payload, action)
        return store.get_provider(provider_name)
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_get_llm_model(payload: dict[str, Any], action: str) -> dict[str, Any]:
    model_key = ensure_string_field(payload, "model_key", action)
    try:
        store = get_llm_config_store(payload, action)
        return store.get_model(model_key)
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_get_llm_environment(payload: dict[str, Any], action: str) -> dict[str, Any]:
    environment_name = ensure_string_field(payload, "environment_name", action)
    try:
        store = get_llm_config_store(payload, action)
        return store.get_environment(environment_name)
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_evaluate_idea_packs(payload: dict[str, Any], action: str) -> dict[str, Any]:
    evaluation_mode = payload.get("evaluation_mode", DEFAULT_EVALUATION_MODE)
    if not isinstance(evaluation_mode, str) or not evaluation_mode.strip():
        raise CliRequestError("INVALID_REQUEST", "evaluation_mode 必须是非空字符串。", action=action)
    batch_id = payload.get("batch_id")
    pack_ids = payload.get("pack_ids")
    if (batch_id is None) == (pack_ids is None):
        raise CliRequestError(
            "INVALID_REQUEST",
            "batch_id 和 pack_ids 必须且只能传一个。",
            action=action,
        )
    if pack_ids is not None:
        if (
            not isinstance(pack_ids, list)
            or not pack_ids
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in pack_ids)
        ):
            raise CliRequestError("INVALID_REQUEST", "pack_ids 必须是非空整数数组。", action=action)

    try:
        repository = get_repository(payload, action)
        packs = repository.get_packs_for_evaluation(batch_id=batch_id, pack_ids=pack_ids)
        created_count = 0
        updated_count = 0
        recommendation_counts: dict[str, int] = {}
        items: list[dict[str, Any]] = []
        for pack in packs:
            if evaluation_mode != DEFAULT_EVALUATION_MODE:
                raise CliRequestError(
                    "INVALID_REQUEST",
                    f"evaluation_mode 仅支持 {DEFAULT_EVALUATION_MODE}。",
                    action=action,
                )
            evaluation = evaluate_deterministic_idea_pack(pack)
            stored_evaluation = repository.upsert_idea_pack_evaluation(
                pack_id=evaluation["pack_id"],
                evaluation_mode=evaluation["evaluation_mode"],
                evaluator_name=evaluation["evaluator_name"],
                total_score=evaluation["total_score"],
                hook_strength_score=evaluation["hook_strength_score"],
                conflict_clarity_score=evaluation["conflict_clarity_score"],
                relationship_tension_score=evaluation["relationship_tension_score"],
                reversal_expandability_score=evaluation["reversal_expandability_score"],
                style_fit_score=evaluation["style_fit_score"],
                plan_readiness_score=evaluation["plan_readiness_score"],
                recommendation=evaluation["recommendation"],
                summary=evaluation["summary"],
                strengths=evaluation["strengths"],
                risks=evaluation["risks"],
            )
            if stored_evaluation["status"] == "created":
                created_count += 1
            else:
                updated_count += 1
            recommendation = stored_evaluation["recommendation"]
            recommendation_counts[recommendation] = recommendation_counts.get(recommendation, 0) + 1
            items.append(
                {
                    "evaluation_id": stored_evaluation["evaluation_id"],
                    "pack_id": stored_evaluation["pack_id"],
                    "status": stored_evaluation["status"],
                    "total_score": stored_evaluation["total_score"],
                    "recommendation": stored_evaluation["recommendation"],
                    "summary": stored_evaluation["summary"],
                }
            )
        return {
            "evaluation_mode": evaluation_mode,
            "created_count": created_count,
            "updated_count": updated_count,
            "recommendation_counts": recommendation_counts,
            "items": items,
        }
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_build_story_plans(payload: dict[str, Any], action: str) -> dict[str, Any]:
    generation_mode = payload.get("generation_mode", "deterministic")
    if not isinstance(generation_mode, str) or generation_mode not in {"deterministic", "llm"}:
        raise CliRequestError(
            "INVALID_REQUEST",
            "generation_mode 仅支持 deterministic 或 llm。",
            action=action,
        )
    target_char_range = normalize_range(
        payload.get("target_char_range"),
        "target_char_range",
        action,
    )
    target_chapter_count = payload.get("target_chapter_count")
    if target_chapter_count is not None and (
        isinstance(target_chapter_count, bool) or not isinstance(target_chapter_count, int)
    ):
        raise CliRequestError(
            "INVALID_REQUEST",
            "target_chapter_count 必须是整数。",
            action=action,
        )
    plan_count = payload.get("plan_count")
    if plan_count is not None and (isinstance(plan_count, bool) or not isinstance(plan_count, int)):
        raise CliRequestError(
            "INVALID_REQUEST",
            "plan_count 必须是整数。",
            action=action,
        )
    model = ensure_optional_string(payload, "model", action)
    provider = ensure_optional_string(payload, "provider", action)
    api_mode = ensure_optional_string(payload, "api_mode", action)
    llm_environment = ensure_optional_string(payload, "llm_environment", action)
    llm_model_keys_override = ensure_optional_string_list(payload, "llm_model_keys_override", action)
    batch_id = payload.get("batch_id")
    pack_ids = payload.get("pack_ids")
    if (batch_id is None) == (pack_ids is None):
        raise CliRequestError(
            "INVALID_REQUEST",
            "batch_id 和 pack_ids 必须且只能传一个。",
            action=action,
        )
    if pack_ids is not None:
        if (
            not isinstance(pack_ids, list)
            or not pack_ids
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in pack_ids)
        ):
            raise CliRequestError("INVALID_REQUEST", "pack_ids 必须是非空整数数组。", action=action)

    if llm_environment is not None and any(value is not None for value in (model, provider, api_mode)):
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_environment 和 provider/model/api_mode 不能混用。",
            action=action,
        )
    if llm_environment is not None and generation_mode != "llm":
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_environment 只能和 generation_mode=llm 一起使用。",
            action=action,
        )
    if llm_model_keys_override is not None and llm_environment is None:
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_model_keys_override 只能和 llm_environment 一起使用。",
            action=action,
        )
    if llm_model_keys_override is not None and generation_mode != "llm":
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_model_keys_override 只能和 generation_mode=llm 一起使用。",
            action=action,
        )

    try:
        repository = get_repository(payload, action)
        _llm_config_store, environment_config, llm_model_keys_override = resolve_llm_environment_config(
            payload,
            action,
            llm_environment=llm_environment,
            llm_model_keys_override=llm_model_keys_override,
        )
        packs = repository.get_packs_for_story_plan_build(batch_id=batch_id, pack_ids=pack_ids)
        if target_char_range is None:
            pack_styles = {pack["style"] for pack in packs}
            if len(pack_styles) != 1:
                raise ValueError("未显式传 target_char_range 时，当前批次或 pack_ids 必须属于同一风格。")
            resolved_target_char_range = resolve_default_story_target_char_range(next(iter(pack_styles)))
        else:
            resolved_target_char_range = normalize_story_target_char_range(
                list(target_char_range) if isinstance(target_char_range, tuple) else target_char_range
            )
        resolved_target_chapter_count = normalize_story_target_chapter_count(target_chapter_count)
        resolved_plan_count = normalize_story_plan_count(plan_count)
        created_count = 0
        existing_count = 0
        if llm_environment is not None:
            resolved_model_name = ""
            resolved_provider_name = ""
            resolved_api_mode = ""
        else:
            resolved_model_name = model or (DEFAULT_LLM_MODEL if generation_mode == "llm" else "")
            resolved_provider_name = provider or (DEFAULT_PROVIDER if generation_mode == "llm" else "")
            resolved_api_mode = api_mode or (DEFAULT_API_MODE if generation_mode == "llm" else "")
        used_model_config_keys: list[str] = []
        fallback_used_count = 0
        total_token_usage = build_empty_token_usage()
        items: list[dict[str, Any]] = []
        for pack in packs:
            if generation_mode == "llm":
                if llm_environment is not None:
                    built_payload = build_llm_story_plans_with_fallbacks(
                        pack=pack,
                        routes=environment_config["routes"],
                        agent_fallback=environment_config["agent_fallback"],
                        target_char_range=resolved_target_char_range,
                        target_chapter_count=resolved_target_chapter_count,
                        plan_count=resolved_plan_count,
                    )
                else:
                    built_payload = build_llm_story_plans(
                        pack=pack,
                        model=model,
                        provider=provider,
                        api_mode=api_mode,
                        target_char_range=resolved_target_char_range,
                        target_chapter_count=resolved_target_chapter_count,
                        plan_count=resolved_plan_count,
                    )
                built_plans = built_payload["plans"]
                if built_plans:
                    resolved_model_name = built_plans[0]["model_name"]
                    resolved_provider_name = built_plans[0]["provider_name"]
                    resolved_api_mode = built_plans[0]["api_mode"]
                if built_plans and built_plans[0].get("model_config_key"):
                    model_config_key = built_plans[0]["model_config_key"]
                    if model_config_key not in used_model_config_keys:
                        used_model_config_keys.append(model_config_key)
                if built_payload.get("fallback_used"):
                    fallback_used_count += 1
                attempt_count = built_payload.get("attempt_count", 1)
                fallback_used = bool(built_payload.get("fallback_used", False))
                attempts = built_payload.get("attempts", [])
                current_token_usage = built_payload.get("token_usage", {})
            else:
                built_plans = build_deterministic_story_plans(
                    pack=pack,
                    target_char_range=resolved_target_char_range,
                    target_chapter_count=resolved_target_chapter_count,
                    plan_count=resolved_plan_count,
                )
                attempt_count = 1
                fallback_used = False
                attempts = []
                current_token_usage = {}

            total_token_usage = merge_token_usages(total_token_usage, current_token_usage)

            for built_plan in built_plans:
                stored_plan = repository.upsert_story_plan(
                    pack_id=built_plan["pack_id"],
                    source_mode=built_plan["source_mode"],
                    style=built_plan["style"],
                    variant_index=built_plan["variant_index"],
                    variant_key=built_plan["variant_key"],
                    variant_label=built_plan["variant_label"],
                    generation_mode=built_plan["generation_mode"],
                    provider_name=built_plan.get("provider_name", ""),
                    api_mode=built_plan.get("api_mode", ""),
                    model_name=built_plan.get("model_name", ""),
                    model_config_key=built_plan.get("model_config_key", ""),
                    provider_response_id=built_plan.get("provider_response_id", ""),
                    token_usage=current_token_usage,
                    title=built_plan["title"],
                    genre_tone=built_plan["genre_tone"],
                    selling_point=built_plan["selling_point"],
                    protagonist_profile=built_plan["protagonist_profile"],
                    protagonist_goal=built_plan["protagonist_goal"],
                    core_relationship=built_plan["core_relationship"],
                    main_conflict=built_plan["main_conflict"],
                    key_turning_point=built_plan["key_turning_point"],
                    ending_direction=built_plan["ending_direction"],
                    chapter_rhythm=built_plan["chapter_rhythm"],
                    writing_brief=built_plan["writing_brief"],
                )
                if stored_plan["status"] == "created":
                    created_count += 1
                else:
                    existing_count += 1
                items.append(
                    {
                        "plan_id": stored_plan["plan_id"],
                        "pack_id": stored_plan["pack_id"],
                        "variant_index": stored_plan["variant_index"],
                        "variant_key": stored_plan["variant_key"],
                        "variant_label": stored_plan["variant_label"],
                        "title": stored_plan["title"],
                        "status": stored_plan["status"],
                        "generation_mode": stored_plan["generation_mode"],
                        "provider_name": stored_plan.get("provider_name", ""),
                        "api_mode": stored_plan.get("api_mode", ""),
                        "model_name": stored_plan.get("model_name", ""),
                        "model_config_key": stored_plan.get("model_config_key", ""),
                        "attempt_count": attempt_count,
                        "fallback_used": fallback_used,
                        "attempts": attempts,
                        "token_usage": normalize_token_usage(current_token_usage),
                    }
                )
        return {
            "generation_mode": generation_mode,
            "target_char_range": list(resolved_target_char_range),
            "target_chapter_count": resolved_target_chapter_count,
            "plan_count": resolved_plan_count,
            "provider_name": resolved_provider_name,
            "api_mode": resolved_api_mode,
            "model_name": resolved_model_name,
            "llm_environment": llm_environment or "",
            "effective_llm_model_keys": environment_config["effective_model_keys"] if environment_config else [],
            "llm_model_keys_override": llm_model_keys_override or [],
            "used_model_config_keys": used_model_config_keys,
            "fallback_used_count": fallback_used_count,
            "created_count": created_count,
            "existing_count": existing_count,
            "token_usage": total_token_usage,
            "items": items,
        }
    except LlmConfigError as exc:
        raise CliRequestError("MISSING_CONFIG", str(exc), action=action) from exc
    except LlmExhaustedError as exc:
        error_code = "AGENT_FALLBACK_REQUIRED" if exc.agent_fallback_required else "UPSTREAM_ERROR"
        raise CliRequestError(
            error_code,
            str(exc),
            action=action,
            details=append_token_usage_details({"attempts": exc.attempts}, exc.token_usage),
        ) from exc
    except LlmTransportError as exc:
        raise CliRequestError(
            "UPSTREAM_ERROR",
            str(exc),
            action=action,
            details=append_token_usage_details(None, getattr(exc, "token_usage", {})),
        ) from exc
    except LlmResponseError as exc:
        raise CliRequestError(
            "UPSTREAM_ERROR",
            str(exc),
            action=action,
            details=append_token_usage_details(None, exc.token_usage),
        ) from exc
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_build_story_payloads(payload: dict[str, Any], action: str) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    plan_ids = payload.get("plan_ids")
    if (batch_id is None) == (plan_ids is None):
        raise CliRequestError(
            "INVALID_REQUEST",
            "batch_id 和 plan_ids 必须且只能传一个。",
            action=action,
        )
    if plan_ids is not None:
        if (
            not isinstance(plan_ids, list)
            or not plan_ids
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in plan_ids)
        ):
            raise CliRequestError("INVALID_REQUEST", "plan_ids 必须是非空整数数组。", action=action)

    try:
        repository = get_repository(payload, action)
        plans = repository.get_story_plans_for_payload_build(batch_id=batch_id, plan_ids=plan_ids)
        created_count = 0
        existing_count = 0
        items: list[dict[str, Any]] = []
        for plan in plans:
            built_payload = build_story_payload(plan=plan)
            stored_payload = repository.upsert_story_payload(
                plan_id=built_payload["plan_id"],
                title=built_payload["title"],
                style=built_payload["style"],
                target_char_range=built_payload["target_char_range"],
                target_chapter_count=built_payload["target_chapter_count"],
                payload=built_payload,
            )
            if stored_payload["status"] == "created":
                created_count += 1
            else:
                existing_count += 1
            items.append(
                {
                    "payload_id": stored_payload["payload_id"],
                    "plan_id": stored_payload["plan_id"],
                    "title": stored_payload["title"],
                    "style": stored_payload["style"],
                    "status": stored_payload["status"],
                }
            )
        return {
            "created_count": created_count,
            "existing_count": existing_count,
            "items": items,
        }
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_build_story_drafts(payload: dict[str, Any], action: str) -> dict[str, Any]:
    generation_mode = payload.get("generation_mode", "deterministic")
    if not isinstance(generation_mode, str) or generation_mode not in {"deterministic", "llm"}:
        raise CliRequestError(
            "INVALID_REQUEST",
            "generation_mode 仅支持 deterministic 或 llm。",
            action=action,
        )
    model = ensure_optional_string(payload, "model", action)
    provider = ensure_optional_string(payload, "provider", action)
    api_mode = ensure_optional_string(payload, "api_mode", action)
    llm_environment = ensure_optional_string(payload, "llm_environment", action)
    llm_model_keys_override = ensure_optional_string_list(payload, "llm_model_keys_override", action)
    batch_id = payload.get("batch_id")
    payload_ids = payload.get("payload_ids")
    if (batch_id is None) == (payload_ids is None):
        raise CliRequestError(
            "INVALID_REQUEST",
            "batch_id 和 payload_ids 必须且只能传一个。",
            action=action,
        )
    if payload_ids is not None:
        if (
            not isinstance(payload_ids, list)
            or not payload_ids
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in payload_ids)
        ):
            raise CliRequestError("INVALID_REQUEST", "payload_ids 必须是非空整数数组。", action=action)

    if llm_environment is not None and any(value is not None for value in (model, provider, api_mode)):
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_environment 和 provider/model/api_mode 不能混用。",
            action=action,
        )
    if llm_environment is not None and generation_mode != "llm":
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_environment 只能和 generation_mode=llm 一起使用。",
            action=action,
        )
    if llm_model_keys_override is not None and llm_environment is None:
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_model_keys_override 只能和 llm_environment 一起使用。",
            action=action,
        )
    if llm_model_keys_override is not None and generation_mode != "llm":
        raise CliRequestError(
            "INVALID_REQUEST",
            "llm_model_keys_override 只能和 generation_mode=llm 一起使用。",
            action=action,
        )

    try:
        repository = get_repository(payload, action)
        _llm_config_store, environment_config, llm_model_keys_override = resolve_llm_environment_config(
            payload,
            action,
            llm_environment=llm_environment,
            llm_model_keys_override=llm_model_keys_override,
        )
        story_payloads = repository.get_story_payloads_for_draft_build(
            batch_id=batch_id,
            payload_ids=payload_ids,
        )
        created_count = 0
        existing_count = 0
        if llm_environment is not None:
            resolved_model_name = ""
            resolved_provider_name = ""
            resolved_api_mode = ""
        else:
            resolved_model_name = model or (DEFAULT_LLM_MODEL if generation_mode == "llm" else "")
            resolved_provider_name = provider or (DEFAULT_PROVIDER if generation_mode == "llm" else "")
            resolved_api_mode = api_mode or (DEFAULT_API_MODE if generation_mode == "llm" else "")
        used_model_config_keys: list[str] = []
        fallback_used_count = 0
        total_token_usage = build_empty_token_usage()
        items: list[dict[str, Any]] = []
        for stored_payload in story_payloads:
            payload_data = {
                **stored_payload["payload"],
                "payload_id": stored_payload["payload_id"],
            }
            if generation_mode == "llm":
                if llm_environment is not None:
                    built_draft = build_llm_story_draft_with_fallbacks(
                        payload=payload_data,
                        routes=environment_config["routes"],
                        agent_fallback=environment_config["agent_fallback"],
                    )
                else:
                    built_draft = build_llm_story_draft(
                        payload=payload_data,
                        model=model,
                        provider=provider,
                        api_mode=api_mode,
                    )
                resolved_model_name = built_draft["model_name"]
                resolved_provider_name = built_draft["provider_name"]
                resolved_api_mode = built_draft["api_mode"]
                if built_draft.get("model_config_key"):
                    model_config_key = built_draft["model_config_key"]
                    if model_config_key not in used_model_config_keys:
                        used_model_config_keys.append(model_config_key)
                if built_draft.get("fallback_used"):
                    fallback_used_count += 1
                attempt_count = built_draft.get("attempt_count", 1)
                fallback_used = bool(built_draft.get("fallback_used", False))
                attempts = built_draft.get("attempts", [])
                current_token_usage = built_draft.get("token_usage", {})
            else:
                built_draft = build_story_markdown_from_payload(payload_data)
                attempt_count = 1
                fallback_used = False
                attempts = []
                current_token_usage = {}

            total_token_usage = merge_token_usages(total_token_usage, current_token_usage)

            stored_draft = repository.upsert_story_draft(
                payload_id=stored_payload["payload_id"],
                generation_mode=generation_mode,
                provider_name=built_draft.get("provider_name", ""),
                api_mode=built_draft.get("api_mode", ""),
                model_name=built_draft.get("model_name", ""),
                model_config_key=built_draft.get("model_config_key", ""),
                provider_response_id=built_draft.get("provider_response_id", ""),
                token_usage=current_token_usage,
                title=built_draft["title"],
                content_markdown=built_draft["content_markdown"],
                summary_text=built_draft["summary_text"],
                body_char_count=built_draft["body_char_count"],
            )
            if stored_draft["status"] == "created":
                created_count += 1
            else:
                existing_count += 1
            items.append(
                {
                    "draft_id": stored_draft["draft_id"],
                    "payload_id": stored_draft["payload_id"],
                    "title": stored_draft["title"],
                    "status": stored_draft["status"],
                    "generation_mode": stored_draft["generation_mode"],
                    "provider_name": stored_draft.get("provider_name", ""),
                    "api_mode": stored_draft.get("api_mode", ""),
                    "model_name": stored_draft.get("model_name", ""),
                    "model_config_key": stored_draft.get("model_config_key", ""),
                    "attempt_count": attempt_count,
                    "fallback_used": fallback_used,
                    "attempts": attempts,
                    "token_usage": normalize_token_usage(current_token_usage),
                }
            )
        return {
            "generation_mode": generation_mode,
            "provider_name": resolved_provider_name,
            "api_mode": resolved_api_mode,
            "model_name": resolved_model_name,
            "llm_environment": llm_environment or "",
            "effective_llm_model_keys": environment_config["effective_model_keys"] if environment_config else [],
            "llm_model_keys_override": llm_model_keys_override or [],
            "used_model_config_keys": used_model_config_keys,
            "fallback_used_count": fallback_used_count,
            "created_count": created_count,
            "existing_count": existing_count,
            "token_usage": total_token_usage,
            "items": items,
        }
    except LlmConfigError as exc:
        raise CliRequestError("MISSING_CONFIG", str(exc), action=action) from exc
    except LlmExhaustedError as exc:
        error_code = "AGENT_FALLBACK_REQUIRED" if exc.agent_fallback_required else "UPSTREAM_ERROR"
        raise CliRequestError(
            error_code,
            str(exc),
            action=action,
            details=append_token_usage_details({"attempts": exc.attempts}, exc.token_usage),
        ) from exc
    except LlmTransportError as exc:
        raise CliRequestError(
            "UPSTREAM_ERROR",
            str(exc),
            action=action,
            details=append_token_usage_details(None, getattr(exc, "token_usage", {})),
        ) from exc
    except LlmResponseError as exc:
        raise CliRequestError(
            "UPSTREAM_ERROR",
            str(exc),
            action=action,
            details=append_token_usage_details(None, exc.token_usage),
        ) from exc
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_upsert_llm_provider(payload: dict[str, Any], action: str) -> dict[str, Any]:
    provider_name = ensure_string_field(payload, "provider_name", action)
    api_key_env = ensure_string_field(payload, "api_key_env", action)
    chat_completions_url = ensure_optional_string(payload, "chat_completions_url", action)
    responses_url = ensure_optional_string(payload, "responses_url", action)
    extra_headers = payload.get("extra_headers")
    try:
        store = get_llm_config_store(payload, action)
        return store.upsert_provider(
            provider_name=provider_name,
            api_key_env=api_key_env,
            chat_completions_url=chat_completions_url,
            responses_url=responses_url,
            extra_headers=extra_headers,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_upsert_llm_model(payload: dict[str, Any], action: str) -> dict[str, Any]:
    model_key = ensure_string_field(payload, "model_key", action)
    provider_name = ensure_string_field(payload, "provider_name", action)
    model_name = ensure_string_field(payload, "model_name", action)
    api_mode = payload.get("api_mode", DEFAULT_API_MODE)
    timeout_seconds = payload.get("timeout_seconds", 60)
    try:
        store = get_llm_config_store(payload, action)
        return store.upsert_model(
            model_key=model_key,
            provider_name=provider_name,
            model_name=model_name,
            api_mode=api_mode,
            timeout_seconds=timeout_seconds,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_upsert_llm_environment(payload: dict[str, Any], action: str) -> dict[str, Any]:
    environment_name = ensure_string_field(payload, "environment_name", action)
    model_keys = payload.get("model_keys")
    agent_fallback = payload.get("agent_fallback", True)
    description = payload.get("description", "")
    try:
        store = get_llm_config_store(payload, action)
        return store.upsert_environment(
            environment_name=environment_name,
            model_keys=model_keys,
            agent_fallback=agent_fallback,
            description=description,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_delete_llm_provider(payload: dict[str, Any], action: str) -> dict[str, Any]:
    provider_name = ensure_string_field(payload, "provider_name", action)
    try:
        store = get_llm_config_store(payload, action)
        return store.delete_provider(provider_name)
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_delete_llm_model(payload: dict[str, Any], action: str) -> dict[str, Any]:
    model_key = ensure_string_field(payload, "model_key", action)
    try:
        store = get_llm_config_store(payload, action)
        return store.delete_model(model_key)
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_delete_llm_environment(payload: dict[str, Any], action: str) -> dict[str, Any]:
    environment_name = ensure_string_field(payload, "environment_name", action)
    try:
        store = get_llm_config_store(payload, action)
        return store.delete_environment(environment_name)
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_list_idea_cards(payload: dict[str, Any], action: str) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    card_status = payload.get("card_status")
    card_ids = payload.get("card_ids")
    try:
        repository = get_repository(payload, action)
        items = repository.list_idea_cards(
            batch_id=batch_id,
            card_status=card_status,
            card_ids=card_ids,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc
    return {"items": items, "count": len(items)}


def handle_list_idea_packs(payload: dict[str, Any], action: str) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    style = payload.get("style")
    generation_mode = payload.get("generation_mode")
    provider_name = payload.get("provider_name")
    model_name = payload.get("model_name")
    pack_status = payload.get("pack_status")
    card_ids = payload.get("card_ids")
    try:
        repository = get_repository(payload, action)
        items = repository.list_idea_packs(
            batch_id=batch_id,
            style=style,
            generation_mode=generation_mode,
            provider_name=provider_name,
            model_name=model_name,
            pack_status=pack_status,
            card_ids=card_ids,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc
    return {"items": items, "count": len(items)}


def handle_list_idea_pack_evaluations(payload: dict[str, Any], action: str) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    pack_ids = payload.get("pack_ids")
    evaluation_mode = payload.get("evaluation_mode")
    recommendation = payload.get("recommendation")
    try:
        repository = get_repository(payload, action)
        items = repository.list_idea_pack_evaluations(
            batch_id=batch_id,
            pack_ids=pack_ids,
            evaluation_mode=evaluation_mode,
            recommendation=recommendation,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc
    return {"items": items, "count": len(items)}


def handle_list_story_plans(payload: dict[str, Any], action: str) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    pack_ids = payload.get("pack_ids")
    style = payload.get("style")
    generation_mode = payload.get("generation_mode")
    provider_name = payload.get("provider_name")
    model_name = payload.get("model_name")
    plan_status = payload.get("plan_status")
    try:
        repository = get_repository(payload, action)
        items = repository.list_story_plans(
            batch_id=batch_id,
            pack_ids=pack_ids,
            style=style,
            generation_mode=generation_mode,
            provider_name=provider_name,
            model_name=model_name,
            plan_status=plan_status,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc
    return {"items": items, "count": len(items)}


def handle_list_story_payloads(payload: dict[str, Any], action: str) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    plan_ids = payload.get("plan_ids")
    style = payload.get("style")
    try:
        repository = get_repository(payload, action)
        items = repository.list_story_payloads(
            batch_id=batch_id,
            plan_ids=plan_ids,
            style=style,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc
    return {"items": items, "count": len(items)}


def handle_list_story_drafts(payload: dict[str, Any], action: str) -> dict[str, Any]:
    batch_id = payload.get("batch_id")
    payload_ids = payload.get("payload_ids")
    generation_mode = payload.get("generation_mode")
    provider_name = payload.get("provider_name")
    model_name = payload.get("model_name")
    draft_status = payload.get("draft_status")
    try:
        repository = get_repository(payload, action)
        items = repository.list_story_drafts(
            batch_id=batch_id,
            payload_ids=payload_ids,
            generation_mode=generation_mode,
            provider_name=provider_name,
            model_name=model_name,
            draft_status=draft_status,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc
    return {"items": items, "count": len(items)}


def handle_update_idea_pack_status(payload: dict[str, Any], action: str) -> dict[str, Any]:
    pack_id = payload.get("pack_id")
    if isinstance(pack_id, bool) or not isinstance(pack_id, int):
        raise CliRequestError("INVALID_REQUEST", "pack_id 必须是整数。", action=action)
    pack_status = ensure_string_field(payload, "pack_status", action)
    review_note = payload.get("review_note", "")
    if not isinstance(review_note, str):
        raise CliRequestError("INVALID_REQUEST", "review_note 必须是字符串。", action=action)

    try:
        repository = get_repository(payload, action)
        return repository.update_idea_pack_status(
            pack_id=pack_id,
            pack_status=pack_status,
            review_note=review_note,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_update_story_plan_status(payload: dict[str, Any], action: str) -> dict[str, Any]:
    plan_id = payload.get("plan_id")
    if isinstance(plan_id, bool) or not isinstance(plan_id, int):
        raise CliRequestError("INVALID_REQUEST", "plan_id 必须是整数。", action=action)
    plan_status = ensure_string_field(payload, "plan_status", action)
    review_note = payload.get("review_note", "")
    if not isinstance(review_note, str):
        raise CliRequestError("INVALID_REQUEST", "review_note 必须是字符串。", action=action)

    try:
        repository = get_repository(payload, action)
        return repository.update_story_plan_status(
            plan_id=plan_id,
            plan_status=plan_status,
            review_note=review_note,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_update_story_draft_status(payload: dict[str, Any], action: str) -> dict[str, Any]:
    draft_id = payload.get("draft_id")
    if isinstance(draft_id, bool) or not isinstance(draft_id, int):
        raise CliRequestError("INVALID_REQUEST", "draft_id 必须是整数。", action=action)
    draft_status = ensure_string_field(payload, "draft_status", action)
    review_note = payload.get("review_note", "")
    if not isinstance(review_note, str):
        raise CliRequestError("INVALID_REQUEST", "review_note 必须是字符串。", action=action)

    try:
        repository = get_repository(payload, action)
        return repository.update_story_draft_status(
            draft_id=draft_id,
            draft_status=draft_status,
            review_note=review_note,
        )
    except ValueError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def handle_archive_run(payload: dict[str, Any], action: str) -> dict[str, Any]:
    run_dir = ensure_string_field(payload, "run_dir", action)
    archive_db_path = ensure_optional_path_string(payload, "archive_db_path", action)
    job_id = ensure_optional_string(payload, "job_id", action)
    source_db_name = ensure_optional_string(payload, "source_db_name", action) or "story_ideas.sqlite3"
    report_name = ensure_optional_string(payload, "report_name", action) or "report.json"
    delete_source_db = payload.get("delete_source_db", False)
    if not isinstance(delete_source_db, bool):
        raise CliRequestError("INVALID_REQUEST", "delete_source_db 必须是布尔值。", action=action)

    try:
        return archive_run(
            run_dir=run_dir,
            archive_db_path=archive_db_path,
            job_id=job_id,
            delete_source_db=delete_source_db,
            source_db_name=source_db_name,
            report_name=report_name,
        )
    except ArchiveError as exc:
        raise CliRequestError("INVALID_REQUEST", str(exc), action=action) from exc


def dispatch_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action == "save":
        return handle_save(payload, action)
    if action == "check_structure":
        return handle_check_structure(payload, action)
    if action == "check_quality":
        return handle_check_quality(payload, action)
    if action == "inspect":
        return handle_inspect(payload, action)
    if action == "generate_ideas":
        return handle_generate_ideas(payload, action)
    if action == "match_idea_cards":
        return handle_match_idea_cards(payload, action)
    if action == "store_idea_cards":
        return handle_store_idea_cards(payload, action)
    if action == "build_idea_packs":
        return handle_build_idea_packs(payload, action)
    if action == "evaluate_idea_packs":
        return handle_evaluate_idea_packs(payload, action)
    if action == "build_story_plans":
        return handle_build_story_plans(payload, action)
    if action == "build_story_payloads":
        return handle_build_story_payloads(payload, action)
    if action == "build_story_drafts":
        return handle_build_story_drafts(payload, action)
    if action == "get_llm_config":
        return handle_get_llm_config(payload, action)
    if action == "export_llm_config":
        return handle_export_llm_config(payload, action)
    if action == "apply_llm_config":
        return handle_apply_llm_config(payload, action)
    if action == "list_llm_providers":
        return handle_list_llm_providers(payload, action)
    if action == "list_llm_models":
        return handle_list_llm_models(payload, action)
    if action == "list_llm_environments":
        return handle_list_llm_environments(payload, action)
    if action == "get_llm_provider":
        return handle_get_llm_provider(payload, action)
    if action == "get_llm_model":
        return handle_get_llm_model(payload, action)
    if action == "get_llm_environment":
        return handle_get_llm_environment(payload, action)
    if action == "upsert_llm_provider":
        return handle_upsert_llm_provider(payload, action)
    if action == "upsert_llm_model":
        return handle_upsert_llm_model(payload, action)
    if action == "upsert_llm_environment":
        return handle_upsert_llm_environment(payload, action)
    if action == "delete_llm_provider":
        return handle_delete_llm_provider(payload, action)
    if action == "delete_llm_model":
        return handle_delete_llm_model(payload, action)
    if action == "delete_llm_environment":
        return handle_delete_llm_environment(payload, action)
    if action == "list_idea_cards":
        return handle_list_idea_cards(payload, action)
    if action == "list_idea_packs":
        return handle_list_idea_packs(payload, action)
    if action == "list_idea_pack_evaluations":
        return handle_list_idea_pack_evaluations(payload, action)
    if action == "list_story_plans":
        return handle_list_story_plans(payload, action)
    if action == "list_story_payloads":
        return handle_list_story_payloads(payload, action)
    if action == "list_story_drafts":
        return handle_list_story_drafts(payload, action)
    if action == "update_idea_pack_status":
        return handle_update_idea_pack_status(payload, action)
    if action == "update_story_plan_status":
        return handle_update_story_plan_status(payload, action)
    if action == "update_story_draft_status":
        return handle_update_story_draft_status(payload, action)
    if action == "archive_run":
        return handle_archive_run(payload, action)
    raise CliRequestError("UNKNOWN_ACTION", f"不支持的 action：{action}", action=action)


def main() -> int:
    action: str | None = None

    try:
        request = read_request()
        action, payload = validate_request(request)
        data = dispatch_action(action, payload)
        response = build_success_response(action, data)
        print(json.dumps(response, ensure_ascii=False))
        return 0
    except CliRequestError as exc:
        response = build_error_response(exc.code, exc.message, exc.action or action, exc.details)
        print(json.dumps(response, ensure_ascii=False))
        return 1
    except Exception as exc:  # pragma: no cover - 兜底分支
        response = build_error_response(
            "INTERNAL_ERROR",
            f"未预期异常：{exc}",
            action,
        )
        print(json.dumps(response, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
