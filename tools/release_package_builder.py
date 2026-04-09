from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any
import zipfile


DEFAULT_EXCLUDE_PATTERNS = [
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".venv/",
    "local/",
    "outputs/",
    "temp/",
    "*/temp/",
    ".env",
    ".env.*",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "Thumbs.db",
]


def _normalize_pattern(value: str) -> str:
    return value.strip().replace("\\", "/")


def _contains_glob(pattern: str) -> bool:
    return any(symbol in pattern for symbol in "*?[]")


def _iter_path_prefixes(normalized_path: str) -> list[str]:
    parts = normalized_path.split("/")
    return ["/".join(parts[:index]) for index in range(1, len(parts) + 1)]


def normalize_exclude_patterns(extra_patterns: list[str] | None = None) -> list[str]:
    patterns: list[str] = []
    for raw_pattern in [*DEFAULT_EXCLUDE_PATTERNS, *(extra_patterns or [])]:
        pattern = _normalize_pattern(str(raw_pattern))
        if pattern and pattern not in patterns:
            patterns.append(pattern)
    return patterns


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_output_dir(source_dir: Path, output_dir: Path) -> None:
    normalized_source = source_dir.resolve(strict=False)
    normalized_output = output_dir.resolve(strict=False)
    if normalized_output == normalized_source:
        raise ValueError("发布包输出目录不能和源码目录相同。")
    if _is_relative_to(normalized_output, normalized_source):
        raise ValueError("发布包输出目录不能放在源码目录里面，避免把 zip 再打回发布仓库。")


def normalize_release_name(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("release_name 不能为空。")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("release_name 不能包含路径分隔符。")
    if normalized.lower().endswith(".zip"):
        normalized = normalized[:-4].rstrip()
    if not normalized:
        raise ValueError("release_name 不能为空。")
    return normalized


def should_exclude(relative_path: Path, patterns: list[str]) -> bool:
    normalized_path = relative_path.as_posix()
    for pattern in patterns:
        if pattern.endswith("/"):
            prefix = pattern[:-1]
            if not _contains_glob(prefix):
                if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
                    return True
                continue
            if any(fnmatch.fnmatch(prefix_candidate, prefix) for prefix_candidate in _iter_path_prefixes(normalized_path)):
                return True
            continue
        if fnmatch.fnmatch(normalized_path, pattern):
            return True
        if "/" not in pattern and fnmatch.fnmatch(relative_path.name, pattern):
            return True
    return False


def iter_release_files(source_dir: Path, patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for child in sorted(source_dir.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not child.is_file() or child.is_symlink():
            continue
        relative_path = child.relative_to(source_dir)
        if should_exclude(relative_path, patterns):
            continue
        files.append(relative_path)
    return files


def build_release_package(
    *,
    source_dir: Path,
    output_dir: Path,
    release_name: str,
    exclude_patterns: list[str] | None = None,
) -> dict[str, Any]:
    normalized_source = source_dir.resolve(strict=False)
    normalized_output = output_dir.resolve(strict=False)
    if not normalized_source.exists():
        raise FileNotFoundError(f"源码目录不存在：{normalized_source}")
    if not normalized_source.is_dir():
        raise ValueError(f"source_dir 不是目录：{normalized_source}")

    validate_output_dir(normalized_source, normalized_output)
    normalized_release_name = normalize_release_name(release_name)
    patterns = normalize_exclude_patterns(exclude_patterns)
    release_files = iter_release_files(normalized_source, patterns)

    normalized_output.mkdir(parents=True, exist_ok=True)
    archive_path = normalized_output / f"{normalized_release_name}.zip"

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in release_files:
            archive.write(normalized_source / relative_path, arcname=relative_path.as_posix())

    return {
        "ok": True,
        "source_dir": str(normalized_source),
        "output_dir": str(normalized_output),
        "archive_path": str(archive_path),
        "archive_name": archive_path.name,
        "release_name": normalized_release_name,
        "file_count": len(release_files),
        "archive_size_bytes": archive_path.stat().st_size,
        "exclude_patterns": patterns,
        "files": [item.as_posix() for item in release_files],
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从发布目录生成用于 GitHub Releases 的干净 zip 包。")
    parser.add_argument("--source-dir", required=True, help="要打包的发布目录路径。")
    parser.add_argument("--output-dir", required=True, help="zip 输出目录。必须位于源码目录外部。")
    parser.add_argument("--release-name", required=True, help="发布包名称，例如 short_novel_write-v0.1.0。")
    parser.add_argument("--exclude", action="append", default=[], help="额外排除规则，可重复传。")
    parser.add_argument("--report-path", help="把执行结果写入 JSON 文件。")
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    result = build_release_package(
        source_dir=Path(args.source_dir),
        output_dir=Path(args.output_dir),
        release_name=args.release_name,
        exclude_patterns=list(args.exclude or []),
    )

    result_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report_path:
        report_path = Path(args.report_path)
        if not report_path.is_absolute():
            report_path = Path.cwd() / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(result_text + "\n", encoding="utf-8", newline="\n")

    print(result_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
