from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any

from tools.story_prose_analyzer import ACTION_CUES, AI_ISM_PHRASES, SENSORY_CUES, split_sentences


VALID_STYLES = {"zhihu", "douban"}
VALID_PROFILE_SOURCE_TYPES = {"built_in", "sample_texts"}


@dataclass(frozen=True, slots=True)
class BuiltInStyleProfile:
    profile_name: str
    style: str
    voice_summary: str
    preferred_traits: tuple[str, ...]
    avoid_phrases: tuple[str, ...]
    dialogue_rules: tuple[str, ...]
    narration_rules: tuple[str, ...]
    scene_rules: tuple[str, ...]
    sentence_rhythm_rules: tuple[str, ...]

    def to_profile_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "source_type": "built_in",
            "style": self.style,
            "voice_summary": self.voice_summary,
            "preferred_traits": list(self.preferred_traits),
            "avoid_phrases": list(self.avoid_phrases),
            "dialogue_rules": list(self.dialogue_rules),
            "narration_rules": list(self.narration_rules),
            "scene_rules": list(self.scene_rules),
            "sentence_rhythm_rules": list(self.sentence_rhythm_rules),
            "sample_metrics": {},
        }


BUILTIN_STYLE_PROFILES: dict[str, BuiltInStyleProfile] = {
    "zhihu_tight_hook": BuiltInStyleProfile(
        profile_name="zhihu_tight_hook",
        style="zhihu",
        voice_summary="强钩子、快推进、短句偏多，优先把危险、代价和信息翻面顶到前台。",
        preferred_traits=(
            "开头尽快抛异常或倒计时",
            "每章都要有信息推进或关系翻面",
            "关键句要更利落，少空转解释",
            "章尾保留明确钩子或代价",
        ),
        avoid_phrases=(
            "那一刻",
            "某种",
            "其实",
            "原来一切",
            "不由得",
        ),
        dialogue_rules=(
            "对话优先承载试探、逼问、反咬，不要只做背景说明。",
            "角色说话要带目的，不要每句都说完整逻辑。",
        ),
        narration_rules=(
            "叙述优先保留动作、证据、选择和后果。",
            "少写空泛感悟，必要情绪要绑在事件结果上。",
        ),
        scene_rules=(
            "每章至少落一个具体现场，优先门口、手机、雨夜、楼道、车站这类可承压场景。",
            "让环境变化服务冲突，不单独写气氛。",
        ),
        sentence_rhythm_rules=(
            "句子以短中句为主，关键转折可以更短。",
            "避免连续三句以上同样的主语起手。",
        ),
    ),
    "douban_subtle_scene": BuiltInStyleProfile(
        profile_name="douban_subtle_scene",
        style="douban",
        voice_summary="场景更细、停顿更多，情绪通过动作、物件和关系余波慢慢显出来。",
        preferred_traits=(
            "先让场景成立，再让情绪浮出来",
            "关系变化要通过对话停顿、动作回避和旧物触发来表现",
            "允许句子舒展，但不能空泛抒情",
            "结尾留余味，不靠硬升华",
        ),
        avoid_phrases=(
            "回不到原来的样子",
            "终于明白",
            "某种",
            "仿佛",
            "其实",
        ),
        dialogue_rules=(
            "对话保留停顿、绕开和没说完的话，别把人物写成作者嘴替。",
            "不同人物说话节奏要有差别，避免同腔同调。",
        ),
        narration_rules=(
            "情绪尽量藏在动作、环境和物件互动里。",
            "少直接下判断，多给读者自己感受的空间。",
        ),
        scene_rules=(
            "优先写房间、车站、楼道、旧宅、厨房、雨夜这类带记忆感的场所。",
            "场景细节不求多，但要准，最好能和关系变化互相照应。",
        ),
        sentence_rhythm_rules=(
            "句子允许长短混排，段落之间保留呼吸感。",
            "避免整章都用同一类抒情句收尾。",
        ),
    ),
}


def _normalize_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    return value.strip()


