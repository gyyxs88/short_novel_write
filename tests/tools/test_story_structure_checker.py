from pathlib import Path

from tools.story_structure_checker import check_story_file, check_story_markdown


VALID_STORY = """# 雨夜来信

## 简介

葬礼结束后，失踪三年的姐姐忽然用旧号码给我发来短信。她说今晚无论谁来敲门，都别让那个人进屋，因为真正死掉的人，也许根本不是她。

## 正文

### 1

我是在送走最后一位亲戚之后，才看到那条短信的。

### 2

母亲说我脸色发白，可她不知道，那个号码三年前就跟着姐姐一起停用了。

### 3

晚上九点，门铃真的响了。猫眼外站着的人，穿着姐姐下葬那天的黑裙子。
"""


def test_check_story_markdown_accepts_complete_story() -> None:
    report = check_story_markdown(
        VALID_STORY,
        target_char_range=(60, 500),
        summary_char_range=(30, 120),
    )

    assert report.is_valid is True
    assert report.title == "雨夜来信"
    assert report.chapter_numbers == [1, 2, 3]
    assert report.issues == []


def test_check_story_markdown_reports_missing_summary_and_broken_chapter_sequence() -> None:
    invalid_story = """# 空屋回声

## 正文

### 1

她回到老宅时，只看见厨房里正在冒热气的锅。

### 3

可那栋房子，已经空了七年。
"""

    report = check_story_markdown(
        invalid_story,
        target_char_range=(10, 500),
        summary_char_range=(30, 120),
    )

    assert report.is_valid is False
    assert any("简介" in issue for issue in report.issues)
    assert any("章节编号" in issue for issue in report.issues)


def test_check_story_file_reads_utf8_markdown(tmp_path: Path) -> None:
    story_file = tmp_path / "story.md"
    story_file.write_text(VALID_STORY, encoding="utf-8")

    report = check_story_file(
        story_file,
        target_char_range=(60, 500),
        summary_char_range=(30, 120),
    )

    assert report.is_valid is True
    assert report.body_chars > 0


def test_check_story_markdown_accepts_small_overflow() -> None:
    small_overflow_story = """# 雨夜来信

## 简介

""" + ("概" * 125) + """

## 正文

### 1

""" + ("文" * 390) + """
"""

    report = check_story_markdown(
        small_overflow_story,
        target_char_range=(60, 500),
        summary_char_range=(30, 120),
    )

    assert report.is_valid is True
    assert report.summary_chars == 125


def test_check_story_markdown_accepts_overlong_body_when_minimum_is_met() -> None:
    overlong_story = """# 雨夜来信

## 简介

""" + ("概" * 80) + """

## 正文

### 1

""" + ("文" * 600) + """

### 2

""" + ("文" * 600) + """
"""

    report = check_story_markdown(
        overlong_story,
        target_char_range=(60, 500),
        summary_char_range=(30, 120),
    )

    assert report.is_valid is True
    assert report.body_chars == 1200
