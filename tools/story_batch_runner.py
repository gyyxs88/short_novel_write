from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
from typing import Any, Callable


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.story_archive_manager import DEFAULT_ARCHIVE_DB_PATH, archive_run
from tools.story_idea_repository import StoryIdeaRepository
from tools.story_plan_builder import (
    normalize_plan_count as normalize_story_plan_count,
    normalize_target_chapter_count as normalize_story_target_chapter_count,
)
from tools.story_regression_runner import (
    build_report_summary,
    invoke_story_action,
    make_stage_result,
    run_single_sample,
    write_report_files,
)
from tools.story_regression_samples import (
    DraftPostprocessConfig,
    GenerationRoute,
    RegressionSample,
    build_default_draft_postprocess,
)
from tools.story_token_usage import build_empty_token_usage, merge_token_usages


DEFAULT_OUTPUT_ROOT = ROOT_DIR / "outputs" / "batch"
DEFAULT_SOURCE_DB_NAME = "story_ideas.sqlite3"
DEFAULT_REPORT_NAME = "report.json"
DEFAULT_MARKDOWN_REPORT_NAME = "report.md"
DEFAULT_MAX_WORKERS = 2

ActionInvoker = Callable[[str, dict[str, Any]], dict[str, Any]]
ArchiveInvoker = Callable[..., dict[str, Any]]

_ARCHIVE_SENTINEL = object()


def parse_csv_filter(raw_value: str | None) -> list[str] | None:
    if raw_value is None:
        return None
    items = [item.strip() for item in raw_value.split(",") if item.strip()]
    return items or None


def build_default_plan_route(style: str) -> GenerationRoute:
    if style == "zhihu":
        return GenerationRoute(generation_mode="llm", llm_environment="zhihu_plan_default")
    return GenerationRoute(generation_mode="llm", llm_environment="douban_plan_default")


def build_default_draft_route(style: str) -> GenerationRoute:
    if style == "zhihu":
        return GenerationRoute(generation_mode="llm", llm_environment="zhihu_draft_default")
    return GenerationRoute(generation_mode="llm", llm_environment="douban_draft_default")


