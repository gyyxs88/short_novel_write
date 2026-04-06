from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tools.story_structure_checker import (
    TITLE_PATTERN,
    count_content_chars,
    extract_chapters,
    extract_section,
)


OPENING_SIGNAL_KEYWORDS = (
    "忽然",
    "突然",
    "失踪",
    "短信",
    "敲门",
    "今晚",
    "真相",
    "秘密",
    "死",
    "别",
    "不能",
    "如果",
)
MIDDLE_SIGNAL_KEYWORDS = (
    "却",
    "但是",
    "然而",
    "原来",
    "直到",
    "偏偏",
    "结果",
    "没想到",
    "才知道",
)
ENDING_SIGNAL_KEYWORDS = (
    "终于",
    "明白",
    "原来",
    "答案",
    "真相",
    "决定",
    "从此",
    "放下",
    "回头",
    "不是",
)
TITLE_STOP_CHARS = {
    "的",
    "了",
    "和",
    "与",
    "在",
    "是",
    "我",
    "你",
    "他",
    "她",
    "它",
    "这",
    "那",
    "个",
}


@dataclass(slots=True)
class StoryQualityReport:
    title: str = ""
    opening_signal_hits: list[str] = field(default_factory=list)
    middle_signal_hits: list[str] = field(default_factory=list)
    ending_signal_hits: list[str] = field(default_factory=list)
    chapter_char_counts: list[int] = field(default_factory=list)
    title_overlap_chars: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def is_passable(self) -> bool:
        return not self.issues


def collect_signal_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if keyword in text and keyword not in hits:
            hits.append(keyword)
    return hits


def extract_title(markdown_text: str) -> str:
    match = TITLE_PATTERN.search(markdown_text)
    if not match:
        return ""
    return match.group(1).strip()


def extract_title_overlap_chars(title: str, story_text: str) -> list[str]:
    overlap: list[str] = []
    for char in title:
        if char.isspace() or char in TITLE_STOP_CHARS:
            continue
        if char in story_text and char not in overlap:
            overlap.append(char)
    return overlap


def build_suggestions(issues: list[str]) -> list[str]:
    suggestions: list[str] = []
    if any("开头" in issue for issue in issues):
        suggestions.append("在简介或第一章前 200 字里更早抛出异常、代价或悬念。")
    if any("中段" in issue for issue in issues):
        suggestions.append("给中段增加一次关系、处境或认知偏转，避免章节只重复情绪。")
    if any("结尾" in issue for issue in issues):
        suggestions.append("让最后一章明确回应主冲突，补足真相、选择或代价回收。")
    if any("标题" in issue for issue in issues):
        suggestions.append("把标题收紧到 6-16 个汉字，并让它和正文里的关键意象或冲突发生关联。")
    return suggestions


def check_story_quality_markdown(markdown_text: str) -> StoryQualityReport:
    report = StoryQualityReport()
    report.title = extract_title(markdown_text)

    summary_text = extract_section(markdown_text, "简介")
    body_text = extract_section(markdown_text, "正文")
    chapters = extract_chapters(body_text)

    if not report.title:
        report.issues.append("标题缺失，无法进行质量检查。")
        report.suggestions = build_suggestions(report.issues)
        return report

    if not summary_text or not chapters:
        report.issues.append("结构不完整，质量检查至少需要标题、简介和正文章节。")
        report.suggestions = build_suggestions(report.issues)
        return report

    first_chapter_text = chapters[0][1]
    opening_text = f"{summary_text}\n{first_chapter_text}"
    report.opening_signal_hits = collect_signal_hits(opening_text, OPENING_SIGNAL_KEYWORDS)
    opening_chars = count_content_chars(opening_text)
    if opening_chars < 120 or not report.opening_signal_hits:
        report.issues.append("开头钩子偏弱，前段缺少足够明显的异常、冲突或悬念信号。")

    report.chapter_char_counts = [count_content_chars(chapter_body) for _, chapter_body in chapters]

    middle_chapters = chapters[1:-1]
    middle_text = "\n".join(chapter_body for _, chapter_body in middle_chapters)
    report.middle_signal_hits = collect_signal_hits(middle_text, MIDDLE_SIGNAL_KEYWORDS)
    if middle_chapters:
        if min(count_content_chars(chapter_body) for _, chapter_body in middle_chapters) < 30:
            report.issues.append("中段推进偏弱，存在过短章节，像在跳过关键推进。")
        elif not report.middle_signal_hits:
            report.issues.append("中段推进偏弱，缺少明显的偏转或升级信号。")

    ending_text = chapters[-1][1]
    ending_chars = count_content_chars(ending_text)
    report.ending_signal_hits = collect_signal_hits(ending_text, ENDING_SIGNAL_KEYWORDS)
    if ending_chars < 40 or not report.ending_signal_hits:
        report.issues.append("结尾回收偏弱，最后一章缺少清晰的回应、揭示或落点。")

    title_length = len(report.title.strip())
    if title_length < 2 or title_length > 16:
        report.issues.append("标题长度不理想，默认应尽量控制在 6-16 个汉字。")

    report.title_overlap_chars = extract_title_overlap_chars(
        report.title,
        f"{summary_text}\n{body_text}",
    )
    if not report.title_overlap_chars:
        report.issues.append("标题贴题度偏弱，正文里缺少能与标题形成呼应的关键意象。")

    report.suggestions = build_suggestions(report.issues)
    return report


def check_story_quality_file(file_path: str | Path) -> StoryQualityReport:
    markdown_text = Path(file_path).read_text(encoding="utf-8")
    return check_story_quality_markdown(markdown_text)
