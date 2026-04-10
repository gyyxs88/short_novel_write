from tools.story_prose_analyzer import analyze_story_prose_markdown
from tools.story_span_rewriter import (
    apply_remove_ai_phrases,
    rewrite_story_spans_deterministic,
    select_rewrite_targets,
)


AI_ISH_STORY = """# 回声里的婚礼

## 简介

婚礼前夜，她收到一条旧号码发来的短信。短信没有解释太多，只说那一刻别相信任何人。

## 正文

### 1

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。

### 2

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。

### 3

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。
"""


def test_select_rewrite_targets_picks_high_priority_issues() -> None:
    analysis = analyze_story_prose_markdown(AI_ISH_STORY, style="zhihu").to_dict()

    targets = select_rewrite_targets(
        analysis,
        rewrite_modes=["remove_ai_phrases", "concretize_emotion"],
        max_spans=2,
    )

    assert len(targets) == 2
    assert all(target.rewrite_modes for target in targets)


def test_rewrite_story_spans_deterministic_rewrites_targeted_spans() -> None:
    analysis = analyze_story_prose_markdown(AI_ISH_STORY, style="zhihu").to_dict()

    result = rewrite_story_spans_deterministic(
        content_markdown=AI_ISH_STORY,
        analysis_report=analysis,
        style="zhihu",
        rewrite_modes=["remove_ai_phrases", "concretize_emotion", "compress_exposition"],
        issue_codes=["ai_ism", "abstract_emotion"],
        max_spans=3,
    )

    assert result["generation_mode"] == "deterministic"
    assert result["changed_span_count"] >= 1
    assert result["after_content_markdown"] != AI_ISH_STORY
    assert any(
        "那一刻" in item["original_text"] and "那一刻" not in item["rewritten_text"]
        for item in result["changed_spans"]
    )
    assert any(item["applied_rewrite_modes"] for item in result["changed_spans"])


def test_rewrite_story_spans_deterministic_can_use_style_profile_avoid_phrases() -> None:
    analysis = analyze_story_prose_markdown(AI_ISH_STORY, style="douban").to_dict()

    result = rewrite_story_spans_deterministic(
        content_markdown=AI_ISH_STORY,
        analysis_report=analysis,
        style="douban",
        profile={
            "style": "douban",
            "avoid_phrases": ["其实", "那一刻"],
        },
        rewrite_modes=["remove_ai_phrases"],
        max_spans=2,
    )

    assert result["changed_span_count"] >= 1
    assert any(
        ("其实" in item["original_text"] or "那一刻" in item["original_text"])
        and "其实" not in item["rewritten_text"]
        and "那一刻" not in item["rewritten_text"]
        for item in result["changed_spans"]
    )


def test_apply_remove_ai_phrases_handles_curated_soft_risk_phrases() -> None:
    rewritten = apply_remove_ai_phrases("她并没有立刻回头，只是带着某种克制的口气，说这件事还有一种别的意味。")

    assert "并没有立刻" not in rewritten
    assert "带着某种" not in rewritten
    assert "某种" not in rewritten
    assert "某种意味" not in rewritten
    assert "没有立刻" in rewritten


def test_rewrite_story_spans_deterministic_marks_high_risk_regret_fragment_as_alert() -> None:
    content_markdown = """# 片段

## 简介

一句话简介。

## 正文

### 1

后悔的是，浪费了十五年时间，去为一个谎言卖命。
"""
    original_text = "后悔的是，浪费了十五年时间，去为一个谎言卖命。"
    start_offset = content_markdown.find(original_text)
    analysis_report = {
        "issues": [
            {
                "issue_code": "abstract_emotion",
                "severity": "high",
                "chapter_number": 1,
                "start_offset": start_offset,
                "end_offset": start_offset + len(original_text),
                "span_text": original_text,
                "evidence": {
                    "matched_term": "后悔",
                    "sentence_length": len(original_text),
                },
            }
        ]
    }

    result = rewrite_story_spans_deterministic(
        content_markdown=content_markdown,
        analysis_report=analysis_report,
        style="zhihu",
        rewrite_modes=["concretize_emotion"],
        issue_codes=["abstract_emotion"],
        max_spans=1,
    )

    assert result["changed_span_count"] == 1
    assert result["risk_alert_count"] == 1
    assert result["risk_alerts"][0]["risk_flags"] == ["missing_subject_for_regret"]
    assert result["changed_spans"][0]["risk_flags"] == ["missing_subject_for_regret"]
    assert result["after_content_markdown"] != content_markdown


def test_select_rewrite_targets_skips_overlapping_spans() -> None:
    analysis_report = {
        "issues": [
            {
                "issue_code": "template_chapter",
                "severity": "high",
                "chapter_number": 1,
                "start_offset": 10,
                "end_offset": 30,
                "span_text": "这是一个较长的模板章节片段，用来覆盖后面的段落起手片段。",
                "evidence": {},
            },
            {
                "issue_code": "repeated_paragraph_opener",
                "severity": "medium",
                "chapter_number": 1,
                "start_offset": 20,
                "end_offset": 40,
                "span_text": "模板章节片段，用来覆盖后面的段落起手片段。",
                "evidence": {},
            },
            {
                "issue_code": "ai_ism",
                "severity": "medium",
                "chapter_number": 1,
                "start_offset": 80,
                "end_offset": 84,
                "span_text": "原来",
                "evidence": {},
            },
        ]
    }

    targets = select_rewrite_targets(analysis_report, max_spans=3)

    assert len(targets) == 2
    assert [target.issue_code for target in targets] == ["template_chapter", "ai_ism"]
