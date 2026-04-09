from __future__ import annotations

import argparse
import filecmp
import json
import shutil
from pathlib import Path
from typing import Any
import fnmatch


DEFAULT_EXCLUDE_PATTERNS = [
    ".git/",
    ".venv/",
    ".pytest_cache/",
    "__pycache__/",
    "AGENTS.md",
    "docs/memory/",
    "docs/superpowers/",
    "outputs/",
    "temp/",
    "*/temp/",
    "local/",
    ".env",
    ".env.*",
    "tools/dev_todoist_cli.py",
    "tests/tools/test_dev_todoist_cli.py",
    "zhihu-yanxuan-short-story2/",
    "*.pyc",
]


def resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _normalize_nonempty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip()


def _path_is_relative_to(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _contains_glob(pattern: str) -> bool:
    return any(symbol in pattern for symbol in "*?[]")


def _iter_path_prefixes(normalized_path: str) -> list[str]:
    parts = normalized_path.split("/")
    return ["/".join(parts[:index]) for index in range(1, len(parts) + 1)]


def normalize_exclude_patterns(extra_patterns: list[str] | None = None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    candidates = list(DEFAULT_EXCLUDE_PATTERNS)
    if extra_patterns is not None:
        if not isinstance(extra_patterns, list):
            raise ValueError("exclude_patterns 必须是字符串数组。")
        candidates.extend(extra_patterns)

    for raw_pattern in candidates:
        pattern = _normalize_nonempty_string(raw_pattern, "exclude_patterns").replace("\\", "/")
        if pattern not in seen:
            normalized.append(pattern)
            seen.add(pattern)
    return normalized


def resolve_target_dir(target_dir: str | Path, source_dir: Path) -> Path:
    raw_target = Path(_normalize_nonempty_string(str(target_dir), "target_dir")).expanduser()
    if not raw_target.is_absolute():
        raw_target = source_dir / raw_target
    return raw_target.resolve(strict=False)


def validate_target_dir(source_dir: Path, target_dir: Path) -> None:
    resolved_source = source_dir.resolve(strict=False)
    resolved_target = target_dir.resolve(strict=False)

    if resolved_source == resolved_target:
        raise ValueError("发布目录不能和开发目录是同一个目录。")
    if _path_is_relative_to(resolved_target, resolved_source):
        raise ValueError("发布目录不能放在开发目录里面，必须使用兄弟目录或其他外部目录。")
    if _path_is_relative_to(resolved_source, resolved_target):
        raise ValueError("发布目录不能作为开发目录的父目录，避免同步时误覆盖开发文件。")


def load_sync_config(config_path: Path, source_dir: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"未找到配置文件：{config_path}")

    raw_text = config_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        raise ValueError("同步配置文件不能为空。")

    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("同步配置文件必须是 JSON 对象。")

    target_dir = resolve_target_dir(data.get("target_dir"), source_dir)
    exclude_patterns = normalize_exclude_patterns(data.get("exclude_patterns"))
    return {
        "target_dir": target_dir,
        "exclude_patterns": exclude_patterns,
    }


def should_exclude(relative_path: Path, patterns: list[str]) -> bool:
    normalized_path = relative_path.as_posix()
    file_name = relative_path.name
    for pattern in patterns:
        if pattern.endswith("/"):
            prefix = pattern.rstrip("/")
            if not _contains_glob(prefix):
                if normalized_path == prefix or normalized_path.startswith(prefix + "/"):
                    return True
                continue
            if any(fnmatch.fnmatch(prefix_candidate, prefix) for prefix_candidate in _iter_path_prefixes(normalized_path)):
                return True
            continue
        if fnmatch.fnmatch(normalized_path, pattern) or fnmatch.fnmatch(file_name, pattern):
            return True
    return False


def iter_sync_files(source_dir: Path, patterns: list[str]) -> list[Path]:
    collected: list[Path] = []

    def walk(current_dir: Path) -> None:
        for child in sorted(current_dir.iterdir(), key=lambda item: item.name.lower()):
            relative_path = child.relative_to(source_dir)
            if should_exclude(relative_path, patterns):
                continue
            if child.is_symlink():
                continue
            if child.is_dir():
                walk(child)
                continue
            if child.is_file():
                collected.append(relative_path)

    walk(source_dir)
    return collected


def find_stale_target_files(target_dir: Path, expected_files: set[str], patterns: list[str]) -> list[str]:
    if not target_dir.exists():
        return []

    stale_files: list[str] = []
    for child in sorted(target_dir.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not child.is_file() or child.is_symlink():
            continue
        relative_path = child.relative_to(target_dir)
        if should_exclude(relative_path, patterns):
            continue
        normalized_path = relative_path.as_posix()
        if normalized_path not in expected_files:
            stale_files.append(normalized_path)
    return stale_files


def find_excluded_target_files(target_dir: Path, patterns: list[str]) -> list[str]:
    if not target_dir.exists():
        return []

    excluded_files: list[str] = []
    for child in sorted(target_dir.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not child.is_file() or child.is_symlink():
            continue
        relative_path = child.relative_to(target_dir)
        normalized_path = relative_path.as_posix()
        if normalized_path.startswith(".git/"):
            continue
        if should_exclude(relative_path, patterns):
            excluded_files.append(normalized_path)
    return excluded_files


def sync_publish_repo(
    *,
    source_dir: Path,
    target_dir: Path,
    exclude_patterns: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    normalized_source = source_dir.resolve(strict=False)
    normalized_target = target_dir.resolve(strict=False)
    patterns = normalize_exclude_patterns(exclude_patterns)
    validate_target_dir(normalized_source, normalized_target)

    source_files = iter_sync_files(normalized_source, patterns)
    expected_files = {path.as_posix() for path in source_files}

    copied_files: list[str] = []
    unchanged_files: list[str] = []

    if not dry_run:
        normalized_target.mkdir(parents=True, exist_ok=True)

    for relative_path in source_files:
        source_file = normalized_source / relative_path
        target_file = normalized_target / relative_path

        if target_file.exists() and filecmp.cmp(source_file, target_file, shallow=False):
            unchanged_files.append(relative_path.as_posix())
            continue

        copied_files.append(relative_path.as_posix())
        if dry_run:
            continue
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)

    stale_target_files = find_stale_target_files(normalized_target, expected_files, patterns)
    excluded_target_files = find_excluded_target_files(normalized_target, patterns)

    return {
        "ok": True,
        "source_dir": str(normalized_source),
        "target_dir": str(normalized_target),
        "dry_run": dry_run,
        "exclude_patterns": patterns,
        "copied_count": len(copied_files),
        "unchanged_count": len(unchanged_files),
        "stale_target_file_count": len(stale_target_files),
        "excluded_target_file_count": len(excluded_target_files),
        "copied_files": copied_files,
        "stale_target_files": stale_target_files,
        "excluded_target_files": excluded_target_files,
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="把开发仓库同步到外部发布目录。")
    parser.add_argument("--target-dir", help="发布目录路径。建议使用开发目录的兄弟目录。")
    parser.add_argument("--config", help="本地同步配置文件路径，例如 local/publish_sync.local.json。")
    parser.add_argument("--dry-run", action="store_true", help="只输出将要同步的结果，不实际复制文件。")
    parser.add_argument("--report-path", help="把执行结果写入 JSON 文件。")
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()
    source_dir = resolve_project_root()

    if args.config:
        config = load_sync_config(Path(args.config), source_dir)
        target_dir = config["target_dir"]
        exclude_patterns = config["exclude_patterns"]
    else:
        if not args.target_dir:
            parser.error("必须提供 --target-dir 或 --config。")
        target_dir = resolve_target_dir(args.target_dir, source_dir)
        exclude_patterns = normalize_exclude_patterns()

    result = sync_publish_repo(
        source_dir=source_dir,
        target_dir=target_dir,
        exclude_patterns=exclude_patterns,
        dry_run=bool(args.dry_run),
    )

    result_text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report_path:
        report_path = Path(args.report_path)
        if not report_path.is_absolute():
            report_path = source_dir / report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(result_text + "\n", encoding="utf-8", newline="\n")

    print(result_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
