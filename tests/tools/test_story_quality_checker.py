from pathlib import Path

from tools.story_quality_checker import check_story_quality_file, check_story_quality_markdown


PASSABLE_STORY = """# 雨夜来信

## 简介

葬礼结束后，失踪三年的姐姐忽然用旧号码给我发来短信。她说今晚无论谁来敲门，都别让那个人进屋，因为真正死掉的人，也许根本不是她。

## 正文

### 1

我是在送走最后一位亲戚之后，才看到那条短信的。屏幕亮起的一瞬间，我几乎把手机摔在地上。那是姐姐的号码，三年前随着她一起消失，后来又随着死亡证明一起盖了章。

### 2

母亲说我脸色发白，可她不知道，那个号码早就停用了。我想删掉短信，手指却悬在半空，因为第二条消息紧跟着跳了出来。她说，门外的人会穿她下葬那天的黑裙子。她还说，如果我想知道当年是谁把她推进河里，就一定要把门反锁。

### 3

晚上九点，门铃真的响了。猫眼外站着的人，穿着姐姐下葬那天的黑裙子。可我终于明白，真正可怕的不是门外那张脸，而是母亲在我身后轻声说出的那句话。她说，别开门，因为死在河里的那个人，一开始就不是你姐姐。
"""


FAILING_STORY = """# 漫长而空泛的抒情标题名字明显过长

## 简介

这是一个普通的故事，讲的是一个人回家。

## 正文

### 1

他今天回家了。他看见桌子，椅子，窗户，天气也还可以。

### 2

他喝水。

### 3

后来他睡了。
"""


def test_check_story_quality_markdown_accepts_story_with_hook_progression_and_payoff() -> None:
    report = check_story_quality_markdown(PASSABLE_STORY)

    assert report.is_passable is True
    assert report.title == "雨夜来信"
    assert report.opening_signal_hits
    assert report.ending_signal_hits
    assert report.issues == []


def test_check_story_quality_markdown_reports_flat_opening_weak_middle_and_title_issue() -> None:
    report = check_story_quality_markdown(FAILING_STORY)

    assert report.is_passable is False
    assert any("开头" in issue for issue in report.issues)
    assert any("中段" in issue for issue in report.issues)
    assert any("结尾" in issue for issue in report.issues)
    assert any("标题" in issue for issue in report.issues)
    assert report.suggestions


def test_check_story_quality_file_reads_utf8_story(tmp_path: Path) -> None:
    story_file = tmp_path / "story.md"
    story_file.write_text(PASSABLE_STORY, encoding="utf-8")

    report = check_story_quality_file(story_file)

    assert report.is_passable is True
    assert report.chapter_char_counts == sorted(report.chapter_char_counts, reverse=True) or report.chapter_char_counts
