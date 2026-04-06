from pathlib import Path

import pytest

from tools.story_idea_seed_generator import (
    generate_idea_seed_batch,
    load_idea_seed_sources,
    read_non_empty_lines,
)


def write_source_files(tmp_path: Path) -> Path:
    data_dir = tmp_path / "idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "Mystery - 悬疑 / 推理\nHistorical - 历史\nRomance - 浪漫 / 爱情\nSci-fi - 科幻\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "Body Swap - 身体互换\nMurders - 谋杀\nEnemies Become Lovers - 敌人变恋人\n"
        "Mistaken Identity - 身份误认\nPower Struggle - 权力斗争\n",
        encoding="utf-8",
        newline="\n",
    )
    return data_dir


def write_alternate_source_files(tmp_path: Path) -> Path:
    data_dir = tmp_path / "alternate-idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "Fantasy - 奇幻\nComedy - 喜剧\nThriller - 惊悚\nSlice of Life - 日常\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "Time Loop - 时间循环\nFamily Secret - 家族秘密\nTreasure Hunt - 寻宝\n"
        "False Memory - 虚假记忆\nCampus Rivalry - 校园竞争\n",
        encoding="utf-8",
        newline="\n",
    )
    return data_dir


def test_load_idea_seed_sources_skips_empty_lines(tmp_path: Path) -> None:
    data_dir = tmp_path / "idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "Mystery - 悬疑 / 推理\n\nHistorical - 历史\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "Body Swap - 身体互换\n\nMurders - 谋杀\n",
        encoding="utf-8",
        newline="\n",
    )

    type_pool, tag_pool = load_idea_seed_sources(data_dir)

    assert type_pool == ["Mystery - 悬疑 / 推理", "Historical - 历史"]
    assert tag_pool == ["Body Swap - 身体互换", "Murders - 谋杀"]


def test_read_non_empty_lines_preserves_non_empty_line_whitespace(tmp_path: Path) -> None:
    source_file = tmp_path / "source.txt"
    source_file.write_text(
        "  Mystery - 悬疑 / 推理  \n\n\tHistorical - 历史\t\n   \n",
        encoding="utf-8",
        newline="\n",
    )

    lines = read_non_empty_lines(source_file)

    assert lines == ["  Mystery - 悬疑 / 推理  ", "\tHistorical - 历史\t"]


def test_load_idea_seed_sources_preserves_non_empty_line_whitespace(tmp_path: Path) -> None:
    data_dir = tmp_path / "idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "  Mystery - 悬疑 / 推理  \n\n Historical - 历史 \n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "  Body Swap - 身体互换  \n\n Murders - 谋杀 \n",
        encoding="utf-8",
        newline="\n",
    )

    type_pool, tag_pool = load_idea_seed_sources(data_dir)

    assert type_pool == ["  Mystery - 悬疑 / 推理  ", " Historical - 历史 "]
    assert tag_pool == ["  Body Swap - 身体互换  ", " Murders - 谋杀 "]


def test_generate_idea_seed_batch_returns_requested_count(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)
    expected_types = {
        "Mystery - 悬疑 / 推理",
        "Historical - 历史",
        "Romance - 浪漫 / 爱情",
        "Sci-fi - 科幻",
    }
    expected_main_tags = {
        "Body Swap - 身体互换",
        "Murders - 谋杀",
        "Enemies Become Lovers - 敌人变恋人",
        "Mistaken Identity - 身份误认",
        "Power Struggle - 权力斗争",
    }

    batch = generate_idea_seed_batch(count=3, seed="demo-seed", data_dir=data_dir)

    assert batch.seed == "demo-seed"
    assert len(batch.items) == 3
    assert [item.id for item in batch.items] == ["idea-001", "idea-002", "idea-003"]
    assert all(len(item.types) == 2 for item in batch.items)
    assert all(len(item.main_tags) == 3 for item in batch.items)
    assert all(len(set(item.types)) == 2 for item in batch.items)
    assert all(len(set(item.main_tags)) == 3 for item in batch.items)
    assert all(set(item.types).issubset(expected_types) for item in batch.items)
    assert all(set(item.main_tags).issubset(expected_main_tags) for item in batch.items)


