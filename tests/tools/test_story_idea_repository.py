from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from tools.story_idea_repository import (
    StoryIdeaRepository,
    canonicalize_card_signature,
)


def make_card(types: list[str], main_tags: list[str]) -> dict[str, list[str]]:
    return {
        "types": types,
        "main_tags": main_tags,
    }


def test_canonicalize_card_signature_ignores_input_order() -> None:
    first = canonicalize_card_signature(
        ["Mystery - 悬疑 / 推理", "Modern - 现代"],
        ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
    )
    second = canonicalize_card_signature(
        ["Modern - 现代", "Mystery - 悬疑 / 推理"],
        ["Secret Past - 隐秘过去", "Missing Person - 失踪", "First Love - 初恋"],
    )

    assert first == second


def test_repository_initializes_expected_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "idea-pipeline" / "story_ideas.sqlite3"
    StoryIdeaRepository(db_path)

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()

    assert {row[0] for row in rows} >= {
        "idea_batch_cards",
        "idea_card_batches",
        "idea_cards",
        "idea_packs",
        "story_plans",
        "story_payloads",
        "story_drafts",
        "story_draft_analyses",
        "story_draft_revisions",
    }


def test_store_idea_cards_deduplicates_across_batches(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")

    first = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            ),
            make_card(
                ["Romance - 恋爱", "School Life - 校园生活"],
                ["First Love - 初恋", "Misunderstanding - 误会", "Reunion - 重逢"],
            ),
        ],
    )
    second = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-b",
        items=[
            make_card(
                ["Modern - 现代", "Mystery - 悬疑 / 推理"],
                ["Secret Past - 隐秘过去", "Missing Person - 失踪", "First Love - 初恋"],
            )
        ],
    )

    assert first["batch_id"] == 1
    assert first["new_card_count"] == 2
    assert second["batch_id"] == 2
    assert second["new_card_count"] == 0
    assert second["existing_card_count"] == 1

    cards = repo.list_idea_cards()
    assert len(cards) == 2


def test_upsert_pack_and_update_status_are_idempotent(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]

    created = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        style_reason="更适合强钩子、强冲突的知乎式整理。",
        hook="一次与失踪有关的异常，把主角拖回旧案现场。",
        core_relationship="主角与那个牵出旧案的人重新对立。",
        main_conflict="主角必须查清失踪真相，同时面对隐秘过去的代价。",
        reversal_direction="表面上是失踪案，真正翻出来的是隐秘过去。",
        recommended_tags=["悬疑 / 推理", "失踪", "初恋"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )
    existing = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        style_reason="不会覆盖已有记录",
        hook="不会覆盖已有记录",
        core_relationship="不会覆盖已有记录",
        main_conflict="不会覆盖已有记录",
        reversal_direction="不会覆盖已有记录",
        recommended_tags=["不会覆盖已有记录"],
        source_cards={"types": [], "main_tags": []},
    )

    assert created["status"] == "created"
    assert existing["status"] == "existing"
    assert created["pack_id"] == existing["pack_id"]
    assert created["generation_mode"] == "deterministic"
    assert created["model_config_key"] == ""

    updated = repo.update_idea_pack_status(
        pack_id=created["pack_id"],
        pack_status="selected",
        review_note="知乎版更适合当前项目默认风格",
    )

    assert updated["pack_status"] == "selected"
    assert updated["review_note"] == "知乎版更适合当前项目默认风格"
    packs = repo.list_idea_packs(pack_status="selected")
    assert len(packs) == 1
    assert packs[0]["pack_id"] == created["pack_id"]