def _normalize_style(style: Any) -> str:
    normalized = _normalize_string(style, "style")
    if normalized not in VALID_STYLES:
        raise ValueError("style 仅支持 zhihu 或 douban。")
    return normalized


def _normalize_profile_name(profile_name: Any) -> str:
    return _normalize_string(profile_name, "profile_name")


def _normalize_sample_texts(sample_texts: Any) -> list[str]:
    if not isinstance(sample_texts, list) or not sample_texts:
        raise ValueError("sample_texts 必须是非空字符串数组。")
    normalized: list[str] = []
    for item in sample_texts:
        normalized.append(_normalize_string(item, "sample_texts"))
    return normalized


def _normalize_source_type(source_type: Any) -> str:
    normalized = _normalize_string(source_type, "source_type")
    if normalized not in VALID_PROFILE_SOURCE_TYPES:
        raise ValueError(f"source_type 仅支持：{sorted(VALID_PROFILE_SOURCE_TYPES)}")
    return normalized


def list_builtin_style_profiles() -> list[dict[str, Any]]:
    return [BUILTIN_STYLE_PROFILES[name].to_profile_dict() for name in sorted(BUILTIN_STYLE_PROFILES)]


def get_builtin_style_profile(profile_name: str) -> dict[str, Any] | None:
    profile = BUILTIN_STYLE_PROFILES.get(profile_name)
    if profile is None:
        return None
    return profile.to_profile_dict()


def _count_dialogue_hits(text: str) -> int:
    return len(re.findall(r"“[^”]+”", text))


def _count_cue_hits(text: str, cues: tuple[str, ...]) -> int:
    return sum(text.count(cue) for cue in cues)


def _pick_top_sample_phrases(sample_texts: list[str]) -> list[str]:
    counter: dict[str, int] = {}
    for text in sample_texts:
        cleaned = re.sub(r"[^\u4e00-\u9fff]", "", text)
        for size in (4, 3):
            for index in range(len(cleaned) - size + 1):
                phrase = cleaned[index : index + size]
                if len(set(phrase)) <= 1:
                    continue
                if phrase in AI_ISM_PHRASES:
                    continue
                counter[phrase] = counter.get(phrase, 0) + 1
    sorted_items = sorted(counter.items(), key=lambda item: (-item[1], -len(item[0]), item[0]))
    return [phrase for phrase, count in sorted_items if count >= 2][:5]


def _build_voice_summary(style: str, *, average_sentence_length: float, dialogue_ratio: float, action_hits: int, sensory_hits: int) -> str:
    rhythm = "句子偏短，推进更利落" if average_sentence_length <= 18 else "句子偏长，叙述更舒展"
    dialogue = "对话占比偏高" if dialogue_ratio >= 0.22 else "叙述占比更高"
    focus = "动作推进更强" if action_hits >= sensory_hits else "氛围细节更强"
    if style == "zhihu":
        return f"{rhythm}，{dialogue}，{focus}，整体更适合强钩子和快速翻面。"
    return f"{rhythm}，{dialogue}，{focus}，整体更适合关系余波和场景慢渗。"


def _build_preferred_traits(style: str, *, average_sentence_length: float, dialogue_ratio: float, top_phrases: list[str]) -> list[str]:
    traits = [
        "优先保留样本文本里已经稳定出现的节奏和叙事重心。",
    ]
    if style == "zhihu":
        traits.extend(
            [
                "开头尽快抛冲突和代价。",
                "优先让信息翻面、关系反咬、章尾留钩。",
            ]
        )
    else:
        traits.extend(
            [
                "先写场景和停顿，再让情绪自己浮出来。",
                "关系变化优先落在动作、目光、物件和对话回避上。",
            ]
        )
    if average_sentence_length <= 18:
        traits.append("保持偏短句节奏，不要突然写成长段解释。")
    else:
        traits.append("允许句子舒展，但一段里要留呼吸点，避免整段同长度。")
    if dialogue_ratio >= 0.22:
        traits.append("对话已经是主要驱动，继续让人物用说话方式区分彼此。")
    if top_phrases:
        traits.append(f"可以保留样本文本里较稳定的表达偏好：{', '.join(top_phrases)}。")
    return traits


