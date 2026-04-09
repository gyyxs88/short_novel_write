from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tools.story_plan_builder import resolve_default_target_char_range


VALID_STYLES = {"zhihu", "douban"}
VALID_GENERATION_MODES = {"deterministic", "llm"}


@dataclass(frozen=True)
class GenerationRoute:
    generation_mode: str = "deterministic"
    llm_environment: str | None = None
    provider: str | None = None
    model: str | None = None
    api_mode: str | None = None

    def __post_init__(self) -> None:
        normalized_mode = self.generation_mode.strip()
        object.__setattr__(self, "generation_mode", normalized_mode)
        if normalized_mode not in VALID_GENERATION_MODES:
            raise ValueError(f"generation_mode 仅支持：{sorted(VALID_GENERATION_MODES)}")

        normalized_environment = self.llm_environment.strip() if isinstance(self.llm_environment, str) else None
        normalized_provider = self.provider.strip() if isinstance(self.provider, str) else None
        normalized_model = self.model.strip() if isinstance(self.model, str) else None
        normalized_api_mode = self.api_mode.strip() if isinstance(self.api_mode, str) else None
        object.__setattr__(self, "llm_environment", normalized_environment or None)
        object.__setattr__(self, "provider", normalized_provider or None)
        object.__setattr__(self, "model", normalized_model or None)
        object.__setattr__(self, "api_mode", normalized_api_mode or None)

        if normalized_mode == "deterministic":
            if any(
                value is not None
                for value in (normalized_environment, normalized_provider, normalized_model, normalized_api_mode)
            ):
                raise ValueError("deterministic 路由不能再传 llm_environment 或 provider/model/api_mode。")
            return

        if normalized_environment and any(value is not None for value in (normalized_provider, normalized_model, normalized_api_mode)):
            raise ValueError("llm_environment 和 provider/model/api_mode 不能混用。")

    def to_action_payload(self) -> dict[str, str]:
        payload = {"generation_mode": self.generation_mode}
        if self.llm_environment is not None:
            payload["llm_environment"] = self.llm_environment
        if self.provider is not None:
            payload["provider"] = self.provider
        if self.model is not None:
            payload["model"] = self.model
        if self.api_mode is not None:
            payload["api_mode"] = self.api_mode
        return payload


@dataclass(frozen=True)
class DraftPostprocessConfig:
    auto_revise: bool = False
    revision_profile_name: str | None = None
    revision_modes: tuple[str, ...] = ()
    revision_issue_codes: tuple[str, ...] = ()
    revision_max_rounds: int = 2
    revision_max_spans_per_round: int = 3

    def __post_init__(self) -> None:
        normalized_profile_name = (
            self.revision_profile_name.strip() if isinstance(self.revision_profile_name, str) else None
        )
        normalized_modes = tuple(
            item.strip() for item in self.revision_modes if isinstance(item, str) and item.strip()
        )
        normalized_issue_codes = tuple(
            item.strip() for item in self.revision_issue_codes if isinstance(item, str) and item.strip()
        )
        object.__setattr__(self, "revision_profile_name", normalized_profile_name or None)
        object.__setattr__(self, "revision_modes", normalized_modes)
        object.__setattr__(self, "revision_issue_codes", normalized_issue_codes)

        if not isinstance(self.auto_revise, bool):
            raise ValueError("auto_revise 必须是布尔值。")
        if not isinstance(self.revision_max_rounds, int) or self.revision_max_rounds < 1:
            raise ValueError("revision_max_rounds 必须大于等于 1。")
        if not isinstance(self.revision_max_spans_per_round, int) or self.revision_max_spans_per_round < 1:
            raise ValueError("revision_max_spans_per_round 必须大于等于 1。")
        if not self.auto_revise and (
            normalized_profile_name is not None or normalized_modes or normalized_issue_codes
        ):
            raise ValueError("关闭 auto_revise 时，不应再传 revision_* 配置。")

    def to_action_payload(self) -> dict[str, object]:
        if not self.auto_revise:
            return {}
        payload: dict[str, object] = {
            "auto_revise": True,
            "revision_max_rounds": self.revision_max_rounds,
            "revision_max_spans_per_round": self.revision_max_spans_per_round,
        }
        if self.revision_profile_name is not None:
            payload["revision_profile_name"] = self.revision_profile_name
        if self.revision_modes:
            payload["revision_modes"] = list(self.revision_modes)
        if self.revision_issue_codes:
            payload["revision_issue_codes"] = list(self.revision_issue_codes)
        return payload