def test_upsert_pack_allows_deterministic_and_llm_variants_to_coexist(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]

    deterministic_pack = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        generation_mode="deterministic",
        style_reason="更适合强钩子、强冲突的知乎式整理。",
        hook="一次与失踪有关的异常，把主角拖回旧案现场。",
        core_relationship="主角与那个牵出旧案的人重新对立。",
        main_conflict="主角必须查清失踪真相，同时面对隐秘过去的代价。",
        reversal_direction="表面上是失踪案，真正翻出来的是隐秘过去。",
        recommended_tags=["悬疑 / 推理", "失踪", "初恋"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )
    llm_pack = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        generation_mode="llm",
        provider_name="openrouter",
        api_mode="chat_completions",
        model_name="gpt-5-mini",
        model_config_key="openrouter_gpt5_mini",
        provider_response_id="resp_123",
        token_usage={"prompt_tokens": 90, "completion_tokens": 30, "total_tokens": 120},
        style_reason="知乎风格更适合这组卡的强冲突表达。",
        hook="她在葬礼结束后收到失踪初恋发来的求救短信。",
        core_relationship="女主与失踪初恋被旧案重新绑回同一条线上。",
        main_conflict="她越想查清失踪真相，越不得不承认自己才是旧案的关键证人。",
        reversal_direction="求救的人未必真是受害者，真正被盯上的也许一直是女主。",
        recommended_tags=["悬疑 / 推理", "失踪", "初恋"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )

    assert deterministic_pack["status"] == "created"
    assert deterministic_pack["generation_mode"] == "deterministic"
    assert llm_pack["status"] == "created"
    assert llm_pack["generation_mode"] == "llm"
    assert llm_pack["provider_name"] == "openrouter"
    assert llm_pack["model_name"] == "gpt-5-mini"
    assert llm_pack["model_config_key"] == "openrouter_gpt5_mini"
    assert llm_pack["token_usage"] == {"prompt_tokens": 90, "completion_tokens": 30, "total_tokens": 120}
    assert llm_pack["pack_id"] != deterministic_pack["pack_id"]

    deterministic_items = repo.list_idea_packs(generation_mode="deterministic")
    llm_items = repo.list_idea_packs(
        generation_mode="llm",
        provider_name="openrouter",
        model_name="gpt-5-mini",
    )
    assert len(deterministic_items) == 1
    assert len(llm_items) == 1
    assert llm_items[0]["provider_response_id"] == "resp_123"
    assert llm_items[0]["token_usage"] == {"prompt_tokens": 90, "completion_tokens": 30, "total_tokens": 120}


def test_upsert_and_list_pack_evaluations(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]
    pack = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        generation_mode="deterministic",
        style_reason="更适合强钩子、强冲突的知乎式整理。",
        hook="她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
        core_relationship="女主与失踪前任、现任未婚夫之间重新形成对立关系。",
        main_conflict="她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
        reversal_direction="她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
        recommended_tags=["悬疑", "婚礼危机", "前任回潮"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )

    created = repo.upsert_idea_pack_evaluation(
        pack_id=pack["pack_id"],
        evaluation_mode="deterministic",
        evaluator_name="heuristic_v1",
        total_score=50,
        hook_strength_score=9,
        conflict_clarity_score=8,
        relationship_tension_score=8,
        reversal_expandability_score=9,
        style_fit_score=8,
        plan_readiness_score=8,
        recommendation="priority_select",
        summary="整体完成度较高。",
        strengths=["钩子强度较强"],
        risks=["暂无明显短板，但仍建议人工复核细节表达"],
    )
    updated = repo.upsert_idea_pack_evaluation(
        pack_id=pack["pack_id"],
        evaluation_mode="deterministic",
        evaluator_name="heuristic_v1",
        total_score=48,
        hook_strength_score=8,
        conflict_clarity_score=8,
        relationship_tension_score=8,
        reversal_expandability_score=8,
        style_fit_score=8,
        plan_readiness_score=8,
        recommendation="shortlist",
        summary="具备 shortlist 价值。",
        strengths=["冲突清晰度较强"],
        risks=["关系张力偏弱，建议重点补强"],
    )

    assert created["status"] == "created"
    assert updated["status"] == "updated"
    assert created["evaluation_id"] == updated["evaluation_id"]
    assert updated["recommendation"] == "shortlist"

    evaluations = repo.list_idea_pack_evaluations(batch_id=stored["batch_id"])
    assert len(evaluations) == 1
    assert evaluations[0]["recommendation"] == "shortlist"
    assert evaluations[0]["pack"]["style"] == "zhihu"


