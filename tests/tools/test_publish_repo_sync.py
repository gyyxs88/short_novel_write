from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.publish_repo_sync import (
    load_sync_config,
    normalize_exclude_patterns,
    sync_publish_repo,
    validate_target_dir,
)


def test_validate_target_dir_rejects_nested_publish_dir(tmp_path: Path) -> None:
    source_dir = tmp_path / "dev_repo"
    nested_target_dir = source_dir / "publish_repo"
    source_dir.mkdir()

    with pytest.raises(ValueError, match="不能放在开发目录里面"):
        validate_target_dir(source_dir, nested_target_dir)


def test_validate_target_dir_rejects_parent_publish_dir(tmp_path: Path) -> None:
    publish_dir = tmp_path / "workspace"
    source_dir = publish_dir / "dev_repo"
    source_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="不能作为开发目录的父目录"):
        validate_target_dir(source_dir, publish_dir)


def test_load_sync_config_resolves_target_dir_from_project_root(tmp_path: Path) -> None:
    source_dir = tmp_path / "short_novel_write"
    source_dir.mkdir()
    config_path = source_dir / "local" / "publish_sync.local.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps(
            {
                "target_dir": "../short_novel_write_publish",
                "exclude_patterns": ["docs/private/"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    loaded = load_sync_config(config_path, source_dir)

    assert loaded["target_dir"] == (tmp_path / "short_novel_write_publish").resolve(strict=False)
    assert "docs/memory/" in loaded["exclude_patterns"]
    assert "docs/private/" in loaded["exclude_patterns"]


def test_sync_publish_repo_skips_private_and_generated_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "dev_repo"
    target_dir = tmp_path / "publish_repo"
    source_dir.mkdir()
    (source_dir / "tools").mkdir()
    (source_dir / "tests" / "tools").mkdir(parents=True)
    (source_dir / "local").mkdir()
    (source_dir / "outputs").mkdir()
    (source_dir / "docs" / "memory").mkdir(parents=True)
    (source_dir / "docs" / "superpowers" / "plans").mkdir(parents=True)
    (source_dir / "zhihu-yanxuan-short-story2").mkdir()
    (source_dir / "README.md").write_text("# demo\n", encoding="utf-8")
    (source_dir / "AGENTS.md").write_text("private rules\n", encoding="utf-8")
    (source_dir / "tools" / "story_cli.py").write_text("print('ok')\n", encoding="utf-8")
    (source_dir / "tools" / "dev_todoist_cli.py").write_text("print('todoist')\n", encoding="utf-8")
    (source_dir / "tests" / "tools" / "test_dev_todoist_cli.py").write_text("def test_ok(): pass\n", encoding="utf-8")
    (source_dir / "local" / "dev_env.ps1").write_text("$env:KEY='secret'\n", encoding="utf-8")
    (source_dir / "outputs" / "report.json").write_text("{}\n", encoding="utf-8")
    (source_dir / "docs" / "memory" / "note.md").write_text("private\n", encoding="utf-8")
    (source_dir / "docs" / "superpowers" / "plans" / "plan.md").write_text("internal plan\n", encoding="utf-8")
    (source_dir / "zhihu-yanxuan-short-story2" / "SKILL.md").write_text("reference project\n", encoding="utf-8")
    (source_dir / ".env").write_text("API_KEY=secret\n", encoding="utf-8")

    result = sync_publish_repo(source_dir=source_dir, target_dir=target_dir)

    assert result["copied_count"] == 2
    assert (target_dir / "README.md").exists()
    assert (target_dir / "tools" / "story_cli.py").exists()
    assert not (target_dir / "AGENTS.md").exists()
    assert not (target_dir / "local" / "dev_env.ps1").exists()
    assert not (target_dir / "outputs" / "report.json").exists()
    assert not (target_dir / "docs" / "memory" / "note.md").exists()
    assert not (target_dir / "docs" / "superpowers" / "plans" / "plan.md").exists()
    assert not (target_dir / "tools" / "dev_todoist_cli.py").exists()
    assert not (target_dir / "tests" / "tools" / "test_dev_todoist_cli.py").exists()
    assert not (target_dir / "zhihu-yanxuan-short-story2" / "SKILL.md").exists()
    assert not (target_dir / ".env").exists()


def test_sync_publish_repo_reports_stale_files_in_target(tmp_path: Path) -> None:
    source_dir = tmp_path / "dev_repo"
    target_dir = tmp_path / "publish_repo"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / "README.md").write_text("# demo\n", encoding="utf-8")
    (target_dir / "README.md").write_text("# old\n", encoding="utf-8")
    (target_dir / "old.txt").write_text("stale\n", encoding="utf-8")

    result = sync_publish_repo(source_dir=source_dir, target_dir=target_dir)

    assert result["copied_files"] == ["README.md"]
    assert result["stale_target_files"] == ["old.txt"]
    assert (target_dir / "README.md").read_text(encoding="utf-8") == "# demo\n"


def test_sync_publish_repo_reports_excluded_files_already_existing_in_target(tmp_path: Path) -> None:
    source_dir = tmp_path / "dev_repo"
    target_dir = tmp_path / "publish_repo"
    source_dir.mkdir()
    target_dir.mkdir()
    (source_dir / "README.md").write_text("# demo\n", encoding="utf-8")
    (target_dir / "AGENTS.md").write_text("old rules\n", encoding="utf-8")
    (target_dir / "docs" / "superpowers").mkdir(parents=True)
    (target_dir / "docs" / "superpowers" / "plan.md").write_text("old plan\n", encoding="utf-8")

    result = sync_publish_repo(source_dir=source_dir, target_dir=target_dir)

    assert result["excluded_target_file_count"] == 2
    assert result["excluded_target_files"] == ["AGENTS.md", "docs/superpowers/plan.md"]
