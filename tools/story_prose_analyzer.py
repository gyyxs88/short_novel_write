from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from tools.story_structure_checker import CHAPTER_PATTERN, SECTION_PATTERN_TEMPLATE, TITLE_PATTERN


ANALYZER_NAME = "prose_analyzer_v1"
CHINESE_CHAR_PATTERN = re.compile(r"[\u4e00-\u9fff]")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[。！？!?])")
PARAGRAPH_SPLIT_PATTERN = re.compile(r"\n\s*\n+")

REPEATED_PHRASE_STOPLIST = {
    "自己",
    "一个",
    "没有",
    "时候",
    "事情",
    "不是",
    "什么",
    "因为",
    "如果",
    "已经",
    "还是",
    "继续",
    "可以",
    "知道",
    "觉得",
    "于是",
    "后来",
    "然后",
    "但是",
    "然而",
    "其实",
    "原来",
    "终于",
}
AI_ISM_PHRASES = (
    "那一刻",
    "不由得",
    "仿佛",
    "似乎",
    "某种",
    "带着某种",
    "带着一种",
    "某种意味",
    "其实",
    "原来",
    "并没有立刻",
    "终于明白",
    "开始松动",
    "某种程度上",
    "回不到原来的样子",
)
ABSTRACT_EMOTION_TERMS = (
    "痛苦",
    "难过",
    "悲伤",
    "绝望",
    "委屈",
    "压抑",
    "不安",
    "愤怒",
    "害怕",
    "恐惧",
    "紧张",
    "崩溃",
    "释然",
    "孤独",
    "拉扯",
    "松动",
    "失控",
    "后悔",
    "心碎",
)
ABSTRACT_RELATION_TERMS = (
    "关系开始",
    "关系正在",
    "情绪开始",
    "情绪正在",
    "平静被打破",
    "回不到原来的样子",
    "再也回不去",
)
ACTION_CUES = (
    "看",
    "听",
    "摸",
    "抓",
    "推",
    "拉",
    "站",
    "坐",
    "走",
    "跑",
    "抬",
    "低头",
    "握",
    "捏",
    "笑",
    "哭",
    "喊",
    "说",
    "问",
    "回头",
    "打开",
    "关上",
    "敲",
    "盯",
    "抖",
    "碰",
    "递",
    "拿",
    "放下",
    "咽",
    "拧",
)
SENSORY_CUES = (
    "门",
    "窗",
    "桌",
    "椅",
    "灯",
    "雨",
    "风",
    "冷",
    "热",
    "亮",
    "暗",
    "潮",
    "湿",
    "手",
    "眼",
    "呼吸",
    "脚步",
    "手机",
    "衣角",
    "气味",
    "声音",
    "走廊",
    "房间",
    "玻璃",
)
KNOWN_OPENERS = (
    "那一刻",
    "直到这时",
    "直到这一章",
    "她知道",
    "她没有",
    "她终于",
    "她还是",
    "她想",
    "她明白",
    "我知道",
    "我没有",
    "我终于",
    "然而",
    "但是",
    "可是",
    "结果",
    "原来",
)
GENERIC_PRONOUN_OPENERS = {"她", "他", "我"}
QUESTION_SENTENCE_ENDINGS = ("？", "?")
EYE_EMOTION_CUE_PATTERNS = (
    re.compile(r"(眼神|眼底)[^。！？\n]{0,8}(闪过|闪烁)"),
    re.compile(r"闪过一丝[^。！？\n]{0,10}"),
)
VAGUE_ATTITUDE_PATTERNS = (
    re.compile(r"带着[^。！？\n]{0,10}意味"),
    re.compile(r"带着[^。！？\n]{0,10}(态度|口吻)"),
)
LAZY_JUDGMENT_PHRASES = (
    "不容拒绝",
    "不容置疑",
    "不易察觉",
    "难以察觉",
    "不可置信",
)
BALANCED_EXPLANATORY_PATTERNS = (
    re.compile(r"不是[^。！？\n]{1,24}而是[^。！？\n]{1,24}"),
    re.compile(r"不仅[^。！？\n]{1,24}更是[^。！？\n]{1,24}"),
)
ANIMAL_SIMILE_PATTERNS = (
    re.compile(r"像一只[\u4e00-\u9fff]{1,4}"),
    re.compile(r"像只[\u4e00-\u9fff]{1,4}"),
)
IMPACT_METAPHOR_PATTERNS = (
    re.compile(r"(掀起|泛起)[^。！？\n]{0,8}(涟漪|波澜|巨浪)"),
    re.compile(r"(像|如同)[^。！？\n]{0,16}(巨石|重锤|惊雷)"),
    re.compile(r"(湖面|心湖|油锅)[^。！？\n]{0,10}(巨石|石子|炸弹|重锤|惊雷)"),
)


