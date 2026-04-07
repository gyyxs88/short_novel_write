from __future__ import annotations

import argparse
from contextlib import closing
import json
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any

from tools.story_token_usage import normalize_token_usage


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE_DB_PATH = ROOT_DIR / "outputs" / "archive" / "archive.sqlite3"
DEFAULT_SOURCE_DB_NAME = "story_ideas.sqlite3"
DEFAULT_REPORT_NAME = "report.json"
ARCHIVE_FORMAT_VERSION = 1

SOURCE_TABLES = (
    "idea_card_batches",
    "idea_cards",
    "idea_batch_cards",
    "idea_packs",
    "idea_pack_evaluations",
    "story_plans",
    "story_payloads",
    "story_drafts",
)

ARCHIVE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS archive_jobs (
    job_id TEXT PRIMARY KEY,
    job_status TEXT NOT NULL,
    prompt TEXT NOT NULL,
    style TEXT NOT NULL,
    case_key TEXT NOT NULL,
    case_notes TEXT NOT NULL,
    run_dir TEXT NOT NULL,
    source_db_path TEXT NOT NULL,
    report_path TEXT NOT NULL,
    run_started_at TEXT NOT NULL,
    run_finished_at TEXT NOT NULL,
    wall_time_seconds REAL NOT NULL,
    total_token_usage_json TEXT NOT NULL,
    selected_card_id INTEGER,
    selected_pack_id INTEGER,
    selected_plan_id INTEGER,
    selected_payload_id INTEGER,
    selected_draft_id INTEGER,
    inspect_overall_ok INTEGER NOT NULL,
    inspect_summary_chars INTEGER NOT NULL,
    inspect_body_chars INTEGER NOT NULL,
    inspect_issues_json TEXT NOT NULL,
    report_json TEXT NOT NULL,
    archive_version INTEGER NOT NULL,
    archived_at TEXT NOT NULL,
    source_db_deleted INTEGER NOT NULL DEFAULT 0,
    source_db_deleted_at TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS archive_stage_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    case_key TEXT NOT NULL,
    stage_order INTEGER NOT NULL,
    stage_name TEXT NOT NULL,
    action_name TEXT NOT NULL,
    ok INTEGER NOT NULL,
    duration_seconds REAL NOT NULL,
    token_usage_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    error_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(job_id, case_key, stage_order)
);

CREATE INDEX IF NOT EXISTS idx_archive_stage_runs_job_id
    ON archive_stage_runs(job_id, case_key, stage_order);

CREATE TABLE IF NOT EXISTS archive_idea_card_batches (
    job_id TEXT NOT NULL,
    source_batch_id INTEGER NOT NULL,
    source_mode TEXT NOT NULL,
    seed TEXT NOT NULL,
    user_prompt TEXT NOT NULL,
    requested_count INTEGER NOT NULL,
    contains_selected_card INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_batch_id)
);

CREATE TABLE IF NOT EXISTS archive_idea_cards (
    job_id TEXT NOT NULL,
    source_card_id INTEGER NOT NULL,
    canonical_signature TEXT NOT NULL,
    card_status TEXT NOT NULL,
    types_json TEXT NOT NULL,
    main_tags_json TEXT NOT NULL,
    selected_flag INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_card_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_idea_cards_job_selected
    ON archive_idea_cards(job_id, selected_flag, source_card_id);

CREATE TABLE IF NOT EXISTS archive_idea_batch_cards (
    job_id TEXT NOT NULL,
    source_link_id INTEGER NOT NULL,
    source_batch_id INTEGER NOT NULL,
    source_card_id INTEGER NOT NULL,
    batch_item_index INTEGER NOT NULL,
    selected_flag INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_link_id)
);

