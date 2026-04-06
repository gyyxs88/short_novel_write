from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import random
import uuid


DEFAULT_TYPE_FILE_NAME = "类型.txt"
DEFAULT_MAIN_TAG_FILE_NAME = "标签.txt"
DEFAULT_BATCH_COUNT = 3


@dataclass(slots=True)
class IdeaSeedItem:
    id: str
    types: list[str] = field(default_factory=list)
    main_tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class IdeaSeedBatch:
    seed: str
    items: list[IdeaSeedItem] = field(default_factory=list)


def resolve_data_dir(data_dir: str | Path | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    return Path(__file__).resolve().parents[1]


def read_non_empty_lines(file_path: Path) -> list[str]:
    return [line for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_idea_seed_sources(data_dir: str | Path | None = None) -> tuple[list[str], list[str]]:
    selected_data_dir = resolve_data_dir(data_dir)
    type_file = selected_data_dir / DEFAULT_TYPE_FILE_NAME
    main_tag_file = selected_data_dir / DEFAULT_MAIN_TAG_FILE_NAME

    if not type_file.exists():
        raise FileNotFoundError(str(type_file))
    if not main_tag_file.exists():
        raise FileNotFoundError(str(main_tag_file))

    type_pool = read_non_empty_lines(type_file)
    main_tag_pool = read_non_empty_lines(main_tag_file)
    return type_pool, main_tag_pool


def normalize_count(count: int) -> int:
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        raise ValueError("count 必须是大于等于 1 的整数。")
    return count


def resolve_seed(seed: str | None = None) -> str:
    if seed is None:
        return uuid.uuid4().hex
    if not isinstance(seed, str):
        raise ValueError("seed 必须是字符串。")
    return seed


def generate_idea_seed_batch(
    *,
    count: int = DEFAULT_BATCH_COUNT,
    seed: str | None = None,
    data_dir: str | Path | None = None,
) -> IdeaSeedBatch:
    normalized_count = normalize_count(count)
    resolved_seed = resolve_seed(seed)
    type_pool, main_tag_pool = load_idea_seed_sources(data_dir)

    if len(type_pool) < 2 or len(main_tag_pool) < 3:
        raise ValueError("创意词池条目不足，至少需要 2 个类型和 3 个主标签。")

    rng = random.Random(resolved_seed)
    items: list[IdeaSeedItem] = []
    for index in range(normalized_count):
        items.append(
            IdeaSeedItem(
                id=f"idea-{index + 1:03d}",
                types=rng.sample(type_pool, 2),
                main_tags=rng.sample(main_tag_pool, 3),
            )
        )

    return IdeaSeedBatch(seed=resolved_seed, items=items)