def _build_avoid_phrases(style: str) -> list[str]:
    common = ["那一刻", "某种", "其实", "不由得", "终于明白"]
    if style == "zhihu":
        return common + ["原来一切", "回不到原来的样子"]
    return common + ["仿佛", "似乎", "关系开始松动"]


def _build_dialogue_rules(style: str, dialogue_ratio: float) -> list[str]:
    rules = [
        "不同人物必须有不同句长、停顿和回避方式，避免同腔同调。",
    ]
    if style == "zhihu":
        rules.append("对话优先承载逼问、试探、反咬和信息反转。")
    else:
        rules.append("对话允许留白和绕开，不要把潜台词全说满。")
    if dialogue_ratio < 0.15:
        rules.append("必要时补一点有效对话，不要整章都靠旁白总结。")
    return rules


def _build_narration_rules(style: str, sensory_hits: int, action_hits: int) -> list[str]:
    rules = [
        "叙述尽量少下抽象判断，多把意思落在动作、物件、空间和结果上。",
    ]
    if style == "zhihu":
        rules.append("说明句尽量压短，优先让因果和代价自己冒出来。")
    else:
        rules.append("允许保留余味，但不要脱离具体场景空转抒情。")
    if sensory_hits > action_hits:
        rules.append("保留细节氛围优势，但不要让环境描写盖过事件推进。")
    else:
        rules.append("推进已经够强，注意给人物和场景留一点可感知的纹理。")
    return rules


