from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


DEFAULT_OUTPUT_DIR = Path("outputs") / "novels"
INVALID_FILENAME_PATTERN = re.compile(r'[\\/:*?"<>|]+')


@dataclass(slots=True)
class StoryWriteResult:
    output_dir: Path
    output_path: Path
    directory_created: bool


def resolve_output_dir(raw_output_dir: str | Path | None) -> Path:
    if raw_output_dir is None:
        return DEFAULT_OUTPUT_DIR

    selected = str(raw_output_dir).strip()
    if not selected:
        return DEFAULT_OUTPUT_DIR

    return Path(selected).expanduser()


def sanitize_title(title: str) -> str:
    sanitized = INVALID_FILENAME_PATTERN.sub("_", title).strip()
    return sanitized or "未命名短篇"


def write_story_markdown(
    title: str,
    content: str,
    output_dir: str | Path | None = None,
    suffix: str = ".md",
) -> StoryWriteResult:
    selected_output_dir = resolve_output_dir(output_dir)
    directory_created = not selected_output_dir.exists()
    selected_output_dir.mkdir(parents=True, exist_ok=True)

    output_path = selected_output_dir / f"{sanitize_title(title)}{suffix}"
    output_path.write_text(content, encoding="utf-8", newline="\n")

    return StoryWriteResult(
        output_dir=selected_output_dir,
        output_path=output_path,
        directory_created=directory_created,
    )
