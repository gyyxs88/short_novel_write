from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

from tools.story_idea_seed_generator import load_idea_seed_sources, normalize_count


TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)

# 第一版保持 deterministic，只补少量高价值语义映射，不引入 LLM。
SEMANTIC_HINT_MAP: dict[str, tuple[str, ...]] = {
    "旧案": ("悬疑", "隐秘过去"),
}

DIRECT_TERM_WEIGHT = 10
SEMANTIC_TERM_WEIGHT = 2


@dataclass(slots=True)
class MatchedIdeaCardItem:
    id: str
    types: list[str] = field(default_factory=list)
    main_tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class MatchedIdeaCardBatch:
    prompt: str
    items: list[MatchedIdeaCardItem] = field(default_factory=list)


def normalize_match_text(text: str) -> str:
    return " ".join(TOKEN_PATTERN.findall(text.lower()))


def extract_match_terms(text: str) -> list[str]:
    terms: set[str] = set()
    for token in normalize_match_text(text).split():
        terms.add(token)
        if not token.isascii() and len(token) >= 2:
            for index in range(len(token) - 1):
                terms.add(token[index : index + 2])
    return sorted(terms)


def expand_semantic_terms(prompt_text: str, prompt_terms: list[str]) -> list[str]:
    expanded: set[str] = set()
    normalized_prompt = normalize_match_text(prompt_text)
    for trigger, hints in SEMANTIC_HINT_MAP.items():
        if trigger in normalized_prompt or trigger in prompt_terms:
            expanded.update(hints)
    return sorted(expanded)


def dedupe_pool(pool: list[str]) -> list[str]:
    unique_items: list[str] = []
    seen: set[str] = set()
    for item in pool:
        normalized_item = item.strip()
        if not normalized_item or normalized_item in seen:
            continue
        seen.add(normalized_item)
        unique_items.append(normalized_item)
    return unique_items


def score_candidate(
    prompt_terms: list[str],
    semantic_terms: list[str],
    normalized_candidate: str,
) -> tuple[int, int, int]:
    direct_score = 0
    semantic_score = 0
    longest = 0

    for term in prompt_terms:
        if term and term in normalized_candidate:
            direct_score += len(term) * DIRECT_TERM_WEIGHT
            longest = max(longest, len(term))

    for term in semantic_terms:
        if term and term in normalized_candidate:
            semantic_score += len(term) * SEMANTIC_TERM_WEIGHT
            longest = max(longest, len(term))

    return direct_score, semantic_score, longest


def rank_pool(
    prompt_terms: list[str],
    semantic_terms: list[str],
    pool: list[str],
) -> list[str]:
    scored_items: list[tuple[tuple[int, int, int, str], str]] = []
    for item in pool:
        normalized_candidate = normalize_match_text(item)
        direct_score, semantic_score, longest = score_candidate(
            prompt_terms,
            semantic_terms,
            normalized_candidate,
        )
        scored_items.append(
            (
                (
                    -direct_score,
                    -semantic_score,
                    -longest,
                    normalized_candidate,
                ),
                item,
            )
        )

    scored_items.sort(key=lambda item: item[0])
    return [item[1] for item in scored_items]


def pick_window(pool: list[str], *, start: int, size: int) -> list[str]:
    if len(pool) < size:
        raise ValueError(f"候选池条目不足，至少需要 {size} 项。")

    selected: list[str] = []
    index = start
    while len(selected) < size:
        candidate = pool[index % len(pool)]
        if candidate not in selected:
            selected.append(candidate)
        index += 1
    return selected


def match_idea_cards_from_prompt(
    *,
    prompt: str,
    count: int = 3,
    data_dir: str | Path | None = None,
) -> MatchedIdeaCardBatch:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt 必须是非空字符串。")

    normalized_prompt = prompt.strip()
    normalized_count = normalize_count(count)
    prompt_terms = extract_match_terms(normalized_prompt)
    semantic_terms = expand_semantic_terms(normalized_prompt, prompt_terms)
    type_pool, main_tag_pool = load_idea_seed_sources(data_dir)
    type_pool = dedupe_pool(type_pool)
    main_tag_pool = dedupe_pool(main_tag_pool)
    if len(type_pool) < 2 or len(main_tag_pool) < 3:
        raise ValueError("创意词池条目不足，至少需要 2 个类型和 3 个主标签。")
    ranked_types = rank_pool(prompt_terms, semantic_terms, type_pool)
    ranked_tags = rank_pool(prompt_terms, semantic_terms, main_tag_pool)

    items: list[MatchedIdeaCardItem] = []
    for index in range(normalized_count):
        items.append(
            MatchedIdeaCardItem(
                id=f"matched-{index + 1:03d}",
                types=pick_window(ranked_types, start=index, size=2),
                main_tags=pick_window(ranked_tags, start=index, size=3),
            )
        )

    return MatchedIdeaCardBatch(prompt=normalized_prompt, items=items)
