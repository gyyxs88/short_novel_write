from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


CLI_PATH = Path(__file__).resolve().parents[2] / "tools" / "story_cli.py"

VALID_STORY = """# 雨夜来信

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

REMINDER_SIGNAL_STORY = """# 回楼的人

## 简介

她回旧楼搬最后一趟东西，却在门口看见多年不见的人。

## 正文

### 1

她把纸箱靠到墙边，抬手去敲门。门一开，对方眼底闪过一丝停顿，又笑着说：“你来得比我记得早。”

### 2

她没有立刻进门，只站在门槛外看着屋里的灯。那人让开半步，话里带着审视意味，像是早就知道她会回来。

### 3

她把箱子搬进屋，鞋底蹭过门口积下的灰。对方的语气不容置疑，不是要她坐下歇一会儿，而是要她把今晚没说完的话一次说清。
"""


def run_cli(raw_input: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI_PATH)],
        input=raw_input,
        text=True,
        capture_output=True,
        check=False,
    )


def parse_stdout_json(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def test_save_action_writes_story_markdown(tmp_path: Path) -> None:
    request = {
        "action": "save",
        "payload": {
            "title": "雨夜来信",
            "content": VALID_STORY,
            "output_dir": str(tmp_path / "novels"),
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["action"] == "save"
    assert Path(response["data"]["output_path"]).read_text(encoding="utf-8") == VALID_STORY


def test_check_structure_action_returns_structure_report() -> None:
    request = {
        "action": "check_structure",
        "payload": {
            "content": VALID_STORY,
            "target_char_range": [60, 5000],
            "summary_char_range": [30, 120],
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["data"]["is_valid"] is True
    assert response["data"]["chapter_numbers"] == [1, 2, 3]


def test_check_quality_action_returns_quality_report() -> None:
    request = {
        "action": "check_quality",
        "payload": {
            "content": VALID_STORY,
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["data"]["is_passable"] is True
    assert response["data"]["opening_signal_hits"]


def test_inspect_action_returns_combined_report() -> None:
    request = {
        "action": "inspect",
        "payload": {
            "content": VALID_STORY,
            "target_char_range": [60, 5000],
            "summary_char_range": [30, 120],
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["data"]["overall_ok"] is True
    assert "structure" in response["data"]
    assert "quality" in response["data"]


def test_analyze_story_prose_action_returns_prose_report() -> None:
    request = {
        "action": "analyze_story_prose",
        "payload": {
            "content": VALID_STORY,
            "style": "zhihu",
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["data"]["analyzer_name"] == "prose_analyzer_v1"
    assert response["data"]["stored"] is False
    assert response["data"]["issue_count"] >= 0
    assert response["data"]["metrics"]["chapter_count"] == 3


def test_analyze_story_prose_action_returns_reminder_risk_signals() -> None:
    request = {
        "action": "analyze_story_prose",
        "payload": {
            "content": REMINDER_SIGNAL_STORY,
            "style": "douban",
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["data"]["risk_signal_count"] >= 3
    assert any(item["signal_code"] == "eye_emotion_cue" for item in response["data"]["risk_signals"])


def test_get_style_profile_action_returns_builtin_profile_without_db_record() -> None:
    request = {
        "action": "get_style_profile",
        "payload": {
            "profile_name": "zhihu_tight_hook",
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["data"]["builtin"] is True
    assert response["data"]["stored"] is False
    assert response["data"]["profile"]["style"] == "zhihu"


def test_invalid_json_returns_invalid_json_error() -> None:
    result = run_cli("{")

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_JSON"


def test_unknown_action_returns_unknown_action_error() -> None:
    request = {
        "action": "unknown",
        "payload": {},
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "UNKNOWN_ACTION"


def test_missing_content_and_file_path_returns_invalid_input_source() -> None:
    request = {
        "action": "check_structure",
        "payload": {},
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_INPUT_SOURCE"


def test_missing_file_returns_file_not_found() -> None:
    request = {
        "action": "check_quality",
        "payload": {
            "file_path": str(Path("D:/Project/douyin-downloader/short_novel_write/not-exists.md")),
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "FILE_NOT_FOUND"


def test_generate_ideas_action_defaults_to_three_items() -> None:
    request = {
        "action": "generate_ideas",
        "payload": {},
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 0
    response = parse_stdout_json(result)
    assert response["ok"] is True
    assert response["action"] == "generate_ideas"
    assert response["data"]["count"] == 3
    assert len(response["data"]["items"]) == 3
    assert response["data"]["seed"]
    assert all(len(item["types"]) == 2 for item in response["data"]["items"])
    assert all(len(item["main_tags"]) == 3 for item in response["data"]["items"])


def test_generate_ideas_action_returns_stable_results_for_same_seed() -> None:
    request = {
        "action": "generate_ideas",
        "payload": {
            "count": 2,
            "seed": "same-seed",
        },
    }

    first = parse_stdout_json(run_cli(json.dumps(request, ensure_ascii=False)))
    second = parse_stdout_json(run_cli(json.dumps(request, ensure_ascii=False)))

    assert first["data"]["seed"] == "same-seed"
    assert first["data"]["items"] == second["data"]["items"]


def test_generate_ideas_action_rejects_invalid_count() -> None:
    request = {
        "action": "generate_ideas",
        "payload": {
            "count": 0,
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"


def test_generate_ideas_action_rejects_non_string_seed() -> None:
    request = {
        "action": "generate_ideas",
        "payload": {
            "seed": 123,
        },
    }

    result = run_cli(json.dumps(request, ensure_ascii=False))

    assert result.returncode == 1
    response = parse_stdout_json(result)
    assert response["ok"] is False
    assert response["error"]["code"] == "INVALID_REQUEST"
