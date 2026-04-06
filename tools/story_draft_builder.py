from __future__ import annotations

from typing import Any

from tools.story_structure_checker import count_content_chars


VALID_STYLES = {"zhihu", "douban"}


def _normalize_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip()


def _normalize_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} 必须是整数。")
    return value


def _strip_trailing_punctuation(text: str) -> str:
    return text.strip().rstrip("。！？；，、：")


def _compact_phrase(text: str, max_chars: int) -> str:
    normalized = _strip_trailing_punctuation(text)
    if len(normalized) <= max_chars:
        return normalized

    candidates = [normalized]
    for separator in ("。", "；", "，", "、", "："):
        candidates.extend(part.strip() for part in normalized.split(separator) if part.strip())

    minimum_length = max(6, max_chars // 2)
    for candidate in candidates:
        if minimum_length <= len(candidate) <= max_chars:
            return candidate
    return normalized[:max_chars].rstrip("，、；：")


def normalize_story_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("payload 必须是对象。")
    style = _normalize_string(payload.get("style"), "payload.style")
    if style not in VALID_STYLES:
        raise ValueError("payload.style 仅支持 zhihu 或 douban。")
    chapter_blueprints = payload.get("chapter_blueprints")
    if not isinstance(chapter_blueprints, list) or not chapter_blueprints:
        raise ValueError("payload.chapter_blueprints 必须是非空数组。")

    normalized_blueprints: list[dict[str, Any]] = []
    for item in chapter_blueprints:
        if not isinstance(item, dict):
            raise ValueError("payload.chapter_blueprints 里的每一项都必须是对象。")
        normalized_blueprints.append(
            {
                "chapter_number": _normalize_int(
                    item.get("chapter_number"),
                    "chapter_blueprints.chapter_number",
                ),
                "stage": _normalize_string(item.get("stage"), "chapter_blueprints.stage"),
                "focus": _normalize_string(item.get("focus"), "chapter_blueprints.focus"),
                "advance": _normalize_string(item.get("advance"), "chapter_blueprints.advance"),
                "chapter_hook": _normalize_string(
                    item.get("chapter_hook"),
                    "chapter_blueprints.chapter_hook",
                ),
                "objective": _normalize_string(
                    item.get("objective"),
                    "chapter_blueprints.objective",
                ),
                "tension": _normalize_string(item.get("tension"), "chapter_blueprints.tension"),
            }
        )

    target_char_range = payload.get("target_char_range")
    if (
        not isinstance(target_char_range, list)
        or len(target_char_range) != 2
        or not all(isinstance(item, int) and not isinstance(item, bool) for item in target_char_range)
    ):
        raise ValueError("payload.target_char_range 必须是两个整数构成的数组。")

    target_chapter_count = _normalize_int(
        payload.get("target_chapter_count"),
        "payload.target_chapter_count",
    )
    if len(normalized_blueprints) != target_chapter_count:
        raise ValueError("payload.chapter_blueprints 数量必须与 target_chapter_count 一致。")

    return {
        "payload_id": payload.get("payload_id"),
        "plan_id": payload.get("plan_id"),
        "style": style,
        "title": _normalize_string(payload.get("title"), "payload.title"),
        "genre_tone": _normalize_string(payload.get("genre_tone"), "payload.genre_tone"),
        "selling_point": _normalize_string(payload.get("selling_point"), "payload.selling_point"),
        "target_char_range": [target_char_range[0], target_char_range[1]],
        "target_chapter_count": target_chapter_count,
        "protagonist_profile": _normalize_string(
            payload.get("protagonist_profile"),
            "payload.protagonist_profile",
        ),
        "protagonist_goal": _normalize_string(
            payload.get("protagonist_goal"),
            "payload.protagonist_goal",
        ),
        "core_relationship": _normalize_string(
            payload.get("core_relationship"),
            "payload.core_relationship",
        ),
        "main_conflict": _normalize_string(payload.get("main_conflict"), "payload.main_conflict"),
        "key_turning_point": _normalize_string(
            payload.get("key_turning_point"),
            "payload.key_turning_point",
        ),
        "ending_direction": _normalize_string(
            payload.get("ending_direction"),
            "payload.ending_direction",
        ),
        "summary_guidance": _normalize_string(
            payload.get("summary_guidance"),
            "payload.summary_guidance",
        ),
        "chapter_blueprints": normalized_blueprints,
    }


def build_summary(payload: dict[str, Any]) -> str:
    if payload["style"] == "zhihu":
        conflict = _compact_phrase(payload["main_conflict"], 24)
        relationship = _compact_phrase(payload["core_relationship"], 18)
        turning_point = _compact_phrase(payload["key_turning_point"], 24)
        return (
            f"{conflict}。"
            f"可当她再次面对{relationship}时，才发现{turning_point}。"
        )
    relationship = _compact_phrase(payload["core_relationship"], 20)
    conflict = _compact_phrase(payload["main_conflict"], 22)
    ending = _compact_phrase(payload["ending_direction"], 22)
    return (
        f"她本想守住{relationship}表面的平静，却被{conflict}重新拖回旧事。"
        f"直到她终于靠近答案，才明白自己终究得面对{ending}。"
    )


def build_opening_paragraph(payload: dict[str, Any], blueprint: dict[str, Any]) -> str:
    if payload["style"] == "zhihu":
        focus = _compact_phrase(blueprint["focus"], 28)
        conflict = _compact_phrase(payload["main_conflict"], 24)
        return (
            f"{blueprint['stage']}来得很突然。"
            f"主角原本还想勉强维持表面的秩序，可当{focus}真的落到眼前，"
            f"她就知道自己已经没有退路。"
            f"那一刻她最先想到的不是逃，而是{conflict}会不会在今晚彻底失控。"
        )
    focus = _compact_phrase(blueprint["focus"], 28)
    relationship = _compact_phrase(payload["core_relationship"], 22)
    return (
        f"{blueprint['stage']}来得并不喧闹，却像一根很细的刺扎进生活的缝里。"
        f"主角明明还想把日子照常往前推，可{focus}让她忽然意识到，"
        f"那些以为已经沉下去的旧情绪并没有真的消失。"
        f"她越想把自己按回平静里，心里越明白，真正开始松动的其实是{relationship}。"
    )


def build_relationship_paragraph(payload: dict[str, Any], blueprint: dict[str, Any]) -> str:
    protagonist_goal = _compact_phrase(payload["protagonist_goal"], 24)
    protagonist_profile = _compact_phrase(payload["protagonist_profile"], 24)
    relationship = _compact_phrase(payload["core_relationship"], 24)
    return (
        f"她之所以迟迟不敢后退，是因为{protagonist_goal}从来不只是一个外部任务。"
        f"{protagonist_profile}这件事在此刻忽然有了非常具体的重量，"
        f"每一次对视、每一次沉默、每一次想把话咽回去的冲动，"
        f"都让{relationship}显得比眼前的线索更难处理。"
        f"她知道自己只要再往前一步，就必须承认有些关系已经不可能回到原样。"
    )


def build_conflict_paragraph(payload: dict[str, Any], blueprint: dict[str, Any]) -> str:
    advance = _compact_phrase(blueprint["advance"], 24)
    conflict = _compact_phrase(payload["main_conflict"], 24)
    return (
        f"然而真正把她逼到墙角的，不只是情绪，而是越来越具体的阻力。"
        f"{advance}之后，局面不再只是缓慢变坏，"
        f"{conflict}里的风险和代价开始一层层压到她身上。"
        f"她必须在继续追下去和立刻止损之间做选择，偏偏任何一个决定，都可能先毁掉她还想保住的那部分生活。"
    )


def build_action_paragraph(payload: dict[str, Any], blueprint: dict[str, Any]) -> str:
    focus = _compact_phrase(blueprint["focus"], 28)
    advance = _compact_phrase(blueprint["advance"], 24)
    return (
        f"她没有真的停下来。"
        f"顺着{focus}继续追下去之后，事情并没有变得更清楚，结果反而冒出更多互相咬住的细节。"
        f"等到{advance}的时候，她才意识到自己看似抓住了方向，真正碰到的却是一块会不断塌陷的地面。"
        f"越是靠近她以为的答案，越能感觉到有人希望她在这里误判。"
    )


def build_turn_paragraph(payload: dict[str, Any], blueprint: dict[str, Any], is_middle_turn: bool) -> str:
    if is_middle_turn:
        turning_point = _compact_phrase(payload["key_turning_point"], 30)
        return (
            f"直到这一章，她才真正碰到故事的偏转。"
            f"{turning_point}并不是一个单纯的揭示，"
            f"而是把她此前所有判断都推向另一个方向。"
            f"她忽然明白，自己一直以为最该提防的人未必是问题本身，"
            f"真正让局面难以收拾的，是每个人都在用不同方式回避那句不愿意说出口的话。"
        )
    advance = _compact_phrase(blueprint["advance"], 24)
    relationship = _compact_phrase(payload["core_relationship"], 24)
    return (
        f"但是局面没有给她太多喘息时间。"
        f"{advance}之后，原本还能勉强维持的平衡开始一点点松动，"
        f"逼她重新计算谁在说谎、谁在退让、谁又在故意装作什么都没发生。"
        f"{relationship}也在这种拉扯里慢慢失去原来的样子。"
        f"她甚至开始怀疑，自己最初坚持的那个解释，也许只是为了让自己好受一点。"
    )


def build_emotion_paragraph(payload: dict[str, Any], blueprint: dict[str, Any], is_final: bool) -> str:
    if is_final:
        return (
            f"走到这里，她终于明白，真正需要被处理的并不只是表面上的事件，"
            f"而是那条一直横在所有人之间的旧账。"
            f"{payload['ending_direction']}不再像一句抽象的结尾说明，"
            f"而是她必须亲手承担的现实后果。"
            f"她没有办法把失去的东西重新拼回去，只能决定从此以后，自己还愿不愿意继续用沉默保护过去。"
        )
    return (
        f"这种推进最难受的地方，在于它并不只改变外部处境。"
        f"她一边逼自己往前，一边却在每一次回头里重新看见以前忽略过的细节。"
        f"原来许多关系之所以还能勉强维持，不是因为误会已经过去，而是因为所有人都默认别把真相说破。"
        f"现在，那个默认正在被一点点拆掉。"
    )


def build_chapter_ending_paragraph(blueprint: dict[str, Any], final_signal: str) -> str:
    chapter_hook = _compact_phrase(blueprint["chapter_hook"], 28)
    return (
        f"她最终还是把自己推到了下一步。"
        f"可真正留在这一章结尾的，并不是短暂的平静，而是{chapter_hook}。"
        f"{final_signal}"
    )


def build_chapter_text(
    *,
    payload: dict[str, Any],
    blueprint: dict[str, Any],
    chapter_index: int,
) -> str:
    middle_turn_index = max(2, payload["target_chapter_count"] // 2)
    is_middle_turn = chapter_index == middle_turn_index
    is_final = chapter_index == payload["target_chapter_count"]
    ending_signal = (
        "结果她终于知道，真正需要面对的不是过去有没有结束，而是自己还要不要继续逃。"
        if is_final
        else "没想到她才刚碰到一点边，局面就已经逼着她在下一章做出更危险的决定。"
    )
    paragraphs = [
        build_opening_paragraph(payload, blueprint),
        build_relationship_paragraph(payload, blueprint),
        build_conflict_paragraph(payload, blueprint),
        build_action_paragraph(payload, blueprint),
        build_turn_paragraph(payload, blueprint, is_middle_turn),
        build_emotion_paragraph(payload, blueprint, is_final),
        build_chapter_ending_paragraph(blueprint, ending_signal),
    ]
    return "\n\n".join(paragraphs)


def build_story_markdown_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized_payload = normalize_story_payload(payload)
    summary_text = build_summary(normalized_payload)
    chapters: list[dict[str, Any]] = []
    markdown_parts = [
        f"# {normalized_payload['title']}",
        "",
        "## 简介",
        "",
        summary_text,
        "",
        "## 正文",
        "",
    ]

    for chapter_index, blueprint in enumerate(normalized_payload["chapter_blueprints"], start=1):
        chapter_text = build_chapter_text(
            payload=normalized_payload,
            blueprint=blueprint,
            chapter_index=chapter_index,
        )
        chapters.append(
            {
                "chapter_number": blueprint["chapter_number"],
                "content": chapter_text,
            }
        )
        markdown_parts.extend(
            [
                f"### {blueprint['chapter_number']}",
                "",
                chapter_text,
                "",
            ]
        )

    content_markdown = "\n".join(markdown_parts).strip() + "\n"
    body_char_count = sum(count_content_chars(chapter["content"]) for chapter in chapters)
    return {
        "title": normalized_payload["title"],
        "summary_text": summary_text,
        "chapters": chapters,
        "content_markdown": content_markdown,
        "body_char_count": body_char_count,
    }
