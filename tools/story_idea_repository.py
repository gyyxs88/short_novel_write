from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_IDEA_DB_PATH = Path("outputs/idea_pipeline/story_ideas.sqlite3")
VALID_SOURCE_MODES = {"seed_generate", "prompt_match"}
VALID_CARD_STATUSES = {"new", "expanded", "discarded"}
VALID_PACK_STATUSES = {"draft", "shortlisted", "selected", "rejected"}
VALID_PLAN_STATUSES = {"draft", "shortlisted", "selected", "rejected"}
VALID_DRAFT_STATUSES = {"draft", "shortlisted", "selected", "rejected"}
VALID_STYLES = {"zhihu", "douban"}
VALID_GENERATION_MODES = {"deterministic", "llm"}
VALID_EVALUATION_MODES = {"deterministic"}
VALID_EVALUATION_RECOMMENDATIONS = {"priority_select", "shortlist", "rework"}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS idea_card_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_mode TEXT NOT NULL,
    seed TEXT,
    user_prompt TEXT,
    requested_count INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idea_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_signature TEXT NOT NULL UNIQUE,
    types_json TEXT NOT NULL,
    main_tags_json TEXT NOT NULL,
    card_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS idea_batch_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL,
    card_id INTEGER NOT NULL,
    batch_item_index INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(batch_id, batch_item_index),
    FOREIGN KEY(batch_id) REFERENCES idea_card_batches(id),
    FOREIGN KEY(card_id) REFERENCES idea_cards(id)
);

CREATE TABLE IF NOT EXISTS idea_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL,
    source_mode TEXT NOT NULL,
    style TEXT NOT NULL,
    generation_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_config_key TEXT NOT NULL,
    provider_response_id TEXT NOT NULL,
    style_reason TEXT NOT NULL,
    hook TEXT NOT NULL,
    core_relationship TEXT NOT NULL,
    main_conflict TEXT NOT NULL,
    reversal_direction TEXT NOT NULL,
    recommended_tags_json TEXT NOT NULL,
    source_cards_json TEXT NOT NULL,
    pack_status TEXT NOT NULL,
    review_note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(card_id, style, generation_mode, provider_name, api_mode, model_name, model_config_key),
    FOREIGN KEY(card_id) REFERENCES idea_cards(id)
);

CREATE INDEX IF NOT EXISTS idx_idea_batch_cards_batch_id ON idea_batch_cards(batch_id);
CREATE INDEX IF NOT EXISTS idx_idea_batch_cards_card_id ON idea_batch_cards(card_id);
CREATE INDEX IF NOT EXISTS idx_idea_packs_status_style_generation_updated_at ON idea_packs(pack_status, style, generation_mode, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_idea_packs_card_id ON idea_packs(card_id);

CREATE TABLE IF NOT EXISTS idea_pack_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    evaluation_mode TEXT NOT NULL,
    evaluator_name TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    hook_strength_score INTEGER NOT NULL,
    conflict_clarity_score INTEGER NOT NULL,
    relationship_tension_score INTEGER NOT NULL,
    reversal_expandability_score INTEGER NOT NULL,
    style_fit_score INTEGER NOT NULL,
    plan_readiness_score INTEGER NOT NULL,
    recommendation TEXT NOT NULL,
    summary TEXT NOT NULL,
    strengths_json TEXT NOT NULL,
    risks_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(pack_id, evaluation_mode, evaluator_name),
    FOREIGN KEY(pack_id) REFERENCES idea_packs(id)
);

CREATE INDEX IF NOT EXISTS idx_idea_pack_evaluations_pack_id ON idea_pack_evaluations(pack_id);
CREATE INDEX IF NOT EXISTS idx_idea_pack_evaluations_total_score ON idea_pack_evaluations(total_score DESC);

CREATE TABLE IF NOT EXISTS story_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL,
    source_mode TEXT NOT NULL,
    style TEXT NOT NULL,
    variant_index INTEGER NOT NULL,
    variant_key TEXT NOT NULL,
    variant_label TEXT NOT NULL,
    generation_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_config_key TEXT NOT NULL,
    provider_response_id TEXT NOT NULL,
    title TEXT NOT NULL,
    genre_tone TEXT NOT NULL,
    selling_point TEXT NOT NULL,
    protagonist_profile TEXT NOT NULL,
    protagonist_goal TEXT NOT NULL,
    core_relationship TEXT NOT NULL,
    main_conflict TEXT NOT NULL,
    key_turning_point TEXT NOT NULL,
    ending_direction TEXT NOT NULL,
    chapter_rhythm_json TEXT NOT NULL,
    writing_brief_json TEXT NOT NULL,
    plan_status TEXT NOT NULL,
    review_note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(pack_id, variant_index, generation_mode, provider_name, api_mode, model_name, model_config_key),
    FOREIGN KEY(pack_id) REFERENCES idea_packs(id)
);

CREATE INDEX IF NOT EXISTS idx_story_plans_pack_id ON story_plans(pack_id);
CREATE INDEX IF NOT EXISTS idx_story_plans_status_generation_updated_at
    ON story_plans(plan_status, generation_mode, updated_at DESC);

CREATE TABLE IF NOT EXISTS story_payloads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL UNIQUE,
    title TEXT NOT NULL,
    style TEXT NOT NULL,
    target_char_range_json TEXT NOT NULL,
    target_chapter_count INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(plan_id) REFERENCES story_plans(id)
);

CREATE INDEX IF NOT EXISTS idx_story_payloads_plan_id ON story_payloads(plan_id);
CREATE INDEX IF NOT EXISTS idx_story_payloads_style_title
    ON story_payloads(style, title);

CREATE TABLE IF NOT EXISTS story_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload_id INTEGER NOT NULL,
    generation_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_config_key TEXT NOT NULL,
    provider_response_id TEXT NOT NULL,
    title TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    body_char_count INTEGER NOT NULL,
    draft_status TEXT NOT NULL,
    review_note TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(payload_id, generation_mode, provider_name, api_mode, model_name, model_config_key),
    FOREIGN KEY(payload_id) REFERENCES story_payloads(id)
);

CREATE INDEX IF NOT EXISTS idx_story_drafts_payload_id ON story_drafts(payload_id);
CREATE INDEX IF NOT EXISTS idx_story_drafts_status_generation_updated_at
    ON story_drafts(draft_status, generation_mode, updated_at DESC);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_idea_db_path(db_path: str | Path | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(__file__).resolve().parents[1] / DEFAULT_IDEA_DB_PATH


def _normalize_string(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip()


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} 必须是非空字符串数组。")
    normalized: list[str] = []
    for item in value:
        normalized.append(_normalize_string(item, field_name))
    return normalized


def _normalize_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} 必须是整数。")
    return value


def _normalize_int_list(value: Any, field_name: str) -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} 必须是非空整数数组。")
    normalized: list[int] = []
    for item in value:
        normalized.append(_normalize_int(item, field_name))
    return normalized


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads_list(raw_text: str) -> list[str]:
    value = json.loads(raw_text)
    if not isinstance(value, list):
        raise ValueError("JSON 内容必须是数组。")
    return value


def canonicalize_card_signature(types: list[str], main_tags: list[str]) -> str:
    normalized_types = sorted(_normalize_string_list(types, "types"))
    normalized_main_tags = sorted(_normalize_string_list(main_tags, "main_tags"))
    return _json_dumps({"types": normalized_types, "main_tags": normalized_main_tags})


class StoryIdeaRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = resolve_idea_db_path(db_path)
        self.initialize()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _validate_source_mode(self, source_mode: str) -> str:
        normalized = _normalize_string(source_mode, "source_mode")
        if normalized not in VALID_SOURCE_MODES:
            raise ValueError(f"source_mode 仅支持：{sorted(VALID_SOURCE_MODES)}")
        return normalized

    def _validate_style(self, style: str) -> str:
        normalized = _normalize_string(style, "style")
        if normalized not in VALID_STYLES:
            raise ValueError(f"style 仅支持：{sorted(VALID_STYLES)}")
        return normalized

    def _validate_generation_mode(self, generation_mode: str) -> str:
        normalized = _normalize_string(generation_mode, "generation_mode")
        if normalized not in VALID_GENERATION_MODES:
            raise ValueError(f"generation_mode 仅支持：{sorted(VALID_GENERATION_MODES)}")
        return normalized

    def _validate_card_status(self, card_status: str) -> str:
        normalized = _normalize_string(card_status, "card_status")
        if normalized not in VALID_CARD_STATUSES:
            raise ValueError(f"card_status 仅支持：{sorted(VALID_CARD_STATUSES)}")
        return normalized

    def _validate_pack_status(self, pack_status: str) -> str:
        normalized = _normalize_string(pack_status, "pack_status")
        if normalized not in VALID_PACK_STATUSES:
            raise ValueError(f"pack_status 仅支持：{sorted(VALID_PACK_STATUSES)}")
        return normalized

    def _validate_plan_status(self, plan_status: str) -> str:
        normalized = _normalize_string(plan_status, "plan_status")
        if normalized not in VALID_PLAN_STATUSES:
            raise ValueError(f"plan_status 仅支持：{sorted(VALID_PLAN_STATUSES)}")
        return normalized

    def _validate_draft_status(self, draft_status: str) -> str:
        normalized = _normalize_string(draft_status, "draft_status")
        if normalized not in VALID_DRAFT_STATUSES:
            raise ValueError(f"draft_status 仅支持：{sorted(VALID_DRAFT_STATUSES)}")
        return normalized

    def _validate_evaluation_mode(self, evaluation_mode: str) -> str:
        normalized = _normalize_string(evaluation_mode, "evaluation_mode")
        if normalized not in VALID_EVALUATION_MODES:
            raise ValueError(f"evaluation_mode 仅支持：{sorted(VALID_EVALUATION_MODES)}")
        return normalized

    def _validate_evaluation_recommendation(self, recommendation: str) -> str:
        normalized = _normalize_string(recommendation, "recommendation")
        if normalized not in VALID_EVALUATION_RECOMMENDATIONS:
            raise ValueError(f"recommendation 仅支持：{sorted(VALID_EVALUATION_RECOMMENDATIONS)}")
        return normalized

    def _row_to_card(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "card_id": row["id"],
            "types": _json_loads_list(row["types_json"]),
            "main_tags": _json_loads_list(row["main_tags_json"]),
            "card_status": row["card_status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _row_to_pack(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "pack_id": row["id"],
            "card_id": row["card_id"],
            "source_mode": row["source_mode"],
            "style": row["style"],
            "generation_mode": row["generation_mode"],
            "provider_name": row["provider_name"],
            "api_mode": row["api_mode"],
            "model_name": row["model_name"],
            "model_config_key": row["model_config_key"],
            "provider_response_id": row["provider_response_id"],
            "style_reason": row["style_reason"],
            "hook": row["hook"],
            "core_relationship": row["core_relationship"],
            "main_conflict": row["main_conflict"],
            "reversal_direction": row["reversal_direction"],
            "recommended_tags": _json_loads_list(row["recommended_tags_json"]),
            "source_cards": json.loads(row["source_cards_json"]),
            "pack_status": row["pack_status"],
            "review_note": row["review_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _row_to_evaluation(self, row: sqlite3.Row) -> dict[str, Any]:
        evaluation = {
            "evaluation_id": row["id"],
            "pack_id": row["pack_id"],
            "evaluation_mode": row["evaluation_mode"],
            "evaluator_name": row["evaluator_name"],
            "total_score": row["total_score"],
            "hook_strength_score": row["hook_strength_score"],
            "conflict_clarity_score": row["conflict_clarity_score"],
            "relationship_tension_score": row["relationship_tension_score"],
            "reversal_expandability_score": row["reversal_expandability_score"],
            "style_fit_score": row["style_fit_score"],
            "plan_readiness_score": row["plan_readiness_score"],
            "recommendation": row["recommendation"],
            "summary": row["summary"],
            "strengths": _json_loads_list(row["strengths_json"]),
            "risks": _json_loads_list(row["risks_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "style" in row.keys():
            evaluation["pack"] = {
                "pack_id": row["pack_id"],
                "style": row["style"],
                "generation_mode": row["generation_mode"],
                "provider_name": row["provider_name"],
                "api_mode": row["api_mode"],
                "model_name": row["model_name"],
                "model_config_key": row["model_config_key"],
                "pack_status": row["pack_status"],
                "hook": row["hook"],
            }
        return evaluation

    def _row_to_story_plan(self, row: sqlite3.Row) -> dict[str, Any]:
        plan = {
            "plan_id": row["id"],
            "pack_id": row["pack_id"],
            "source_mode": row["source_mode"],
            "style": row["style"],
            "variant_index": row["variant_index"],
            "variant_key": row["variant_key"],
            "variant_label": row["variant_label"],
            "generation_mode": row["generation_mode"],
            "provider_name": row["provider_name"],
            "api_mode": row["api_mode"],
            "model_name": row["model_name"],
            "model_config_key": row["model_config_key"],
            "provider_response_id": row["provider_response_id"],
            "title": row["title"],
            "genre_tone": row["genre_tone"],
            "selling_point": row["selling_point"],
            "protagonist_profile": row["protagonist_profile"],
            "protagonist_goal": row["protagonist_goal"],
            "core_relationship": row["core_relationship"],
            "main_conflict": row["main_conflict"],
            "key_turning_point": row["key_turning_point"],
            "ending_direction": row["ending_direction"],
            "chapter_rhythm": json.loads(row["chapter_rhythm_json"]),
            "writing_brief": json.loads(row["writing_brief_json"]),
            "plan_status": row["plan_status"],
            "review_note": row["review_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "pack_generation_mode" in row.keys():
            plan["pack"] = {
                "pack_id": row["pack_id"],
                "pack_generation_mode": row["pack_generation_mode"],
                "pack_provider_name": row["pack_provider_name"],
                "pack_model_name": row["pack_model_name"],
                "pack_status": row["pack_status"],
                "pack_style": row["style"],
            }
        return plan

    def _row_to_story_payload(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            raise ValueError("payload_json 必须是对象。")
        payload_data = {
            "payload_id": row["id"],
            "plan_id": row["plan_id"],
            "title": row["title"],
            "style": row["style"],
            "target_char_range": json.loads(row["target_char_range_json"]),
            "target_chapter_count": row["target_chapter_count"],
            "payload": payload,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "plan_generation_mode" in row.keys():
            payload_data["plan"] = {
                "plan_id": row["plan_id"],
                "variant_index": row["variant_index"],
                "variant_key": row["variant_key"],
                "variant_label": row["variant_label"],
                "plan_generation_mode": row["plan_generation_mode"],
                "plan_status": row["plan_status"],
            }
        return payload_data

    def _row_to_story_draft(self, row: sqlite3.Row) -> dict[str, Any]:
        draft = {
            "draft_id": row["id"],
            "payload_id": row["payload_id"],
            "generation_mode": row["generation_mode"],
            "provider_name": row["provider_name"],
            "api_mode": row["api_mode"],
            "model_name": row["model_name"],
            "model_config_key": row["model_config_key"],
            "provider_response_id": row["provider_response_id"],
            "title": row["title"],
            "content_markdown": row["content_markdown"],
            "summary_text": row["summary_text"],
            "body_char_count": row["body_char_count"],
            "draft_status": row["draft_status"],
            "review_note": row["review_note"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        if "payload_title" in row.keys():
            draft["payload"] = {
                "payload_id": row["payload_id"],
                "payload_title": row["payload_title"],
                "payload_style": row["payload_style"],
                "target_chapter_count": row["target_chapter_count"],
            }
        return draft

    def store_idea_cards(
        self,
        *,
        source_mode: str,
        items: list[dict[str, Any]],
        seed: str | None = None,
        user_prompt: str | None = None,
    ) -> dict[str, Any]:
        normalized_source_mode = self._validate_source_mode(source_mode)
        if normalized_source_mode == "seed_generate":
            seed = _normalize_string(seed, "seed")
        else:
            user_prompt = _normalize_string(user_prompt, "user_prompt")

        if not isinstance(items, list) or not items:
            raise ValueError("items 必须是非空数组。")

        normalized_items: list[dict[str, list[str]]] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("items 里的每一项都必须是对象。")
            types = _normalize_string_list(item.get("types"), "types")
            main_tags = _normalize_string_list(item.get("main_tags"), "main_tags")
            if len(types) != 2:
                raise ValueError("每张原始卡组必须包含 2 个类型。")
            if len(main_tags) != 3:
                raise ValueError("每张原始卡组必须包含 3 个主标签。")
            normalized_items.append({"types": types, "main_tags": main_tags})

        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO idea_card_batches (source_mode, seed, user_prompt, requested_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_source_mode, seed, user_prompt, len(normalized_items), now),
            )
            batch_id = int(cursor.lastrowid)
            new_card_count = 0
            existing_card_count = 0
            stored_items: list[dict[str, Any]] = []

            for index, item in enumerate(normalized_items, start=1):
                signature = canonicalize_card_signature(item["types"], item["main_tags"])
                existing_row = connection.execute(
                    "SELECT id FROM idea_cards WHERE canonical_signature = ?",
                    (signature,),
                ).fetchone()
                if existing_row is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO idea_cards (
                            canonical_signature,
                            types_json,
                            main_tags_json,
                            card_status,
                            created_at,
                            updated_at
                        )
                        VALUES (?, ?, ?, 'new', ?, ?)
                        """,
                        (
                            signature,
                            _json_dumps(item["types"]),
                            _json_dumps(item["main_tags"]),
                            now,
                            now,
                        ),
                    )
                    card_id = int(cursor.lastrowid)
                    new_card_count += 1
                    status = "created"
                else:
                    card_id = int(existing_row["id"])
                    existing_card_count += 1
                    status = "existing"

                connection.execute(
                    """
                    INSERT INTO idea_batch_cards (batch_id, card_id, batch_item_index, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (batch_id, card_id, index, now),
                )
                stored_items.append(
                    {
                        "card_id": card_id,
                        "batch_item_index": index,
                        "status": status,
                        "types": item["types"],
                        "main_tags": item["main_tags"],
                    }
                )

        return {
            "batch_id": batch_id,
            "total_items": len(normalized_items),
            "new_card_count": new_card_count,
            "existing_card_count": existing_card_count,
            "items": stored_items,
        }

    def list_idea_cards(
        self,
        *,
        batch_id: int | None = None,
        card_status: str | None = None,
        card_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT c.id, c.types_json, c.main_tags_json, c.card_status, c.created_at, c.updated_at",
            "FROM idea_cards c",
        ]
        if batch_id is not None:
            batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = c.id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(batch_id)
        else:
            sql_lines.append("WHERE 1 = 1")

        if card_status is not None:
            sql_lines.append("AND c.card_status = ?")
            params.append(self._validate_card_status(card_status))

        if card_ids is not None:
            card_ids = _normalize_int_list(card_ids, "card_ids")
            placeholders = ", ".join("?" for _ in card_ids)
            sql_lines.append(f"AND c.id IN ({placeholders})")
            params.extend(card_ids)

        sql_lines.append("ORDER BY c.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_card(row) for row in rows]

    def get_cards_for_build(
        self,
        *,
        batch_id: int | None = None,
        card_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        if (batch_id is None) == (card_ids is None):
            raise ValueError("batch_id 和 card_ids 必须且只能传一个。")

        with self._connect() as connection:
            if batch_id is not None:
                batch_id = _normalize_int(batch_id, "batch_id")
                rows = connection.execute(
                    """
                    SELECT
                        c.id,
                        c.types_json,
                        c.main_tags_json,
                        c.card_status,
                        c.created_at,
                        c.updated_at,
                        bc.batch_item_index,
                        b.source_mode
                    FROM idea_batch_cards bc
                    JOIN idea_cards c ON c.id = bc.card_id
                    JOIN idea_card_batches b ON b.id = bc.batch_id
                    WHERE bc.batch_id = ?
                      AND c.card_status != 'discarded'
                    ORDER BY bc.batch_item_index ASC, c.id ASC
                    """,
                    (batch_id,),
                ).fetchall()
            else:
                card_ids = _normalize_int_list(card_ids, "card_ids")
                order_case = " ".join(
                    f"WHEN {card_id} THEN {index}" for index, card_id in enumerate(card_ids)
                )
                placeholders = ", ".join("?" for _ in card_ids)
                rows = connection.execute(
                    f"""
                    SELECT
                        c.id,
                        c.types_json,
                        c.main_tags_json,
                        c.card_status,
                        c.created_at,
                        c.updated_at,
                        (
                            SELECT b.source_mode
                            FROM idea_batch_cards bc
                            JOIN idea_card_batches b ON b.id = bc.batch_id
                            WHERE bc.card_id = c.id
                            ORDER BY bc.batch_id DESC, bc.batch_item_index ASC
                            LIMIT 1
                        ) AS source_mode
                    FROM idea_cards c
                    WHERE c.id IN ({placeholders})
                      AND c.card_status != 'discarded'
                    ORDER BY CASE c.id {order_case} END, c.id ASC
                    """,
                    card_ids,
                ).fetchall()

        cards: list[dict[str, Any]] = []
        for row in rows:
            card = self._row_to_card(row)
            card["card_status"] = row["card_status"]
            if "source_mode" in row.keys() and row["source_mode"] is not None:
                card["source_mode"] = row["source_mode"]
            if "batch_item_index" in row.keys():
                card["batch_item_index"] = row["batch_item_index"]
            cards.append(card)
        return cards

    def get_packs_for_evaluation(
        self,
        *,
        batch_id: int | None = None,
        pack_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        if (batch_id is None) == (pack_ids is None):
            raise ValueError("batch_id 和 pack_ids 必须且只能传一个。")

        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT p.id, p.card_id, p.source_mode, p.style, p.generation_mode, p.provider_name, p.api_mode, p.model_name, p.model_config_key, p.provider_response_id, p.style_reason, p.hook,",
            "p.core_relationship, p.main_conflict, p.reversal_direction, p.recommended_tags_json,",
            "p.source_cards_json, p.pack_status, p.review_note, p.created_at, p.updated_at",
            "FROM idea_packs p",
        ]
        if batch_id is not None:
            batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = p.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(batch_id)
        else:
            pack_ids = _normalize_int_list(pack_ids, "pack_ids")
            placeholders = ", ".join("?" for _ in pack_ids)
            sql_lines.append(f"WHERE p.id IN ({placeholders})")
            params.extend(pack_ids)

        sql_lines.append("ORDER BY p.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_pack(row) for row in rows]

    def get_packs_for_story_plan_build(
        self,
        *,
        batch_id: int | None = None,
        pack_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        return self.get_packs_for_evaluation(batch_id=batch_id, pack_ids=pack_ids)

    def upsert_idea_pack(
        self,
        *,
        card_id: int,
        source_mode: str,
        style: str,
        generation_mode: str = "deterministic",
        provider_name: str = "",
        api_mode: str = "",
        model_name: str = "",
        model_config_key: str = "",
        provider_response_id: str = "",
        style_reason: str,
        hook: str,
        core_relationship: str,
        main_conflict: str,
        reversal_direction: str,
        recommended_tags: list[str],
        source_cards: dict[str, Any],
        pack_status: str = "draft",
        review_note: str = "",
    ) -> dict[str, Any]:
        card_id = _normalize_int(card_id, "card_id")
        normalized_style = self._validate_style(style)
        normalized_generation_mode = self._validate_generation_mode(generation_mode)

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    card_id,
                    source_mode,
                    style,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    style_reason,
                    hook,
                    core_relationship,
                    main_conflict,
                    reversal_direction,
                    recommended_tags_json,
                    source_cards_json,
                    pack_status,
                    review_note,
                    created_at,
                    updated_at
                FROM idea_packs
                WHERE card_id = ? AND style = ? AND generation_mode = ? AND provider_name = ? AND api_mode = ? AND model_name = ? AND model_config_key = ?
                """,
                (
                    card_id,
                    normalized_style,
                    normalized_generation_mode,
                    provider_name.strip() if isinstance(provider_name, str) else "",
                    api_mode.strip() if isinstance(api_mode, str) else "",
                    model_name.strip() if isinstance(model_name, str) else "",
                    model_config_key.strip() if isinstance(model_config_key, str) else "",
                ),
            ).fetchone()
            if existing_row is not None:
                return {"status": "existing", **self._row_to_pack(existing_row)}

            normalized_source_mode = self._validate_source_mode(source_mode)
            normalized_pack_status = self._validate_pack_status(pack_status)
            normalized_provider_name = provider_name.strip() if isinstance(provider_name, str) else ""
            normalized_api_mode = api_mode.strip() if isinstance(api_mode, str) else ""
            normalized_model_name = model_name.strip() if isinstance(model_name, str) else ""
            normalized_model_config_key = (
                model_config_key.strip() if isinstance(model_config_key, str) else ""
            )
            normalized_provider_response_id = (
                provider_response_id.strip() if isinstance(provider_response_id, str) else ""
            )
            normalized_style_reason = _normalize_string(style_reason, "style_reason")
            normalized_hook = _normalize_string(hook, "hook")
            normalized_core_relationship = _normalize_string(core_relationship, "core_relationship")
            normalized_main_conflict = _normalize_string(main_conflict, "main_conflict")
            normalized_reversal_direction = _normalize_string(reversal_direction, "reversal_direction")
            normalized_recommended_tags = _normalize_string_list(recommended_tags, "recommended_tags")
            normalized_review_note = review_note.strip() if isinstance(review_note, str) else ""
            if not isinstance(source_cards, dict):
                raise ValueError("source_cards 必须是对象。")
            normalized_source_cards = {
                "types": _normalize_string_list(source_cards.get("types"), "source_cards.types"),
                "main_tags": _normalize_string_list(source_cards.get("main_tags"), "source_cards.main_tags"),
            }
            if len(normalized_source_cards["types"]) != 2:
                raise ValueError("source_cards.types 必须恰好包含 2 个类型。")
            if len(normalized_source_cards["main_tags"]) != 3:
                raise ValueError("source_cards.main_tags 必须恰好包含 3 个主标签。")
            now = utc_now()

            connection.execute(
                """
                INSERT INTO idea_packs (
                    card_id,
                    source_mode,
                    style,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    style_reason,
                    hook,
                    core_relationship,
                    main_conflict,
                    reversal_direction,
                    recommended_tags_json,
                    source_cards_json,
                    pack_status,
                    review_note,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    normalized_source_mode,
                    normalized_style,
                    normalized_generation_mode,
                    normalized_provider_name,
                    normalized_api_mode,
                    normalized_model_name,
                    normalized_model_config_key,
                    normalized_provider_response_id,
                    normalized_style_reason,
                    normalized_hook,
                    normalized_core_relationship,
                    normalized_main_conflict,
                    normalized_reversal_direction,
                    _json_dumps(normalized_recommended_tags),
                    _json_dumps(normalized_source_cards),
                    normalized_pack_status,
                    normalized_review_note,
                    now,
                    now,
                ),
            )
            pack_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
            connection.execute(
                """
                UPDATE idea_cards
                SET card_status = 'expanded',
                    updated_at = ?
                WHERE id = ? AND card_status = 'new'
                """,
                (now, card_id),
            )
            stored_row = connection.execute(
                """
                SELECT
                    id,
                    card_id,
                    source_mode,
                    style,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    style_reason,
                    hook,
                    core_relationship,
                    main_conflict,
                    reversal_direction,
                    recommended_tags_json,
                    source_cards_json,
                    pack_status,
                    review_note,
                    created_at,
                    updated_at
                FROM idea_packs
                WHERE id = ?
                """,
                (pack_id,),
            ).fetchone()

        return {"status": "created", **self._row_to_pack(stored_row)}

    def list_idea_packs(
        self,
        *,
        batch_id: int | None = None,
        style: str | None = None,
        generation_mode: str | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        pack_status: str | None = None,
        card_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT p.id, p.card_id, p.source_mode, p.style, p.generation_mode, p.provider_name, p.api_mode, p.model_name, p.model_config_key, p.provider_response_id, p.style_reason, p.hook,",
            "p.core_relationship, p.main_conflict, p.reversal_direction, p.recommended_tags_json,",
            "p.source_cards_json, p.pack_status, p.review_note, p.created_at, p.updated_at",
            "FROM idea_packs p",
        ]
        if batch_id is not None:
            batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = p.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(batch_id)
        else:
            sql_lines.append("WHERE 1 = 1")

        if style is not None:
            sql_lines.append("AND p.style = ?")
            params.append(self._validate_style(style))

        if generation_mode is not None:
            sql_lines.append("AND p.generation_mode = ?")
            params.append(self._validate_generation_mode(generation_mode))

        if provider_name is not None:
            sql_lines.append("AND p.provider_name = ?")
            params.append(_normalize_string(provider_name, "provider_name"))

        if model_name is not None:
            sql_lines.append("AND p.model_name = ?")
            params.append(_normalize_string(model_name, "model_name"))

        if pack_status is not None:
            sql_lines.append("AND p.pack_status = ?")
            params.append(self._validate_pack_status(pack_status))

        if card_ids is not None:
            card_ids = _normalize_int_list(card_ids, "card_ids")
            placeholders = ", ".join("?" for _ in card_ids)
            sql_lines.append(f"AND p.card_id IN ({placeholders})")
            params.extend(card_ids)

        sql_lines.append("ORDER BY p.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_pack(row) for row in rows]

    def update_idea_pack_status(
        self,
        *,
        pack_id: int,
        pack_status: str,
        review_note: str = "",
    ) -> dict[str, Any]:
        pack_id = _normalize_int(pack_id, "pack_id")
        normalized_pack_status = self._validate_pack_status(pack_status)
        normalized_review_note = review_note.strip() if isinstance(review_note, str) else ""
        now = utc_now()

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    card_id,
                    source_mode,
                    style,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    style_reason,
                    hook,
                    core_relationship,
                    main_conflict,
                    reversal_direction,
                    recommended_tags_json,
                    source_cards_json,
                    pack_status,
                    review_note,
                    created_at,
                    updated_at
                FROM idea_packs
                WHERE id = ?
                """,
                (pack_id,),
            ).fetchone()
            if existing_row is None:
                raise ValueError(f"未找到 pack_id={pack_id} 的创意包。")

            connection.execute(
                """
                UPDATE idea_packs
                SET pack_status = ?,
                    review_note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (normalized_pack_status, normalized_review_note, now, pack_id),
            )
            updated_row = connection.execute(
                """
                SELECT
                    id,
                    card_id,
                    source_mode,
                    style,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    style_reason,
                    hook,
                    core_relationship,
                    main_conflict,
                    reversal_direction,
                    recommended_tags_json,
                    source_cards_json,
                    pack_status,
                    review_note,
                    created_at,
                    updated_at
                FROM idea_packs
                WHERE id = ?
                """,
                (pack_id,),
            ).fetchone()

        return self._row_to_pack(updated_row)

    def upsert_story_plan(
        self,
        *,
        pack_id: int,
        source_mode: str,
        style: str,
        variant_index: int,
        variant_key: str,
        variant_label: str,
        generation_mode: str = "deterministic",
        provider_name: str = "",
        api_mode: str = "",
        model_name: str = "",
        model_config_key: str = "",
        provider_response_id: str = "",
        title: str,
        genre_tone: str,
        selling_point: str,
        protagonist_profile: str,
        protagonist_goal: str,
        core_relationship: str,
        main_conflict: str,
        key_turning_point: str,
        ending_direction: str,
        chapter_rhythm: list[dict[str, Any]],
        writing_brief: dict[str, Any],
        plan_status: str = "draft",
        review_note: str = "",
    ) -> dict[str, Any]:
        normalized_pack_id = _normalize_int(pack_id, "pack_id")
        normalized_source_mode = self._validate_source_mode(source_mode)
        normalized_style = self._validate_style(style)
        normalized_variant_index = _normalize_int(variant_index, "variant_index")
        if normalized_variant_index < 1:
            raise ValueError("variant_index 必须大于等于 1。")
        normalized_variant_key = _normalize_string(variant_key, "variant_key")
        normalized_variant_label = _normalize_string(variant_label, "variant_label")
        normalized_generation_mode = self._validate_generation_mode(generation_mode)
        normalized_provider_name = provider_name.strip() if isinstance(provider_name, str) else ""
        normalized_api_mode = api_mode.strip() if isinstance(api_mode, str) else ""
        normalized_model_name = model_name.strip() if isinstance(model_name, str) else ""
        normalized_model_config_key = (
            model_config_key.strip() if isinstance(model_config_key, str) else ""
        )
        normalized_provider_response_id = (
            provider_response_id.strip() if isinstance(provider_response_id, str) else ""
        )
        normalized_title = _normalize_string(title, "title")
        normalized_genre_tone = _normalize_string(genre_tone, "genre_tone")
        normalized_selling_point = _normalize_string(selling_point, "selling_point")
        normalized_protagonist_profile = _normalize_string(
            protagonist_profile,
            "protagonist_profile",
        )
        normalized_protagonist_goal = _normalize_string(protagonist_goal, "protagonist_goal")
        normalized_core_relationship = _normalize_string(core_relationship, "core_relationship")
        normalized_main_conflict = _normalize_string(main_conflict, "main_conflict")
        normalized_key_turning_point = _normalize_string(key_turning_point, "key_turning_point")
        normalized_ending_direction = _normalize_string(ending_direction, "ending_direction")
        if not isinstance(chapter_rhythm, list) or not chapter_rhythm:
            raise ValueError("chapter_rhythm 必须是非空数组。")
        if not isinstance(writing_brief, dict) or not writing_brief:
            raise ValueError("writing_brief 必须是非空对象。")
        normalized_plan_status = self._validate_plan_status(plan_status)
        normalized_review_note = review_note.strip() if isinstance(review_note, str) else ""
        now = utc_now()

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    pack_id,
                    source_mode,
                    style,
                    variant_index,
                    variant_key,
                    variant_label,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    genre_tone,
                    selling_point,
                    protagonist_profile,
                    protagonist_goal,
                    core_relationship,
                    main_conflict,
                    key_turning_point,
                    ending_direction,
                    chapter_rhythm_json,
                    writing_brief_json,
                    plan_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_plans
                WHERE pack_id = ? AND variant_index = ? AND generation_mode = ? AND provider_name = ? AND api_mode = ? AND model_name = ? AND model_config_key = ?
                """,
                (
                    normalized_pack_id,
                    normalized_variant_index,
                    normalized_generation_mode,
                    normalized_provider_name,
                    normalized_api_mode,
                    normalized_model_name,
                    normalized_model_config_key,
                ),
            ).fetchone()
            if existing_row is not None:
                return {"status": "existing", **self._row_to_story_plan(existing_row)}

            connection.execute(
                """
                INSERT INTO story_plans (
                    pack_id,
                    source_mode,
                    style,
                    variant_index,
                    variant_key,
                    variant_label,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    genre_tone,
                    selling_point,
                    protagonist_profile,
                    protagonist_goal,
                    core_relationship,
                    main_conflict,
                    key_turning_point,
                    ending_direction,
                    chapter_rhythm_json,
                    writing_brief_json,
                    plan_status,
                    review_note,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_pack_id,
                    normalized_source_mode,
                    normalized_style,
                    normalized_variant_index,
                    normalized_variant_key,
                    normalized_variant_label,
                    normalized_generation_mode,
                    normalized_provider_name,
                    normalized_api_mode,
                    normalized_model_name,
                    normalized_model_config_key,
                    normalized_provider_response_id,
                    normalized_title,
                    normalized_genre_tone,
                    normalized_selling_point,
                    normalized_protagonist_profile,
                    normalized_protagonist_goal,
                    normalized_core_relationship,
                    normalized_main_conflict,
                    normalized_key_turning_point,
                    normalized_ending_direction,
                    _json_dumps(chapter_rhythm),
                    _json_dumps(writing_brief),
                    normalized_plan_status,
                    normalized_review_note,
                    now,
                    now,
                ),
            )
            plan_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
            stored_row = connection.execute(
                """
                SELECT
                    id,
                    pack_id,
                    source_mode,
                    style,
                    variant_index,
                    variant_key,
                    variant_label,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    genre_tone,
                    selling_point,
                    protagonist_profile,
                    protagonist_goal,
                    core_relationship,
                    main_conflict,
                    key_turning_point,
                    ending_direction,
                    chapter_rhythm_json,
                    writing_brief_json,
                    plan_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_plans
                WHERE id = ?
                """,
                (plan_id,),
            ).fetchone()

        return {"status": "created", **self._row_to_story_plan(stored_row)}

    def list_story_plans(
        self,
        *,
        batch_id: int | None = None,
        pack_ids: list[int] | None = None,
        style: str | None = None,
        generation_mode: str | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        plan_status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT sp.id, sp.pack_id, sp.source_mode, sp.style, sp.variant_index, sp.variant_key, sp.variant_label, sp.generation_mode,",
            "sp.provider_name, sp.api_mode, sp.model_name, sp.model_config_key, sp.provider_response_id, sp.title, sp.genre_tone,",
            "sp.selling_point, sp.protagonist_profile, sp.protagonist_goal, sp.core_relationship, sp.main_conflict, sp.key_turning_point,",
            "sp.ending_direction, sp.chapter_rhythm_json, sp.writing_brief_json, sp.plan_status, sp.review_note, sp.created_at, sp.updated_at,",
            "p.generation_mode AS pack_generation_mode, p.provider_name AS pack_provider_name, p.model_name AS pack_model_name, p.pack_status",
            "FROM story_plans sp",
            "JOIN idea_packs p ON p.id = sp.pack_id",
        ]
        if batch_id is not None:
            batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = p.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(batch_id)
        else:
            sql_lines.append("WHERE 1 = 1")

        if pack_ids is not None:
            normalized_pack_ids = _normalize_int_list(pack_ids, "pack_ids")
            placeholders = ", ".join("?" for _ in normalized_pack_ids)
            sql_lines.append(f"AND sp.pack_id IN ({placeholders})")
            params.extend(normalized_pack_ids)

        if style is not None:
            sql_lines.append("AND sp.style = ?")
            params.append(self._validate_style(style))

        if generation_mode is not None:
            sql_lines.append("AND sp.generation_mode = ?")
            params.append(self._validate_generation_mode(generation_mode))

        if provider_name is not None:
            sql_lines.append("AND sp.provider_name = ?")
            params.append(_normalize_string(provider_name, "provider_name"))

        if model_name is not None:
            sql_lines.append("AND sp.model_name = ?")
            params.append(_normalize_string(model_name, "model_name"))

        if plan_status is not None:
            sql_lines.append("AND sp.plan_status = ?")
            params.append(self._validate_plan_status(plan_status))

        sql_lines.append("ORDER BY sp.pack_id ASC, sp.variant_index ASC, sp.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_story_plan(row) for row in rows]

    def update_story_plan_status(
        self,
        *,
        plan_id: int,
        plan_status: str,
        review_note: str = "",
    ) -> dict[str, Any]:
        normalized_plan_id = _normalize_int(plan_id, "plan_id")
        normalized_plan_status = self._validate_plan_status(plan_status)
        normalized_review_note = review_note.strip() if isinstance(review_note, str) else ""
        now = utc_now()

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    pack_id,
                    source_mode,
                    style,
                    variant_index,
                    variant_key,
                    variant_label,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    genre_tone,
                    selling_point,
                    protagonist_profile,
                    protagonist_goal,
                    core_relationship,
                    main_conflict,
                    key_turning_point,
                    ending_direction,
                    chapter_rhythm_json,
                    writing_brief_json,
                    plan_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_plans
                WHERE id = ?
                """,
                (normalized_plan_id,),
            ).fetchone()
            if existing_row is None:
                raise ValueError(f"未找到 plan_id={normalized_plan_id} 的方案。")

            connection.execute(
                """
                UPDATE story_plans
                SET plan_status = ?,
                    review_note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (normalized_plan_status, normalized_review_note, now, normalized_plan_id),
            )
            updated_row = connection.execute(
                """
                SELECT
                    id,
                    pack_id,
                    source_mode,
                    style,
                    variant_index,
                    variant_key,
                    variant_label,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    genre_tone,
                    selling_point,
                    protagonist_profile,
                    protagonist_goal,
                    core_relationship,
                    main_conflict,
                    key_turning_point,
                    ending_direction,
                    chapter_rhythm_json,
                    writing_brief_json,
                    plan_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_plans
                WHERE id = ?
                """,
                (normalized_plan_id,),
            ).fetchone()

        return self._row_to_story_plan(updated_row)

    def get_story_plans_for_payload_build(
        self,
        *,
        batch_id: int | None = None,
        plan_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        if (batch_id is None) == (plan_ids is None):
            raise ValueError("batch_id 和 plan_ids 必须且只能传一个。")

        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT sp.id, sp.pack_id, sp.source_mode, sp.style, sp.variant_index, sp.variant_key, sp.variant_label, sp.generation_mode,",
            "sp.provider_name, sp.api_mode, sp.model_name, sp.model_config_key, sp.provider_response_id, sp.title, sp.genre_tone,",
            "sp.selling_point, sp.protagonist_profile, sp.protagonist_goal, sp.core_relationship, sp.main_conflict, sp.key_turning_point,",
            "sp.ending_direction, sp.chapter_rhythm_json, sp.writing_brief_json, sp.plan_status, sp.review_note, sp.created_at, sp.updated_at",
            "FROM story_plans sp",
        ]
        if batch_id is not None:
            normalized_batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_packs p ON p.id = sp.pack_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = p.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(normalized_batch_id)
        else:
            normalized_plan_ids = _normalize_int_list(plan_ids, "plan_ids")
            placeholders = ", ".join("?" for _ in normalized_plan_ids)
            sql_lines.append(f"WHERE sp.id IN ({placeholders})")
            params.extend(normalized_plan_ids)

        sql_lines.append("ORDER BY sp.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_story_plan(row) for row in rows]

    def upsert_story_payload(
        self,
        *,
        plan_id: int,
        title: str,
        style: str,
        target_char_range: list[int],
        target_chapter_count: int,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_plan_id = _normalize_int(plan_id, "plan_id")
        normalized_title = _normalize_string(title, "title")
        normalized_style = self._validate_style(style)
        normalized_target_char_range = target_char_range
        if (
            not isinstance(normalized_target_char_range, list)
            or len(normalized_target_char_range) != 2
            or not all(isinstance(item, int) and not isinstance(item, bool) for item in normalized_target_char_range)
        ):
            raise ValueError("target_char_range 必须是两个整数构成的数组。")
        normalized_target_chapter_count = _normalize_int(
            target_chapter_count,
            "target_chapter_count",
        )
        if normalized_target_chapter_count < 1:
            raise ValueError("target_chapter_count 必须大于等于 1。")
        if not isinstance(payload, dict) or not payload:
            raise ValueError("payload 必须是非空对象。")
        now = utc_now()

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    plan_id,
                    title,
                    style,
                    target_char_range_json,
                    target_chapter_count,
                    payload_json,
                    created_at,
                    updated_at
                FROM story_payloads
                WHERE plan_id = ?
                """,
                (normalized_plan_id,),
            ).fetchone()
            if existing_row is not None:
                return {"status": "existing", **self._row_to_story_payload(existing_row)}

            connection.execute(
                """
                INSERT INTO story_payloads (
                    plan_id,
                    title,
                    style,
                    target_char_range_json,
                    target_chapter_count,
                    payload_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_plan_id,
                    normalized_title,
                    normalized_style,
                    _json_dumps(normalized_target_char_range),
                    normalized_target_chapter_count,
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )
            payload_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
            stored_row = connection.execute(
                """
                SELECT
                    id,
                    plan_id,
                    title,
                    style,
                    target_char_range_json,
                    target_chapter_count,
                    payload_json,
                    created_at,
                    updated_at
                FROM story_payloads
                WHERE id = ?
                """,
                (payload_id,),
            ).fetchone()
        return {"status": "created", **self._row_to_story_payload(stored_row)}

    def list_story_payloads(
        self,
        *,
        batch_id: int | None = None,
        plan_ids: list[int] | None = None,
        style: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT sp.id, sp.plan_id, sp.title, sp.style, sp.target_char_range_json, sp.target_chapter_count, sp.payload_json, sp.created_at, sp.updated_at,",
            "p.variant_index, p.variant_key, p.variant_label, p.generation_mode AS plan_generation_mode, p.plan_status",
            "FROM story_payloads sp",
            "JOIN story_plans p ON p.id = sp.plan_id",
        ]
        if batch_id is not None:
            normalized_batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_packs ip ON ip.id = p.pack_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = ip.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(normalized_batch_id)
        else:
            sql_lines.append("WHERE 1 = 1")

        if plan_ids is not None:
            normalized_plan_ids = _normalize_int_list(plan_ids, "plan_ids")
            placeholders = ", ".join("?" for _ in normalized_plan_ids)
            sql_lines.append(f"AND sp.plan_id IN ({placeholders})")
            params.extend(normalized_plan_ids)

        if style is not None:
            sql_lines.append("AND sp.style = ?")
            params.append(self._validate_style(style))

        sql_lines.append("ORDER BY sp.plan_id ASC, sp.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_story_payload(row) for row in rows]

    def get_story_payloads_for_draft_build(
        self,
        *,
        batch_id: int | None = None,
        payload_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        if (batch_id is None) == (payload_ids is None):
            raise ValueError("batch_id 和 payload_ids 必须且只能传一个。")

        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT sp.id, sp.plan_id, sp.title, sp.style, sp.target_char_range_json, sp.target_chapter_count, sp.payload_json, sp.created_at, sp.updated_at",
            "FROM story_payloads sp",
            "JOIN story_plans p ON p.id = sp.plan_id",
        ]
        if batch_id is not None:
            normalized_batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_packs ip ON ip.id = p.pack_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = ip.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(normalized_batch_id)
        else:
            normalized_payload_ids = _normalize_int_list(payload_ids, "payload_ids")
            placeholders = ", ".join("?" for _ in normalized_payload_ids)
            sql_lines.append(f"WHERE sp.id IN ({placeholders})")
            params.extend(normalized_payload_ids)

        sql_lines.append("ORDER BY sp.plan_id ASC, sp.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_story_payload(row) for row in rows]

    def upsert_story_draft(
        self,
        *,
        payload_id: int,
        generation_mode: str = "deterministic",
        provider_name: str = "",
        api_mode: str = "",
        model_name: str = "",
        model_config_key: str = "",
        provider_response_id: str = "",
        title: str,
        content_markdown: str,
        summary_text: str,
        body_char_count: int,
        draft_status: str = "draft",
        review_note: str = "",
    ) -> dict[str, Any]:
        normalized_payload_id = _normalize_int(payload_id, "payload_id")
        normalized_generation_mode = self._validate_generation_mode(generation_mode)
        normalized_provider_name = provider_name.strip() if isinstance(provider_name, str) else ""
        normalized_api_mode = api_mode.strip() if isinstance(api_mode, str) else ""
        normalized_model_name = model_name.strip() if isinstance(model_name, str) else ""
        normalized_model_config_key = (
            model_config_key.strip() if isinstance(model_config_key, str) else ""
        )
        normalized_provider_response_id = (
            provider_response_id.strip() if isinstance(provider_response_id, str) else ""
        )
        normalized_title = _normalize_string(title, "title")
        normalized_content_markdown = _normalize_string(content_markdown, "content_markdown")
        normalized_summary_text = _normalize_string(summary_text, "summary_text")
        normalized_body_char_count = _normalize_int(body_char_count, "body_char_count")
        if normalized_body_char_count < 1:
            raise ValueError("body_char_count 必须大于等于 1。")
        normalized_draft_status = self._validate_draft_status(draft_status)
        normalized_review_note = review_note.strip() if isinstance(review_note, str) else ""
        now = utc_now()

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    payload_id,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    content_markdown,
                    summary_text,
                    body_char_count,
                    draft_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_drafts
                WHERE payload_id = ? AND generation_mode = ? AND provider_name = ? AND api_mode = ? AND model_name = ? AND model_config_key = ?
                """,
                (
                    normalized_payload_id,
                    normalized_generation_mode,
                    normalized_provider_name,
                    normalized_api_mode,
                    normalized_model_name,
                    normalized_model_config_key,
                ),
            ).fetchone()
            if existing_row is not None:
                return {"status": "existing", **self._row_to_story_draft(existing_row)}

            connection.execute(
                """
                INSERT INTO story_drafts (
                    payload_id,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    content_markdown,
                    summary_text,
                    body_char_count,
                    draft_status,
                    review_note,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized_payload_id,
                    normalized_generation_mode,
                    normalized_provider_name,
                    normalized_api_mode,
                    normalized_model_name,
                    normalized_model_config_key,
                    normalized_provider_response_id,
                    normalized_title,
                    normalized_content_markdown,
                    normalized_summary_text,
                    normalized_body_char_count,
                    normalized_draft_status,
                    normalized_review_note,
                    now,
                    now,
                ),
            )
            draft_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
            stored_row = connection.execute(
                """
                SELECT
                    id,
                    payload_id,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    content_markdown,
                    summary_text,
                    body_char_count,
                    draft_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_drafts
                WHERE id = ?
                """,
                (draft_id,),
            ).fetchone()
        return {"status": "created", **self._row_to_story_draft(stored_row)}

    def list_story_drafts(
        self,
        *,
        batch_id: int | None = None,
        payload_ids: list[int] | None = None,
        generation_mode: str | None = None,
        provider_name: str | None = None,
        model_name: str | None = None,
        draft_status: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT sd.id, sd.payload_id, sd.generation_mode, sd.provider_name, sd.api_mode, sd.model_name, sd.model_config_key, sd.provider_response_id,",
            "sd.title, sd.content_markdown, sd.summary_text, sd.body_char_count, sd.draft_status, sd.review_note, sd.created_at, sd.updated_at,",
            "sp.title AS payload_title, sp.style AS payload_style, sp.target_chapter_count",
            "FROM story_drafts sd",
            "JOIN story_payloads sp ON sp.id = sd.payload_id",
            "JOIN story_plans p ON p.id = sp.plan_id",
        ]
        if batch_id is not None:
            normalized_batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_packs ip ON ip.id = p.pack_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = ip.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(normalized_batch_id)
        else:
            sql_lines.append("WHERE 1 = 1")

        if payload_ids is not None:
            normalized_payload_ids = _normalize_int_list(payload_ids, "payload_ids")
            placeholders = ", ".join("?" for _ in normalized_payload_ids)
            sql_lines.append(f"AND sd.payload_id IN ({placeholders})")
            params.extend(normalized_payload_ids)

        if generation_mode is not None:
            sql_lines.append("AND sd.generation_mode = ?")
            params.append(self._validate_generation_mode(generation_mode))

        if provider_name is not None:
            sql_lines.append("AND sd.provider_name = ?")
            params.append(_normalize_string(provider_name, "provider_name"))

        if model_name is not None:
            sql_lines.append("AND sd.model_name = ?")
            params.append(_normalize_string(model_name, "model_name"))

        if draft_status is not None:
            sql_lines.append("AND sd.draft_status = ?")
            params.append(self._validate_draft_status(draft_status))

        sql_lines.append("ORDER BY sd.payload_id ASC, sd.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_story_draft(row) for row in rows]

    def update_story_draft_status(
        self,
        *,
        draft_id: int,
        draft_status: str,
        review_note: str = "",
    ) -> dict[str, Any]:
        normalized_draft_id = _normalize_int(draft_id, "draft_id")
        normalized_draft_status = self._validate_draft_status(draft_status)
        normalized_review_note = review_note.strip() if isinstance(review_note, str) else ""
        now = utc_now()

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    payload_id,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    content_markdown,
                    summary_text,
                    body_char_count,
                    draft_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_drafts
                WHERE id = ?
                """,
                (normalized_draft_id,),
            ).fetchone()
            if existing_row is None:
                raise ValueError(f"未找到 draft_id={normalized_draft_id} 的正文草稿。")

            connection.execute(
                """
                UPDATE story_drafts
                SET draft_status = ?,
                    review_note = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (normalized_draft_status, normalized_review_note, now, normalized_draft_id),
            )
            updated_row = connection.execute(
                """
                SELECT
                    id,
                    payload_id,
                    generation_mode,
                    provider_name,
                    api_mode,
                    model_name,
                    model_config_key,
                    provider_response_id,
                    title,
                    content_markdown,
                    summary_text,
                    body_char_count,
                    draft_status,
                    review_note,
                    created_at,
                    updated_at
                FROM story_drafts
                WHERE id = ?
                """,
                (normalized_draft_id,),
            ).fetchone()
        return self._row_to_story_draft(updated_row)

    def upsert_idea_pack_evaluation(
        self,
        *,
        pack_id: int,
        evaluation_mode: str,
        evaluator_name: str,
        total_score: int,
        hook_strength_score: int,
        conflict_clarity_score: int,
        relationship_tension_score: int,
        reversal_expandability_score: int,
        style_fit_score: int,
        plan_readiness_score: int,
        recommendation: str,
        summary: str,
        strengths: list[str],
        risks: list[str],
    ) -> dict[str, Any]:
        normalized_pack_id = _normalize_int(pack_id, "pack_id")
        normalized_evaluation_mode = self._validate_evaluation_mode(evaluation_mode)
        normalized_evaluator_name = _normalize_string(evaluator_name, "evaluator_name")
        normalized_total_score = _normalize_int(total_score, "total_score")
        normalized_hook_strength_score = _normalize_int(hook_strength_score, "hook_strength_score")
        normalized_conflict_clarity_score = _normalize_int(conflict_clarity_score, "conflict_clarity_score")
        normalized_relationship_tension_score = _normalize_int(
            relationship_tension_score,
            "relationship_tension_score",
        )
        normalized_reversal_expandability_score = _normalize_int(
            reversal_expandability_score,
            "reversal_expandability_score",
        )
        normalized_style_fit_score = _normalize_int(style_fit_score, "style_fit_score")
        normalized_plan_readiness_score = _normalize_int(plan_readiness_score, "plan_readiness_score")
        normalized_recommendation = self._validate_evaluation_recommendation(recommendation)
        normalized_summary = _normalize_string(summary, "summary")
        normalized_strengths = _normalize_string_list(strengths, "strengths")
        normalized_risks = _normalize_string_list(risks, "risks")
        now = utc_now()

        with self._connect() as connection:
            existing_row = connection.execute(
                """
                SELECT
                    id,
                    pack_id,
                    evaluation_mode,
                    evaluator_name,
                    total_score,
                    hook_strength_score,
                    conflict_clarity_score,
                    relationship_tension_score,
                    reversal_expandability_score,
                    style_fit_score,
                    plan_readiness_score,
                    recommendation,
                    summary,
                    strengths_json,
                    risks_json,
                    created_at,
                    updated_at
                FROM idea_pack_evaluations
                WHERE pack_id = ? AND evaluation_mode = ? AND evaluator_name = ?
                """,
                (
                    normalized_pack_id,
                    normalized_evaluation_mode,
                    normalized_evaluator_name,
                ),
            ).fetchone()
            if existing_row is None:
                connection.execute(
                    """
                    INSERT INTO idea_pack_evaluations (
                        pack_id,
                        evaluation_mode,
                        evaluator_name,
                        total_score,
                        hook_strength_score,
                        conflict_clarity_score,
                        relationship_tension_score,
                        reversal_expandability_score,
                        style_fit_score,
                        plan_readiness_score,
                        recommendation,
                        summary,
                        strengths_json,
                        risks_json,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_pack_id,
                        normalized_evaluation_mode,
                        normalized_evaluator_name,
                        normalized_total_score,
                        normalized_hook_strength_score,
                        normalized_conflict_clarity_score,
                        normalized_relationship_tension_score,
                        normalized_reversal_expandability_score,
                        normalized_style_fit_score,
                        normalized_plan_readiness_score,
                        normalized_recommendation,
                        normalized_summary,
                        _json_dumps(normalized_strengths),
                        _json_dumps(normalized_risks),
                        now,
                        now,
                    ),
                )
                evaluation_id = int(connection.execute("SELECT last_insert_rowid()").fetchone()[0])
                status = "created"
            else:
                evaluation_id = int(existing_row["id"])
                connection.execute(
                    """
                    UPDATE idea_pack_evaluations
                    SET total_score = ?,
                        hook_strength_score = ?,
                        conflict_clarity_score = ?,
                        relationship_tension_score = ?,
                        reversal_expandability_score = ?,
                        style_fit_score = ?,
                        plan_readiness_score = ?,
                        recommendation = ?,
                        summary = ?,
                        strengths_json = ?,
                        risks_json = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        normalized_total_score,
                        normalized_hook_strength_score,
                        normalized_conflict_clarity_score,
                        normalized_relationship_tension_score,
                        normalized_reversal_expandability_score,
                        normalized_style_fit_score,
                        normalized_plan_readiness_score,
                        normalized_recommendation,
                        normalized_summary,
                        _json_dumps(normalized_strengths),
                        _json_dumps(normalized_risks),
                        now,
                        evaluation_id,
                    ),
                )
                status = "updated"

            stored_row = connection.execute(
                """
                SELECT
                    id,
                    pack_id,
                    evaluation_mode,
                    evaluator_name,
                    total_score,
                    hook_strength_score,
                    conflict_clarity_score,
                    relationship_tension_score,
                    reversal_expandability_score,
                    style_fit_score,
                    plan_readiness_score,
                    recommendation,
                    summary,
                    strengths_json,
                    risks_json,
                    created_at,
                    updated_at
                FROM idea_pack_evaluations
                WHERE id = ?
                """,
                (evaluation_id,),
            ).fetchone()

        return {"status": status, **self._row_to_evaluation(stored_row)}

    def list_idea_pack_evaluations(
        self,
        *,
        batch_id: int | None = None,
        pack_ids: list[int] | None = None,
        evaluation_mode: str | None = None,
        recommendation: str | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = []
        sql_lines = [
            "SELECT DISTINCT e.id, e.pack_id, e.evaluation_mode, e.evaluator_name, e.total_score, e.hook_strength_score, e.conflict_clarity_score,",
            "e.relationship_tension_score, e.reversal_expandability_score, e.style_fit_score, e.plan_readiness_score, e.recommendation,",
            "e.summary, e.strengths_json, e.risks_json, e.created_at, e.updated_at,",
            "p.style, p.generation_mode, p.provider_name, p.api_mode, p.model_name, p.model_config_key, p.pack_status, p.hook",
            "FROM idea_pack_evaluations e",
            "JOIN idea_packs p ON p.id = e.pack_id",
        ]
        if batch_id is not None:
            batch_id = _normalize_int(batch_id, "batch_id")
            sql_lines.append("JOIN idea_batch_cards bc ON bc.card_id = p.card_id")
            sql_lines.append("WHERE bc.batch_id = ?")
            params.append(batch_id)
        else:
            sql_lines.append("WHERE 1 = 1")

        if pack_ids is not None:
            pack_ids = _normalize_int_list(pack_ids, "pack_ids")
            placeholders = ", ".join("?" for _ in pack_ids)
            sql_lines.append(f"AND e.pack_id IN ({placeholders})")
            params.extend(pack_ids)

        if evaluation_mode is not None:
            sql_lines.append("AND e.evaluation_mode = ?")
            params.append(self._validate_evaluation_mode(evaluation_mode))

        if recommendation is not None:
            sql_lines.append("AND e.recommendation = ?")
            params.append(self._validate_evaluation_recommendation(recommendation))

        sql_lines.append("ORDER BY e.total_score DESC, e.id ASC")
        with self._connect() as connection:
            rows = connection.execute("\n".join(sql_lines), params).fetchall()
        return [self._row_to_evaluation(row) for row in rows]