def parse_draft_postprocess_definition(
    raw_value: Any,
    *,
    default_config: DraftPostprocessConfig,
    field_name: str,
) -> DraftPostprocessConfig:
    if raw_value is None:
        return default_config
    if not isinstance(raw_value, dict):
        raise ValueError(f"{field_name} 必须是对象。")

    resolved_auto_revise = raw_value.get("auto_revise", default_config.auto_revise)
    if not isinstance(resolved_auto_revise, bool):
        raise ValueError(f"{field_name}.auto_revise 必须是布尔值。")
    if not resolved_auto_revise:
        try:
            return DraftPostprocessConfig(auto_revise=False)
        except ValueError as exc:  # pragma: no cover
            raise ValueError(f"{field_name} 不合法：{exc}") from exc

    try:
        return DraftPostprocessConfig(
            auto_revise=True,
            revision_profile_name=raw_value.get(
                "revision_profile_name",
                default_config.revision_profile_name,
            ),
            revision_modes=tuple(
                raw_value.get("revision_modes", default_config.revision_modes)
            ),
            revision_issue_codes=tuple(
                raw_value.get("revision_issue_codes", default_config.revision_issue_codes)
            ),
            revision_max_rounds=int(
                raw_value.get("revision_max_rounds", default_config.revision_max_rounds)
            ),
            revision_max_spans_per_round=int(
                raw_value.get(
                    "revision_max_spans_per_round",
                    default_config.revision_max_spans_per_round,
                )
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 不合法：{exc}") from exc


def parse_route_definition(
    raw_value: Any,
    *,
    default_route: GenerationRoute,
    field_name: str,
) -> GenerationRoute:
    if raw_value is None:
        return default_route
    if not isinstance(raw_value, dict):
        raise ValueError(f"{field_name} 必须是对象。")
    try:
        return GenerationRoute(
            generation_mode=str(raw_value.get("generation_mode", default_route.generation_mode)),
            llm_environment=raw_value.get("llm_environment"),
            provider=raw_value.get("provider"),
            model=raw_value.get("model"),
            api_mode=raw_value.get("api_mode"),
        )
    except ValueError as exc:
        raise ValueError(f"{field_name} 不合法：{exc}") from exc


def validate_job_id(raw_job_id: Any, *, index: int) -> str:
    if not isinstance(raw_job_id, str) or not raw_job_id.strip():
        raise ValueError(f"第 {index} 个 job 缺少合法的 job_id。")
    normalized = raw_job_id.strip()
    if normalized in {".", ".."}:
        raise ValueError(f"job_id 不合法：{normalized}")
    if Path(normalized).name != normalized or any(sep in normalized for sep in ("\\", "/")):
        raise ValueError(f"job_id 不能包含路径分隔符：{normalized}")
    return normalized


def build_job_sample(raw_job: dict[str, Any], *, index: int) -> RegressionSample:
    if not isinstance(raw_job, dict):
        raise ValueError(f"第 {index} 个 job 必须是对象。")
    job_id = validate_job_id(raw_job.get("job_id"), index=index)
    style = raw_job.get("style")
    prompt = raw_job.get("prompt")
    if not isinstance(style, str) or not style.strip():
        raise ValueError(f"job_id={job_id} 缺少合法的 style。")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"job_id={job_id} 缺少合法的 prompt。")

    target_char_range = raw_job.get("target_char_range")
    if target_char_range is not None:
        if (
            not isinstance(target_char_range, list)
            or len(target_char_range) != 2
            or not all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in target_char_range)
            or target_char_range[0] > target_char_range[1]
        ):
            raise ValueError(f"job_id={job_id} 的 target_char_range 必须是两个递增正整数。")
        normalized_target_char_range: tuple[int, int] | None = (target_char_range[0], target_char_range[1])
    else:
        normalized_target_char_range = None

    def read_positive_int(field_name: str, default: int) -> int:
        value = raw_job.get(field_name, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"job_id={job_id} 的 {field_name} 必须是大于等于 1 的整数。")
        return value

    notes = raw_job.get("notes", "")
    if not isinstance(notes, str):
        raise ValueError(f"job_id={job_id} 的 notes 必须是字符串。")

    raw_tags = raw_job.get("tags", [])
    if raw_tags is None:
        raw_tags = []
    if not isinstance(raw_tags, list) or any(not isinstance(item, str) or not item.strip() for item in raw_tags):
        raise ValueError(f"job_id={job_id} 的 tags 必须是字符串数组。")

    default_plan_route = build_default_plan_route(style.strip())
    default_draft_route = build_default_draft_route(style.strip())
    idea_pack_route = parse_route_definition(
        raw_job.get("idea_pack_route"),
        default_route=GenerationRoute(),
        field_name=f"job_id={job_id}.idea_pack_route",
    )
    plan_route = parse_route_definition(
        raw_job.get("plan_route"),
        default_route=default_plan_route,
        field_name=f"job_id={job_id}.plan_route",
    )
    draft_route = parse_route_definition(
        raw_job.get("draft_route"),
        default_route=default_draft_route,
        field_name=f"job_id={job_id}.draft_route",
    )
    draft_postprocess = parse_draft_postprocess_definition(
        raw_job.get("draft_postprocess"),
        default_config=build_default_draft_postprocess(style.strip()),
        field_name=f"job_id={job_id}.draft_postprocess",
    )

    try:
        normalized_target_chapter_count = normalize_story_target_chapter_count(
            raw_job.get("target_chapter_count", 6)
        )
    except ValueError as exc:
        raise ValueError(f"job_id={job_id} 的 target_chapter_count 不合法：{exc}") from exc

    try:
        normalized_plan_count = normalize_story_plan_count(raw_job.get("plan_count", 4))
    except ValueError as exc:
        raise ValueError(f"job_id={job_id} 的 plan_count 不合法：{exc}") from exc

    return RegressionSample(
        sample_key=job_id,
        style=style.strip(),
        prompt=prompt.strip(),
        target_char_range=normalized_target_char_range,
        target_chapter_count=normalized_target_chapter_count,
        candidate_count=read_positive_int("candidate_count", 3),
        plan_count=normalized_plan_count,
        selected_plan_variant_index=read_positive_int("selected_plan_variant_index", 1),
        idea_pack_route=idea_pack_route,
        plan_route=plan_route,
        draft_route=draft_route,
        draft_postprocess=draft_postprocess,
        notes=notes.strip(),
        tags=tuple(item.strip() for item in raw_tags if item.strip()),
    )