def test_upsert_story_plans_and_update_status(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]
    pack = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        generation_mode="deterministic",
        style_reason="更适合强钩子、强冲突的知乎式整理。",
        hook="她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
        core_relationship="女主与失踪前任、现任未婚夫之间重新形成对立关系。",
        main_conflict="她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
        reversal_direction="她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
        recommended_tags=["悬疑", "婚礼危机", "前任回潮"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )

    created = repo.upsert_story_plan(
        pack_id=pack["pack_id"],
        source_mode="seed_generate",
        style="zhihu",
        variant_index=1,
        variant_key="truth_hunt",
        variant_label="真相追猎型",
        generation_mode="deterministic",
        token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        title="短信背后的真相",
        genre_tone="现代悬疑反转，快节奏推进。",
        selling_point="用婚礼倒计时压迫感推动真相翻面。",
        protagonist_profile="一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
        protagonist_goal="查清短信和失踪案背后的操盘逻辑。",
        core_relationship="女主与失踪前任、现任未婚夫形成三角对峙。",
        main_conflict="她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
        key_turning_point="她发现最关键的短信其实是有人故意递到她手里的诱饵。",
        ending_direction="主角公开真相，但必须亲手切断一段再也回不去的关系。",
        chapter_rhythm=[
            {
                "chapter_number": 1,
                "stage": "异常闯入",
                "focus": "短信到来",
                "advance": "主角被迫回头追查",
                "chapter_hook": "她意识到这条短信不是恶作剧。",
            }
        ],
        writing_brief={
            "title": "短信背后的真相",
            "genre_tone": "现代悬疑反转，快节奏推进。",
            "target_char_range": [5000, 8000],
            "target_chapter_count": 6,
            "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
            "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
            "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
            "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
            "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
            "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
        },
    )
    existing = repo.upsert_story_plan(
        pack_id=pack["pack_id"],
        source_mode="seed_generate",
        style="zhihu",
        variant_index=1,
        variant_key="truth_hunt",
        variant_label="真相追猎型",
        generation_mode="deterministic",
        title="不会覆盖已有记录",
        genre_tone="不会覆盖已有记录",
        selling_point="不会覆盖已有记录",
        protagonist_profile="不会覆盖已有记录",
        protagonist_goal="不会覆盖已有记录",
        core_relationship="不会覆盖已有记录",
        main_conflict="不会覆盖已有记录",
        key_turning_point="不会覆盖已有记录",
        ending_direction="不会覆盖已有记录",
        chapter_rhythm=[{"chapter_number": 1, "stage": "A", "focus": "B", "advance": "C", "chapter_hook": "D"}],
        writing_brief={"title": "不会覆盖已有记录"},
    )

    assert created["status"] == "created"
    assert existing["status"] == "existing"
    assert created["plan_id"] == existing["plan_id"]
    assert created["token_usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    updated = repo.update_story_plan_status(
        plan_id=created["plan_id"],
        plan_status="selected",
        review_note="这版方案最适合进入正文阶段",
    )

    assert updated["plan_status"] == "selected"
    assert updated["review_note"] == "这版方案最适合进入正文阶段"
    plans = repo.list_story_plans(batch_id=stored["batch_id"], plan_status="selected")
    assert len(plans) == 1
    assert plans[0]["title"] == "短信背后的真相"
    assert plans[0]["pack"]["pack_status"] == "draft"