@dataclass(slots=True)
class ChapterSpan:
    chapter_number: int
    content: str
    start_offset: int
    end_offset: int

    @property
    def paragraphs(self) -> list[str]:
        return split_paragraphs(self.content)


@dataclass(slots=True)
class StoryProseIssue:
    issue_code: str
    severity: str
    message: str
    rewrite_goal: str
    chapter_number: int | None = None
    span_text: str = ""
    start_offset: int = 0
    end_offset: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_code": self.issue_code,
            "severity": self.severity,
            "message": self.message,
            "rewrite_goal": self.rewrite_goal,
            "chapter_number": self.chapter_number,
            "span_text": self.span_text,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class StoryProseRiskSignal:
    signal_code: str
    message: str
    review_hint: str
    chapter_number: int | None = None
    span_text: str = ""
    start_offset: int = 0
    end_offset: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_code": self.signal_code,
            "message": self.message,
            "review_hint": self.review_hint,
            "chapter_number": self.chapter_number,
            "span_text": self.span_text,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class StoryProseAnalysisReport:
    title: str = ""
    style: str = ""
    analyzer_name: str = ANALYZER_NAME
    overall_score: int = 100
    dimension_scores: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    issues: list[StoryProseIssue] = field(default_factory=list)
    risk_signals: list[StoryProseRiskSignal] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def risk_signal_count(self) -> int:
        return len(self.risk_signals)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "style": self.style,
            "analyzer_name": self.analyzer_name,
            "overall_score": self.overall_score,
            "dimension_scores": self.dimension_scores,
            "metrics": self.metrics,
            "issue_count": self.issue_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "risk_signal_count": self.risk_signal_count,
            "risk_signals": [signal.to_dict() for signal in self.risk_signals],
            "suggestions": self.suggestions,
        }


def _extract_title(markdown_text: str) -> str:
    match = TITLE_PATTERN.search(markdown_text)
    if not match:
        return ""
    return match.group(1).strip()


def _extract_section_span(markdown_text: str, title: str) -> tuple[str, int, int]:
    pattern = re.compile(SECTION_PATTERN_TEMPLATE.format(title=re.escape(title)))
    match = pattern.search(markdown_text)
    if not match:
        return "", -1, -1
    return match.group(1).strip(), match.start(1), match.end(1)


def _extract_chapter_spans(markdown_text: str) -> list[ChapterSpan]:
    body_text, body_start, _body_end = _extract_section_span(markdown_text, "正文")
    if not body_text or body_start < 0:
        return []
    chapters: list[ChapterSpan] = []
    for match in CHAPTER_PATTERN.finditer(body_text):
        chapters.append(
            ChapterSpan(
                chapter_number=int(match.group(1)),
                content=match.group(2).strip(),
                start_offset=body_start + match.start(2),
                end_offset=body_start + match.end(2),
            )
        )
    return chapters


def split_paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in PARAGRAPH_SPLIT_PATTERN.split(text.strip()) if paragraph.strip()]


def split_sentences(text: str) -> list[str]:
    chunks = SENTENCE_SPLIT_PATTERN.split(text.strip())
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def normalize_chinese_text(text: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff]", "", text)


def locate_span_offsets(chapter: ChapterSpan, span_text: str) -> tuple[int, int]:
    if not span_text:
        return chapter.start_offset, chapter.start_offset
    local_index = chapter.content.find(span_text)
    if local_index == -1 and len(span_text) > 40:
        prefix = span_text[:40]
        prefix_index = chapter.content.find(prefix)
        if prefix_index != -1:
            start_offset = chapter.start_offset + prefix_index
            return start_offset, start_offset + len(span_text)
    if local_index == -1:
        return chapter.start_offset, chapter.start_offset
    return chapter.start_offset + local_index, chapter.start_offset + local_index + len(span_text)