@dataclass(frozen=True)
class RegressionSample:
    sample_key: str
    style: str
    prompt: str
    target_char_range: tuple[int, int] | None = None
    target_chapter_count: int = 6
    candidate_count: int = 3
    plan_count: int = 4
    idea_pack_route: GenerationRoute = GenerationRoute()
    plan_route: GenerationRoute = GenerationRoute(
        generation_mode="llm",
        llm_environment="zhihu_plan_default",
    )
    draft_route: GenerationRoute = GenerationRoute(
        generation_mode="llm",
        llm_environment="zhihu_draft_default",
    )
    draft_postprocess: DraftPostprocessConfig = DraftPostprocessConfig()
    selected_plan_variant_index: int = 1
    enabled: bool = True
    notes: str = ""
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        normalized_key = self.sample_key.strip()
        normalized_style = self.style.strip()
        normalized_prompt = self.prompt.strip()
        normalized_notes = self.notes.strip()
        normalized_tags = tuple(item.strip() for item in self.tags if isinstance(item, str) and item.strip())
        normalized_target_char_range = self.target_char_range
        if normalized_target_char_range is None:
            normalized_target_char_range = resolve_default_target_char_range(normalized_style)
        object.__setattr__(self, "sample_key", normalized_key)
        object.__setattr__(self, "style", normalized_style)
        object.__setattr__(self, "prompt", normalized_prompt)
        object.__setattr__(self, "notes", normalized_notes)
        object.__setattr__(self, "tags", normalized_tags)
        object.__setattr__(self, "target_char_range", normalized_target_char_range)

        if not normalized_key:
            raise ValueError("sample_key 必须是非空字符串。")
        if normalized_style not in VALID_STYLES:
            raise ValueError(f"style 仅支持：{sorted(VALID_STYLES)}")
        if not normalized_prompt:
            raise ValueError("prompt 必须是非空字符串。")
        if (
            len(normalized_target_char_range) != 2
            or not all(isinstance(item, int) and item > 0 for item in normalized_target_char_range)
            or normalized_target_char_range[0] > normalized_target_char_range[1]
        ):
            raise ValueError("target_char_range 必须是两个递增正整数。")
        if not isinstance(self.target_chapter_count, int) or self.target_chapter_count < 1:
            raise ValueError("target_chapter_count 必须大于等于 1。")
        if not isinstance(self.candidate_count, int) or self.candidate_count < 1:
            raise ValueError("candidate_count 必须大于等于 1。")
        if not isinstance(self.plan_count, int) or self.plan_count < 1:
            raise ValueError("plan_count 必须大于等于 1。")
        if not isinstance(self.selected_plan_variant_index, int) or self.selected_plan_variant_index < 1:
            raise ValueError("selected_plan_variant_index 必须大于等于 1。")
        if not isinstance(self.draft_postprocess, DraftPostprocessConfig):
            raise ValueError("draft_postprocess 必须是 DraftPostprocessConfig。")


_ZHIHU_PLAN_ROUTE = GenerationRoute(generation_mode="llm", llm_environment="zhihu_plan_default")
_ZHIHU_DRAFT_ROUTE = GenerationRoute(generation_mode="llm", llm_environment="zhihu_draft_default")
_DOUBAN_PLAN_ROUTE = GenerationRoute(generation_mode="llm", llm_environment="douban_plan_default")
_DOUBAN_DRAFT_ROUTE = GenerationRoute(generation_mode="llm", llm_environment="douban_draft_default")
_ZHIHU_DRAFT_POSTPROCESS = DraftPostprocessConfig(
    auto_revise=True,
    revision_profile_name="zhihu_tight_hook",
    revision_modes=("remove_ai_phrases", "compress_exposition", "concretize_emotion"),
    revision_max_rounds=2,
    revision_max_spans_per_round=3,
)
_DOUBAN_DRAFT_POSTPROCESS = DraftPostprocessConfig(
    auto_revise=True,
    revision_profile_name="douban_subtle_scene",
    revision_modes=("remove_ai_phrases", "compress_exposition", "concretize_emotion", "strengthen_scene"),
    revision_max_rounds=2,
    revision_max_spans_per_round=3,
)


