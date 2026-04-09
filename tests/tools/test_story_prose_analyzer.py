from pathlib import Path

from tools.story_prose_analyzer import analyze_story_prose_file, analyze_story_prose_markdown


AI_ISH_STORY = """# 回声里的婚礼

## 简介

婚礼前夜，她收到一条旧号码发来的短信。短信没有解释太多，只说那一刻别相信任何人。

## 正文

### 1

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。

她终于明白事情正在失控。原来所有平静都只是某种表象。

### 2

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。

她终于明白事情正在失控。原来所有平静都只是某种表象。

### 3

她知道事情正在失控。她感到痛苦，也感到不安。那一刻她知道自己已经回不到原来的样子。

她知道关系正在松动。她感到难过，也感到压抑。其实她心里只剩下一种说不清的拉扯。

她终于明白事情正在失控。原来所有平静都只是某种表象。
"""


MORE_CONCRETE_STORY = """# 雨站旧信

## 简介

暴雨夜最后一班车停在小站，她被迫和多年不见的姐姐困在候车室里，桌上的旧信封一浸水，十年前那场失踪案的名字就浮了出来。

## 正文

### 1

候车室的灯坏了一半，雨水顺着玻璃往下淌。她把湿透的帆布包放到长椅上，指尖一碰，才发现信封边角已经泡开了。

“别拆。”姐姐站在门边，鞋跟沾着泥，声音却比雨还轻。

她没听，直接把信纸抽出来。纸上那行熟悉的字刚露出来，她的手就僵住了。

### 2

风从门缝里钻进来，吹得桌上的车票直抖。她把票根压在杯底，抬头时正看见姐姐把手机扣到身后，像是怕她看到屏幕上的名字。

“你还在替他瞒着？”她问。

姐姐没有立刻回话，只把唇抿得很紧，过了几秒才说：“我是在替你收拾那年的残局。”

### 3

广播终于响起时，雨势反而更大了。她抓起那封旧信，追到站台边，鞋底踩进积水，冷意一下窜上小腿。

姐姐被她拽得回过身，脸色发白。她把信拍到对方胸口，一字一顿地说：“今天不上车也行，但这次你得把那天谁在码头等我说清楚。”
"""


DIALOGUE_FRAGMENT_STORY = """# 迟来的对话

## 简介

重逢后的夜里，她终于问出那句埋了很多年的话。

## 正文

### 1

“你后悔吗？”她盯着他，声音很轻。

“我这辈子最后悔的事，是没早点告诉你。”他说完后抬手按住杯沿，指节泛白。
"""


def test_analyze_story_prose_markdown_reports_repetition_abstraction_and_template_signals() -> None:
    report = analyze_story_prose_markdown(AI_ISH_STORY, style="zhihu")

    issue_codes = {issue.issue_code for issue in report.issues}

    assert report.title == "回声里的婚礼"
    assert report.issue_count > 0
    assert report.overall_score < 80
    assert "repeated_phrase" in issue_codes
    assert "repeated_paragraph_opener" in issue_codes
    assert "ai_ism" in issue_codes
    assert "abstract_emotion" in issue_codes
    assert "scene_thin" in issue_codes
    assert "template_chapter" in issue_codes
    assert report.metrics["chapter_count"] == 3
    assert report.metrics["ai_ism_total_hits"] >= 3
    assert report.metrics["scene_thin_chapter_count"] >= 1
    assert report.suggestions


def test_analyze_story_prose_markdown_gives_higher_score_to_more_concrete_story() -> None:
    ai_ish_report = analyze_story_prose_markdown(AI_ISH_STORY, style="zhihu")
    concrete_report = analyze_story_prose_markdown(MORE_CONCRETE_STORY, style="douban")

    assert concrete_report.overall_score > ai_ish_report.overall_score
    assert concrete_report.metrics["chapter_count"] == 3
    assert concrete_report.metrics["scene_thin_chapter_count"] == 0


def test_analyze_story_prose_file_reads_utf8_story(tmp_path: Path) -> None:
    story_file = tmp_path / "story.md"
    story_file.write_text(AI_ISH_STORY, encoding="utf-8")

    report = analyze_story_prose_file(story_file, style="zhihu")

    assert report.title == "回声里的婚礼"
    assert report.issue_count >= 1


def test_analyze_story_prose_markdown_skips_dialogue_question_fragments_for_abstract_emotion() -> None:
    report = analyze_story_prose_markdown(DIALOGUE_FRAGMENT_STORY, style="zhihu")

    assert not any(
        issue.issue_code == "abstract_emotion" and "你后悔吗" in issue.span_text
        for issue in report.issues
    )