def build_dimension_scores(issues: list[StoryProseIssue]) -> dict[str, int]:
    issue_weights = {
        "repeated_phrase": 15,
        "repeated_paragraph_opener": 12,
        "ai_ism": 12,
        "abstract_emotion": 14,
        "scene_thin": 18,
        "template_chapter": 18,
    }
    dimensions = {code: 100 for code in issue_weights}
    for issue in issues:
        deduction = issue_weights.get(issue.issue_code, 10)
        if issue.severity == "medium":
            deduction = max(8, deduction - 4)
        dimensions[issue.issue_code] = max(0, dimensions.get(issue.issue_code, 100) - deduction)
    return dimensions


def build_overall_score(dimension_scores: dict[str, int]) -> int:
    if not dimension_scores:
        return 100
    return max(0, min(100, round(sum(dimension_scores.values()) / len(dimension_scores))))


def build_suggestions(
    issues: list[StoryProseIssue],
    *,
    style: str = "",
    risk_signals: list[StoryProseRiskSignal] | None = None,
) -> list[str]:
    suggestions: list[str] = []
    issue_codes = {issue.issue_code for issue in issues}
    signal_codes = {signal.signal_code for signal in (risk_signals or [])}
    if "repeated_phrase" in issue_codes:
        suggestions.append("先删掉高频复用短语，把重复表达拆成更具体的动作、物件或句式。")
    if "repeated_paragraph_opener" in issue_codes:
        suggestions.append("打散段落起手式，不要连续多段都用同一类主语或转折词开头。")
    if "ai_ism" in issue_codes:
        suggestions.append("减少高频 AI 腔词，优先改掉“那一刻”“仿佛”“其实”这类胶水表达。")
    if "abstract_emotion" in issue_codes:
        suggestions.append("把抽象情绪改成可见动作、身体反应、停顿、对话或物件互动。")
    if "scene_thin" in issue_codes:
        suggestions.append("给稀薄章节补一个具体场景，让空间、动作、声音或对话先落地，再承接情绪。")
    if "template_chapter" in issue_codes:
        suggestions.append("打散章节模板感，避免每章都按同一种段落职责和同一种起手节奏展开。")
    if "eye_emotion_cue" in signal_codes:
        suggestions.append("少用“眼神闪过”“眼底闪过”这类直给神态提示，优先换成动作、停顿或对白。")
    if "vague_attitude_phrase" in signal_codes:
        suggestions.append("少用“带着……意味/口吻/态度”这类空泛补缀词，尽量把意味落成具体说话方式或动作。")
    if "lazy_judgment_phrase" in signal_codes:
        suggestions.append("少用“不容置疑”“难以察觉”这类作者代判语，让读者从现场自己得出判断。")
    if "balanced_explanatory_sentence" in signal_codes:
        suggestions.append("控制“不是……而是……”这类整齐解释句的密度，必要时拆成两句写。")
    if "animal_simile" in signal_codes:
        suggestions.append("遇到“像一只……”这类动物比喻，先看它是不是人物真正会想到的比法，不贴就删。")
    if "impact_metaphor_cliche" in signal_codes:
        suggestions.append("少用“巨石”“惊雷”“涟漪”“波澜”这类冲击型套比喻，先看现场动作和结果能不能自己成立。")
    if style == "douban":
        suggestions.append("豆瓣风优先压掉空泛抒情，把余味落在具体场景和人物停顿上。")
    if style == "zhihu":
        suggestions.append("知乎风优先保留钩子和推进，但要避免每章都用同样的强转折句法。")
    deduplicated: list[str] = []
    for suggestion in suggestions:
        if suggestion not in deduplicated:
            deduplicated.append(suggestion)
    return deduplicated


def _phrase_is_usable(phrase: str) -> bool:
    if len(phrase) < 2:
        return False
    if phrase in REPEATED_PHRASE_STOPLIST:
        return False
    if len(set(phrase)) <= 1:
        return False
    return bool(CHINESE_CHAR_PATTERN.search(phrase))