def load_batch_jobs(job_file_path: str | Path) -> list[RegressionSample]:
    resolved_path = Path(job_file_path)
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ValueError(f"未找到 jobs 文件：{resolved_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"jobs 文件不是合法 JSON：{resolved_path}") from exc

    if isinstance(payload, dict):
        raw_jobs = payload.get("jobs")
    else:
        raw_jobs = payload
    if not isinstance(raw_jobs, list) or not raw_jobs:
        raise ValueError("jobs 文件必须是非空数组，或包含非空 jobs 数组。")

    samples: list[RegressionSample] = []
    seen_job_ids: set[str] = set()
    for index, raw_job in enumerate(raw_jobs, start=1):
        sample = build_job_sample(raw_job, index=index)
        if sample.sample_key in seen_job_ids:
            raise ValueError(f"job_id 不能重复：{sample.sample_key}")
        seen_job_ids.add(sample.sample_key)
        samples.append(sample)
    return samples


def initialize_run_database(
    *,
    db_path: Path,
    template_db_path: Path | None,
) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if template_db_path is not None:
        if not template_db_path.exists():
            raise ValueError(f"模板库不存在：{template_db_path}")
        shutil.copy2(template_db_path, db_path)
        return
    StoryIdeaRepository(db_path)


def build_unexpected_failure_case(sample: RegressionSample, message: str) -> dict[str, Any]:
    stage = make_stage_result(
        stage="runner_internal",
        action="runner_internal",
        ok=False,
        duration_seconds=0.0,
        error={
            "code": "INTERNAL_ERROR",
            "message": message,
            "details": {},
        },
    )
    return {
        "sample_key": sample.sample_key,
        "style": sample.style,
        "prompt": sample.prompt,
        "enabled": sample.enabled,
        "notes": sample.notes,
        "tags": list(sample.tags),
        "route": {
            "idea_pack": sample.idea_pack_route.to_action_payload(),
            "plan": sample.plan_route.to_action_payload(),
            "draft": sample.draft_route.to_action_payload(),
            "draft_postprocess": sample.draft_postprocess.to_action_payload(),
        },
        "target_char_range": list(sample.target_char_range),
        "target_chapter_count": sample.target_chapter_count,
        "plan_count": sample.plan_count,
        "candidate_count": sample.candidate_count,
        "status": "failed",
        "final_stage": "runner_internal",
        "failure_type": "internal_error",
        "batch_id": None,
        "selected_pack": {},
        "selected_plan": {},
        "selected_payload": {},
        "selected_draft": {},
        "inspect": {},
        "token_usage": build_empty_token_usage(),
        "stages": [stage],
    }


def build_job_report(
    *,
    sample: RegressionSample,
    case_result: dict[str, Any],
    run_dir: Path,
    db_path: Path,
    wall_time_seconds: float,
    batch_name: str,
) -> dict[str, Any]:
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sample_set": batch_name,
        "run_dir": str(run_dir),
        "db_path": str(db_path),
        "wall_time_seconds": round(wall_time_seconds, 3),
        "case_type": "batch_job",
        "cases": [case_result],
        "summary": build_report_summary([case_result]),
        "job_meta": {
            "job_id": sample.sample_key,
            "style": sample.style,
            "target_char_range": list(sample.target_char_range),
            "target_chapter_count": sample.target_chapter_count,
        },
    }
    report.update(write_report_files(report=report, run_dir=run_dir))
    return report