def _build_scene_rules(style: str, sensory_hits: int, action_hits: int) -> list[str]:
    rules = [
        "每个关键段落最好能看见具体空间、动作或物件，不要只剩概括句。",
    ]
    if style == "zhihu":
        rules.append("场景优先服务冲突，让现场细节直接参与推进。")
    else:
        rules.append("场景优先服务关系余波，让旧物、环境和停顿带出潜台词。")
    if sensory_hits < max(3, action_hits // 2):
        rules.append("适当补一点声音、气味、光线或触感，增加场景触达感。")
    return rules


def _build_sentence_rhythm_rules(average_sentence_length: float) -> list[str]:
    rules = [
        "避免连续多句同一主语起手。",
        "长短句要交替，关键句允许更短。",
    ]
    if average_sentence_length > 26:
        rules.append("长句已经偏多，后续写作注意拆句，避免整段都拖长。")
    elif average_sentence_length < 14:
        rules.append("短句已经偏多，后续可以穿插少量舒展句，让节奏别太硬。")
    return rules


def build_style_profile_from_samples(
    *,
    profile_name: str,
    style: str,
    sample_texts: list[str],
) -> dict[str, Any]:
    normalized_profile_name = _normalize_profile_name(profile_name)
    normalized_style = _normalize_style(style)
    normalized_sample_texts = _normalize_sample_texts(sample_texts)

    sentences = [sentence for text in normalized_sample_texts for sentence in split_sentences(text)]
    total_sentence_length = sum(len(re.sub(r"\s+", "", sentence)) for sentence in sentences)
    average_sentence_length = round(total_sentence_length / max(1, len(sentences)), 2)
    total_chars = sum(len(re.sub(r"\s+", "", text)) for text in normalized_sample_texts)
    dialogue_hits = sum(_count_dialogue_hits(text) for text in normalized_sample_texts)
    action_hits = sum(_count_cue_hits(text, ACTION_CUES) for text in normalized_sample_texts)
    sensory_hits = sum(_count_cue_hits(text, SENSORY_CUES) for text in normalized_sample_texts)
    dialogue_ratio = round(dialogue_hits / max(1, len(sentences)), 2)
    top_phrases = _pick_top_sample_phrases(normalized_sample_texts)

    return {
        "profile_name": normalized_profile_name,
        "source_type": "sample_texts",
        "style": normalized_style,
        "voice_summary": _build_voice_summary(
            normalized_style,
            average_sentence_length=average_sentence_length,
            dialogue_ratio=dialogue_ratio,
            action_hits=action_hits,
            sensory_hits=sensory_hits,
        ),
        "preferred_traits": _build_preferred_traits(
            normalized_style,
            average_sentence_length=average_sentence_length,
            dialogue_ratio=dialogue_ratio,
            top_phrases=top_phrases,
        ),
        "avoid_phrases": _build_avoid_phrases(normalized_style),
        "dialogue_rules": _build_dialogue_rules(normalized_style, dialogue_ratio),
        "narration_rules": _build_narration_rules(normalized_style, sensory_hits, action_hits),
        "scene_rules": _build_scene_rules(normalized_style, sensory_hits, action_hits),
        "sentence_rhythm_rules": _build_sentence_rhythm_rules(average_sentence_length),
        "sample_metrics": {
            "sample_count": len(normalized_sample_texts),
            "total_chars": total_chars,
            "sentence_count": len(sentences),
            "average_sentence_length": average_sentence_length,
            "dialogue_hits": dialogue_hits,
            "dialogue_ratio": dialogue_ratio,
            "action_hits": action_hits,
            "sensory_hits": sensory_hits,
            "top_phrases": top_phrases,
        },
    }


def build_style_profile_from_builtin(
    *,
    profile_name: str,
    builtin_profile_name: str,
) -> dict[str, Any]:
    normalized_profile_name = _normalize_profile_name(profile_name)
    normalized_builtin_profile_name = _normalize_profile_name(builtin_profile_name)
    builtin_profile = get_builtin_style_profile(normalized_builtin_profile_name)
    if builtin_profile is None:
        raise ValueError(f"未找到内置风格画像：{normalized_builtin_profile_name}")
    profile = deepcopy(builtin_profile)
    profile["profile_name"] = normalized_profile_name
    profile["based_on"] = normalized_builtin_profile_name
    return profile


def build_style_profile(
    *,
    profile_name: str,
    style: str | None = None,
    sample_texts: list[str] | None = None,
    builtin_profile_name: str | None = None,
) -> dict[str, Any]:
    normalized_profile_name = _normalize_profile_name(profile_name)
    if sample_texts is not None and builtin_profile_name is not None:
        raise ValueError("sample_texts 和 builtin_profile_name 不能同时传。")

    if sample_texts is not None:
        if style is None:
            raise ValueError("使用 sample_texts 构建画像时，style 必填。")
        return build_style_profile_from_samples(
            profile_name=normalized_profile_name,
            style=style,
            sample_texts=sample_texts,
        )

    if builtin_profile_name is not None:
        return build_style_profile_from_builtin(
            profile_name=normalized_profile_name,
            builtin_profile_name=builtin_profile_name,
        )

    builtin_profile = get_builtin_style_profile(normalized_profile_name)
    if builtin_profile is not None:
        return builtin_profile

    raise ValueError("必须传 sample_texts，或传 builtin_profile_name，或直接使用内置 profile_name。")


def normalize_style_profile_record(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("profile 必须是对象。")
    normalized = {
        "profile_name": _normalize_profile_name(record.get("profile_name")),
        "source_type": _normalize_source_type(record.get("source_type")),
        "style": _normalize_style(record.get("style")),
        "voice_summary": _normalize_string(record.get("voice_summary"), "voice_summary"),
        "preferred_traits": [item for item in _normalize_sample_texts(record.get("preferred_traits"))],
        "avoid_phrases": [item for item in _normalize_sample_texts(record.get("avoid_phrases"))],
        "dialogue_rules": [item for item in _normalize_sample_texts(record.get("dialogue_rules"))],
        "narration_rules": [item for item in _normalize_sample_texts(record.get("narration_rules"))],
        "scene_rules": [item for item in _normalize_sample_texts(record.get("scene_rules"))],
        "sentence_rhythm_rules": [
            item for item in _normalize_sample_texts(record.get("sentence_rhythm_rules"))
        ],
        "sample_metrics": record.get("sample_metrics", {}),
    }
    if not isinstance(normalized["sample_metrics"], dict):
        raise ValueError("sample_metrics 必须是对象。")
    based_on = record.get("based_on")
    if based_on is not None:
        normalized["based_on"] = _normalize_string(based_on, "based_on")
    return normalized
