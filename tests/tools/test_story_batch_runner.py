from __future__ import annotations

import json
from pathlib import Path
import threading
import time

from tools.story_batch_runner import (
    initialize_run_database,
    load_batch_jobs,
    run_batch_jobs,
)
from tools.story_regression_samples import (
    DraftPostprocessConfig,
    GenerationRoute,
    RegressionSample,
    build_default_draft_postprocess,
)


def build_sample(job_id: str, *, style: str = "zhihu") -> RegressionSample:
    return RegressionSample(
        sample_key=job_id,
        style=style,
        prompt=f"{job_id} prompt",
        idea_pack_route=GenerationRoute(),
        plan_route=GenerationRoute(),
        draft_route=GenerationRoute(),
        draft_postprocess=build_default_draft_postprocess(style),
        target_char_range=(3000, 5000),
        target_chapter_count=4,
        candidate_count=2,
        plan_count=2,
    )


def build_success_response(action: str, data: dict) -> dict:
    return {
        "ok": True,
        "action": action,
        "data": data,
    }


def build_fake_invoker():
    batch_to_prompt: dict[int, str] = {}
    payload_to_prompt: dict[int, str] = {}
    store_counter = {"value": 0}

    def invoke(action: str, payload: dict) -> dict:
        if action == "match_idea_cards":
            return build_success_response(
                action,
                {
                    "count": 1,
                    "items": [
                        {
                            "id": 1,
                            "types": ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                            "main_tags": ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
                        }
                    ],
                },
            )

        if action == "store_idea_cards":
            store_counter["value"] += 1
            batch_id = store_counter["value"]
            batch_to_prompt[batch_id] = payload["user_prompt"]
            return build_success_response(
                action,
                {
                    "batch_id": batch_id,
                    "new_card_count": 1,
                    "existing_card_count": 0,
                },
            )

        if action == "build_idea_packs":
            batch_id = payload["batch_id"]
            pack_id = batch_id * 100 + 1
            return build_success_response(
                action,
                {
                    "generation_mode": payload["generation_mode"],
                    "created_count": 1,
                    "existing_count": 0,
                    "token_usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                    "items": [{"pack_id": pack_id}],
                },
            )

        if action == "evaluate_idea_packs":
            batch_id = payload["batch_id"]
            return build_success_response(
                action,
                {
                    "created_count": 1,
                    "updated_count": 0,
                    "recommendation_counts": {"shortlist": 1},
                    "items": [
                        {
                            "pack_id": batch_id * 100 + 1,
                            "total_score": 44,
                            "recommendation": "shortlist",
                        }
                    ],
                },
            )

        if action == "build_story_plans":
            pack_id = payload["pack_ids"][0]
            plan_id = pack_id * 10 + 1
            return build_success_response(
                action,
                {
                    "generation_mode": payload["generation_mode"],
                    "created_count": 1,
                    "existing_count": 0,
                    "token_usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
                    "items": [
                        {
                            "plan_id": plan_id,
                            "variant_index": 1,
                            "title": f"方案-{pack_id}",
                        }
                    ],
                },
            )

        if action == "build_story_payloads":
            plan_id = payload["plan_ids"][0]
            payload_id = plan_id * 10 + 1
            prompt = next(
                prompt
                for batch_id, prompt in batch_to_prompt.items()
                if batch_id * 100 + 1 == (plan_id - 1) // 10
            )
            payload_to_prompt[payload_id] = prompt
            return build_success_response(
                action,
                {
                    "created_count": 1,
                    "existing_count": 0,
                    "items": [
                        {
                            "payload_id": payload_id,
                            "plan_id": plan_id,
                            "title": f"Payload-{plan_id}",
                        }
                    ],
                },
            )

        if action == "build_story_drafts":
            payload_id = payload["payload_ids"][0]
            prompt = payload_to_prompt[payload_id]
            auto_revise = bool(payload.get("auto_revise", False))
            return build_success_response(
                action,
                {
                    "generation_mode": payload["generation_mode"],
                    "created_count": 1,
                    "existing_count": 0,
                    "auto_revise": auto_revise,
                    "auto_revised_count": 1 if auto_revise else 0,
                    "token_usage": {"prompt_tokens": 40, "completion_tokens": 60, "total_tokens": 100},
                    "items": [
                        {
                            "draft_id": payload_id * 10 + 1,
                            "prompt": prompt,
                            "auto_revised": auto_revise,
                            "revision_round_count": 1 if auto_revise else 0,
                            "content_changed": auto_revise,
                            "body_char_count_before_revision": 6100,
                            "body_char_count_after_revision": 6200,
                            "body_char_count_delta": 100 if auto_revise else 0,
                        }
                    ],
                },
            )

        if action == "list_story_drafts":
            payload_id = payload["payload_ids"][0]
            return build_success_response(
                action,
                {
                    "count": 1,
                    "items": [
                        {
                            "draft_id": payload_id * 10 + 1,
                            "payload_id": payload_id,
                            "generation_mode": payload["generation_mode"],
                            "title": f"Draft-{payload_id}",
                            "body_char_count": 6200,
                            "content_markdown": "# 标题\n\n## 简介\n这是一段合格简介。\n\n## 正文\n### 1\n正文内容足够长。",
                        }
                    ],
                },
            )

        if action == "inspect":
            return build_success_response(
                action,
                {
                    "overall_ok": True,
                    "structure": {
                        "summary_chars": 80,
                        "body_chars": 6200,
                        "issues": [],
                    },
                    "quality": {
                        "issues": [],
                    },
                },
            )

        raise AssertionError(f"未处理的 action: {action}")

    return invoke