CREATE TABLE IF NOT EXISTS archive_idea_packs (
    job_id TEXT NOT NULL,
    source_pack_id INTEGER NOT NULL,
    source_card_id INTEGER NOT NULL,
    source_mode TEXT NOT NULL,
    style TEXT NOT NULL,
    generation_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_config_key TEXT NOT NULL,
    pack_status TEXT NOT NULL,
    total_score INTEGER,
    recommendation TEXT NOT NULL,
    selected_flag INTEGER NOT NULL,
    token_usage_json TEXT NOT NULL,
    hook TEXT NOT NULL,
    main_conflict TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_pack_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_idea_packs_job_selected
    ON archive_idea_packs(job_id, selected_flag, source_pack_id);

CREATE TABLE IF NOT EXISTS archive_idea_pack_evaluations (
    job_id TEXT NOT NULL,
    source_evaluation_id INTEGER NOT NULL,
    source_pack_id INTEGER NOT NULL,
    evaluation_mode TEXT NOT NULL,
    evaluator_name TEXT NOT NULL,
    total_score INTEGER NOT NULL,
    recommendation TEXT NOT NULL,
    selected_flag INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_evaluation_id)
);

CREATE TABLE IF NOT EXISTS archive_story_plans (
    job_id TEXT NOT NULL,
    source_plan_id INTEGER NOT NULL,
    source_pack_id INTEGER NOT NULL,
    variant_index INTEGER NOT NULL,
    variant_key TEXT NOT NULL,
    variant_label TEXT NOT NULL,
    title TEXT NOT NULL,
    style TEXT NOT NULL,
    generation_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_config_key TEXT NOT NULL,
    plan_status TEXT NOT NULL,
    selected_flag INTEGER NOT NULL,
    token_usage_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_plan_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_story_plans_job_selected
    ON archive_story_plans(job_id, selected_flag, source_plan_id);

CREATE TABLE IF NOT EXISTS archive_story_payloads (
    job_id TEXT NOT NULL,
    source_payload_id INTEGER NOT NULL,
    source_plan_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    style TEXT NOT NULL,
    target_char_range_json TEXT NOT NULL,
    target_chapter_count INTEGER NOT NULL,
    selected_flag INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_payload_id)
);

CREATE TABLE IF NOT EXISTS archive_story_drafts (
    job_id TEXT NOT NULL,
    source_draft_id INTEGER NOT NULL,
    source_payload_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    generation_mode TEXT NOT NULL,
    provider_name TEXT NOT NULL,
    api_mode TEXT NOT NULL,
    model_name TEXT NOT NULL,
    model_config_key TEXT NOT NULL,
    body_char_count INTEGER NOT NULL,
    draft_status TEXT NOT NULL,
    selected_flag INTEGER NOT NULL,
    token_usage_json TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    record_json TEXT NOT NULL,
    PRIMARY KEY (job_id, source_draft_id)
);

CREATE INDEX IF NOT EXISTS idx_archive_story_drafts_job_selected
    ON archive_story_drafts(job_id, selected_flag, source_draft_id);
