from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

from tools.story_prose_analyzer import AI_ISM_PHRASES


VALID_REWRITE_MODES = {
    "remove_ai_phrases",
    "concretize_emotion",
    "strengthen_scene",
    "diversify_dialogue",
    "compress_exposition",
    "break_template_rhythm",
}
ISSUE_MODE_MAP = {
    "repeated_phrase": ["compress_exposition"],
    "repeated_paragraph_opener": ["break_template_rhythm"],
    "ai_ism": ["remove_ai_phrases"],
    "abstract_emotion": ["concretize_emotion"],
    "scene_thin": ["strengthen_scene"],
    "template_chapter": ["break_template_rhythm", "compress_exposition"],
}
SEVERITY_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}
DEFAULT_MAX_SPANS = 3
MIN_ABSTRACT_EMOTION_SPAN_LENGTH = 10
HIGH_RISK_REGRET_TERM = "后悔"
QUESTION_SENTENCE_ENDINGS = ("？", "?")
SUBJECT_PRONOUN_HINTS = ("她", "他", "我")

AI_ISM_REPLACEMENTS = {
    "那一刻": "",
    "不由得": "",
    "仿佛": "像",
    "似乎": "像是",
    "某种": "",
    "带着某种": "带着",
    "带着一种": "带着",
    "某种意味": "意味",
    "其实": "",
    "原来": "",
    "并没有立刻": "没有立刻",
    "终于明白": "这才明白",
    "开始松动": "露出裂口",
    "某种程度上": "",
    "回不到原来的样子": "再也装不回从前",
}
ABSTRACT_EMOTION_REPLACEMENTS = {
    "她感到痛苦，也感到不安。": {
        "zhihu": "她攥紧手指，后背一下绷住，连呼吸都乱了。",
        "douban": "她把指节扣进掌心，肩背发紧，呼吸一点点沉下去。",
    },
    "她感到难过，也感到压抑。": {
        "zhihu": "她喉咙发紧，话到嘴边又被自己硬生生咽了回去。",
        "douban": "她没再抬头，只把指腹慢慢压在杯壁上，像怕一开口就漏出情绪。",
    },
}
GENERIC_EMOTION_SCENE_LINES = {
    "zhihu": "她先低头稳了一下呼吸，指尖却还是在发抖。",
    "douban": "她把手指藏进袖口里，呼吸慢了一拍，眼神也跟着避开了对方。",
}
SCENE_BOOST_LINES = {
    "zhihu": [
        "门外的风把门页轻轻撞了一下，她低头时才发现掌心已经出了一层潮汗。",
        "手机屏在掌心一亮，冷白的光把她脸上的犹豫照得再也藏不住。",
        "走廊里忽然传来一声脚步回响，她下意识把话停在了嘴边。",
    ],
    "douban": [
        "窗缝里钻进来的潮气落在手背上，她这才意识到房间安静得过分。",
        "桌角那只没喝完的杯子还留着一点凉意，像是有人刚离开不久。",
        "走廊尽头的灯忽明忽暗，她把话含在嘴里，半天没有真正说出口。",
    ],
}
RHYTHM_LEADS = {
    "zhihu": [
        "手机先震了一下，局面这才真正失控。",
        "门外忽然响了一声，她原本想压住的念头立刻翻了出来。",
        "桌上的光影一晃，她再想装作镇定已经来不及了。",
    ],
    "douban": [
        "窗缝里的风先动了一下，原本勉强稳住的平静也跟着散开。",
        "灯影落在桌角，她这才发现自己连手都没真正放松过。",
        "门口传来很轻的一声响，她心里那点迟疑便慢慢浮了上来。",
    ],
}


@dataclass(slots=True)
class RewriteTarget:
    target_index: int
    issue_code: str
    severity: str
    rewrite_modes: list[str]
    chapter_number: int | None
    start_offset: int
    end_offset: int
    original_text: str
    evidence: dict[str, Any]


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} 必须是非空字符串数组。")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field_name} 必须是非空字符串数组。")
        normalized.append(item.strip())
    return normalized