def run_one_batch_job(
    *,
    sample: RegressionSample,
    batch_run_dir: Path,
    batch_name: str,
    template_db_path: Path | None,
    invoke_action: ActionInvoker,
) -> dict[str, Any]:
    job_run_dir = batch_run_dir / "jobs" / sample.sample_key
    if job_run_dir.exists():
        raise ValueError(f"job 目录已存在：{job_run_dir}")
    job_run_dir.mkdir(parents=True, exist_ok=False)

    db_path = job_run_dir / DEFAULT_SOURCE_DB_NAME
    started = time.perf_counter()
    try:
        initialize_run_database(db_path=db_path, template_db_path=template_db_path)
        case_result = run_single_sample(
            sample=sample,
            db_path=db_path,
            invoke_action=invoke_action,
        )
    except Exception as exc:
        case_result = build_unexpected_failure_case(sample, f"未预期异常：{exc}")
    wall_time_seconds = time.perf_counter() - started

    report = build_job_report(
        sample=sample,
        case_result=case_result,
        run_dir=job_run_dir,
        db_path=db_path,
        wall_time_seconds=wall_time_seconds,
        batch_name=batch_name,
    )

    return {
        "job_id": sample.sample_key,
        "style": sample.style,
        "status": case_result["status"],
        "final_stage": case_result["final_stage"],
        "failure_type": case_result["failure_type"],
        "run_dir": str(job_run_dir),
        "db_path": str(db_path),
        "report_json_path": report["json_report_path"],
        "report_markdown_path": report["markdown_report_path"],
        "wall_time_seconds": round(wall_time_seconds, 3),
        "token_usage": case_result.get("token_usage", build_empty_token_usage()),
        "selected_draft": case_result.get("selected_draft", {}),
        "inspect": case_result.get("inspect", {}),
        "case": case_result,
        "archive": {
            "status": "pending",
            "archive_db_path": "",
            "source_db_deleted": False,
            "error": "",
        },
    }


def merge_batch_token_usage(job_results: list[dict[str, Any]]) -> dict[str, int]:
    total = build_empty_token_usage()
    for item in job_results:
        total = merge_token_usages(total, item.get("token_usage", {}))
    return total


def build_batch_summary(job_results: list[dict[str, Any]], *, wall_time_seconds: float) -> dict[str, Any]:
    passed_count = sum(1 for item in job_results if item["status"] == "passed")
    failed_count = len(job_results) - passed_count
    archived_count = sum(1 for item in job_results if item["archive"]["status"] == "archived")
    archive_failed_count = sum(1 for item in job_results if item["archive"]["status"] == "failed")
    case_summary = build_report_summary(
        [item["case"] for item in job_results if isinstance(item.get("case"), dict)]
    )

    return {
        "job_count": len(job_results),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "inspect_pass_rate": round(passed_count / len(job_results), 4) if job_results else 0.0,
        "archived_count": archived_count,
        "archive_failed_count": archive_failed_count,
        "all_passed": failed_count == 0,
        "all_archived": archived_count == len(job_results) and archive_failed_count == 0,
        "token_usage": merge_batch_token_usage(job_results),
        "final_stage_counts": case_summary["stage_failure_counts"],
        "failure_type_counts": case_summary["failure_type_counts"],
        "auto_revised_job_count": case_summary["auto_revised_job_count"],
        "draft_changed_job_count": case_summary["draft_changed_job_count"],
        "revision_round_count_total": case_summary["revision_round_count_total"],
        "revision_round_count_avg": case_summary["revision_round_count_avg"],
        "selected_draft_body_char_delta_total": case_summary["selected_draft_body_char_delta_total"],
        "selected_draft_body_char_change_total": case_summary["selected_draft_body_char_change_total"],
        "wall_time_seconds": round(wall_time_seconds, 3),
    }


