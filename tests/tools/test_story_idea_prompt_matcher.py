from __future__ import annotations

from pathlib import Path

import pytest

from tools.story_idea_prompt_matcher import match_idea_cards_from_prompt


def write_source_files(tmp_path: Path) -> Path:
    data_dir = tmp_path / "idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "School Life - 校园生活\nMystery - 旧案悬疑\nModern - 现代\nRomance - 恋爱\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "Missing Person - 失踪\nFirst Love - 初恋\nSecret Past - 隐秘过去\n"
        "Reunion - 重逢\nMisunderstanding - 误会\n",
        encoding="utf-8",
        newline="\n",
    )
    return data_dir


def write_duplicate_source_files(tmp_path: Path) -> Path:
    data_dir = tmp_path / "duplicate-idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "Modern - 现代\nModern - 现代\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "Missing Person - 失踪\nMissing Person - 失踪\nFirst Love - 初恋\n",
        encoding="utf-8",
        newline="\n",
    )
    return data_dir


def test_match_idea_cards_from_prompt_prefers_overlapping_terms(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)

    batch = match_idea_cards_from_prompt(
        prompt="我想写校园初恋和失踪旧案",
        count=2,
        data_dir=data_dir,
    )

    assert batch.prompt == "我想写校园初恋和失踪旧案"
    assert len(batch.items) == 2
    assert batch.items[0].types == ["Mystery - 旧案悬疑", "School Life - 校园生活"]
    assert batch.items[0].main_tags == [
        "First Love - 初恋",
        "Missing Person - 失踪",
        "Secret Past - 隐秘过去",
    ]


def test_match_idea_cards_from_prompt_is_stable_for_same_prompt(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)

    first = match_idea_cards_from_prompt(
        prompt="我想写校园初恋和失踪旧案",
        count=2,
        data_dir=data_dir,
    )
    second = match_idea_cards_from_prompt(
        prompt="我想写校园初恋和失踪旧案",
        count=2,
        data_dir=data_dir,
    )

    assert first == second


def test_match_idea_cards_from_prompt_rejects_blank_prompt(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)

    with pytest.raises(ValueError, match="prompt 必须是非空字符串。"):
        match_idea_cards_from_prompt(prompt="   ", count=1, data_dir=data_dir)


def test_match_idea_cards_from_prompt_rejects_duplicate_dirty_source_pool(
    tmp_path: Path,
) -> None:
    data_dir = write_duplicate_source_files(tmp_path)

    with pytest.raises(ValueError, match="创意词池条目不足"):
        match_idea_cards_from_prompt(
            prompt="我想写失踪和初恋",
            count=1,
            data_dir=data_dir,
        )