"""


class ArchiveError(Exception):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ArchiveError(f"未找到归档所需文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ArchiveError(f"归档文件不是合法 JSON：{path}") from exc
    if not isinstance(payload, dict):
        raise ArchiveError(f"归档文件必须是 JSON 对象：{path}")
    return payload


def _read_table_rows(db_path: Path, table_name: str) -> list[dict[str, Any]]:
    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(f"SELECT * FROM {table_name} ORDER BY id ASC").fetchall()
    return [dict(row) for row in rows]


def _read_source_snapshot(source_db_path: Path) -> dict[str, list[dict[str, Any]]]:
    if not source_db_path.exists():
        raise ArchiveError(f"未找到源业务库：{source_db_path}")
    return {table_name: _read_table_rows(source_db_path, table_name) for table_name in SOURCE_TABLES}


def _extract_primary_case(report: dict[str, Any]) -> dict[str, Any]:
    cases = report.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ArchiveError("report.json 缺少 cases，无法归档。")
    if len(cases) > 1:
        raise ArchiveError("当前归档器只支持单 job 单 case 的 report.json。")
    case = cases[0]
    if not isinstance(case, dict):
        raise ArchiveError("report.json 的 case 必须是对象。")
    return case


def _extract_stage_token_usage(stage: dict[str, Any]) -> dict[str, int]:
    summary = stage.get("summary", {})
    if isinstance(summary, dict) and "token_usage" in summary:
        return normalize_token_usage(summary.get("token_usage"))
    error = stage.get("error", {})
    if not isinstance(error, dict):
        return normalize_token_usage({})
    details = error.get("details", {})
    if not isinstance(details, dict):
        return normalize_token_usage({})
    return normalize_token_usage(details.get("token_usage", {}))


def _build_pack_evaluation_lookup(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    lookup: dict[int, dict[str, Any]] = {}
    for row in rows:
        pack_id = int(row["pack_id"])
        current = lookup.get(pack_id)
        if current is None or int(row.get("total_score", 0)) >= int(current.get("total_score", 0)):
            lookup[pack_id] = row
    return lookup


def _build_archive_payload(
    *,
    run_dir: Path,
    source_db_path: Path,
    report_path: Path,
    report: dict[str, Any],
    source_snapshot: dict[str, list[dict[str, Any]]],
    job_id: str,
) -> dict[str, Any]:
    case = _extract_primary_case(report)
    selected_pack_id = int(case.get("selected_pack", {}).get("pack_id") or 0) or None
    selected_plan_id = int(case.get("selected_plan", {}).get("plan_id") or 0) or None
    selected_payload_id = int(case.get("selected_payload", {}).get("payload_id") or 0) or None
    selected_draft_id = int(case.get("selected_draft", {}).get("draft_id") or 0) or None

    selected_card_id: int | None = None
    if selected_pack_id is not None:
        for pack_row in source_snapshot["idea_packs"]:
            if int(pack_row["id"]) == selected_pack_id:
                selected_card_id = int(pack_row["card_id"])
                break

    pack_evaluation_lookup = _build_pack_evaluation_lookup(source_snapshot["idea_pack_evaluations"])
    archived_at = utc_now()

    stage_rows = []
    for index, stage in enumerate(case.get("stages", []), start=1):
        if not isinstance(stage, dict):
            continue
        stage_rows.append(
            {
                "job_id": job_id,
                "case_key": str(case.get("sample_key", "") or ""),
                "stage_order": index,
                "stage_name": str(stage.get("stage", "") or ""),
                "action_name": str(stage.get("action", "") or ""),
                "ok": 1 if bool(stage.get("ok")) else 0,
                "duration_seconds": float(stage.get("duration_seconds", 0.0) or 0.0),
                "token_usage_json": _json_dumps(_extract_stage_token_usage(stage)),
                "summary_json": _json_dumps(stage.get("summary", {})),
                "error_json": _json_dumps(stage.get("error", {})),
                "created_at": archived_at,
            }
        )

    batch_rows = []
    for row in source_snapshot["idea_card_batches"]:
        batch_id = int(row["id"])
        contains_selected_card = 0
        if selected_card_id is not None:
            contains_selected_card = 1 if any(
                int(link_row["batch_id"]) == batch_id and int(link_row["card_id"]) == selected_card_id
                for link_row in source_snapshot["idea_batch_cards"]
            ) else 0
        batch_rows.append(
            {
                "job_id": job_id,
                "source_batch_id": batch_id,
                "source_mode": str(row.get("source_mode", "") or ""),
                "seed": str(row.get("seed", "") or ""),
                "user_prompt": str(row.get("user_prompt", "") or ""),
                "requested_count": int(row.get("requested_count", 0) or 0),
                "contains_selected_card": contains_selected_card,
                "created_at": str(row.get("created_at", "") or ""),
                "record_json": _json_dumps(row),
            }
        )

    card_rows = [
        {
            "job_id": job_id,
            "source_card_id": int(row["id"]),
            "canonical_signature": str(row.get("canonical_signature", "") or ""),
            "card_status": str(row.get("card_status", "") or ""),
            "types_json": str(row.get("types_json", "") or "[]"),
            "main_tags_json": str(row.get("main_tags_json", "") or "[]"),
            "selected_flag": 1 if selected_card_id is not None and int(row["id"]) == selected_card_id else 0,
            "created_at": str(row.get("created_at", "") or ""),
            "updated_at": str(row.get("updated_at", "") or ""),
            "record_json": _json_dumps(row),
        }
        for row in source_snapshot["idea_cards"]
    ]

    batch_card_rows = [
        {
            "job_id": job_id,
            "source_link_id": int(row["id"]),
            "source_batch_id": int(row["batch_id"]),
            "source_card_id": int(row["card_id"]),
            "batch_item_index": int(row["batch_item_index"]),
            "selected_flag": 1 if selected_card_id is not None and int(row["card_id"]) == selected_card_id else 0,
            "created_at": str(row.get("created_at", "") or ""),
            "record_json": _json_dumps(row),
        }
        for row in source_snapshot["idea_batch_cards"]
    ]

    pack_rows = []
    for row in source_snapshot["idea_packs"]:
        pack_id = int(row["id"])
        evaluation = pack_evaluation_lookup.get(pack_id)
        pack_rows.append(
            {
                "job_id": job_id,
                "source_pack_id": pack_id,
                "source_card_id": int(row["card_id"]),
                "source_mode": str(row.get("source_mode", "") or ""),
                "style": str(row.get("style", "") or ""),
                "generation_mode": str(row.get("generation_mode", "") or ""),
                "provider_name": str(row.get("provider_name", "") or ""),
                "api_mode": str(row.get("api_mode", "") or ""),
                "model_name": str(row.get("model_name", "") or ""),
                "model_config_key": str(row.get("model_config_key", "") or ""),
                "pack_status": str(row.get("pack_status", "") or ""),
                "total_score": int(evaluation["total_score"]) if evaluation is not None else None,
                "recommendation": str(evaluation.get("recommendation", "") or "") if evaluation is not None else "",
                "selected_flag": 1 if selected_pack_id is not None and pack_id == selected_pack_id else 0,
                "token_usage_json": str(row.get("token_usage_json") or _json_dumps(normalize_token_usage({}))),
                "hook": str(row.get("hook", "") or ""),
                "main_conflict": str(row.get("main_conflict", "") or ""),
                "created_at": str(row.get("created_at", "") or ""),
                "updated_at": str(row.get("updated_at", "") or ""),
                "record_json": _json_dumps(row),
            }
        )

    evaluation_rows = [
        {
            "job_id": job_id,
            "source_evaluation_id": int(row["id"]),
            "source_pack_id": int(row["pack_id"]),
            "evaluation_mode": str(row.get("evaluation_mode", "") or ""),
            "evaluator_name": str(row.get("evaluator_name", "") or ""),
            "total_score": int(row.get("total_score", 0) or 0),
            "recommendation": str(row.get("recommendation", "") or ""),
            "selected_flag": 1 if selected_pack_id is not None and int(row["pack_id"]) == selected_pack_id else 0,
            "created_at": str(row.get("created_at", "") or ""),
            "updated_at": str(row.get("updated_at", "") or ""),
            "record_json": _json_dumps(row),
        }
        for row in source_snapshot["idea_pack_evaluations"]
    ]

    plan_rows = [
        {
            "job_id": job_id,
            "source_plan_id": int(row["id"]),
            "source_pack_id": int(row["pack_id"]),
            "variant_index": int(row.get("variant_index", 0) or 0),
            "variant_key": str(row.get("variant_key", "") or ""),
            "variant_label": str(row.get("variant_label", "") or ""),
            "title": str(row.get("title", "") or ""),
            "style": str(row.get("style", "") or ""),
            "generation_mode": str(row.get("generation_mode", "") or ""),
            "provider_name": str(row.get("provider_name", "") or ""),
            "api_mode": str(row.get("api_mode", "") or ""),
            "model_name": str(row.get("model_name", "") or ""),
            "model_config_key": str(row.get("model_config_key", "") or ""),
            "plan_status": str(row.get("plan_status", "") or ""),
            "selected_flag": 1 if selected_plan_id is not None and int(row["id"]) == selected_plan_id else 0,
            "token_usage_json": str(row.get("token_usage_json") or _json_dumps(normalize_token_usage({}))),
            "created_at": str(row.get("created_at", "") or ""),
            "updated_at": str(row.get("updated_at", "") or ""),
            "record_json": _json_dumps(row),
        }
        for row in source_snapshot["story_plans"]
    ]

    payload_rows = [
        {
            "job_id": job_id,
            "source_payload_id": int(row["id"]),
            "source_plan_id": int(row["plan_id"]),
            "title": str(row.get("title", "") or ""),
            "style": str(row.get("style", "") or ""),
            "target_char_range_json": str(row.get("target_char_range_json", "") or "[]"),
            "target_chapter_count": int(row.get("target_chapter_count", 0) or 0),
            "selected_flag": 1 if selected_payload_id is not None and int(row["id"]) == selected_payload_id else 0,
            "created_at": str(row.get("created_at", "") or ""),
            "updated_at": str(row.get("updated_at", "") or ""),
            "record_json": _json_dumps(row),
        }
        for row in source_snapshot["story_payloads"]
    ]

    draft_rows = [
        {
            "job_id": job_id,
            "source_draft_id": int(row["id"]),
            "source_payload_id": int(row["payload_id"]),
            "title": str(row.get("title", "") or ""),
            "generation_mode": str(row.get("generation_mode", "") or ""),
            "provider_name": str(row.get("provider_name", "") or ""),
            "api_mode": str(row.get("api_mode", "") or ""),
            "model_name": str(row.get("model_name", "") or ""),
            "model_config_key": str(row.get("model_config_key", "") or ""),
            "body_char_count": int(row.get("body_char_count", 0) or 0),
            "draft_status": str(row.get("draft_status", "") or ""),
            "selected_flag": 1 if selected_draft_id is not None and int(row["id"]) == selected_draft_id else 0,
            "token_usage_json": str(row.get("token_usage_json") or _json_dumps(normalize_token_usage({}))),
            "summary_text": str(row.get("summary_text", "") or ""),
            "content_markdown": str(row.get("content_markdown", "") or ""),
            "created_at": str(row.get("created_at", "") or ""),
            "updated_at": str(row.get("updated_at", "") or ""),
            "record_json": _json_dumps(row),
        }
        for row in source_snapshot["story_drafts"]
    ]

    job_row = {
        "job_id": job_id,
        "job_status": str(case.get("status", "") or ""),
        "prompt": str(case.get("prompt", "") or ""),
        "style": str(case.get("style", "") or ""),
        "case_key": str(case.get("sample_key", "") or ""),
        "case_notes": str(case.get("notes", "") or ""),
        "run_dir": str(run_dir),
        "source_db_path": str(source_db_path),
        "report_path": str(report_path),
        "run_started_at": str(report.get("generated_at", "") or ""),
        "run_finished_at": str(report.get("generated_at", "") or ""),
        "wall_time_seconds": float(report.get("wall_time_seconds", 0.0) or 0.0),
        "total_token_usage_json": _json_dumps(normalize_token_usage(case.get("token_usage", {}))),
        "selected_card_id": selected_card_id,
        "selected_pack_id": selected_pack_id,
        "selected_plan_id": selected_plan_id,
        "selected_payload_id": selected_payload_id,
        "selected_draft_id": selected_draft_id,
        "inspect_overall_ok": 1 if bool(case.get("inspect", {}).get("overall_ok")) else 0,
        "inspect_summary_chars": int(case.get("inspect", {}).get("summary_chars", 0) or 0),
        "inspect_body_chars": int(case.get("inspect", {}).get("body_chars", 0) or 0),
        "inspect_issues_json": _json_dumps(case.get("inspect", {}).get("issues", [])),
        "report_json": _json_dumps(report),
        "archive_version": ARCHIVE_FORMAT_VERSION,
        "archived_at": archived_at,
        "source_db_deleted": 0,
        "source_db_deleted_at": "",
    }

    return {
        "job_row": job_row,
        "stage_rows": stage_rows,
        "batch_rows": batch_rows,
        "card_rows": card_rows,
        "batch_card_rows": batch_card_rows,
        "pack_rows": pack_rows,
        "evaluation_rows": evaluation_rows,
        "plan_rows": plan_rows,
        "payload_rows": payload_rows,
        "draft_rows": draft_rows,
        "selected_ids": {
            "card_id": selected_card_id,
            "pack_id": selected_pack_id,
            "plan_id": selected_plan_id,
            "payload_id": selected_payload_id,
            "draft_id": selected_draft_id,
        },
        "counts": {
            "idea_card_batches": len(batch_rows),
            "idea_cards": len(card_rows),
            "idea_batch_cards": len(batch_card_rows),
            "idea_packs": len(pack_rows),
            "idea_pack_evaluations": len(evaluation_rows),
            "story_plans": len(plan_rows),
            "story_payloads": len(payload_rows),
            "story_drafts": len(draft_rows),
            "stage_runs": len(stage_rows),
        },
    }


class StoryArchiveStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_ARCHIVE_DB_PATH
        self.initialize()

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            with connection:
                connection.executescript(ARCHIVE_SCHEMA_SQL)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def archive_payload(self, archive_payload: dict[str, Any]) -> None:
        job_id = archive_payload["job_row"]["job_id"]
        with closing(self._connect()) as connection:
            with connection:
                self._delete_existing_job(connection, job_id)
                self._insert_job(connection, archive_payload["job_row"])
                self._insert_stage_rows(connection, archive_payload["stage_rows"])
                self._insert_table_rows(connection, "archive_idea_card_batches", archive_payload["batch_rows"])
                self._insert_table_rows(connection, "archive_idea_cards", archive_payload["card_rows"])
                self._insert_table_rows(connection, "archive_idea_batch_cards", archive_payload["batch_card_rows"])
                self._insert_table_rows(connection, "archive_idea_packs", archive_payload["pack_rows"])
                self._insert_table_rows(connection, "archive_idea_pack_evaluations", archive_payload["evaluation_rows"])
                self._insert_table_rows(connection, "archive_story_plans", archive_payload["plan_rows"])
                self._insert_table_rows(connection, "archive_story_payloads", archive_payload["payload_rows"])
                self._insert_table_rows(connection, "archive_story_drafts", archive_payload["draft_rows"])

    def mark_source_db_deleted(self, job_id: str, *, deleted_at: str) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    UPDATE archive_jobs
                    SET source_db_deleted = 1,
                        source_db_deleted_at = ?
                    WHERE job_id = ?
                    """,
                    (deleted_at, job_id),
                )

    def validate_job(
        self,
        *,
        job_id: str,
        expected_counts: dict[str, int],
        selected_ids: dict[str, int | None],
    ) -> None:
        issues: list[str] = []
        with closing(self._connect()) as connection:
            job_row = connection.execute(
                "SELECT job_id FROM archive_jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if job_row is None:
                issues.append("archive_jobs 中未找到 job 记录。")

            table_to_name = {
                "archive_idea_card_batches": "idea_card_batches",
                "archive_idea_cards": "idea_cards",
                "archive_idea_batch_cards": "idea_batch_cards",
                "archive_idea_packs": "idea_packs",
                "archive_idea_pack_evaluations": "idea_pack_evaluations",
                "archive_story_plans": "story_plans",
                "archive_story_payloads": "story_payloads",
                "archive_story_drafts": "story_drafts",
                "archive_stage_runs": "stage_runs",
            }
            for table_name, expected_key in table_to_name.items():
                actual_count = int(
                    connection.execute(
                        f"SELECT COUNT(*) FROM {table_name} WHERE job_id = ?",
                        (job_id,),
                    ).fetchone()[0]
                )
                if actual_count != expected_counts[expected_key]:
                    issues.append(
                        f"{table_name} 记录数不匹配：期望 {expected_counts[expected_key]}，实际 {actual_count}。"
                    )

            if selected_ids.get("pack_id") is not None:
                row = connection.execute(
                    """
                    SELECT source_pack_id
                    FROM archive_idea_packs
                    WHERE job_id = ? AND source_pack_id = ? AND selected_flag = 1
                    """,
                    (job_id, selected_ids["pack_id"]),
                ).fetchone()
                if row is None:
                    issues.append("未找到被选中的 archive_idea_packs 记录。")

            if selected_ids.get("plan_id") is not None:
                row = connection.execute(
                    """
                    SELECT source_plan_id
                    FROM archive_story_plans
                    WHERE job_id = ? AND source_plan_id = ? AND selected_flag = 1
                    """,
                    (job_id, selected_ids["plan_id"]),
                ).fetchone()
                if row is None:
                    issues.append("未找到被选中的 archive_story_plans 记录。")

            if selected_ids.get("payload_id") is not None:
                row = connection.execute(
                    """
                    SELECT source_payload_id
                    FROM archive_story_payloads
                    WHERE job_id = ? AND source_payload_id = ? AND selected_flag = 1
                    """,
                    (job_id, selected_ids["payload_id"]),
                ).fetchone()
                if row is None:
                    issues.append("未找到被选中的 archive_story_payloads 记录。")

            if selected_ids.get("draft_id") is not None:
                row = connection.execute(
                    """
                    SELECT source_draft_id, content_markdown
                    FROM archive_story_drafts
                    WHERE job_id = ? AND source_draft_id = ? AND selected_flag = 1
                    """,
                    (job_id, selected_ids["draft_id"]),
                ).fetchone()
                if row is None:
                    issues.append("未找到被选中的 archive_story_drafts 记录。")
                elif not isinstance(row["content_markdown"], str) or not row["content_markdown"].strip():
                    issues.append("被选中的 archive_story_drafts 缺少 content_markdown。")

        if issues:
            raise ArchiveError("归档校验失败：" + "；".join(issues))

    def _delete_existing_job(self, connection: sqlite3.Connection, job_id: str) -> None:
        for table_name in (
            "archive_stage_runs",
            "archive_idea_card_batches",
            "archive_idea_cards",
            "archive_idea_batch_cards",
            "archive_idea_packs",
            "archive_idea_pack_evaluations",
            "archive_story_plans",
            "archive_story_payloads",
            "archive_story_drafts",
            "archive_jobs",
        ):
            connection.execute(f"DELETE FROM {table_name} WHERE job_id = ?", (job_id,))

    def _insert_job(self, connection: sqlite3.Connection, row: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO archive_jobs (
                job_id, job_status, prompt, style, case_key, case_notes, run_dir, source_db_path,
                report_path, run_started_at, run_finished_at, wall_time_seconds, total_token_usage_json,
                selected_card_id, selected_pack_id, selected_plan_id, selected_payload_id, selected_draft_id,
                inspect_overall_ok, inspect_summary_chars, inspect_body_chars, inspect_issues_json,
                report_json, archive_version, archived_at, source_db_deleted, source_db_deleted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["job_id"],
                row["job_status"],
                row["prompt"],
                row["style"],
                row["case_key"],
                row["case_notes"],
                row["run_dir"],
                row["source_db_path"],
                row["report_path"],
                row["run_started_at"],
                row["run_finished_at"],
                row["wall_time_seconds"],
                row["total_token_usage_json"],
                row["selected_card_id"],
                row["selected_pack_id"],
                row["selected_plan_id"],
                row["selected_payload_id"],
                row["selected_draft_id"],
                row["inspect_overall_ok"],
                row["inspect_summary_chars"],
                row["inspect_body_chars"],
                row["inspect_issues_json"],
                row["report_json"],
                row["archive_version"],
                row["archived_at"],
                row["source_db_deleted"],
                row["source_db_deleted_at"],
            ),
        )

    def _insert_stage_rows(self, connection: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            connection.execute(
                """
                INSERT INTO archive_stage_runs (
                    job_id, case_key, stage_order, stage_name, action_name, ok, duration_seconds,
                    token_usage_json, summary_json, error_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["job_id"],
                    row["case_key"],
                    row["stage_order"],
                    row["stage_name"],
                    row["action_name"],
                    row["ok"],
                    row["duration_seconds"],
                    row["token_usage_json"],
                    row["summary_json"],
                    row["error_json"],
                    row["created_at"],
                ),
            )

    def _insert_table_rows(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        rows: list[dict[str, Any]],
    ) -> None:
        if not rows:
            return
        columns = list(rows[0].keys())
        placeholders = ", ".join("?" for _ in columns)
        sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        for row in rows:
            connection.execute(sql, tuple(row[column] for column in columns))


def archive_run(
    *,
    run_dir: str | Path,
    archive_db_path: str | Path | None = None,
    job_id: str | None = None,
    delete_source_db: bool = False,
    source_db_name: str = DEFAULT_SOURCE_DB_NAME,
    report_name: str = DEFAULT_REPORT_NAME,
) -> dict[str, Any]:
    resolved_run_dir = Path(run_dir)
    resolved_job_id = job_id.strip() if isinstance(job_id, str) and job_id.strip() else resolved_run_dir.name
    source_db_path = resolved_run_dir / source_db_name
    report_path = resolved_run_dir / report_name
    report = _read_json_file(report_path)
    source_snapshot = _read_source_snapshot(source_db_path)
    archive_payload = _build_archive_payload(
        run_dir=resolved_run_dir,
        source_db_path=source_db_path,
        report_path=report_path,
        report=report,
        source_snapshot=source_snapshot,
        job_id=resolved_job_id,
    )
    archive_store = StoryArchiveStore(archive_db_path)
    archive_store.archive_payload(archive_payload)
    archive_store.validate_job(
        job_id=resolved_job_id,
        expected_counts=archive_payload["counts"],
        selected_ids=archive_payload["selected_ids"],
    )

    source_db_deleted = False
    if delete_source_db:
        source_db_path.unlink()
        archive_store.mark_source_db_deleted(resolved_job_id, deleted_at=utc_now())
        source_db_deleted = True

    return {
        "job_id": resolved_job_id,
        "archive_db_path": str(archive_store.db_path),
        "run_dir": str(resolved_run_dir),
        "report_path": str(report_path),
        "source_db_path": str(source_db_path),
        "source_db_deleted": source_db_deleted,
        "counts": archive_payload["counts"],
        "selected_ids": archive_payload["selected_ids"],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把单 job 运行库归档到 archive.sqlite3。")
    parser.add_argument("--run-dir", required=True, help="任务运行目录，需包含 story_ideas.sqlite3 和 report.json。")
    parser.add_argument("--archive-db", default=str(DEFAULT_ARCHIVE_DB_PATH), help="归档库路径。")
    parser.add_argument("--job-id", default="", help="归档 job_id，默认使用 run_dir 目录名。")
    parser.add_argument("--delete-source-db", action="store_true", help="归档成功后删除源业务库。")
    parser.add_argument("--source-db-name", default=DEFAULT_SOURCE_DB_NAME, help="源业务库文件名。")
    parser.add_argument("--report-name", default=DEFAULT_REPORT_NAME, help="报告文件名。")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        result = archive_run(
            run_dir=args.run_dir,
            archive_db_path=args.archive_db,
            job_id=args.job_id,
            delete_source_db=args.delete_source_db,
            source_db_name=args.source_db_name,
            report_name=args.report_name,
        )
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": {"message": str(exc)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