def build_default_draft_postprocess(style: str) -> DraftPostprocessConfig:
    normalized_style = style.strip()
    if normalized_style == "zhihu":
        return _ZHIHU_DRAFT_POSTPROCESS
    if normalized_style == "douban":
        return _DOUBAN_DRAFT_POSTPROCESS
    raise ValueError(f"style 仅支持：{sorted(VALID_STYLES)}")


BUILTIN_SAMPLES = (
    RegressionSample(
        sample_key="zhihu_wedding_sms",
        style="zhihu",
        prompt="婚礼前夜，女主收到失踪前任的求救短信，被迫在婚礼开始前查清旧案和未婚夫秘密，默认知乎风格，1-3万字。",
        plan_route=_ZHIHU_PLAN_ROUTE,
        draft_route=_ZHIHU_DRAFT_ROUTE,
        draft_postprocess=_ZHIHU_DRAFT_POSTPROCESS,
        notes="已在真实校准里验证过。",
        tags=("default", "verified", "zhihu"),
    ),
    RegressionSample(
        sample_key="zhihu_divorce_notice",
        style="zhihu",
        prompt="离婚冷静期最后一天，女主收到丈夫的死亡赔偿通知，可丈夫昨晚明明还在家里，默认知乎风格，1-3万字。",
        plan_route=_ZHIHU_PLAN_ROUTE,
        draft_route=_ZHIHU_DRAFT_ROUTE,
        draft_postprocess=_ZHIHU_DRAFT_POSTPROCESS,
        notes="已在真实校准里验证过。",
        tags=("default", "verified", "zhihu"),
    ),
    RegressionSample(
        sample_key="zhihu_hostage_livestream",
        style="zhihu",
        prompt="头部女主播在婚礼直播时收到绑匪发来的倒计时视频，视频里的被绑者竟是三年前失踪的弟弟，她必须在热搜炸开前查出幕后操盘者，默认知乎风格，1-3万字。",
        plan_route=_ZHIHU_PLAN_ROUTE,
        draft_route=_ZHIHU_DRAFT_ROUTE,
        draft_postprocess=_ZHIHU_DRAFT_POSTPROCESS,
        notes="新增知乎强钩子样本。",
        tags=("default", "zhihu"),
    ),
    RegressionSample(
        sample_key="zhihu_fake_obituary",
        style="zhihu",
        prompt="葬礼主持结束后，女主收到自己的讣告推送，发布时间却是明天凌晨，她必须在二十四小时内查出是谁提前替她写好了死亡结局，默认知乎风格，1-3万字。",
        plan_route=_ZHIHU_PLAN_ROUTE,
        draft_route=_ZHIHU_DRAFT_ROUTE,
        draft_postprocess=_ZHIHU_DRAFT_POSTPROCESS,
        notes="新增知乎倒计时样本。",
        tags=("default", "zhihu"),
    ),
    RegressionSample(
        sample_key="zhihu_inheritance_key",
        style="zhihu",
        prompt="父亲遗嘱要求女主在四十八小时内带着前男友回旧宅开锁，否则全部遗产自动捐出，可锁里藏着一宗十年前命案的最后证据，默认知乎风格，1-3万字。",
        plan_route=_ZHIHU_PLAN_ROUTE,
        draft_route=_ZHIHU_DRAFT_ROUTE,
        draft_postprocess=_ZHIHU_DRAFT_POSTPROCESS,
        notes="新增知乎高概念样本。",
        tags=("default", "zhihu"),
    ),
    RegressionSample(
        sample_key="douban_funeral_letter",
        style="douban",
        prompt="母亲葬礼结束后，女主在旧书里翻到高中恋人写给自己的未寄出信，决定回小城住一周，默认豆瓣风格，1-2万字。",
        plan_route=_DOUBAN_PLAN_ROUTE,
        draft_route=_DOUBAN_DRAFT_ROUTE,
        draft_postprocess=_DOUBAN_DRAFT_POSTPROCESS,
        notes="已在真实校准里验证过。",
        tags=("default", "verified", "douban"),
    ),
    RegressionSample(
        sample_key="douban_closed_cinema",
        style="douban",
        prompt="停业多年的老影院准备拆除前一周，女主回城整理遗物，在放映室里找到少年时暗恋对象留下的录音带，默认豆瓣风格，1-2万字。",
        plan_route=_DOUBAN_PLAN_ROUTE,
        draft_route=_DOUBAN_DRAFT_ROUTE,
        draft_postprocess=_DOUBAN_DRAFT_POSTPROCESS,
        notes="新增豆瓣关系余味样本。",
        tags=("default", "douban"),
    ),
    RegressionSample(
        sample_key="douban_rain_station",
        style="douban",
        prompt="暴雨夜最后一班火车停在小站，女主被迫和多年未见的姐姐共住候车室，旧日失踪案和家里最不能提的那个人一起被翻出来，默认豆瓣风格，1-2万字。",
        plan_route=_DOUBAN_PLAN_ROUTE,
        draft_route=_DOUBAN_DRAFT_ROUTE,
        draft_postprocess=_DOUBAN_DRAFT_POSTPROCESS,
        notes="新增豆瓣家庭关系样本。",
        tags=("default", "douban"),
    ),
    RegressionSample(
        sample_key="douban_old_house_key",
        style="douban",
        prompt="外婆去世后，女主拿到一把从未见过的旧钥匙，顺着地址回到海边小城，发现少年时最亲近的人早就替她藏起一段没人肯说的往事，默认豆瓣风格，1-2万字。",
        plan_route=_DOUBAN_PLAN_ROUTE,
        draft_route=_DOUBAN_DRAFT_ROUTE,
        draft_postprocess=_DOUBAN_DRAFT_POSTPROCESS,
        notes="新增豆瓣返乡样本。",
        tags=("default", "douban"),
    ),
    RegressionSample(
        sample_key="douban_archive_photo",
        style="douban",
        prompt="档案馆整理旧照片时，女主发现母亲年轻时和自己初恋站在同一张合影里，她只好回到阔别多年的厂区宿舍，把那段被全家默许删除的关系重新拼起来，默认豆瓣风格，1-2万字。",
        plan_route=_DOUBAN_PLAN_ROUTE,
        draft_route=_DOUBAN_DRAFT_ROUTE,
        draft_postprocess=_DOUBAN_DRAFT_POSTPROCESS,
        notes="新增豆瓣记忆追索样本。",
        tags=("default", "douban"),
    ),
)


