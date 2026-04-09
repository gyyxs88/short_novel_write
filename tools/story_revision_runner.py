from __future__ import annotations

from collections.abc import Callable
from typing import Any

from tools.story_prose_analyzer import ANALYZER_NAME, analyze_story_prose_markdown
from tools.story_span_rewriter import rewrite_story_spans_deterministic, select_rewrite_targets


DEFAULT_MAX_ROUNDS = 2
DEFAULT_MAX_SPANS_PER_ROUND = 3
VALID_STOP_REASONS = {
    "max_rounds_reached",
    "no_issues_remaining",
    "no_rewrite_targets",
    "no_changes_applied",
}


def normalize_positive_int(value: Any, *, field_name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field_name} 必须是大于等于 1 的整数。")
    return value


def build_fallback_issue_codes(analysis_report: dict[str, Any]) -> list[str]:
    issues = analysis_report.get("issues")
    if not isinstance(issues, list):
        return []
    issue_codes: list[str] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        issue_code = item.get("issue_code")
        if not isinstance(issue_code, str) or not issue_code.strip():
            continue
        normalized_issue_code = issue_code.strip()
        if normalized_issue_code == "repeated_phrase":
            continue
        if normalized_issue_code not in issue_codes:
            issue_codes.append(normalized_issue_code)
    return issue_codes


def revise_story_draft_deterministic(
    *,
    content_markdown: str,
    style: str = "",
    profile: dict[str, Any] | None = None,
    analyzer_name: str = ANALYZER_NAME,
    revision_modes: list[str] | None = None,
    issue_codes: list[str] | None = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    max_spans_per_round: int = DEFAULT_MAX_SPANS_PER_ROUND,
    span_judge_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(content_markdown, str) or not content_markdown.strip():
        raise ValueError("content_markdown 必须是非空字符串。")
    if not isinstance(analyzer_name, str) or not analyzer_name.strip():
        raise ValueError("analyzer_name 必须是非空字符串。")

    normalized_max_rounds = normalize_positive_int(
        max_rounds,
        field_name="max_rounds",
        default=DEFAULT_MAX_ROUNDS,
    )
    normalized_max_spans_per_round = normalize_positive_int(
        max_spans_per_round,
        field_name="max_spans_per_round",
        default=DEFAULT_MAX_SPANS_PER_ROUND,
    )

    current_content = content_markdown
    initial_analysis = analyze_story_prose_markdown(current_content, style=style)
    initial_analysis.analyzer_name = analyzer_name.strip()
    current_analysis_dict = initial_analysis.to_dict()

    rounds: list[dict[str, Any]] = []
    stop_reason = "max_rounds_reached"

    for round_index in range(1, normalized_max_rounds + 1):
        if current_analysis_dict["issue_count"] <= 0:
            stop_reason = "no_issues_remaining"
            break

        active_issue_codes = list(issue_codes or [])
        targets = select_rewrite_targets(
            current_analysis_dict,
            rewrite_modes=revision_modes,
            issue_codes=active_issue_codes or None,
            max_spans=normalized_max_spans_per_round,
        )
        if not targets and not active_issue_codes:
            fallback_issue_codes = build_fallback_issue_codes(current_analysis_dict)
            if fallback_issue_codes:
                active_issue_codes = fallback_issue_codes
                targets = select_rewrite_targets(
                    current_analysis_dict,
                    rewrite_modes=revision_modes,
                    issue_codes=active_issue_codes,
                    max_spans=normalized_max_spans_per_round,
                )
        if not targets:
            stop_reason = "no_rewrite_targets"
            break

        rewrite_result = rewrite_story_spans_deterministic(
            content_markdown=current_content,
            analysis_report=current_analysis_dict,
            style=style,
            profile=profile,
            rewrite_modes=revision_modes,
            issue_codes=active_issue_codes or None,
            max_spans=normalized_max_spans_per_round,
        )
        if rewrite_result["changed_span_count"] <= 0 and not issue_codes:
            fallback_issue_codes = build_fallback_issue_codes(current_analysis_dict)
            if fallback_issue_codes and fallback_issue_codes != active_issue_codes:
                active_issue_codes = fallback_issue_codes
                rewrite_result = rewrite_story_spans_deterministic(
                    content_markdown=current_content,
                    analysis_report=current_analysis_dict,
                    style=style,
                    profile=profile,
                    rewrite_modes=revision_modes,
                    issue_codes=active_issue_codes,
                    max_spans=normalized_max_spans_per_round,
                )
        if rewrite_result["changed_span_count"] > 0 and span_judge_fn is not None:
            rewrite_result = span_judge_fn(
                before_content_markdown=current_content,
                rewrite_result=rewrite_result,
                round_index=round_index,
                analysis_report=current_analysis_dict,
                style=style,
                profile=profile,
            )
        if rewrite_result["changed_span_count"] <= 0:
            stop_reason = "no_changes_applied"
            break

        next_content = rewrite_result["after_content_markdown"]
        next_analysis = analyze_story_prose_markdown(next_content, style=style)
        next_analysis.analyzer_name = analyzer_name.strip()
        next_analysis_dict = next_analysis.to_dict()

        rounds.append(
            {
                "round_index": round_index,
                "analysis_report_before": current_analysis_dict,
                "analysis_report_after": next_analysis_dict,
                "changed_spans": rewrite_result["changed_spans"],
                "changed_span_count": rewrite_result["changed_span_count"],
                "risk_alerts": rewrite_result.get("risk_alerts", []),
                "risk_alert_count": rewrite_result.get("risk_alert_count", 0),
                "review_metadata": rewrite_result.get("review_metadata", {}),
                "revision_summary": rewrite_result["revision_summary"],
                "requested_revision_modes": list(revision_modes or []),
                "requested_issue_codes": list(active_issue_codes or []),
                "after_content_markdown": next_content,
            }
        )

        current_content = next_content
        current_analysis_dict = next_analysis_dict

    if not rounds and current_analysis_dict["issue_count"] <= 0:
        stop_reason = "no_issues_remaining"
    elif rounds and current_analysis_dict["issue_count"] <= 0:
        stop_reason = "no_issues_remaining"
    elif rounds and stop_reason == "max_rounds_reached":
        stop_reason = "max_rounds_reached"

    if stop_reason not in VALID_STOP_REASONS:
        raise ValueError("stop_reason 超出允许范围。")

    return {
        "generation_mode": "deterministic",
        "analyzer_name": analyzer_name.strip(),
        "style": style.strip(),
        "profile_name": profile.get("profile_name", "") if isinstance(profile, dict) else "",
        "requested_revision_modes": list(revision_modes or []),
        "requested_issue_codes": list(issue_codes or []),
        "max_rounds": normalized_max_rounds,
        "max_spans_per_round": normalized_max_spans_per_round,
        "round_count": len(rounds),
        "rounds": rounds,
        "stop_reason": stop_reason,
        "before_content_markdown": content_markdown,
        "after_content_markdown": current_content,
        "initial_analysis_report": initial_analysis.to_dict(),
        "final_analysis_report": current_analysis_dict,
        "initial_issue_count": initial_analysis.issue_count,
        "final_issue_count": current_analysis_dict["issue_count"],
        "issue_count_delta": current_analysis_dict["issue_count"] - initial_analysis.issue_count,
        "initial_overall_score": initial_analysis.overall_score,
        "final_overall_score": current_analysis_dict["overall_score"],
        "overall_score_delta": current_analysis_dict["overall_score"] - initial_analysis.overall_score,
    }