def normalize_rewrite_modes(value: Any) -> list[str]:
    modes = _normalize_string_list(value, "rewrite_modes")
    for mode in modes:
        if mode not in VALID_REWRITE_MODES:
            raise ValueError(f"rewrite_modes 仅支持：{sorted(VALID_REWRITE_MODES)}")
    deduplicated: list[str] = []
    for mode in modes:
        if mode not in deduplicated:
            deduplicated.append(mode)
    return deduplicated


def normalize_issue_codes(value: Any) -> list[str]:
    codes = _normalize_string_list(value, "issue_codes")
    deduplicated: list[str] = []
    for code in codes:
        if code not in deduplicated:
            deduplicated.append(code)
    return deduplicated


def normalize_max_spans(value: Any) -> int:
    if value is None:
        return DEFAULT_MAX_SPANS
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("max_spans 必须是大于等于 1 的整数。")
    return value


def resolve_target_end_offset(target: RewriteTarget) -> int:
    inferred_end = target.start_offset + len(target.original_text)
    return max(target.end_offset, inferred_end)


def spans_overlap(
    *,
    start_offset: int,
    end_offset: int,
    selected_ranges: list[tuple[int, int]],
) -> bool:
    if end_offset <= start_offset:
        return False
    return any(start_offset < selected_end and selected_start < end_offset for selected_start, selected_end in selected_ranges)


def resolve_issue_rewrite_modes(issue_code: str) -> list[str]:
    return ISSUE_MODE_MAP.get(issue_code, ["remove_ai_phrases"])


def _coerce_issue(issue: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(issue, dict):
        raise ValueError("analysis_report.issues 里的每一项都必须是对象。")
    issue_code = issue.get("issue_code")
    if not isinstance(issue_code, str) or not issue_code.strip():
        raise ValueError("analysis_report.issues.issue_code 必须是非空字符串。")
    return {
        "issue_code": issue_code.strip(),
        "severity": issue.get("severity", "medium") if isinstance(issue.get("severity"), str) else "medium",
        "chapter_number": issue.get("chapter_number") if isinstance(issue.get("chapter_number"), int) else None,
        "start_offset": issue.get("start_offset") if isinstance(issue.get("start_offset"), int) else 0,
        "end_offset": issue.get("end_offset") if isinstance(issue.get("end_offset"), int) else 0,
        "span_text": issue.get("span_text", "") if isinstance(issue.get("span_text"), str) else "",
        "evidence": issue.get("evidence", {}) if isinstance(issue.get("evidence"), dict) else {},
    }


def select_rewrite_targets(
    analysis_report: dict[str, Any],
    *,
    rewrite_modes: list[str] | None = None,
    issue_codes: list[str] | None = None,
    max_spans: int = DEFAULT_MAX_SPANS,
) -> list[RewriteTarget]:
    if not isinstance(analysis_report, dict):
        raise ValueError("analysis_report 必须是对象。")
    raw_issues = analysis_report.get("issues")
    if not isinstance(raw_issues, list) or not raw_issues:
        return []

    normalized_rewrite_modes = rewrite_modes or []
    normalized_issue_codes = issue_codes or []
    max_target_count = normalize_max_spans(max_spans)

    candidates: list[RewriteTarget] = []
    for index, raw_issue in enumerate(raw_issues):
        issue = _coerce_issue(raw_issue)
        if normalized_issue_codes and issue["issue_code"] not in normalized_issue_codes:
            continue
        default_modes = resolve_issue_rewrite_modes(issue["issue_code"])
        selected_modes = (
            [mode for mode in default_modes if mode in normalized_rewrite_modes]
            if normalized_rewrite_modes
            else default_modes
        )
        if not selected_modes:
            continue
        candidates.append(
            RewriteTarget(
                target_index=index,
                issue_code=issue["issue_code"],
                severity=issue["severity"],
                rewrite_modes=selected_modes,
                chapter_number=issue["chapter_number"],
                start_offset=issue["start_offset"],
                end_offset=issue["end_offset"],
                original_text=issue["span_text"],
                evidence=issue["evidence"],
            )
        )

    candidates.sort(
        key=lambda item: (
            SEVERITY_ORDER.get(item.severity, 9),
            item.start_offset,
            item.target_index,
        )
    )
    selected_targets: list[RewriteTarget] = []
    selected_ranges: list[tuple[int, int]] = []
    for candidate in candidates:
        candidate_end = resolve_target_end_offset(candidate)
        if spans_overlap(
            start_offset=candidate.start_offset,
            end_offset=candidate_end,
            selected_ranges=selected_ranges,
        ):
            continue
        selected_targets.append(candidate)
        selected_ranges.append((candidate.start_offset, candidate_end))
        if len(selected_targets) >= max_target_count:
            break
    return selected_targets


def collapse_text_whitespace(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"([，。！？；])\1+", r"\1", normalized)
    return normalized.strip()


def apply_remove_ai_phrases(text: str, *, avoid_phrases: list[str] | None = None) -> str:
    rewritten = text
    for phrase, replacement in AI_ISM_REPLACEMENTS.items():
        rewritten = rewritten.replace(phrase, replacement)
    for phrase in avoid_phrases or []:
        if phrase in AI_ISM_REPLACEMENTS:
            continue
        rewritten = rewritten.replace(phrase, "")
    rewritten = re.sub(r"(?<!\n)\s+", " ", rewritten)
    rewritten = re.sub(r"([，。！？；、])\s*", r"\1", rewritten)
    rewritten = re.sub(r"(，){2,}", "，", rewritten)
    return collapse_text_whitespace(rewritten)


def apply_compress_exposition(text: str) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[。！？!?])", text) if sentence.strip()]
    deduplicated: list[str] = []
    seen_signatures: set[str] = set()
    for sentence in sentences:
        signature = re.sub(r"[^\u4e00-\u9fff]", "", sentence)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        deduplicated.append(sentence)
    if len(deduplicated) >= 3:
        compressed: list[str] = []
        for sentence in deduplicated:
            if any(pattern in sentence for pattern in ("她知道", "我知道", "原来", "其实")) and len(compressed) >= 2:
                continue
            compressed.append(sentence)
        deduplicated = compressed or deduplicated
    return collapse_text_whitespace("".join(deduplicated))