SAMPLE_SETS = {
    "default": tuple(sample.sample_key for sample in BUILTIN_SAMPLES if sample.enabled),
    "verified": tuple(sample.sample_key for sample in BUILTIN_SAMPLES if "verified" in sample.tags),
    "zhihu": tuple(sample.sample_key for sample in BUILTIN_SAMPLES if sample.style == "zhihu" and sample.enabled),
    "douban": tuple(sample.sample_key for sample in BUILTIN_SAMPLES if sample.style == "douban" and sample.enabled),
}


def list_builtin_samples() -> list[RegressionSample]:
    return list(BUILTIN_SAMPLES)


def get_sample_set_names() -> list[str]:
    return sorted(SAMPLE_SETS.keys())


def select_builtin_samples(
    *,
    sample_set: str = "default",
    sample_keys: Iterable[str] | None = None,
    styles: Iterable[str] | None = None,
    include_disabled: bool = False,
) -> list[RegressionSample]:
    if sample_set not in SAMPLE_SETS:
        raise ValueError(f"sample_set 仅支持：{sorted(SAMPLE_SETS)}")

    wanted_keys = set(SAMPLE_SETS[sample_set])
    if sample_keys is not None:
        normalized_keys = {item.strip() for item in sample_keys if isinstance(item, str) and item.strip()}
        if not normalized_keys:
            raise ValueError("sample_keys 过滤后不能为空。")
        wanted_keys &= normalized_keys

    normalized_styles = None
    if styles is not None:
        normalized_styles = {item.strip() for item in styles if isinstance(item, str) and item.strip()}
        if not normalized_styles:
            raise ValueError("styles 过滤后不能为空。")
        invalid_styles = normalized_styles - VALID_STYLES
        if invalid_styles:
            raise ValueError(f"styles 仅支持：{sorted(VALID_STYLES)}")

    selected: list[RegressionSample] = []
    for sample in BUILTIN_SAMPLES:
        if sample.sample_key not in wanted_keys:
            continue
        if normalized_styles is not None and sample.style not in normalized_styles:
            continue
        if not include_disabled and not sample.enabled:
            continue
        selected.append(sample)

    if not selected:
        raise ValueError("过滤后没有可执行的回归样本。")
    return selected