def test_generate_idea_seed_batch_uses_each_data_dir_source_pool(
    tmp_path: Path,
) -> None:
    primary_data_dir = write_source_files(tmp_path)
    alternate_data_dir = write_alternate_source_files(tmp_path)
    primary_types = {
        "Mystery - 悬疑 / 推理",
        "Historical - 历史",
        "Romance - 浪漫 / 爱情",
        "Sci-fi - 科幻",
    }
    primary_main_tags = {
        "Body Swap - 身体互换",
        "Murders - 谋杀",
        "Enemies Become Lovers - 敌人变恋人",
        "Mistaken Identity - 身份误认",
        "Power Struggle - 权力斗争",
    }
    alternate_types = {
        "Fantasy - 奇幻",
        "Comedy - 喜剧",
        "Thriller - 惊悚",
        "Slice of Life - 日常",
    }
    alternate_main_tags = {
        "Time Loop - 时间循环",
        "Family Secret - 家族秘密",
        "Treasure Hunt - 寻宝",
        "False Memory - 虚假记忆",
        "Campus Rivalry - 校园竞争",
    }

    primary_batch = generate_idea_seed_batch(
        count=3,
        seed="shared-seed",
        data_dir=primary_data_dir,
    )
    alternate_batch = generate_idea_seed_batch(
        count=3,
        seed="shared-seed",
        data_dir=alternate_data_dir,
    )

    assert primary_batch.seed == "shared-seed"
    assert alternate_batch.seed == "shared-seed"
    assert primary_batch.items != alternate_batch.items
    assert all(set(item.types).issubset(primary_types) for item in primary_batch.items)
    assert all(
        set(item.main_tags).issubset(primary_main_tags) for item in primary_batch.items
    )
    assert all(set(item.types).issubset(alternate_types) for item in alternate_batch.items)
    assert all(
        set(item.main_tags).issubset(alternate_main_tags)
        for item in alternate_batch.items
    )


def test_generate_idea_seed_batch_is_stable_for_same_seed(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)

    first = generate_idea_seed_batch(count=2, seed="same-seed", data_dir=data_dir)
    second = generate_idea_seed_batch(count=2, seed="same-seed", data_dir=data_dir)

    assert first == second


def test_generate_idea_seed_batch_rejects_invalid_count(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)

    with pytest.raises(ValueError, match="count 必须是大于等于 1 的整数。"):
        generate_idea_seed_batch(count=0, seed="demo-seed", data_dir=data_dir)


def test_generate_idea_seed_batch_rejects_bool_count(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)

    with pytest.raises(ValueError, match="count 必须是大于等于 1 的整数。"):
        generate_idea_seed_batch(count=True, seed="demo-seed", data_dir=data_dir)


def test_generate_idea_seed_batch_rejects_non_string_seed(tmp_path: Path) -> None:
    data_dir = write_source_files(tmp_path)

    with pytest.raises(ValueError, match="seed 必须是字符串。"):
        generate_idea_seed_batch(count=1, seed=123, data_dir=data_dir)


def test_generate_idea_seed_batch_rejects_insufficient_source_items(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "idea-data"
    data_dir.mkdir()
    (data_dir / "类型.txt").write_text(
        "Mystery - 悬疑 / 推理\n",
        encoding="utf-8",
        newline="\n",
    )
    (data_dir / "标签.txt").write_text(
        "Body Swap - 身体互换\nMurders - 谋杀\n",
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(
        ValueError,
        match="创意词池条目不足，至少需要 2 个类型和 3 个主标签。",
    ):
        generate_idea_seed_batch(count=1, seed="demo-seed", data_dir=data_dir)