def guess_subject(text: str) -> str:
    if "我" in text:
        return "我"
    if "他" in text:
        return "他"
    return "她"


def apply_concretize_emotion(text: str, *, style: str) -> str:
    rewritten = text
    for sentence, replacements in ABSTRACT_EMOTION_REPLACEMENTS.items():
        if sentence in rewritten:
            rewritten = rewritten.replace(sentence, replacements.get(style, replacements["zhihu"]))
    if rewritten == text:
        subject = guess_subject(text)
        generic_line = GENERIC_EMOTION_SCENE_LINES.get(style, GENERIC_EMOTION_SCENE_LINES["zhihu"])
        rewritten = re.sub(
            r"[。！？!?]?\s*$",
            "",
            text,
        )
        if subject == "我":
            generic_line = generic_line.replace("她", "我")
        elif subject == "他":
            generic_line = generic_line.replace("她", "他")
        rewritten = f"{generic_line}"
    return collapse_text_whitespace(rewritten)


def apply_strengthen_scene(text: str, *, style: str, target_index: int) -> str:
    line_candidates = SCENE_BOOST_LINES.get(style, SCENE_BOOST_LINES["zhihu"])
    scene_line = line_candidates[target_index % len(line_candidates)]
    if scene_line in text:
        return collapse_text_whitespace(text)
    if text.startswith(scene_line):
        return collapse_text_whitespace(text)
    return collapse_text_whitespace(f"{scene_line}{text}")


