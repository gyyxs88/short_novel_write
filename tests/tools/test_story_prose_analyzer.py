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


SOFT_RISK_PHRASE_STORY = """# 雨夜名单

## 简介

旧名单被雨水泡开后，她意识到今晚不会像值班表上写的那样平静结束。

## 正文

### 1

她并没有立刻开门，只把手按在门锁上。门外那句问候带着某种熟悉的拖音，像是故意把她往旧事里拉。

### 2

她并没有立刻回话，只盯着水迹往地板缝里渗。对方笑的时候还带着一种过分平稳的意味，让她想起名单上被划掉的第二个名字。

### 3

她并没有立刻后退。那句“别怕”里有某种意味不明的安抚，反而把走廊里的脚步声衬得更近。
"""


REMINDER_SIGNAL_STORY = """# 旧走廊

## 简介

她回旧楼拿走最后一只箱子，却在走廊尽头看见多年不见的人。

## 正文

### 1

走廊的灯只亮了一半，她把纸箱放到墙边，抬手去按门铃。对方开门时，眼底闪过一丝停顿，接着笑着说：“你比我记得的来得早。”

### 2

她把箱角往上托了托，没有马上进门。那人侧身让路，话里带着审视意味，像是早就把她今晚会来算进了顺序里。

### 3

她低头看见门口那双旧拖鞋，手指压在箱带上，没有松开。她这才明白，真正让她停住的不是这层楼太冷，而是屋里那盏还替她留着的灯。

### 4

她把箱子搬进屋，鞋底蹭过门口积下的灰。桌上的杯口还有热气，这份热意不仅让她想起去年冬天，更是把她没说出口的话一起逼到了喉咙口。

### 5

她把门轻轻关上，背后那道锁舌咔哒一声落下。对方说话的语气不容置疑，像是早就替她把这次重逢的顺序排好了。
"""


METAPHOR_REMINDER_STORY = """# 失约夜

## 简介

她在约定取消后的夜里重新回到河边，想把那件事彻底想明白。

## 正文

### 1

她站在桥边，听见手机震了一下。那条消息像一只猫一样轻轻蹭过来，偏偏让她整个人都绷住了。

### 2

他把最后一句解释发来时，那几个字像投入平静湖面的巨石，把她原本压住的念头全都掀了起来。

### 3

她把手机扣回口袋，沿着河栏往前走。原本想装作没事的心思，却在那一刻泛起一圈又一圈波澜。
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


def test_analyze_story_prose_markdown_counts_curated_soft_risk_phrases_as_ai_ism() -> None:
    report = analyze_story_prose_markdown(SOFT_RISK_PHRASE_STORY, style="zhihu")

    phrase_counts = {
        item["phrase"]: item["count"]
        for item in report.metrics["ai_ism_phrase_counts"]
    }

    assert any(issue.issue_code == "ai_ism" for issue in report.issues)
    assert phrase_counts["并没有立刻"] == 3
    assert phrase_counts["带着某种"] >= 1


def test_analyze_story_prose_markdown_surfaces_reminder_only_risk_signals() -> None:
    report = analyze_story_prose_markdown(REMINDER_SIGNAL_STORY, style="douban")

    signal_codes = {signal.signal_code for signal in report.risk_signals}
    issue_codes = {issue.issue_code for issue in report.issues}

    assert report.risk_signal_count >= 4
    assert "eye_emotion_cue" in signal_codes
    assert "vague_attitude_phrase" in signal_codes
    assert "balanced_explanatory_sentence" in signal_codes
    assert "lazy_judgment_phrase" in signal_codes
    assert "eye_emotion_cue" not in issue_codes
    assert "balanced_explanatory_sentence" not in issue_codes
    assert report.metrics["risk_signal_total_hits"] >= report.risk_signal_count
    assert any("眼神闪过" in suggestion for suggestion in report.suggestions)


def test_analyze_story_prose_markdown_surfaces_animal_and_impact_metaphor_signals() -> None:
    report = analyze_story_prose_markdown(METAPHOR_REMINDER_STORY, style="zhihu")

    signal_codes = {signal.signal_code for signal in report.risk_signals}

    assert "animal_simile" in signal_codes
    assert "impact_metaphor_cliche" in signal_codes
    assert any("动物比喻" in signal.message for signal in report.risk_signals)
    assert any("冲击型套路比喻" in signal.message for signal in report.risk_signals)
    assert any(
        "像一只" in signal.evidence.get("matched_text", "")
        or "巨石" in signal.evidence.get("matched_text", "")
        or "波澜" in signal.evidence.get("matched_text", "")
        for signal in report.risk_signals
    )
