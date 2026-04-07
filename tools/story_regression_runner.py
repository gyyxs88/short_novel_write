from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools import story_cli
from tools.story_regression_samples import (
    RegressionSample,
    get_sample_set_names,
    select_builtin_samples,
)
from tools.story_token_usage import (
    build_empty_token_usage,
    has_token_usage,
    merge_token_usages,
    normalize_token_usage,
)


DEFAULT_OUTPUT_ROOT = ROOT_DIR / "outputs" / "regression"
SUMMARY_CHAR_RANGE = [50, 120]
RECOMMENDATION_PRIORITY = {
    "priority_select": 3,
    "shortlist": 2,
    "rework": 1,
}
ActionInvoker = Callable[[str, dict[str, Any]], dict[str, Any]]


def invoke_story_action(action: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        data = story_cli.dispatch_action(action, payload)
        return story_cli.build_success_response(action, data)
    except story_cli.CliRequestError as exc:
        return story_cli.build_error_response(exc.code, exc.message, exc.action or action, exc.details)
    except Exception as exc:  # pragma: no cover - 兜底分支
        return story_cli.build_error_response(
            "INTERNAL_ERROR",
            f"未预期异常：{exc}",
            action,
        )


def parse_csv_filter(raw_value: str | None) -> list[str] | None:
    if raw_value is None:
        return None
    items = [item.strip() for item in raw_value.split(",") if item.strip()]
    return items or None


def build_route_summary(sample: RegressionSample) -> dict[str, Any]:
    return {
        "idea_pack": sample.idea_pack_route.to_action_payload(),
        "plan": sample.plan_route.to_action_payload(),
        "draft": sample.draft_route.to_action_payload(),
    }


def summarize_action_data(action: str, data: dict[str, Any]) -> dict[str, Any]:
    if action == "match_idea_cards":
        items = data.get("items", [])
        return {
            "count": data.get("count", len(items)),
            "top_item_ids": [item.get("id") for item in items[:3]],
        }
    if action == "store_idea_cards":
        return {
            "batch_id": data.get("batch_id"),
            "new_card_count": data.get("new_card_count"),
            "existing_card_count": data.get("existing_card_count"),
        }
    if action in {"build_idea_packs", "build_story_plans", "build_story_payloads", "build_story_drafts"}:
        summary = {
            "generation_mode": data.get("generation_mode", ""),
            "created_count": data.get("created_count"),
            "existing_count": data.get("existing_count"),
            "item_count": len(data.get("items", [])),
        }
        token_usage = normalize_token_usage(data.get("token_usage", {}))
        if has_token_usage(token_usage):
            summary["token_usage"] = token_usage
        return summary
    if action == "evaluate_idea_packs":
        return {
            "created_count": data.get("created_count"),
            "updated_count": data.get("updated_count"),
            "recommendation_counts": data.get("recommendation_counts", {}),
        }
    if action == "list_story_drafts":
        items = data.get("items", [])
        first_item = items[0] if items else {}
        return {
            "count": data.get("count", len(items)),
            "draft_ids": [item.get("draft_id") for item in items[:3]],
            "body_char_count": first_item.get("body_char_count"),
        }
    if action == "inspect":
        structure = data.get("structure", {})
        quality = data.get("quality", {})
        return {
            "overall_ok": data.get("overall_ok"),
            "summary_chars": structure.get("summary_chars"),
            "body_chars": structure.get("body_chars"),
            "structure_issue_count": len(structure.get("issues", [])),
            "quality_issue_count": len(quality.get("issues", [])),
        }
    return {"keys": sorted(data.keys())}


def classify_failure(
    *,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> str:
    normalized_code = (code or "").strip().lower()
    detail_text = json.dumps(details or {}, ensure_ascii=False)
    combined = f"{normalized_code} {message or ''} {detail_text}".lower()
    if "timeout" in combined or "timed out" in combined or "超时" in combined:
        return "timeout"
    if "json" in combined or "不是合法 json" in combined or "bad json" in combined:
        return "invalid_json"
    if (
        "environment_name" in combined
        or "model_key" in combined
        or "llm_config" in combined
        or "环境配置" in combined
        or "模型配置" in combined
        or "供应商配置" in combined
    ):
        return "missing_config"
    if "字数" in combined or "summary_chars" in combined or "简介" in combined:
        return "length_constraint"
    if normalized_code == "missing_config":
        return "missing_config"
    if normalized_code == "agent_fallback_required":
        return "agent_fallback_required"
    if normalized_code == "upstream_error":
        return "upstream_error"
    if normalized_code == "invalid_request":
        return "invalid_request"
    if normalized_code == "file_not_found":
        return "file_not_found"
    if normalized_code == "internal_error":
        return "internal_error"
    return "other"


def classify_inspect_failure(inspect_data: dict[str, Any]) -> tuple[str, list[str]]:
    structure = inspect_data.get("structure", {})
    quality = inspect_data.get("quality", {})
    issues = [str(item) for item in structure.get("issues", []) + quality.get("issues", [])]
    if not issues:
        return "inspect_failed", issues
    joined = " ".join(issues)
    if "字数" in joined or "简介" in joined:
        return "length_constraint", issues
    if structure.get("issues") and quality.get("issues"):
        return "inspect_mixed", issues
    if structure.get("issues"):
        return "inspect_structure", issues
    return "inspect_quality", issues


def make_stage_result(
    *,
    stage: str,
    action: str | None,
    ok: bool,
    duration_seconds: float,
    summary: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage_result = {
        "stage": stage,
        "action": action or "",
        "ok": ok,
        "duration_seconds": round(duration_seconds, 3),
        "summary": summary or {},
        "error": error or {},
    }
    if error and "failure_type" not in stage_result["error"]:
        stage_result["error"]["failure_type"] = classify_failure(
            code=error.get("code", ""),
            message=error.get("message", ""),
            details=error.get("details"),
        )
    return stage_result


def extract_stage_token_usage(stage_result: dict[str, Any]) -> dict[str, int]:
    summary = stage_result.get("summary", {})
    if isinstance(summary, dict) and "token_usage" in summary:
        return normalize_token_usage(summary.get("token_usage"))
    error = stage_result.get("error", {})
    if not isinstance(error, dict):
        return build_empty_token_usage()
    details = error.get("details", {})
    if not isinstance(details, dict):
        return build_empty_token_usage()
    return normalize_token_usage(details.get("token_usage", {}))


def summarize_case_token_usage(stages: list[dict[str, Any]]) -> dict[str, int]:
    total = build_empty_token_usage()
    for stage in stages:
        total = merge_token_usages(total, extract_stage_token_usage(stage))
    return total


def call_action(
    *,
    stage: str,
    action: str,
    payload: dict[str, Any],
    invoke_action: ActionInvoker,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    started = time.perf_counter()
    response = invoke_action(action, payload)
    duration_seconds = time.perf_counter() - started
    if response.get("ok"):
        data = response["data"]
        return (
            make_stage_result(
                stage=stage,
                action=action,
                ok=True,
                duration_seconds=duration_seconds,
                summary=summarize_action_data(action, data),
            ),
            data,
        )

    error = response.get("error", {})
    return (
        make_stage_result(
            stage=stage,
            action=action,
            ok=False,
            duration_seconds=duration_seconds,
            error={
                "code": error.get("code", ""),
                "message": error.get("message", ""),
                "details": error.get("details", {}),
            },
        ),
        None,
    )


def pick_selected_evaluation(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    if not evaluations:
        raise ValueError("没有可选的创意包评测结果。")
    return max(
        evaluations,
        key=lambda item: (
            int(item.get("total_score", 0)),
            RECOMMENDATION_PRIORITY.get(str(item.get("recommendation", "")), 0),
            -int(item.get("pack_id", 0)),
        ),
    )


def pick_selected_plan(plans: list[dict[str, Any]], variant_index: int) -> dict[str, Any]:
    if not plans:
        raise ValueError("没有可选的方案结果。")
    for item in plans:
        if item.get("variant_index") == variant_index:
            return item
    return plans[0]


def find_selected_payload(payloads: list[dict[str, Any]], plan_id: int) -> dict[str, Any]:
    for item in payloads:
        if item.get("plan_id") == plan_id:
            return item
    raise ValueError(f"未找到 plan_id={plan_id} 对应的 payload。")


def find_selected_draft(drafts: list[dict[str, Any]], payload_id: int, generation_mode: str) -> dict[str, Any]:
    for item in drafts:
        if item.get("payload_id") == payload_id and item.get("generation_mode") == generation_mode:
            return item
    raise ValueError(f"未找到 payload_id={payload_id} / generation_mode={generation_mode} 对应的草稿。")


def run_single_sample(
    *,
    sample: RegressionSample,
    db_path: Path,
    invoke_action: ActionInvoker,
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    sample_result = {
        "sample_key": sample.sample_key,
        "style": sample.style,
        "prompt": sample.prompt,
        "enabled": sample.enabled,
        "notes": sample.notes,
        "tags": list(sample.tags),
        "route": build_route_summary(sample),
        "target_char_range": list(sample.target_char_range),
        "target_chapter_count": sample.target_chapter_count,
        "plan_count": sample.plan_count,
        "candidate_count": sample.candidate_count,
        "status": "running",
        "final_stage": "",
        "failure_type": "",
        "batch_id": None,
        "selected_pack": {},
        "selected_plan": {},
        "selected_payload": {},
        "selected_draft": {},
        "inspect": {},
        "token_usage": build_empty_token_usage(),
        "stages": stages,
    }
    shared_payload = {
        "db_path": str(db_path),
    }

    def fail(stage_result: dict[str, Any]) -> dict[str, Any]:
        stages.append(stage_result)
        sample_result["status"] = "failed"
        sample_result["final_stage"] = stage_result["stage"]
        sample_result["failure_type"] = stage_result["error"].get("failure_type", "other")
        sample_result["token_usage"] = summarize_case_token_usage(stages)
        return sample_result

    match_stage, matched_data = call_action(
        stage="match_idea_cards",
        action="match_idea_cards",
        payload={
            **shared_payload,
            "prompt": sample.prompt,
            "count": sample.candidate_count,
        },
        invoke_action=invoke_action,
    )
    if matched_data is None:
        return fail(match_stage)
    stages.append(match_stage)

    store_stage, stored_data = call_action(
        stage="store_idea_cards",
        action="store_idea_cards",
        payload={
            **shared_payload,
            "source_mode": "prompt_match",
            "user_prompt": sample.prompt,
            "items": matched_data["items"],
        },
        invoke_action=invoke_action,
    )
    if stored_data is None:
        return fail(store_stage)
    stages.append(store_stage)
    sample_result["batch_id"] = stored_data.get("batch_id")

    build_packs_stage, built_packs_data = call_action(
        stage="build_idea_packs",
        action="build_idea_packs",
        payload={
            **shared_payload,
            "batch_id": stored_data["batch_id"],
            "style": sample.style,
            **sample.idea_pack_route.to_action_payload(),
        },
        invoke_action=invoke_action,
    )
    if built_packs_data is None:
        return fail(build_packs_stage)
    stages.append(build_packs_stage)

    evaluate_stage, evaluated_data = call_action(
        stage="evaluate_idea_packs",
        action="evaluate_idea_packs",
        payload={
            **shared_payload,
            "batch_id": stored_data["batch_id"],
        },
        invoke_action=invoke_action,
    )
    if evaluated_data is None:
        return fail(evaluate_stage)
    stages.append(evaluate_stage)

    try:
        selected_pack = pick_selected_evaluation(evaluated_data.get("items", []))
    except ValueError as exc:
        return fail(
            make_stage_result(
                stage="select_pack",
                action="evaluate_idea_packs",
                ok=False,
                duration_seconds=0.0,
                error={"code": "NO_SELECTED_PACK", "message": str(exc), "details": {}},
            )
        )
    stages.append(
        make_stage_result(
            stage="select_pack",
            action="evaluate_idea_packs",
            ok=True,
            duration_seconds=0.0,
            summary={
                "pack_id": selected_pack.get("pack_id"),
                "total_score": selected_pack.get("total_score"),
                "recommendation": selected_pack.get("recommendation"),
            },
        )
    )
    sample_result["selected_pack"] = {
        "pack_id": selected_pack.get("pack_id"),
        "total_score": selected_pack.get("total_score"),
        "recommendation": selected_pack.get("recommendation"),
    }

    build_plans_stage, built_plans_data = call_action(
        stage="build_story_plans",
        action="build_story_plans",
        payload={
            **shared_payload,
            "pack_ids": [selected_pack["pack_id"]],
            "target_char_range": list(sample.target_char_range),
            "target_chapter_count": sample.target_chapter_count,
            "plan_count": sample.plan_count,
            **sample.plan_route.to_action_payload(),
        },
        invoke_action=invoke_action,
    )
    if built_plans_data is None:
        return fail(build_plans_stage)
    stages.append(build_plans_stage)

    try:
        selected_plan = pick_selected_plan(
            built_plans_data.get("items", []),
            sample.selected_plan_variant_index,
        )
    except ValueError as exc:
        return fail(
            make_stage_result(
                stage="select_plan",
                action="build_story_plans",
                ok=False,
                duration_seconds=0.0,
                error={"code": "NO_SELECTED_PLAN", "message": str(exc), "details": {}},
            )
        )
    stages.append(
        make_stage_result(
            stage="select_plan",
            action="build_story_plans",
            ok=True,
            duration_seconds=0.0,
            summary={
                "plan_id": selected_plan.get("plan_id"),
                "variant_index": selected_plan.get("variant_index"),
                "title": selected_plan.get("title"),
            },
        )
    )
    sample_result["selected_plan"] = {
        "plan_id": selected_plan.get("plan_id"),
        "variant_index": selected_plan.get("variant_index"),
        "title": selected_plan.get("title"),
    }

    build_payloads_stage, built_payloads_data = call_action(
        stage="build_story_payloads",
        action="build_story_payloads",
        payload={
            **shared_payload,
            "plan_ids": [selected_plan["plan_id"]],
        },
        invoke_action=invoke_action,
    )
    if built_payloads_data is None:
        return fail(build_payloads_stage)
    stages.append(build_payloads_stage)

    try:
        selected_payload = find_selected_payload(
            built_payloads_data.get("items", []),
            selected_plan["plan_id"],
        )
    except ValueError as exc:
        return fail(
            make_stage_result(
                stage="select_payload",
                action="build_story_payloads",
                ok=False,
                duration_seconds=0.0,
                error={"code": "NO_SELECTED_PAYLOAD", "message": str(exc), "details": {}},
            )
        )
    stages.append(
        make_stage_result(
            stage="select_payload",
            action="build_story_payloads",
            ok=True,
            duration_seconds=0.0,
            summary={
                "payload_id": selected_payload.get("payload_id"),
                "title": selected_payload.get("title"),
            },
        )
    )
    sample_result["selected_payload"] = {
        "payload_id": selected_payload.get("payload_id"),
        "title": selected_payload.get("title"),
    }

    build_drafts_stage, built_drafts_data = call_action(
        stage="build_story_drafts",
        action="build_story_drafts",
        payload={
            **shared_payload,
            "payload_ids": [selected_payload["payload_id"]],
            **sample.draft_route.to_action_payload(),
        },
        invoke_action=invoke_action,
    )
    if built_drafts_data is None:
        return fail(build_drafts_stage)
    stages.append(build_drafts_stage)

    fetch_draft_stage, listed_drafts_data = call_action(
        stage="fetch_story_draft",
        action="list_story_drafts",
        payload={
            **shared_payload,
            "payload_ids": [selected_payload["payload_id"]],
            "generation_mode": sample.draft_route.generation_mode,
        },
        invoke_action=invoke_action,
    )
    if listed_drafts_data is None:
        return fail(fetch_draft_stage)
    stages.append(fetch_draft_stage)

    try:
        selected_draft = find_selected_draft(
            listed_drafts_data.get("items", []),
            selected_payload["payload_id"],
            sample.draft_route.generation_mode,
        )
    except ValueError as exc:
        return fail(
            make_stage_result(
                stage="fetch_story_draft",
                action="list_story_drafts",
                ok=False,
                duration_seconds=0.0,
                error={"code": "NO_SELECTED_DRAFT", "message": str(exc), "details": {}},
            )
        )
    sample_result["selected_draft"] = {
        "draft_id": selected_draft.get("draft_id"),
        "title": selected_draft.get("title"),
        "body_char_count": selected_draft.get("body_char_count"),
    }

    inspect_stage, inspect_data = call_action(
        stage="inspect",
        action="inspect",
        payload={
            **shared_payload,
            "content": selected_draft["content_markdown"],
            "target_char_range": list(sample.target_char_range),
            "summary_char_range": SUMMARY_CHAR_RANGE,
        },
        invoke_action=invoke_action,
    )
    if inspect_data is None:
        return fail(inspect_stage)

    if not inspect_data.get("overall_ok", False):
        failure_type, issues = classify_inspect_failure(inspect_data)
        return fail(
            make_stage_result(
                stage="inspect",
                action="inspect",
                ok=False,
                duration_seconds=inspect_stage["duration_seconds"],
                summary=inspect_stage["summary"],
                error={
                    "code": "INSPECT_NOT_PASSABLE",
                    "message": "inspect 未通过。",
                    "details": {"issues": issues},
                    "failure_type": failure_type,
                },
            )
        )

    stages.append(inspect_stage)
    sample_result["inspect"] = {
        "overall_ok": inspect_data.get("overall_ok"),
        "summary_chars": inspect_data.get("structure", {}).get("summary_chars"),
        "body_chars": inspect_data.get("structure", {}).get("body_chars"),
        "issues": inspect_data.get("structure", {}).get("issues", []) + inspect_data.get("quality", {}).get("issues", []),
    }
    sample_result["token_usage"] = summarize_case_token_usage(stages)
    sample_result["status"] = "passed"
    sample_result["final_stage"] = "inspect"
    return sample_result


def build_style_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    style_summary: dict[str, dict[str, int]] = {}
    for case in cases:
        bucket = style_summary.setdefault(
            case["style"],
            {"sample_count": 0, "passed_count": 0, "failed_count": 0},
        )
        bucket["sample_count"] += 1
        if case["status"] == "passed":
            bucket["passed_count"] += 1
        else:
            bucket["failed_count"] += 1
    return style_summary


def build_count_map(cases: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for case in cases:
        if case["status"] == "passed":
            continue
        key = case.get(field_name, "") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_report_summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    passed_count = sum(1 for case in cases if case["status"] == "passed")
    failed_count = len(cases) - passed_count
    total_token_usage = build_empty_token_usage()
    for case in cases:
        total_token_usage = merge_token_usages(total_token_usage, case.get("token_usage", {}))
    return {
        "sample_count": len(cases),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "inspect_pass_rate": round(passed_count / len(cases), 4) if cases else 0.0,
        "style_summary": build_style_summary(cases),
        "stage_failure_counts": build_count_map(cases, "final_stage"),
        "failure_type_counts": build_count_map(cases, "failure_type"),
        "all_passed": failed_count == 0,
        "token_usage": total_token_usage,
    }


def render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# 真实样本回归报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 运行目录：`{report['run_dir']}`",
        f"- 数据库：`{report['db_path']}`",
        "- LLM 配置：`与本次数据库同库存储`",
        f"- 样本集合：`{report['sample_set']}`",
        f"- 样本数量：`{report['summary']['sample_count']}`",
        f"- 通过数量：`{report['summary']['passed_count']}`",
        f"- 失败数量：`{report['summary']['failed_count']}`",
        f"- inspect 通过率：`{report['summary']['inspect_pass_rate']}`",
        f"- prompt tokens：`{report['summary']['token_usage']['prompt_tokens']}`",
        f"- completion tokens：`{report['summary']['token_usage']['completion_tokens']}`",
        f"- total tokens：`{report['summary']['token_usage']['total_tokens']}`",
        "",
        "## 风格汇总",
        "",
    ]
    for style, summary in report["summary"]["style_summary"].items():
        lines.append(f"- `{style}`：样本 `{summary['sample_count']}`，通过 `{summary['passed_count']}`，失败 `{summary['failed_count']}`")
    lines.extend(["", "## 失败阶段统计", ""])
    if report["summary"]["stage_failure_counts"]:
        for stage, count in report["summary"]["stage_failure_counts"].items():
            lines.append(f"- `{stage}`：`{count}`")
    else:
        lines.append("- 无")
    lines.extend(["", "## 失败类型统计", ""])
    if report["summary"]["failure_type_counts"]:
        for failure_type, count in report["summary"]["failure_type_counts"].items():
            lines.append(f"- `{failure_type}`：`{count}`")
    else:
        lines.append("- 无")
    lines.extend(["", "## 样本明细", ""])
    for case in report["cases"]:
        lines.extend(
            [
                f"### {case['sample_key']}",
                "",
                f"- 状态：`{case['status']}`",
                f"- 风格：`{case['style']}`",
                f"- prompt：{case['prompt']}",
                f"- 路线：pack `{case['route']['idea_pack']}` / plan `{case['route']['plan']}` / draft `{case['route']['draft']}`",
                f"- 选中创意包：`{case['selected_pack']}`",
                f"- 选中方案：`{case['selected_plan']}`",
                f"- 选中 payload：`{case['selected_payload']}`",
                f"- 选中草稿：`{case['selected_draft']}`",
                f"- tokens：`{case.get('token_usage', build_empty_token_usage())}`",
            ]
        )
        if case["inspect"]:
            lines.append(f"- inspect：`{case['inspect']}`")
        if case["status"] != "passed":
            lines.append(f"- 失败阶段：`{case['final_stage']}` / 类型：`{case['failure_type']}`")
        lines.append("")
        lines.append("| 阶段 | 动作 | ok | 耗时(秒) | 摘要 | 错误 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for stage in case["stages"]:
            lines.append(
                "| {stage} | {action} | {ok} | {duration} | {summary} | {error} |".format(
                    stage=stage["stage"],
                    action=stage["action"] or "-",
                    ok="yes" if stage["ok"] else "no",
                    duration=stage["duration_seconds"],
                    summary=json.dumps(stage["summary"], ensure_ascii=False),
                    error=json.dumps(stage["error"], ensure_ascii=False),
                )
            )
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def write_report_files(*, report: dict[str, Any], run_dir: Path) -> dict[str, str]:
    json_path = run_dir / "report.json"
    markdown_path = run_dir / "report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_markdown_report(report), encoding="utf-8")
    return {
        "json_report_path": str(json_path),
        "markdown_report_path": str(markdown_path),
    }


def run_regression(
    *,
    samples: list[RegressionSample],
    output_root: Path,
    run_name: str | None = None,
    sample_set: str = "custom",
    invoke_action: ActionInvoker = invoke_story_action,
) -> dict[str, Any]:
    output_root.mkdir(parents=True, exist_ok=True)
    resolved_run_name = run_name.strip() if isinstance(run_name, str) and run_name.strip() else time.strftime("story_regression_%Y%m%d_%H%M%S")
    run_dir = output_root / resolved_run_name
    if run_dir.exists():
        raise ValueError(f"运行目录已存在：{run_dir}")
    run_dir.mkdir(parents=True, exist_ok=False)

    db_path = run_dir / "story_ideas.sqlite3"
    cases = [
        run_single_sample(
            sample=sample,
            db_path=db_path,
            invoke_action=invoke_action,
        )
        for sample in samples
    ]
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sample_set": sample_set,
        "run_dir": str(run_dir),
        "db_path": str(db_path),
        "cases": cases,
        "summary": build_report_summary(cases),
    }
    report.update(write_report_files(report=report, run_dir=run_dir))
    return report


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="运行真实样本回归并生成 JSON/Markdown 报告。")
    parser.add_argument("--sample-set", default="default", choices=get_sample_set_names(), help="内置样本集合名。")
    parser.add_argument("--sample-keys", default="", help="只运行指定样本，逗号分隔。")
    parser.add_argument("--styles", default="", help="只运行指定风格，逗号分隔，可选 zhihu,douban。")
    parser.add_argument("--include-disabled", action="store_true", help="包含 disabled 样本。")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="报告输出根目录。")
    parser.add_argument("--run-name", default="", help="本次运行目录名；不传则自动按时间生成。")
    parser.add_argument("--fail-on-sample-failure", action="store_true", help="只要有样本失败就返回退出码 1。")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        selected_sample_keys = parse_csv_filter(args.sample_keys)
        selected_styles = parse_csv_filter(args.styles)
        samples = select_builtin_samples(
            sample_set=args.sample_set,
            sample_keys=selected_sample_keys,
            styles=selected_styles,
            include_disabled=args.include_disabled,
        )
        report = run_regression(
            samples=samples,
            output_root=Path(args.output_root),
            run_name=args.run_name,
            sample_set=args.sample_set,
        )
        report["sample_keys_filter"] = selected_sample_keys or []
        report["styles_filter"] = selected_styles or []
        Path(report["json_report_path"]).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "run_dir": report["run_dir"],
                    "db_path": report["db_path"],
                    "json_report_path": report["json_report_path"],
                    "markdown_report_path": report["markdown_report_path"],
                    "summary": report["summary"],
                },
                ensure_ascii=False,
            )
        )
        if args.fail_on_sample_failure and not report["summary"]["all_passed"]:
            return 1
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": {"message": str(exc)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