def test_upsert_story_payload_and_story_draft_flow(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]
    pack = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        generation_mode="deterministic",
        style_reason="更适合强钩子、强冲突的知乎式整理。",
        hook="她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
        core_relationship="女主与失踪前任、现任未婚夫之间重新形成对立关系。",
        main_conflict="她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
        reversal_direction="她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
        recommended_tags=["悬疑", "婚礼危机", "前任回潮"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )
    plan = repo.upsert_story_plan(
        pack_id=pack["pack_id"],
        source_mode="seed_generate",
        style="zhihu",
        variant_index=1,
        variant_key="truth_hunt",
        variant_label="真相追猎型",
        generation_mode="deterministic",
        title="短信背后的真相",
        genre_tone="现代悬疑反转，快节奏推进。",
        selling_point="用婚礼倒计时压迫感推动真相翻面。",
        protagonist_profile="一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
        protagonist_goal="查清短信和失踪案背后的操盘逻辑。",
        core_relationship="女主与失踪前任、现任未婚夫形成三角对峙。",
        main_conflict="她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
        key_turning_point="她发现最关键的短信其实是有人故意递到她手里的诱饵。",
        ending_direction="主角公开真相，但必须亲手切断一段再也回不去的关系。",
        chapter_rhythm=[
            {
                "chapter_number": 1,
                "stage": "异常闯入",
                "focus": "短信到来",
                "advance": "主角被迫回头追查",
                "chapter_hook": "她意识到这条短信不是恶作剧。",
            }
        ],
        writing_brief={
            "title": "短信背后的真相",
            "genre_tone": "现代悬疑反转，快节奏推进。",
            "target_char_range": [5000, 8000],
            "target_chapter_count": 1,
            "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
            "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
            "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
            "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
            "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
            "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
        },
    )

    payload = repo.upsert_story_payload(
        plan_id=plan["plan_id"],
        title="短信背后的真相",
        style="zhihu",
        target_char_range=[5000, 8000],
        target_chapter_count=1,
        payload={
            "plan_id": plan["plan_id"],
            "style": "zhihu",
            "title": "短信背后的真相",
            "genre_tone": "现代悬疑反转，快节奏推进。",
            "selling_point": "用婚礼倒计时压迫感推动真相翻面。",
            "target_char_range": [5000, 8000],
            "target_chapter_count": 1,
            "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
            "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
            "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
            "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
            "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
            "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
            "summary_guidance": "先抛出危险和倒计时。",
            "chapter_blueprints": [
                {
                    "chapter_number": 1,
                    "stage": "异常闯入",
                    "focus": "短信到来",
                    "advance": "主角被迫回头追查",
                    "chapter_hook": "她意识到这条短信不是恶作剧。",
                    "objective": "把主角拖入危机。",
                    "tension": "强化风险和倒计时。",
                }
            ],
            "writing_rules": ["默认先写简介，再写正文。"],
            "source_plan": {
                "pack_id": pack["pack_id"],
                "variant_index": 1,
                "variant_key": "truth_hunt",
                "variant_label": "真相追猎型",
                "generation_mode": "deterministic",
                "provider_name": "",
                "api_mode": "",
                "model_name": "",
                "model_config_key": "",
                "provider_response_id": "",
            },
        },
    )
    draft = repo.upsert_story_draft(
        payload_id=payload["payload_id"],
        generation_mode="deterministic",
        token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        title="短信背后的真相",
        content_markdown="# 短信背后的真相\n\n## 简介\n\n一句简介。\n\n## 正文\n\n### 1\n\n第一章正文。",
        summary_text="一句简介。",
        body_char_count=6,
    )

    assert payload["status"] == "created"
    assert draft["status"] == "created"
    assert draft["token_usage"] == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    assert repo.list_story_payloads(batch_id=stored["batch_id"])[0]["payload_id"] == payload["payload_id"]
    assert repo.list_story_drafts(batch_id=stored["batch_id"])[0]["draft_id"] == draft["draft_id"]

    updated = repo.update_story_draft_status(
        draft_id=draft["draft_id"],
        draft_status="selected",
        review_note="这版正文可以继续精修",
    )
    assert updated["draft_status"] == "selected"
    assert updated["review_note"] == "这版正文可以继续精修"

    revised = repo.update_story_draft_content(
        draft_id=draft["draft_id"],
        title="短信背后的真相",
        content_markdown="# 短信背后的真相\n\n## 简介\n\n一句更完整的简介。\n\n## 正文\n\n### 1\n\n修订后的第一章正文。",
        summary_text="一句更完整的简介。",
        body_char_count=9,
    )
    assert revised["draft_id"] == draft["draft_id"]
    assert revised["summary_text"] == "一句更完整的简介。"
    assert "修订后的第一章正文" in revised["content_markdown"]
    assert revised["body_char_count"] == 9