def analyze_repeated_phrases(chapters: list[ChapterSpan]) -> tuple[list[StoryProseIssue], dict[str, Any]]:
    chapter_phrase_counters: dict[int, Counter[str]] = defaultdict(Counter)
    overall_counter: Counter[str] = Counter()
    thresholds = {4: 3, 3: 4, 2: 6}

    for chapter in chapters:
        cleaned = normalize_chinese_text(chapter.content)
        for n, threshold in thresholds.items():
            if len(cleaned) < n:
                continue
            for index in range(len(cleaned) - n + 1):
                phrase = cleaned[index : index + n]
                if not _phrase_is_usable(phrase):
                    continue
                overall_counter[phrase] += 1
                chapter_phrase_counters[chapter.chapter_number][phrase] += 1

    suspicious_items: list[tuple[str, int, list[int]]] = []
    for phrase, count in overall_counter.items():
        threshold = thresholds.get(len(phrase), 4)
        if count < threshold:
            continue
        chapter_numbers = sorted(
            chapter_number
            for chapter_number, phrase_counter in chapter_phrase_counters.items()
            if phrase_counter[phrase] > 0
        )
        if len(chapter_numbers) < 2 and max(
            chapter_phrase_counters[chapter_number][phrase] for chapter_number in chapter_numbers
        ) < threshold:
            continue
        suspicious_items.append((phrase, count, chapter_numbers))

    suspicious_items.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))
    issues: list[StoryProseIssue] = []
    for phrase, count, chapter_numbers in suspicious_items[:3]:
        target_chapter = next((chapter for chapter in chapters if chapter.chapter_number in chapter_numbers), None)
        start_offset = 0
        end_offset = 0
        span_text = phrase
        if target_chapter is not None:
            start_offset, end_offset = locate_span_offsets(target_chapter, phrase)
        issues.append(
            StoryProseIssue(
                issue_code="repeated_phrase",
                severity="high" if count >= 6 else "medium",
                message=f"短语“{phrase}”重复过多，读起来像模板回声。",
                rewrite_goal="把重复短语改成不同的动作、意象或句法，不要整章复读同一个说法。",
                chapter_number=target_chapter.chapter_number if target_chapter else None,
                span_text=span_text,
                start_offset=start_offset,
                end_offset=end_offset,
                evidence={
                    "phrase": phrase,
                    "count": count,
                    "chapter_numbers": chapter_numbers,
                },
            )
        )

    return issues, {
        "repeated_phrase_count": len(suspicious_items),
        "top_repeated_phrases": [
            {"phrase": phrase, "count": count, "chapter_numbers": chapter_numbers}
            for phrase, count, chapter_numbers in suspicious_items[:5]
        ],
    }


def normalize_paragraph_opener(paragraph: str) -> str:
    normalized = paragraph.strip().lstrip("“\"'（(").strip()
    if not normalized:
        return ""
    for opener in KNOWN_OPENERS:
        if normalized.startswith(opener):
            return opener
    if normalized[0] in GENERIC_PRONOUN_OPENERS:
        return normalized[0]
    return normalized[:4]


def analyze_repeated_paragraph_openers(chapters: list[ChapterSpan]) -> tuple[list[StoryProseIssue], dict[str, Any]]:
    opener_occurrences: dict[str, list[tuple[int, str, ChapterSpan]]] = defaultdict(list)
    for chapter in chapters:
        for paragraph in chapter.paragraphs:
            opener = normalize_paragraph_opener(paragraph)
            if not opener:
                continue
            opener_occurrences[opener].append((chapter.chapter_number, paragraph, chapter))

    suspicious: list[tuple[str, list[tuple[int, str, ChapterSpan]]]] = []
    for opener, occurrences in opener_occurrences.items():
        if opener in GENERIC_PRONOUN_OPENERS:
            if len(occurrences) >= 4:
                suspicious.append((opener, occurrences))
            continue
        if len(occurrences) >= 3:
            suspicious.append((opener, occurrences))

    suspicious.sort(key=lambda item: (-len(item[1]), item[0]))
    issues: list[StoryProseIssue] = []
    for opener, occurrences in suspicious[:3]:
        chapter_number, paragraph, chapter = occurrences[0]
        start_offset, end_offset = locate_span_offsets(chapter, paragraph)
        issues.append(
            StoryProseIssue(
                issue_code="repeated_paragraph_opener",
                severity="high" if len(occurrences) >= 5 else "medium",
                message=f"段落起手式“{opener}”重复过多，段落节奏容易显得单一。",
                rewrite_goal="打散段首表达，换掉重复主语或转折词，让段落切入方式更有变化。",
                chapter_number=chapter_number,
                span_text=paragraph,
                start_offset=start_offset,
                end_offset=end_offset,
                evidence={
                    "opener": opener,
                    "count": len(occurrences),
                    "chapter_numbers": sorted({item[0] for item in occurrences}),
                },
            )
        )

    return issues, {
        "repeated_paragraph_opener_count": len(suspicious),
        "top_repeated_paragraph_openers": [
            {
                "opener": opener,
                "count": len(occurrences),
                "chapter_numbers": sorted({item[0] for item in occurrences}),
            }
            for opener, occurrences in suspicious[:5]
        ],
    }