def render_batch_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# 批量任务运行报告",
        "",
        f"- 生成时间：`{report['generated_at']}`",
        f"- 批次目录：`{report['batch_run_dir']}`",
        f"- 归档库：`{report['archive_db_path']}`",
        f"- 模板库：`{report['template_db_path']}`",
        f"- 并发 worker：`{report['max_workers']}`",
        f"- 归档后删除运行库：`{'yes' if report['delete_source_db'] else 'no'}`",
        f"- job 数量：`{report['summary']['job_count']}`",
        f"- 通过数量：`{report['summary']['passed_count']}`",
        f"- 失败数量：`{report['summary']['failed_count']}`",
        f"- 已归档数量：`{report['summary']['archived_count']}`",
        f"- 归档失败数量：`{report['summary']['archive_failed_count']}`",
        f"- 自动修订 job 数：`{report['summary']['auto_revised_job_count']}`",
        f"- 终稿发生变化的 job 数：`{report['summary']['draft_changed_job_count']}`",
        f"- 修订总轮次：`{report['summary']['revision_round_count_total']}`",
        f"- 平均修订轮次：`{report['summary']['revision_round_count_avg']}`",
        f"- 终稿字数净变化：`{report['summary']['selected_draft_body_char_delta_total']}`",
        f"- 首终稿字数变化总量：`{report['summary']['selected_draft_body_char_change_total']}`",
        f"- 总耗时：`{report['summary']['wall_time_seconds']}` 秒",
        f"- prompt tokens：`{report['summary']['token_usage']['prompt_tokens']}`",
        f"- completion tokens：`{report['summary']['token_usage']['completion_tokens']}`",
        f"- total tokens：`{report['summary']['token_usage']['total_tokens']}`",
        "",
        "## Job 明细",
        "",
        "| job_id | style | status | auto_revised | changed | rounds | delta | final_stage | failure_type | archive | deleted | run_dir |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["jobs"]:
        selected_draft = item.get("selected_draft", {})
        lines.append(
            "| {job_id} | {style} | {status} | {auto_revised} | {changed} | {rounds} | {delta} | {final_stage} | {failure_type} | {archive_status} | {deleted} | `{run_dir}` |".format(
                job_id=item["job_id"],
                style=item["style"],
                status=item["status"],
                auto_revised="yes" if selected_draft.get("auto_revised") else "no",
                changed="yes" if selected_draft.get("content_changed") else "no",
                rounds=selected_draft.get("revision_round_count", 0),
                delta=selected_draft.get("body_char_count_delta", 0),
                final_stage=item["final_stage"] or "-",
                failure_type=item["failure_type"] or "-",
                archive_status=item["archive"]["status"],
                deleted="yes" if item["archive"].get("source_db_deleted") else "no",
                run_dir=item["run_dir"],
            )
        )
    lines.extend(["", "## 失败统计", ""])
    if report["summary"]["failure_type_counts"]:
        for failure_type, count in report["summary"]["failure_type_counts"].items():
            lines.append(f"- `{failure_type}`：`{count}`")
    else:
        lines.append("- 无")
    lines.extend(["", "## 归档错误", ""])
    archive_errors = [item for item in report["jobs"] if item["archive"]["status"] == "failed"]
    if archive_errors:
        for item in archive_errors:
            lines.append(f"- `{item['job_id']}`：{item['archive']['error']}")
    else:
        lines.append("- 无")
    return "\n".join(lines).strip() + "\n"


def write_batch_report_files(*, report: dict[str, Any], batch_run_dir: Path) -> dict[str, str]:
    json_path = batch_run_dir / "batch_report.json"
    markdown_path = batch_run_dir / "batch_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_batch_markdown_report(report), encoding="utf-8")
    return {
        "json_report_path": str(json_path),
        "markdown_report_path": str(markdown_path),
    }