def test_create_and_list_story_draft_analyses(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]
    pack = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        generation_mode="deterministic",
        style_reason="更适合强钩子、强冲突的知乎式整理。",
        hook="她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
        core_relationship="女主与失踪前任、现任未婚夫之间重新形成对立关系。",
        main_conflict="她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
        reversal_direction="她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
        recommended_tags=["悬疑", "婚礼危机", "前任回潮"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )
    plan = repo.upsert_story_plan(
        pack_id=pack["pack_id"],
        source_mode="seed_generate",
        style="zhihu",
        variant_index=1,
        variant_key="truth_hunt",
        variant_label="真相追猎型",
        generation_mode="deterministic",
        title="短信背后的真相",
        genre_tone="现代悬疑反转，快节奏推进。",
        selling_point="用婚礼倒计时压迫感推动真相翻面。",
        protagonist_profile="一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
        protagonist_goal="查清短信和失踪案背后的操盘逻辑。",
        core_relationship="女主与失踪前任、现任未婚夫形成三角对峙。",
        main_conflict="她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
        key_turning_point="她发现最关键的短信其实是有人故意递到她手里的诱饵。",
        ending_direction="主角公开真相，但必须亲手切断一段再也回不去的关系。",
        chapter_rhythm=[
            {
                "chapter_number": 1,
                "stage": "异常闯入",
                "focus": "短信到来",
                "advance": "主角被迫回头追查",
                "chapter_hook": "她意识到这条短信不是恶作剧。",
            }
        ],
        writing_brief={
            "title": "短信背后的真相",
            "genre_tone": "现代悬疑反转，快节奏推进。",
            "target_char_range": [5000, 8000],
            "target_chapter_count": 1,
            "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
            "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
            "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
            "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
            "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
            "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
        },
    )
    payload = repo.upsert_story_payload(
        plan_id=plan["plan_id"],
        title="短信背后的真相",
        style="zhihu",
        target_char_range=[5000, 8000],
        target_chapter_count=1,
        payload={
            "plan_id": plan["plan_id"],
            "style": "zhihu",
            "title": "短信背后的真相",
            "genre_tone": "现代悬疑反转，快节奏推进。",
            "selling_point": "用婚礼倒计时压迫感推动真相翻面。",
            "target_char_range": [5000, 8000],
            "target_chapter_count": 1,
            "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
            "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
            "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
            "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
            "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
            "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
            "summary_guidance": "先抛出危险和倒计时。",
            "chapter_blueprints": [
                {
                    "chapter_number": 1,
                    "stage": "异常闯入",
                    "focus": "短信到来",
                    "advance": "主角被迫回头追查",
                    "chapter_hook": "她意识到这条短信不是恶作剧。",
                    "objective": "把主角拖入危机。",
                    "tension": "强化风险和倒计时。",
                }
            ],
        },
    )
    draft = repo.upsert_story_draft(
        payload_id=payload["payload_id"],
        generation_mode="deterministic",
        title="短信背后的真相",
        content_markdown="# 短信背后的真相\n\n## 简介\n\n一句简介。\n\n## 正文\n\n### 1\n\n她知道事情正在失控。她感到痛苦，也感到不安。",
        summary_text="一句简介。",
        body_char_count=22,
    )

    analysis = repo.create_story_draft_analysis(
        draft_id=draft["draft_id"],
        analyzer_name="prose_analyzer_v1",
        style="zhihu",
        profile_name="zhihu_tight_hook",
        overall_score=62,
        dimension_scores={
            "repeated_phrase": 70,
            "repeated_paragraph_opener": 75,
            "ai_ism": 65,
            "abstract_emotion": 60,
            "scene_thin": 50,
            "template_chapter": 80,
        },
        issue_count=3,
        analysis_report={
            "overall_score": 62,
            "issue_count": 3,
            "issues": [
                {"issue_code": "ai_ism"},
                {"issue_code": "abstract_emotion"},
                {"issue_code": "scene_thin"},
            ],
        },
    )

    fetched_draft = repo.get_story_draft(draft_id=draft["draft_id"])
    listed = repo.list_story_draft_analyses(batch_id=stored["batch_id"])

    assert fetched_draft["draft_id"] == draft["draft_id"]
    assert analysis["draft_id"] == draft["draft_id"]
    assert analysis["overall_score"] == 62
    assert analysis["draft"]["payload_style"] == "zhihu"
    assert listed[0]["analysis_id"] == analysis["analysis_id"]
    assert listed[0]["profile_name"] == "zhihu_tight_hook"


