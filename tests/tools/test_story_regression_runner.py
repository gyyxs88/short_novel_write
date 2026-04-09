from __future__ import annotations

import json
from pathlib import Path

from tools.story_regression_runner import run_regression, run_single_sample
from tools.story_regression_samples import (
    DraftPostprocessConfig,
    GenerationRoute,
    RegressionSample,
    select_builtin_samples,
)


def build_success_response(action: str, data: dict) -> dict:
    return {
        "ok": True,
        "action": action,
        "data": data,
    }


def build_error_response(action: str, code: str, message: str, details: dict | None = None) -> dict:
    return {
        "ok": False,
        "action": action,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


def build_sample(
    sample_key: str,
    *,
    style: str = "zhihu",
    draft_postprocess: DraftPostprocessConfig | None = None,
) -> RegressionSample:
    llm_environment = f"{style}_plan_default"
    draft_environment = f"{style}_draft_default"
    return RegressionSample(
        sample_key=sample_key,
        style=style,
        prompt=f"{sample_key} prompt",
        idea_pack_route=GenerationRoute(),
        plan_route=GenerationRoute(generation_mode="llm", llm_environment=llm_environment),
        draft_route=GenerationRoute(generation_mode="llm", llm_environment=draft_environment),
        draft_postprocess=draft_postprocess or DraftPostprocessConfig(),
    )


def build_fake_invoker(*, fail_prompts: set[str] | None = None):
    fail_prompts = fail_prompts or set()
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
            if prompt in fail_prompts:
                return build_error_response(
                    action,
                    "UPSTREAM_ERROR",
                    "未预期异常：The read operation timed out",
                    {"token_usage": {"prompt_tokens": 40, "completion_tokens": 0, "total_tokens": 40}},
                )
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


def test_select_builtin_samples_supports_set_and_style_filters() -> None:
    samples = select_builtin_samples(sample_set="verified", styles=["zhihu"])

    assert len(samples) == 2
    assert all(sample.style == "zhihu" for sample in samples)
    assert {sample.sample_key for sample in samples} == {
        "zhihu_wedding_sms",
        "zhihu_divorce_notice",
    }


def test_run_regression_writes_reports_and_counts_timeout_failures(tmp_path: Path) -> None:
    first = build_sample(
        "sample-pass",
        draft_postprocess=DraftPostprocessConfig(
            auto_revise=True,
            revision_profile_name="zhihu_tight_hook",
        ),
    )
    second = build_sample("sample-timeout")
    report = run_regression(
        samples=[first, second],
        output_root=tmp_path,
        run_name="regression-demo",
        sample_set="test",
        invoke_action=build_fake_invoker(fail_prompts={"sample-timeout prompt"}),
    )

    assert report["summary"]["sample_count"] == 2
    assert report["summary"]["passed_count"] == 1
    assert report["summary"]["failed_count"] == 1
    assert report["summary"]["failure_type_counts"] == {"timeout": 1}
    assert report["summary"]["stage_failure_counts"] == {"build_story_drafts": 1}
    assert report["summary"]["auto_revised_job_count"] == 1
    assert report["summary"]["draft_changed_job_count"] == 1
    assert report["summary"]["revision_round_count_total"] == 1
    assert report["summary"]["revision_round_count_avg"] == 1.0
    assert report["summary"]["selected_draft_body_char_delta_total"] == 100
    assert report["summary"]["selected_draft_body_char_change_total"] == 100
    assert report["summary"]["token_usage"] == {"prompt_tokens": 140, "completion_tokens": 130, "total_tokens": 270}
    assert Path(report["json_report_path"]).exists()
    assert Path(report["markdown_report_path"]).exists()

    json_report = json.loads(Path(report["json_report_path"]).read_text(encoding="utf-8"))
    assert json_report["summary"]["failed_count"] == 1
    markdown_report = Path(report["markdown_report_path"]).read_text(encoding="utf-8")
    assert "sample-timeout" in markdown_report
    assert "build_story_drafts" in markdown_report


def test_run_single_sample_marks_inspect_length_failure(tmp_path: Path) -> None:
    sample = build_sample("inspect-failed")
    base_invoke = build_fake_invoker()

    def invoke(action: str, payload: dict) -> dict:
        if action == "inspect":
            return build_success_response(
                action,
                {
                    "overall_ok": False,
                    "structure": {
                        "summary_chars": 180,
                        "body_chars": 3200,
                        "issues": ["正文总字数不符合要求。", "简介字数不符合要求。"],
                    },
                    "quality": {"issues": []},
                },
            )
        return base_invoke(action, payload)

    result = run_single_sample(
        sample=sample,
        db_path=tmp_path / "story.sqlite3",
        invoke_action=invoke,
    )

    assert result["status"] == "failed"
    assert result["final_stage"] == "inspect"
    assert result["failure_type"] == "length_constraint"
    assert result["stages"][-1]["error"]["code"] == "INSPECT_NOT_PASSABLE"
    assert result["token_usage"] == {"prompt_tokens": 70, "completion_tokens": 95, "total_tokens": 165}


def test_run_single_sample_passes_auto_revise_payload_and_records_postprocess(tmp_path: Path) -> None:
    sample = build_sample(
        "auto-revise",
        draft_postprocess=DraftPostprocessConfig(
            auto_revise=True,
            revision_profile_name="zhihu_tight_hook",
            revision_modes=("remove_ai_phrases", "compress_exposition"),
            revision_max_rounds=2,
            revision_max_spans_per_round=2,
        ),
    )
    captured_build_draft_payloads: list[dict] = []
    base_invoke = build_fake_invoker()

    def invoke(action: str, payload: dict) -> dict:
        if action == "build_story_drafts":
            captured_build_draft_payloads.append(payload)
        return base_invoke(action, payload)

    result = run_single_sample(
        sample=sample,
        db_path=tmp_path / "story.sqlite3",
        invoke_action=invoke,
    )

    assert result["status"] == "passed"
    assert captured_build_draft_payloads
    assert captured_build_draft_payloads[0]["auto_revise"] is True
    assert captured_build_draft_payloads[0]["revision_profile_name"] == "zhihu_tight_hook"
    assert captured_build_draft_payloads[0]["revision_modes"] == ["remove_ai_phrases", "compress_exposition"]
    assert result["route"]["draft_postprocess"]["auto_revise"] is True
    assert result["selected_draft"]["auto_revised"] is True
    assert result["selected_draft"]["revision_round_count"] == 1
    assert result["selected_draft"]["content_changed"] is True
    assert result["selected_draft"]["body_char_count_before_revision"] == 6100
    assert result["selected_draft"]["body_char_count_after_revision"] == 6200
    assert result["selected_draft"]["body_char_count_delta"] == 100