def run_batch_jobs(
    *,
    jobs: list[RegressionSample],
    output_root: Path,
    run_name: str | None = None,
    template_db_path: Path | None = None,
    archive_db_path: Path = DEFAULT_ARCHIVE_DB_PATH,
    max_workers: int = DEFAULT_MAX_WORKERS,
    delete_source_db: bool = True,
    invoke_action: ActionInvoker = invoke_story_action,
    archive_job_fn: ArchiveInvoker = archive_run,
) -> dict[str, Any]:
    if max_workers < 1:
        raise ValueError("max_workers 必须大于等于 1。")

    output_root.mkdir(parents=True, exist_ok=True)
    resolved_run_name = run_name.strip() if isinstance(run_name, str) and run_name.strip() else time.strftime("story_batch_%Y%m%d_%H%M%S")
    batch_run_dir = output_root / resolved_run_name
    if batch_run_dir.exists():
        raise ValueError(f"批次目录已存在：{batch_run_dir}")
    (batch_run_dir / "jobs").mkdir(parents=True, exist_ok=False)

    archive_queue: queue.Queue[dict[str, Any] | object] = queue.Queue()
    archive_results: dict[str, dict[str, Any]] = {}
    archive_lock = threading.Lock()

    def archive_worker() -> None:
        while True:
            item = archive_queue.get()
            try:
                if item is _ARCHIVE_SENTINEL:
                    return
                assert isinstance(item, dict)
                job_id = str(item["job_id"])
                try:
                    archive_result = archive_job_fn(
                        run_dir=item["run_dir"],
                        archive_db_path=archive_db_path,
                        job_id=job_id,
                        delete_source_db=delete_source_db,
                    )
                    archive_state = {
                        "status": "archived",
                        "archive_db_path": archive_result.get("archive_db_path", str(archive_db_path)),
                        "source_db_deleted": bool(archive_result.get("source_db_deleted", False)),
                        "error": "",
                        "counts": archive_result.get("counts", {}),
                        "selected_ids": archive_result.get("selected_ids", {}),
                    }
                except Exception as exc:
                    archive_state = {
                        "status": "failed",
                        "archive_db_path": str(archive_db_path),
                        "source_db_deleted": False,
                        "error": str(exc),
                        "counts": {},
                        "selected_ids": {},
                    }
                with archive_lock:
                    archive_results[job_id] = archive_state
            finally:
                archive_queue.task_done()

    worker_thread = threading.Thread(target=archive_worker, name="story-batch-archiver", daemon=True)
    worker_thread.start()

    started = time.perf_counter()
    job_results_in_order: list[dict[str, Any] | None] = [None] * len(jobs)
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_index = {
                executor.submit(
                    run_one_batch_job,
                    sample=sample,
                    batch_run_dir=batch_run_dir,
                    batch_name=resolved_run_name,
                    template_db_path=template_db_path,
                    invoke_action=invoke_action,
                ): index
                for index, sample in enumerate(jobs)
            }
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                result = future.result()
                job_results_in_order[index] = result
                archive_queue.put(result)
    finally:
        archive_queue.join()
        archive_queue.put(_ARCHIVE_SENTINEL)
        worker_thread.join()
    wall_time_seconds = time.perf_counter() - started

    job_results: list[dict[str, Any]] = []
    for item in job_results_in_order:
        if item is None:
            continue
        item["archive"] = archive_results.get(
            item["job_id"],
            {
                "status": "failed",
                "archive_db_path": str(archive_db_path),
                "source_db_deleted": False,
                "error": "归档线程未返回结果。",
                "counts": {},
                "selected_ids": {},
            },
        )
        job_results.append(item)

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "batch_run_dir": str(batch_run_dir),
        "archive_db_path": str(archive_db_path),
        "template_db_path": str(template_db_path) if template_db_path is not None else "",
        "max_workers": max_workers,
        "delete_source_db": delete_source_db,
        "jobs": job_results,
        "summary": build_batch_summary(job_results, wall_time_seconds=wall_time_seconds),
    }
    report.update(write_batch_report_files(report=report, batch_run_dir=batch_run_dir))
    return report


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="批量并发运行小说任务，并串行归档到 archive.sqlite3。")
    parser.add_argument("--jobs-file", required=True, help="批量 job 定义文件，支持 JSON 数组或 {\"jobs\": [...]}。")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="批次输出根目录。")
    parser.add_argument("--run-name", default="", help="批次目录名，不传则自动按时间生成。")
    parser.add_argument("--template-db", default="", help="模板库路径；会为每个 job 复制一份独立运行库。")
    parser.add_argument("--archive-db", default=str(DEFAULT_ARCHIVE_DB_PATH), help="统一归档库路径。")
    parser.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS, help="并发 worker 数。")
    parser.add_argument("--keep-source-db", action="store_true", help="归档成功后保留每个 job 的源运行库。")
    parser.add_argument("--fail-on-job-failure", action="store_true", help="只要有任一 job 失败就返回退出码 1。")
    parser.add_argument("--fail-on-archive-failure", action="store_true", help="只要有任一 job 归档失败就返回退出码 1。")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        jobs = load_batch_jobs(args.jobs_file)
        report = run_batch_jobs(
            jobs=jobs,
            output_root=Path(args.output_root),
            run_name=args.run_name,
            template_db_path=Path(args.template_db) if isinstance(args.template_db, str) and args.template_db.strip() else None,
            archive_db_path=Path(args.archive_db),
            max_workers=args.max_workers,
            delete_source_db=not args.keep_source_db,
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "batch_run_dir": report["batch_run_dir"],
                    "archive_db_path": report["archive_db_path"],
                    "json_report_path": report["json_report_path"],
                    "markdown_report_path": report["markdown_report_path"],
                    "summary": report["summary"],
                },
                ensure_ascii=False,
            )
        )
        if args.fail_on_job_failure and not report["summary"]["all_passed"]:
            return 1
        if args.fail_on_archive_failure and not report["summary"]["all_archived"]:
            return 1
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": {"message": str(exc)}}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