def test_upsert_get_and_list_story_style_profiles(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")

    created = repo.upsert_story_style_profile(
        profile_name="sample_douban",
        source_type="sample_texts",
        style="douban",
        profile={
            "profile_name": "sample_douban",
            "source_type": "sample_texts",
            "style": "douban",
            "voice_summary": "句子偏长，场景和停顿更显眼。",
            "preferred_traits": ["先写场景，再让情绪浮出来。"],
            "avoid_phrases": ["那一刻", "其实"],
            "dialogue_rules": ["对话允许留白。"],
            "narration_rules": ["少直接下判断。"],
            "scene_rules": ["场景细节要准。"],
            "sentence_rhythm_rules": ["长短句交替。"],
            "sample_metrics": {"sample_count": 2},
        },
    )
    updated = repo.upsert_story_style_profile(
        profile_name="sample_douban",
        source_type="sample_texts",
        style="douban",
        profile={
            "profile_name": "sample_douban",
            "source_type": "sample_texts",
            "style": "douban",
            "voice_summary": "句子偏长，场景更细。",
            "preferred_traits": ["先写场景，再让情绪浮出来。", "关系变化落在动作里。"],
            "avoid_phrases": ["那一刻", "其实"],
            "dialogue_rules": ["对话允许留白。"],
            "narration_rules": ["少直接下判断。"],
            "scene_rules": ["场景细节要准。"],
            "sentence_rhythm_rules": ["长短句交替。"],
            "sample_metrics": {"sample_count": 3},
        },
    )
    fetched = repo.get_story_style_profile(profile_name="sample_douban")
    listed = repo.list_story_style_profiles(style="douban", source_type="sample_texts")

    assert created["status"] == "created"
    assert updated["status"] == "updated"
    assert fetched["profile_name"] == "sample_douban"
    assert fetched["profile"]["sample_metrics"]["sample_count"] == 3
    assert listed[0]["profile_name"] == "sample_douban"


def test_create_and_list_story_draft_revisions(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]
    pack = repo.upsert_idea_pack(
        card_id=card_id,
        source_mode="seed_generate",
        style="zhihu",
        generation_mode="deterministic",
        style_reason="更适合强钩子、强冲突的知乎式整理。",
        hook="她在婚礼前夜收到一条来自失踪前任的短信，内容只有一句：别嫁给他。",
        core_relationship="女主与失踪前任、现任未婚夫之间重新形成对立关系。",
        main_conflict="她必须在婚礼开始前查清前任失踪和未婚夫家族的关系，否则自己会成为下一个被灭口的人。",
        reversal_direction="她以为前任是来破坏婚礼，真正的反转却是未婚夫才是当年失踪案的操盘者。",
        recommended_tags=["悬疑", "婚礼危机", "前任回潮"],
        source_cards={
            "types": ["Modern - 现代", "Mystery - 悬疑 / 推理"],
            "main_tags": [
                "First Love - 初恋",
                "Missing Person - 失踪",
                "Secret Past - 隐秘过去",
            ],
        },
    )
    plan = repo.upsert_story_plan(
        pack_id=pack["pack_id"],
        source_mode="seed_generate",
        style="zhihu",
        variant_index=1,
        variant_key="truth_hunt",
        variant_label="真相追猎型",
        generation_mode="deterministic",
        title="短信背后的真相",
        genre_tone="现代悬疑反转，快节奏推进。",
        selling_point="用婚礼倒计时压迫感推动真相翻面。",
        protagonist_profile="一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
        protagonist_goal="查清短信和失踪案背后的操盘逻辑。",
        core_relationship="女主与失踪前任、现任未婚夫形成三角对峙。",
        main_conflict="她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
        key_turning_point="她发现最关键的短信其实是有人故意递到她手里的诱饵。",
        ending_direction="主角公开真相，但必须亲手切断一段再也回不去的关系。",
        chapter_rhythm=[
            {
                "chapter_number": 1,
                "stage": "异常闯入",
                "focus": "短信到来",
                "advance": "主角被迫回头追查",
                "chapter_hook": "她意识到这条短信不是恶作剧。",
            }
        ],
        writing_brief={
            "title": "短信背后的真相",
            "genre_tone": "现代悬疑反转，快节奏推进。",
            "target_char_range": [5000, 8000],
            "target_chapter_count": 1,
            "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
            "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
            "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
            "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
            "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
            "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
        },
    )
    payload = repo.upsert_story_payload(
        plan_id=plan["plan_id"],
        title="短信背后的真相",
        style="zhihu",
        target_char_range=[5000, 8000],
        target_chapter_count=1,
        payload={
            "plan_id": plan["plan_id"],
            "style": "zhihu",
            "title": "短信背后的真相",
            "genre_tone": "现代悬疑反转，快节奏推进。",
            "selling_point": "用婚礼倒计时压迫感推动真相翻面。",
            "target_char_range": [5000, 8000],
            "target_chapter_count": 1,
            "protagonist_profile": "一个被短信重新拖回旧局、不得不亲手拆解真相的人。",
            "protagonist_goal": "查清短信和失踪案背后的操盘逻辑。",
            "core_relationship": "女主与失踪前任、现任未婚夫形成三角对峙。",
            "main_conflict": "她必须在婚礼开始前查清真相，否则自己会先成为被灭口的人。",
            "key_turning_point": "她发现最关键的短信其实是有人故意递到她手里的诱饵。",
            "ending_direction": "主角公开真相，但必须亲手切断一段再也回不去的关系。",
            "summary_guidance": "先抛出危险和倒计时。",
            "chapter_blueprints": [
                {
                    "chapter_number": 1,
                    "stage": "异常闯入",
                    "focus": "短信到来",
                    "advance": "主角被迫回头追查",
                    "chapter_hook": "她意识到这条短信不是恶作剧。",
                    "objective": "把主角拖入危机。",
                    "tension": "强化风险和倒计时。",
                }
            ],
        },
    )
    draft = repo.upsert_story_draft(
        payload_id=payload["payload_id"],
        generation_mode="deterministic",
        title="短信背后的真相",
        content_markdown="# 短信背后的真相\n\n## 简介\n\n一句简介。\n\n## 正文\n\n### 1\n\n她知道事情正在失控。那一刻她感到不安。",
        summary_text="一句简介。",
        body_char_count=20,
    )
    analysis = repo.create_story_draft_analysis(
        draft_id=draft["draft_id"],
        analyzer_name="prose_analyzer_v1",
        style="zhihu",
        profile_name="zhihu_tight_hook",
        overall_score=60,
        dimension_scores={"ai_ism": 60},
        issue_count=1,
        analysis_report={
            "issues": [
                {
                    "issue_code": "ai_ism",
                    "severity": "high",
                    "chapter_number": 1,
                    "span_text": "那一刻她感到不安。",
                    "start_offset": 33,
                    "end_offset": 42,
                    "evidence": {"phrase": "那一刻"},
                }
            ]
        },
    )

    revision = repo.create_story_draft_revision(
        draft_id=draft["draft_id"],
        analysis_id=analysis["analysis_id"],
        generation_mode="deterministic",
        revision_modes=["remove_ai_phrases"],
        before_content_markdown=draft["content_markdown"],
        after_content_markdown="# 短信背后的真相\n\n## 简介\n\n一句简介。\n\n## 正文\n\n### 1\n\n她知道事情正在失控。她感到不安。",
        changed_spans=[
            {
                "issue_code": "ai_ism",
                "original_text": "那一刻她感到不安。",
                "rewritten_text": "她感到不安。",
            }
        ],
        revision_summary="本次共改写 1 个片段，处理问题：ai_ism；应用方式：remove_ai_phrases。",
        review_metadata={
            "risk_alert_count": 0,
            "llm_judge": {
                "model_name": "mock-judge",
                "accepted_candidate_count": 1,
            },
        },
    )

    latest_analysis = repo.get_latest_story_draft_analysis(draft_id=draft["draft_id"])
    fetched_analysis = repo.get_story_draft_analysis(analysis_id=analysis["analysis_id"])
    listed = repo.list_story_draft_revisions(draft_ids=[draft["draft_id"]])

    assert latest_analysis["analysis_id"] == analysis["analysis_id"]
    assert fetched_analysis["analysis_id"] == analysis["analysis_id"]
    assert revision["draft_id"] == draft["draft_id"]
    assert revision["review_metadata"]["llm_judge"]["model_name"] == "mock-judge"
    assert listed[0]["revision_id"] == revision["revision_id"]
    assert listed[0]["revision_modes"] == ["remove_ai_phrases"]
    assert listed[0]["review_metadata"]["llm_judge"]["accepted_candidate_count"] == 1


def test_get_cards_for_build_with_card_ids_keeps_source_mode(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="prompt_match",
        user_prompt="我想写校园初恋和失踪旧案",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )

    cards = repo.get_cards_for_build(card_ids=[stored["items"][0]["card_id"]])

    assert len(cards) == 1
    assert cards[0]["source_mode"] == "prompt_match"


def test_repository_rejects_bool_ids_and_invalid_source_cards_on_create(tmp_path: Path) -> None:
    repo = StoryIdeaRepository(tmp_path / "story_ideas.sqlite3")
    stored = repo.store_idea_cards(
        source_mode="seed_generate",
        seed="seed-a",
        items=[
            make_card(
                ["Mystery - 悬疑 / 推理", "Modern - 现代"],
                ["Missing Person - 失踪", "First Love - 初恋", "Secret Past - 隐秘过去"],
            )
        ],
    )
    card_id = stored["items"][0]["card_id"]

    with pytest.raises(ValueError, match="card_id 必须是整数"):
        repo.upsert_idea_pack(
            card_id=True,
            source_mode="seed_generate",
            style="zhihu",
            style_reason="说明",
            hook="钩子",
            core_relationship="关系",
            main_conflict="冲突",
            reversal_direction="反转",
            recommended_tags=["标签"],
            source_cards={"types": ["A", "B"], "main_tags": ["X", "Y", "Z"]},
        )

    with pytest.raises(ValueError, match="batch_id 必须是整数"):
        repo.list_idea_cards(batch_id=True)

    with pytest.raises(ValueError, match="card_ids 必须是整数"):
        repo.get_cards_for_build(card_ids=[True])

    with pytest.raises(ValueError, match="pack_id 必须是整数"):
        repo.update_idea_pack_status(pack_id=True, pack_status="selected")

    with pytest.raises(ValueError, match="plan_id 必须是整数"):
        repo.update_story_plan_status(plan_id=True, plan_status="selected")

    with pytest.raises(ValueError, match="draft_id 必须是整数"):
        repo.update_story_draft_status(draft_id=True, draft_status="selected")

    with pytest.raises(ValueError, match="source_cards.types 必须恰好包含 2 个类型"):
        repo.upsert_idea_pack(
            card_id=card_id,
            source_mode="seed_generate",
            style="zhihu",
            style_reason="更适合强钩子、强冲突的知乎式整理。",
            hook="一次与失踪有关的异常，把主角拖回旧案现场。",
            core_relationship="主角与那个牵出旧案的人重新对立。",
            main_conflict="主角必须查清失踪真相，同时面对隐秘过去的代价。",
            reversal_direction="表面上是失踪案，真正翻出来的是隐秘过去。",
            recommended_tags=["悬疑 / 推理", "失踪", "初恋"],
            source_cards={
                "types": ["Mystery - 悬疑 / 推理"],
                "main_tags": [
                    "First Love - 初恋",
                    "Missing Person - 失踪",
                    "Secret Past - 隐秘过去",
                ],
            },
        )
