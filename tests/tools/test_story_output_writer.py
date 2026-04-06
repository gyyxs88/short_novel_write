from pathlib import Path

from tools.story_output_writer import (
    DEFAULT_OUTPUT_DIR,
    sanitize_title,
    write_story_markdown,
)


def test_sanitize_title_replaces_windows_invalid_characters() -> None:
    assert sanitize_title(' 禁忌:/标题?*<>|" ') == "禁忌_标题_"
    assert sanitize_title("   ") == "未命名短篇"


def test_write_story_markdown_creates_directory_and_writes_utf8_file(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "novels"
    content = "# 雨夜来信\n\n## 简介\n\n这是一段测试内容。\n\n## 正文\n\n### 1\n\n第一章正文。"

    result = write_story_markdown(
        title=' 雨夜:/来信? ',
        content=content,
        output_dir=output_dir,
    )

    assert result.output_dir == output_dir
    assert result.directory_created is True
    assert result.output_path == output_dir / "雨夜_来信_.md"
    assert result.output_path.read_text(encoding="utf-8") == content


def test_default_output_dir_uses_outputs_novels() -> None:
    assert DEFAULT_OUTPUT_DIR == Path("outputs") / "novels"