def test_initialize_run_database_copies_template_db(tmp_path: Path) -> None:
    template_db_path = tmp_path / "template.sqlite3"
    template_db_path.write_bytes(b"demo-template")
    target_db_path = tmp_path / "run" / "story_ideas.sqlite3"

    initialize_run_database(
        db_path=target_db_path,
        template_db_path=template_db_path,
    )

    assert target_db_path.read_bytes() == b"demo-template"


def test_load_batch_jobs_rejects_duplicate_job_ids(tmp_path: Path) -> None:
    job_file_path = tmp_path / "jobs.json"
    job_file_path.write_text(
        json.dumps(
            [
                {"job_id": "job-1", "style": "zhihu", "prompt": "prompt-1"},
                {"job_id": "job-1", "style": "zhihu", "prompt": "prompt-2"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        load_batch_jobs(job_file_path)
    except ValueError as exc:
        assert "job_id 不能重复" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("预期应抛出重复 job_id 错误。")


def test_load_batch_jobs_accepts_utf8_bom_json(tmp_path: Path) -> None:
    job_file_path = tmp_path / "jobs_bom.json"
    job_file_path.write_text(
        json.dumps(
            [
                {"job_id": "job-bom", "style": "zhihu", "prompt": "prompt-bom"},
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )

    jobs = load_batch_jobs(job_file_path)

    assert len(jobs) == 1
    assert jobs[0].sample_key == "job-bom"
    assert jobs[0].draft_postprocess.auto_revise is True
    assert jobs[0].draft_postprocess.revision_profile_name == "zhihu_tight_hook"


def test_load_batch_jobs_can_disable_draft_postprocess(tmp_path: Path) -> None:
    job_file_path = tmp_path / "jobs_disable_postprocess.json"
    job_file_path.write_text(
        json.dumps(
            [
                {
                    "job_id": "job-no-revise",
                    "style": "douban",
                    "prompt": "prompt-disable",
                    "draft_postprocess": {
                        "auto_revise": False,
                    },
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    jobs = load_batch_jobs(job_file_path)

    assert len(jobs) == 1
    assert jobs[0].draft_postprocess == DraftPostprocessConfig(auto_revise=False)


def test_load_batch_jobs_rejects_invalid_plan_count_early(tmp_path: Path) -> None:
    job_file_path = tmp_path / "jobs_invalid_plan_count.json"
    job_file_path.write_text(
        json.dumps(
            [
                {
                    "job_id": "job-invalid-plan",
                    "style": "zhihu",
                    "prompt": "prompt-invalid-plan",
                    "plan_count": 2,
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    try:
        load_batch_jobs(job_file_path)
    except ValueError as exc:
        assert "plan_count" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("预期应抛出非法 plan_count 错误。")


def test_run_batch_jobs_archives_serially_and_writes_reports(tmp_path: Path) -> None:
    jobs = [build_sample("job-alpha"), build_sample("job-beta")]
    archive_state = {
        "active": 0,
        "max_active": 0,
        "calls": [],
    }
    archive_lock = threading.Lock()

    def fake_archive_job_fn(**kwargs) -> dict:
        with archive_lock:
            archive_state["active"] += 1
            archive_state["max_active"] = max(archive_state["max_active"], archive_state["active"])
        time.sleep(0.05)
        with archive_lock:
            archive_state["calls"].append(kwargs["job_id"])
            archive_state["active"] -= 1
        return {
            "job_id": kwargs["job_id"],
            "archive_db_path": str(kwargs["archive_db_path"]),
            "source_db_deleted": kwargs["delete_source_db"],
            "counts": {"story_drafts": 1},
            "selected_ids": {"draft_id": 1},
        }

    report = run_batch_jobs(
        jobs=jobs,
        output_root=tmp_path,
        run_name="batch-demo",
        archive_db_path=tmp_path / "archive.sqlite3",
        max_workers=2,
        delete_source_db=True,
        invoke_action=build_fake_invoker(),
        archive_job_fn=fake_archive_job_fn,
    )

    assert report["summary"]["job_count"] == 2
    assert report["summary"]["passed_count"] == 2
    assert report["summary"]["archived_count"] == 2
    assert report["summary"]["archive_failed_count"] == 0
    assert report["summary"]["auto_revised_job_count"] == 2
    assert report["summary"]["draft_changed_job_count"] == 2
    assert report["summary"]["revision_round_count_total"] == 2
    assert report["summary"]["revision_round_count_avg"] == 1.0
    assert report["summary"]["selected_draft_body_char_delta_total"] == 200
    assert report["summary"]["selected_draft_body_char_change_total"] == 200
    assert report["summary"]["token_usage"] == {
        "prompt_tokens": 140,
        "completion_tokens": 190,
        "total_tokens": 330,
    }
    assert Path(report["json_report_path"]).exists() is True
    assert Path(report["markdown_report_path"]).exists() is True
    assert archive_state["max_active"] == 1
    assert set(archive_state["calls"]) == {"job-alpha", "job-beta"}

    first_job = report["jobs"][0]
    assert Path(first_job["report_json_path"]).exists() is True
    assert Path(first_job["report_markdown_path"]).exists() is True
    assert first_job["archive"]["status"] == "archived"
    assert first_job["archive"]["source_db_deleted"] is True
    assert first_job["selected_draft"]["auto_revised"] is True
    assert first_job["selected_draft"]["revision_round_count"] == 1
    assert first_job["selected_draft"]["content_changed"] is True
    assert first_job["selected_draft"]["body_char_count_before_revision"] == 6100
    assert first_job["selected_draft"]["body_char_count_after_revision"] == 6200
    assert first_job["selected_draft"]["body_char_count_delta"] == 100
