from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from tools.release_package_builder import build_release_package, validate_output_dir


def test_build_release_package_creates_clean_zip(tmp_path: Path) -> None:
    source_dir = tmp_path / "publish_repo"
    output_dir = tmp_path / "release_artifacts"
    (source_dir / "tools").mkdir(parents=True)
    (source_dir / ".git").mkdir()
    (source_dir / "__pycache__").mkdir()
    (source_dir / ".pytest_cache").mkdir()
    (source_dir / "tests" / "temp").mkdir(parents=True)
    (source_dir / "local").mkdir()
    (source_dir / "outputs").mkdir()

    (source_dir / "README.md").write_text("# demo\n", encoding="utf-8")
    (source_dir / "tools" / "story_cli.py").write_text("print('ok')\n", encoding="utf-8")
    (source_dir / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (source_dir / "__pycache__" / "story.cpython-313.pyc").write_bytes(b"pyc")
    (source_dir / ".pytest_cache" / "cache.txt").write_text("cache\n", encoding="utf-8")
    (source_dir / "tests" / "temp" / "ssh.log").write_text("secret log\n", encoding="utf-8")
    (source_dir / "local" / "secret.txt").write_text("secret\n", encoding="utf-8")
    (source_dir / "outputs" / "draft.md").write_text("draft\n", encoding="utf-8")

    result = build_release_package(
        source_dir=source_dir,
        output_dir=output_dir,
        release_name="short_novel_write-v0.1.0",
    )

    archive_path = Path(result["archive_path"])
    assert archive_path.exists()
    assert result["archive_name"] == "short_novel_write-v0.1.0.zip"
    assert result["file_count"] == 2

    with zipfile.ZipFile(archive_path) as archive:
        assert sorted(archive.namelist()) == ["README.md", "tools/story_cli.py"]


def test_validate_output_dir_rejects_output_inside_source_dir(tmp_path: Path) -> None:
    source_dir = tmp_path / "publish_repo"
    source_dir.mkdir()
    output_dir = source_dir / "releases"

    with pytest.raises(ValueError, match="输出目录不能放在源码目录里面"):
        validate_output_dir(source_dir, output_dir)


def test_build_release_package_supports_extra_excludes(tmp_path: Path) -> None:
    source_dir = tmp_path / "publish_repo"
    output_dir = tmp_path / "release_artifacts"
    (source_dir / "docs").mkdir(parents=True)
    (source_dir / "README.md").write_text("# demo\n", encoding="utf-8")
    (source_dir / "docs" / "internal.md").write_text("internal\n", encoding="utf-8")

    result = build_release_package(
        source_dir=source_dir,
        output_dir=output_dir,
        release_name="short_novel_write-v0.1.1",
        exclude_patterns=["docs/"],
    )

    with zipfile.ZipFile(Path(result["archive_path"])) as archive:
        assert archive.namelist() == ["README.md"]


def test_build_release_package_excludes_nested_temp_dirs(tmp_path: Path) -> None:
    source_dir = tmp_path / "publish_repo"
    output_dir = tmp_path / "release_artifacts"
    (source_dir / "tests" / "fixtures" / "temp").mkdir(parents=True)
    (source_dir / "README.md").write_text("# demo\n", encoding="utf-8")
    (source_dir / "tests" / "fixtures" / "temp" / "debug.txt").write_text("debug\n", encoding="utf-8")

    result = build_release_package(
        source_dir=source_dir,
        output_dir=output_dir,
        release_name="short_novel_write-v0.1.2",
    )

    with zipfile.ZipFile(Path(result["archive_path"])) as archive:
        assert archive.namelist() == ["README.md"]