def analyze_ai_ism_hits(chapters: list[ChapterSpan]) -> tuple[list[StoryProseIssue], dict[str, Any]]:
    phrase_counts: list[tuple[str, int]] = []
    for phrase in AI_ISM_PHRASES:
        total = sum(chapter.content.count(phrase) for chapter in chapters)
        if total > 0:
            phrase_counts.append((phrase, total))
    phrase_counts.sort(key=lambda item: (-item[1], item[0]))
    total_hits = sum(count for _, count in phrase_counts)
    issues: list[StoryProseIssue] = []
    if total_hits >= 3:
        phrase = phrase_counts[0][0]
        target_chapter = next((chapter for chapter in chapters if phrase in chapter.content), None)
        start_offset = 0
        end_offset = 0
        if target_chapter is not None:
            start_offset, end_offset = locate_span_offsets(target_chapter, phrase)
        issues.append(
            StoryProseIssue(
                issue_code="ai_ism",
                severity="high" if total_hits >= 5 else "medium",
                message="正文里高频出现 AI 腔胶水词，读感会变得过于顺滑和同质。",
                rewrite_goal="保留必要意思，但把 AI 腔词替换成更具体的动作、因果或细节。",
                chapter_number=target_chapter.chapter_number if target_chapter else None,
                span_text=phrase,
                start_offset=start_offset,
                end_offset=end_offset,
                evidence={
                    "total_hits": total_hits,
                    "phrase_counts": [{"phrase": phrase_text, "count": count} for phrase_text, count in phrase_counts],
                },
            )
        )
    return issues, {
        "ai_ism_total_hits": total_hits,
        "ai_ism_phrase_counts": [{"phrase": phrase, "count": count} for phrase, count in phrase_counts],
    }


def sentence_has_concrete_support(sentence: str) -> bool:
    if "“" in sentence and "”" in sentence:
        return True
    return any(cue in sentence for cue in ACTION_CUES) or any(cue in sentence for cue in SENSORY_CUES)


def sentence_has_unbalanced_dialogue_quotes(sentence: str) -> bool:
    return sentence.count("“") != sentence.count("”")


def analyze_abstract_emotion(chapters: list[ChapterSpan]) -> tuple[list[StoryProseIssue], dict[str, Any]]:
    hits: list[tuple[ChapterSpan, str, str, int, int]] = []
    for chapter in chapters:
        search_cursor = 0
        for sentence in split_sentences(chapter.content):
            local_start = chapter.content.find(sentence, search_cursor)
            if local_start == -1:
                local_start = chapter.content.find(sentence)
            local_end = local_start + len(sentence) if local_start >= 0 else -1
            if local_end >= 0:
                search_cursor = local_end
            matched_term = next(
                (
                    term
                    for term in (*ABSTRACT_RELATION_TERMS, *ABSTRACT_EMOTION_TERMS)
                    if term in sentence
                ),
                "",
            )
            if not matched_term:
                continue
            if sentence.endswith(QUESTION_SENTENCE_ENDINGS):
                continue
            if sentence_has_unbalanced_dialogue_quotes(sentence):
                continue
            if sentence_has_concrete_support(sentence):
                continue
            hits.append((chapter, sentence, matched_term, local_start, local_end))

    issues: list[StoryProseIssue] = []
    for chapter, sentence, matched_term, local_start, local_end in hits[:4]:
        if local_start >= 0 and local_end >= 0:
            start_offset = chapter.start_offset + local_start
            end_offset = chapter.start_offset + local_end
        else:
            start_offset, end_offset = locate_span_offsets(chapter, sentence)
        issues.append(
            StoryProseIssue(
                issue_code="abstract_emotion",
                severity="high" if len(sentence) >= 18 else "medium",
                message="这里直接宣告情绪或关系变化，但缺少动作、对话或场景支撑。",
                rewrite_goal="把抽象感受落成动作、停顿、物件互动、身体反应或一句更像人物会说的话。",
                chapter_number=chapter.chapter_number,
                span_text=sentence,
                start_offset=start_offset,
                end_offset=end_offset,
                evidence={
                    "matched_term": matched_term,
                    "sentence_length": len(sentence),
                },
            )
        )

    return issues, {
        "abstract_emotion_count": len(hits),
        "abstract_emotion_terms": [matched_term for _chapter, _sentence, matched_term, _start, _end in hits[:10]],
    }


