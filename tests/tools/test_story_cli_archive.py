from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.story_cli import CliRequestError, dispatch_action
from tools.story_idea_repository import StoryIdeaRepository


def make_card(types: list[str], main_tags: list[str]) -> dict[str, list[str]]:
    return {"types": types, "main_tags": main_tags}


def build_run_dir_with_story_data(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run_cli_archive"
    run_dir.mkdir()
    source_db_path = run_dir / "story_ideas.sqlite3"
    repo = StoryIdeaRepository(source_db_path)

    stored = repo.store_idea_cards(
        source_mode="prompt_match",
        user_prompt="婚礼前夜，女主收到失踪前任的求救短信。",
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
        source_mode="prompt_match",
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
    evaluation = repo.upsert_idea_pack_evaluation(
        pack_id=pack["pack_id"],
        evaluation_mode="deterministic",
        evaluator_name="heuristic_v1",
        total_score=49,
        hook_strength_score=8,
        conflict_clarity_score=8,
        relationship_tension_score=8,
        reversal_expandability_score=8,
        style_fit_score=9,
        plan_readiness_score=8,
        recommendation="shortlist",
        summary="可进入方案阶段。",
        strengths=["钩子清晰"],
        risks=["仍需人工润色"],
    )
    plan = repo.upsert_story_plan(
        pack_id=pack["pack_id"],
        source_mode="prompt_match",
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
        },
    )
    draft = repo.upsert_story_draft(
        payload_id=payload["payload_id"],
        generation_mode="deterministic",
        token_usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        title="短信背后的真相",
        content_markdown="# 短信背后的真相\n\n## 简介\n\n一句合格简介。\n\n## 正文\n\n### 1\n\n第一章正文足够长。",
        summary_text="一句合格简介。",
        body_char_count=8,
    )

    report = {
        "generated_at": "2026-04-07 12:00:00",
        "run_dir": str(run_dir),
        "db_path": str(source_db_path),
        "sample_set": "archive_demo",
        "wall_time_seconds": 123.456,
        "summary": {
            "sample_count": 1,
            "passed_count": 1,
            "failed_count": 0,
            "inspect_pass_rate": 1.0,
            "token_usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        },
        "cases": [
            {
                "sample_key": "archive_demo_case",
                "style": "zhihu",
                "prompt": "婚礼前夜，女主收到失踪前任的求救短信。",
                "notes": "用于 CLI 归档测试。",
                "status": "passed",
                "selected_pack": {
                    "pack_id": pack["pack_id"],
                    "total_score": evaluation["total_score"],
                    "recommendation": evaluation["recommendation"],
                },
                "selected_plan": {
                    "plan_id": plan["plan_id"],
                    "variant_index": 1,
                    "title": plan["title"],
                },
                "selected_payload": {
                    "payload_id": payload["payload_id"],
                    "title": payload["title"],
                },
                "selected_draft": {
                    "draft_id": draft["draft_id"],
                    "title": draft["title"],
                    "body_char_count": draft["body_char_count"],
                },
                "inspect": {
                    "overall_ok": True,
                    "summary_chars": 6,
                    "body_chars": 8,
                    "issues": [],
                },
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                "stages": [
                    {
                        "stage": "build_idea_packs",
                        "action": "build_idea_packs",
                        "ok": True,
                        "duration_seconds": 1.23,
                        "summary": {"token_usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}},
                        "error": {},
                    },
                    {
                        "stage": "inspect",
                        "action": "inspect",
                        "ok": True,
                        "duration_seconds": 0.01,
                        "summary": {"overall_ok": True},
                        "error": {},
                    },
                ],
            }
        ],
    }
    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return run_dir


def test_dispatch_archive_run_returns_archive_result(tmp_path: Path) -> None:
    run_dir = build_run_dir_with_story_data(tmp_path)
    archive_db_path = tmp_path / "archive.sqlite3"

    result = dispatch_action(
        "archive_run",
        {
            "run_dir": str(run_dir),
            "archive_db_path": str(archive_db_path),
            "delete_source_db": True,
        },
    )

    assert result["job_id"] == "run_cli_archive"
    assert result["source_db_deleted"] is True
    assert archive_db_path.exists() is True
    assert (run_dir / "story_ideas.sqlite3").exists() is False


def test_dispatch_archive_run_rejects_non_boolean_delete_flag(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_invalid"
    run_dir.mkdir()

    with pytest.raises(CliRequestError) as exc_info:
        dispatch_action(
            "archive_run",
            {
                "run_dir": str(run_dir),
                "delete_source_db": "yes",
            },
        )

    assert exc_info.value.code == "INVALID_REQUEST"
    assert "delete_source_db" in exc_info.value.message