def apply_break_template_rhythm(text: str, *, style: str, target_index: int) -> str:
    line_candidates = RHYTHM_LEADS.get(style, RHYTHM_LEADS["zhihu"])
    lead_line = line_candidates[target_index % len(line_candidates)]
    paragraphs = [paragraph for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if not paragraphs:
        return collapse_text_whitespace(f"{lead_line}{text}")
    first_paragraph = paragraphs[0].strip()
    first_paragraph = re.sub(r"^(她|他|我|那一刻|直到这时|直到这一章|然而|但是|可是)", "", first_paragraph).strip()
    paragraphs[0] = f"{lead_line}{first_paragraph}"
    return collapse_text_whitespace("\n\n".join(paragraphs))


def apply_diversify_dialogue(text: str, *, style: str) -> str:
    if "“" not in text or "”" not in text:
        return collapse_text_whitespace(text)
    if style == "douban":
        return collapse_text_whitespace(text.replace("她说", "").replace("他说", ""))
    return collapse_text_whitespace(text.replace("她说", "她压低声音").replace("他说", "他顿了一下"))


def rewrite_span_text_deterministic(
    original_text: str,
    *,
    rewrite_modes: list[str],
    style: str,
    target_index: int,
    avoid_phrases: list[str] | None = None,
) -> tuple[str, list[str]]:
    rewritten = original_text
    applied_modes: list[str] = []
    for mode in rewrite_modes:
        next_text = rewritten
        if mode == "remove_ai_phrases":
            next_text = apply_remove_ai_phrases(rewritten, avoid_phrases=avoid_phrases)
        elif mode == "compress_exposition":
            next_text = apply_compress_exposition(rewritten)
        elif mode == "concretize_emotion":
            next_text = apply_concretize_emotion(rewritten, style=style)
        elif mode == "strengthen_scene":
            next_text = apply_strengthen_scene(rewritten, style=style, target_index=target_index)
        elif mode == "break_template_rhythm":
            next_text = apply_break_template_rhythm(rewritten, style=style, target_index=target_index)
        elif mode == "diversify_dialogue":
            next_text = apply_diversify_dialogue(rewritten, style=style)
        if next_text != rewritten:
            rewritten = next_text
            applied_modes.append(mode)
    return collapse_text_whitespace(rewritten), applied_modes


def resolve_style(profile: dict[str, Any] | None, fallback_style: str) -> str:
    if isinstance(profile, dict):
        style = profile.get("style")
        if isinstance(style, str) and style.strip():
            return style.strip()
    return fallback_style.strip() or "zhihu"


def resolve_avoid_phrases(profile: dict[str, Any] | None) -> list[str]:
    if not isinstance(profile, dict):
        return []
    value = profile.get("avoid_phrases")
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def build_risk_alert_record(target: RewriteTarget, *, risk_flags: list[str]) -> dict[str, Any]:
    return {
        "target_index": target.target_index,
        "issue_code": target.issue_code,
        "chapter_number": target.chapter_number,
        "start_offset": target.start_offset,
        "end_offset": target.end_offset,
        "original_text": target.original_text,
        "requested_rewrite_modes": target.rewrite_modes,
        "evidence": target.evidence,
        "risk_flags": list(risk_flags),
    }


def build_rewrite_risk_flags(target: RewriteTarget) -> list[str]:
    risk_flags: list[str] = []
    original_text = collapse_text_whitespace(target.original_text)
    if not original_text:
        return ["empty_original_text"]
    if target.issue_code != "abstract_emotion":
        return risk_flags
    if "“" in original_text or "”" in original_text:
        risk_flags.append("dialogue_fragment")
    if original_text.endswith(QUESTION_SENTENCE_ENDINGS):
        risk_flags.append("question_sentence")
    if len(original_text) < MIN_ABSTRACT_EMOTION_SPAN_LENGTH:
        risk_flags.append("span_too_short")
    matched_term = target.evidence.get("matched_term", "") if isinstance(target.evidence, dict) else ""
    if (
        matched_term == HIGH_RISK_REGRET_TERM
        and not any(pronoun in original_text for pronoun in SUBJECT_PRONOUN_HINTS)
    ):
        risk_flags.append("missing_subject_for_regret")
    return risk_flags


def apply_changed_spans(content_markdown: str, changed_spans: list[dict[str, Any]]) -> str:
    rewritten = content_markdown
    sorted_spans = sorted(changed_spans, key=lambda item: item["start_offset"], reverse=True)
    for span in sorted_spans:
        start_offset = span["start_offset"]
        end_offset = span["end_offset"]
        original_text = span["original_text"]
        current_slice = rewritten[start_offset:end_offset]
        if current_slice != original_text and original_text:
            located_index = rewritten.find(original_text, max(0, start_offset - 80))
            if located_index == -1:
                raise ValueError("原文片段与偏移不匹配，无法安全回写改写结果。")
            start_offset = located_index
            end_offset = located_index + len(original_text)
        rewritten = f"{rewritten[:start_offset]}{span['rewritten_text']}{rewritten[end_offset:]}"
    return rewritten


def build_revision_summary(
    changed_spans: list[dict[str, Any]],
    *,
    risk_alerts: list[dict[str, Any]] | None = None,
) -> str:
    risk_alerts = risk_alerts or []
    if not changed_spans:
        if risk_alerts:
            return f"本次发现 {len(risk_alerts)} 个高风险提醒，但没有形成有效改写。"
        return "本次没有找到可改写片段。"
    issue_codes: list[str] = []
    rewrite_modes: list[str] = []
    for item in changed_spans:
        if item["issue_code"] not in issue_codes:
            issue_codes.append(item["issue_code"])
        for mode in item["applied_rewrite_modes"]:
            if mode not in rewrite_modes:
                rewrite_modes.append(mode)
    summary = (
        f"本次共改写 {len(changed_spans)} 个片段，"
        f"处理问题：{', '.join(issue_codes)}；"
        f"应用方式：{', '.join(rewrite_modes) if rewrite_modes else '无'}。"
    )
    if risk_alerts:
        summary = f"{summary} 其中 {len(risk_alerts)} 个片段带高风险提醒，建议后续复核。"
    return summary


def rewrite_story_spans_deterministic(
    *,
    content_markdown: str,
    analysis_report: dict[str, Any],
    style: str = "",
    profile: dict[str, Any] | None = None,
    rewrite_modes: list[str] | None = None,
    issue_codes: list[str] | None = None,
    max_spans: int = DEFAULT_MAX_SPANS,
) -> dict[str, Any]:
    normalized_rewrite_modes = normalize_rewrite_modes(rewrite_modes) if rewrite_modes else []
    normalized_issue_codes = normalize_issue_codes(issue_codes) if issue_codes else []
    targets = select_rewrite_targets(
        analysis_report,
        rewrite_modes=normalized_rewrite_modes or None,
        issue_codes=normalized_issue_codes or None,
        max_spans=max_spans,
    )
    resolved_style = resolve_style(profile, style)
    avoid_phrases = resolve_avoid_phrases(profile)

    changed_spans: list[dict[str, Any]] = []
    risk_alerts: list[dict[str, Any]] = []
    for target in targets:
        risk_flags = build_rewrite_risk_flags(target)
        rewritten_text, applied_modes = rewrite_span_text_deterministic(
            target.original_text,
            rewrite_modes=target.rewrite_modes,
            style=resolved_style,
            target_index=target.target_index,
            avoid_phrases=avoid_phrases,
        )
        if rewritten_text == target.original_text:
            continue
        if risk_flags:
            risk_alerts.append(build_risk_alert_record(target, risk_flags=risk_flags))
        changed_spans.append(
            {
                "target_index": target.target_index,
                "issue_code": target.issue_code,
                "chapter_number": target.chapter_number,
                "start_offset": target.start_offset,
                "end_offset": target.end_offset,
                "original_text": target.original_text,
                "rewritten_text": rewritten_text,
                "requested_rewrite_modes": target.rewrite_modes,
                "applied_rewrite_modes": applied_modes,
                "evidence": target.evidence,
                "risk_flags": list(risk_flags),
                "revision_reason": f"按 {', '.join(applied_modes)} 处理 {target.issue_code}。",
            }
        )

    after_content_markdown = apply_changed_spans(content_markdown, changed_spans) if changed_spans else content_markdown
    return {
        "generation_mode": "deterministic",
        "style": resolved_style,
        "changed_spans": changed_spans,
        "changed_span_count": len(changed_spans),
        "risk_alerts": risk_alerts,
        "risk_alert_count": len(risk_alerts),
        "after_content_markdown": after_content_markdown,
        "revision_summary": build_revision_summary(changed_spans, risk_alerts=risk_alerts),
    }