def count_cue_hits(text: str, cues: tuple[str, ...]) -> int:
    return sum(text.count(cue) for cue in cues)


def analyze_scene_density(chapters: list[ChapterSpan]) -> tuple[list[StoryProseIssue], dict[str, Any]]:
    sparse_chapters: list[dict[str, Any]] = []
    issues: list[StoryProseIssue] = []
    for chapter in chapters:
        dialogue_hits = len(re.findall(r"“[^”]+”", chapter.content))
        action_hits = count_cue_hits(chapter.content, ACTION_CUES)
        sensory_hits = count_cue_hits(chapter.content, SENSORY_CUES)
        char_count = len(re.sub(r"\s+", "", chapter.content))
        support_score = dialogue_hits * 2 + action_hits + sensory_hits
        sparse = char_count >= 80 and support_score <= max(3, char_count // 120)
        chapter_metrics = {
            "chapter_number": chapter.chapter_number,
            "char_count": char_count,
            "dialogue_hits": dialogue_hits,
            "action_hits": action_hits,
            "sensory_hits": sensory_hits,
            "support_score": support_score,
        }
        if sparse:
            sparse_chapters.append(chapter_metrics)
            span_text = chapter.content[:120]
            start_offset, end_offset = locate_span_offsets(chapter, span_text)
            issues.append(
                StoryProseIssue(
                    issue_code="scene_thin",
                    severity="high" if support_score <= 1 else "medium",
                    message=f"第 {chapter.chapter_number} 章场景支撑偏弱，解释和概括多于现场动作。",
                    rewrite_goal="补一个可见场景，把空间、动作、声音、物件或对话放进这一章。",
                    chapter_number=chapter.chapter_number,
                    span_text=span_text,
                    start_offset=start_offset,
                    end_offset=end_offset,
                    evidence=chapter_metrics,
                )
            )

    return issues, {
        "scene_thin_chapter_count": len(sparse_chapters),
        "scene_thin_chapters": sparse_chapters,
    }


def analyze_template_chapters(chapters: list[ChapterSpan]) -> tuple[list[StoryProseIssue], dict[str, Any]]:
    if len(chapters) < 2:
        return [], {"template_position_hits": []}

    position_counters: dict[int, Counter[str]] = defaultdict(Counter)
    chapter_paragraph_counts: list[int] = []
    for chapter in chapters:
        paragraphs = chapter.paragraphs
        chapter_paragraph_counts.append(len(paragraphs))
        for position, paragraph in enumerate(paragraphs[:8], start=1):
            starter = normalize_paragraph_opener(paragraph)
            if len(starter) >= 2:
                position_counters[position][starter] += 1

    required_count = max(2, (len(chapters) + 1) // 2)
    template_hits: list[dict[str, Any]] = []
    for position, counter in sorted(position_counters.items()):
        starter, count = counter.most_common(1)[0]
        if count >= required_count and len(starter) >= 2:
            template_hits.append(
                {
                    "position": position,
                    "starter": starter,
                    "count": count,
                }
            )

    issues: list[StoryProseIssue] = []
    if len(template_hits) >= 3:
        anchor_chapter = chapters[0]
        paragraphs = anchor_chapter.paragraphs
        span_text = "\n\n".join(paragraphs[: min(3, len(paragraphs))])
        start_offset, end_offset = locate_span_offsets(anchor_chapter, span_text[:240])
        issues.append(
            StoryProseIssue(
                issue_code="template_chapter",
                severity="high",
                message="多章段落起手和职责分布过于一致，章节像按同一模板反复展开。",
                rewrite_goal="打散章节骨架，不要每章都按同一组段落职责和同一种切入方式写。",
                chapter_number=anchor_chapter.chapter_number,
                span_text=span_text[:240],
                start_offset=start_offset,
                end_offset=end_offset,
                evidence={
                    "template_position_hits": template_hits,
                    "chapter_paragraph_counts": chapter_paragraph_counts,
                },
            )
        )

    return issues, {
        "template_position_hits": template_hits,
        "chapter_paragraph_counts": chapter_paragraph_counts,
    }


def _build_risk_signal(
    *,
    signal_code: str,
    message: str,
    review_hint: str,
    chapter: ChapterSpan,
    span_text: str,
    evidence: dict[str, Any],
) -> StoryProseRiskSignal:
    start_offset, end_offset = locate_span_offsets(chapter, span_text)
    return StoryProseRiskSignal(
        signal_code=signal_code,
        message=message,
        review_hint=review_hint,
        chapter_number=chapter.chapter_number,
        span_text=span_text,
        start_offset=start_offset,
        end_offset=end_offset,
        evidence=evidence,
    )


def analyze_soft_risk_signals(chapters: list[ChapterSpan]) -> tuple[list[StoryProseRiskSignal], dict[str, Any]]:
    signal_groups: dict[str, list[StoryProseRiskSignal]] = defaultdict(list)

    for chapter in chapters:
        for sentence in split_sentences(chapter.content):
            for pattern in EYE_EMOTION_CUE_PATTERNS:
                match = pattern.search(sentence)
                if match is None:
                    continue
                signal_groups["eye_emotion_cue"].append(
                    _build_risk_signal(
                        signal_code="eye_emotion_cue",
                        message="这里用了“眼神/眼底闪过”一类神态提示，读感容易落回常见套路。",
                        review_hint="先看这句是不是在直接替读者解释情绪；如果是，优先换成动作、停顿或对白。",
                        chapter=chapter,
                        span_text=sentence,
                        evidence={"matched_text": match.group(0)},
                    )
                )
                break

            for pattern in VAGUE_ATTITUDE_PATTERNS:
                match = pattern.search(sentence)
                if match is None:
                    continue
                signal_groups["vague_attitude_phrase"].append(
                    _build_risk_signal(
                        signal_code="vague_attitude_phrase",
                        message="这里用了“带着……意味/口吻/态度”一类空泛补缀词，容易把人物状态写虚。",
                        review_hint="先看能不能把“意味/口吻/态度”拆成更具体的说话方式、动作或现场反应。",
                        chapter=chapter,
                        span_text=sentence,
                        evidence={"matched_text": match.group(0)},
                    )
                )
                break

            matched_lazy_judgment = next((phrase for phrase in LAZY_JUDGMENT_PHRASES if phrase in sentence), "")
            if matched_lazy_judgment:
                signal_groups["lazy_judgment_phrase"].append(
                    _build_risk_signal(
                        signal_code="lazy_judgment_phrase",
                        message="这里直接下了作者判断，读者看到的是结论，不是过程。",
                        review_hint="先看这句能不能改成现场证据，让读者自己感觉到“强硬”“隐蔽”或“震惊”。",
                        chapter=chapter,
                        span_text=sentence,
                        evidence={"matched_text": matched_lazy_judgment},
                    )
                )

            for pattern in BALANCED_EXPLANATORY_PATTERNS:
                match = pattern.search(sentence)
                if match is None:
                    continue
                signal_groups["balanced_explanatory_sentence"].append(
                    _build_risk_signal(
                        signal_code="balanced_explanatory_sentence",
                        message="这里用了过于整齐的平衡解释句，容易显得像总结或作者收束。",
                        review_hint="先看这句是不是在替读者讲道理；如果是，考虑拆成两句，或让信息通过事件落地。",
                        chapter=chapter,
                        span_text=sentence,
                        evidence={"matched_text": match.group(0)},
                    )
                )
                break

            for pattern in ANIMAL_SIMILE_PATTERNS:
                match = pattern.search(sentence)
                if match is None:
                    continue
                signal_groups["animal_simile"].append(
                    _build_risk_signal(
                        signal_code="animal_simile",
                        message="这里用了“像一只……”的动物比喻，容易显得省力或落进常见套路。",
                        review_hint="先看这个比喻是不是贴人物视角和现场语境；如果只是为了制造形象感，优先删掉或换成动作。",
                        chapter=chapter,
                        span_text=sentence,
                        evidence={"matched_text": match.group(0)},
                    )
                )
                break

            for pattern in IMPACT_METAPHOR_PATTERNS:
                match = pattern.search(sentence)
                if match is None:
                    continue
                signal_groups["impact_metaphor_cliche"].append(
                    _build_risk_signal(
                        signal_code="impact_metaphor_cliche",
                        message="这里用了冲击型套路比喻，读感容易落回常见的“巨石/惊雷/涟漪”套句。",
                        review_hint="先看这句是不是在用比喻代替真正的事件冲击；如果是，优先改回动作、停顿或结果。",
                        chapter=chapter,
                        span_text=sentence,
                        evidence={"matched_text": match.group(0)},
                    )
                )
                break

    ordered_codes = (
        "eye_emotion_cue",
        "vague_attitude_phrase",
        "lazy_judgment_phrase",
        "balanced_explanatory_sentence",
        "animal_simile",
        "impact_metaphor_cliche",
    )
    risk_signals: list[StoryProseRiskSignal] = []
    metrics = {
        "risk_signal_count": 0,
        "risk_signal_total_hits": 0,
        "risk_signal_counts": [],
    }
    for signal_code in ordered_codes:
        items = signal_groups.get(signal_code, [])
        if not items:
            continue
        risk_signals.extend(items[:2])
        metrics["risk_signal_counts"].append(
            {
                "signal_code": signal_code,
                "count": len(items),
                "chapter_numbers": sorted({item.chapter_number for item in items if item.chapter_number is not None}),
            }
        )
    metrics["risk_signal_total_hits"] = sum(item["count"] for item in metrics["risk_signal_counts"])
    return risk_signals, metrics


def analyze_story_prose_markdown(markdown_text: str, *, style: str = "") -> StoryProseAnalysisReport:
    report = StoryProseAnalysisReport()
    report.title = _extract_title(markdown_text)
    report.style = style.strip()

    chapters = _extract_chapter_spans(markdown_text)
    if not chapters:
        report.issues.append(
            StoryProseIssue(
                issue_code="missing_chapters",
                severity="high",
                message="正文缺少可分析章节，无法继续做文本气味诊断。",
                rewrite_goal="先保证 Markdown 里存在可解析的 `## 正文` 和 `### 章节` 结构。",
            )
        )
        report.dimension_scores = build_dimension_scores(report.issues)
        report.overall_score = build_overall_score(report.dimension_scores)
        report.metrics = {"chapter_count": 0, "risk_signal_count": 0, "risk_signal_total_hits": 0, "risk_signal_counts": []}
        report.suggestions = build_suggestions(report.issues, style=report.style, risk_signals=report.risk_signals)
        return report

    analyzers = (
        analyze_repeated_phrases,
        analyze_repeated_paragraph_openers,
        analyze_ai_ism_hits,
        analyze_abstract_emotion,
        analyze_scene_density,
        analyze_template_chapters,
    )
    metrics: dict[str, Any] = {"chapter_count": len(chapters)}
    for analyzer in analyzers:
        issues, analyzer_metrics = analyzer(chapters)
        report.issues.extend(issues)
        metrics.update(analyzer_metrics)

    risk_signals, risk_signal_metrics = analyze_soft_risk_signals(chapters)
    report.risk_signals.extend(risk_signals)
    metrics.update(risk_signal_metrics)

    report.dimension_scores = build_dimension_scores(report.issues)
    report.overall_score = build_overall_score(report.dimension_scores)
    metrics["issue_count"] = report.issue_count
    metrics["risk_signal_count"] = report.risk_signal_count
    report.metrics = metrics
    report.suggestions = build_suggestions(report.issues, style=report.style, risk_signals=report.risk_signals)
    return report


def analyze_story_prose_file(file_path: str | Path, *, style: str = "") -> StoryProseAnalysisReport:
    markdown_text = Path(file_path).read_text(encoding="utf-8")
    return analyze_story_prose_markdown(markdown_text, style=style)
