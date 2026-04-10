from tools.story_style_profile import (
    build_style_profile,
    get_builtin_style_profile,
    list_builtin_style_profiles,
)


def test_list_builtin_style_profiles_contains_expected_profiles() -> None:
    items = list_builtin_style_profiles()

    names = {item["profile_name"] for item in items}
    assert "zhihu_tight_hook" in names
    assert "douban_subtle_scene" in names


def test_build_style_profile_from_builtin_uses_builtin_shape() -> None:
    profile = build_style_profile(profile_name="zhihu_tight_hook")

    assert profile["profile_name"] == "zhihu_tight_hook"
    assert profile["source_type"] == "built_in"
    assert profile["style"] == "zhihu"
    assert profile["preferred_traits"]
    assert "并没有立刻" in profile["avoid_phrases"]
    assert "带着某种" in profile["avoid_phrases"]


def test_build_style_profile_from_samples_generates_metrics_and_rules() -> None:
    profile = build_style_profile(
        profile_name="sample_douban",
        style="douban",
        sample_texts=[
            "她把旧钥匙放进掌心，金属凉得发硬。‘别开门。’姐姐站在走廊尽头，声音很轻。",
            "雨水顺着窗缝往里渗，她抬手去擦，却先闻到木头受潮后的气味。",
        ],
    )

    assert profile["profile_name"] == "sample_douban"
    assert profile["source_type"] == "sample_texts"
    assert profile["style"] == "douban"
    assert profile["sample_metrics"]["sample_count"] == 2
    assert profile["sample_metrics"]["average_sentence_length"] > 0
    assert profile["dialogue_rules"]
    assert profile["scene_rules"]


def test_get_builtin_style_profile_returns_none_for_unknown_name() -> None:
    assert get_builtin_style_profile("missing_profile") is None
