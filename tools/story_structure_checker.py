from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re


TITLE_PATTERN = re.compile(r"(?m)^#\s+(.+?)\s*$")
SECTION_PATTERN_TEMPLATE = r"(?ms)^##\s+{title}\s*$\s*(.*?)(?=^##\s+|\Z)"
CHAPTER_PATTERN = re.compile(r"(?ms)^###\s+(\d+)\s*$\s*(.*?)(?=^###\s+\d+\s*$|\Z)")
SUMMARY_MAX_OVERFLOW_FLOOR = 5
SUMMARY_MAX_OVERFLOW_CAP = 20
TOTAL_MAX_OVERFLOW_FLOOR = 100
TOTAL_MAX_OVERFLOW_CAP = 300


@dataclass(slots=True)
class StoryStructureReport:
    title: str = ""
    summary_chars: int = 0
    body_chars: int = 0
    chapter_numbers: list[int] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def count_content_chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def calculate_small_overflow_allowance(
    max_chars: int,
    *,
    floor: int,
    cap: int,
) -> int:
    return max(floor, min(cap, max(1, max_chars // 10)))


def extract_section(markdown_text: str, title: str) -> str:
    pattern = re.compile(SECTION_PATTERN_TEMPLATE.format(title=re.escape(title)))
    match = pattern.search(markdown_text)
    if not match:
        return ""
    return match.group(1).strip()


def extract_chapters(body_text: str) -> list[tuple[int, str]]:
    chapters: list[tuple[int, str]] = []
    for match in CHAPTER_PATTERN.finditer(body_text):
        chapter_number = int(match.group(1))
        chapter_body = match.group(2).strip()
        chapters.append((chapter_number, chapter_body))
    return chapters


def check_story_markdown(
    markdown_text: str,
    target_char_range: tuple[int, int] | None = None,
    summary_char_range: tuple[int, int] = (50, 120),
) -> StoryStructureReport:
    report = StoryStructureReport()

    title_match = TITLE_PATTERN.search(markdown_text)
    if title_match:
        report.title = title_match.group(1).strip()
    else:
        report.issues.append("缺少标题。")

    summary_text = extract_section(markdown_text, "简介")
    if not summary_text:
        report.issues.append("缺少简介部分。")
    else:
        report.summary_chars = count_content_chars(summary_text)
        min_summary_chars, max_summary_chars = summary_char_range
        max_summary_with_overflow = max_summary_chars + calculate_small_overflow_allowance(
            max_summary_chars,
            floor=SUMMARY_MAX_OVERFLOW_FLOOR,
            cap=SUMMARY_MAX_OVERFLOW_CAP,
        )
        if report.summary_chars < min_summary_chars or report.summary_chars > max_summary_with_overflow:
            report.issues.append(
                f"简介字数不符合要求，应在 {min_summary_chars}-{max_summary_with_overflow} 字之间。"
            )

    body_text = extract_section(markdown_text, "正文")
    if not body_text:
        report.issues.append("缺少正文部分。")
        return report

    chapters = extract_chapters(body_text)
    if not chapters:
        report.issues.append("正文中缺少章节。")
        return report

    report.chapter_numbers = [chapter_number for chapter_number, _ in chapters]
    expected_numbers = list(range(1, len(report.chapter_numbers) + 1))
    if report.chapter_numbers != expected_numbers:
        report.issues.append("章节编号不连续，应从 1 开始依次递增。")

    report.body_chars = sum(count_content_chars(chapter_body) for _, chapter_body in chapters)

    if target_char_range is not None:
        total_chars = report.summary_chars + report.body_chars
        min_chars, max_chars = target_char_range
        max_total_with_overflow = max_chars + calculate_small_overflow_allowance(
            max_chars,
            floor=TOTAL_MAX_OVERFLOW_FLOOR,
            cap=TOTAL_MAX_OVERFLOW_CAP,
        )
        if total_chars < min_chars or total_chars > max_total_with_overflow:
            report.issues.append(f"正文总字数不符合要求，应在 {min_chars}-{max_total_with_overflow} 字之间。")

    return report


def check_story_file(
    file_path: str | Path,
    target_char_range: tuple[int, int] | None = None,
    summary_char_range: tuple[int, int] = (50, 120),
) -> StoryStructureReport:
    markdown_text = Path(file_path).read_text(encoding="utf-8")
    return check_story_markdown(
        markdown_text,
        target_char_range=target_char_range,
        summary_char_range=summary_char_range,
    )
