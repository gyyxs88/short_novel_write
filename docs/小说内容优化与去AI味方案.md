# 小说内容优化与去 AI 味方案

## 当前进度

- 第一阶段“文本气味诊断层”已落地：`story_prose_analyzer.py`、`analyze_story_prose`、`story_draft_analyses`
- 第二阶段“风格画像层”已落地：`story_style_profile.py`、`build_style_profile`、`list_style_profiles`、`get_style_profile`、`story_style_profiles`
- 第三阶段“局部改写层”已落地：`story_span_rewriter.py`、`rewrite_story_spans`、`list_story_draft_revisions`、`story_draft_revisions`
- 第四阶段“修订编排层”已落地：`story_revision_runner.py`、`revise_story_draft`，并复用 `story_draft_analyses` / `story_draft_revisions` 串起多轮修订闭环
- 第五阶段“生成链自动修订后处理”已落地：`build_story_drafts` 新增 `auto_revise`、`revision_profile_name`、`revision_modes` 等参数，建稿后可自动跑修订并把结果回写到 `story_drafts`
- 第六阶段“回归样本与默认工作流接入自动修订”已落地：`story_regression_runner.py`、`story_regression_samples.py`、`SKILL.md`、`references/workflow.md` 已统一接入草稿后处理配置
- 第七阶段“批量任务接入自动修订后处理”已落地：`story_batch_runner.py` 的 jobs 现已支持 `draft_postprocess`，并默认按风格启用自动修订后处理
- 第八阶段“批量报告与归档修订指标增强”已落地：批量报告、单 job 回归报告和 `archive.sqlite3` 现已统一记录自动修订数量、修订轮次以及首稿/终稿差异指标
- 验收补强“异常改写保护”已升级：`abstract_emotion` 现已补上对白问句/不平衡引号过滤；高风险 regret / 对白片段不再被 deterministic 层硬跳过，而是先落 `risk_alerts` 提醒，再允许接入 `judge_llm_environment -> agent_review_required` 两层复核

## 1. 这阶段要解决什么

当前仓库已经把“创意 -> 方案 -> payload -> 正文 -> inspect -> save”主链路跑通了，但正文层的检查和修订仍然偏“结构合格”：

- `tools/story_quality_checker.py` 主要检查开头钩子、中段推进、结尾回收、标题贴题
- `tools/story_draft_llm_builder.py` 已经有按风格写作和失败修补能力
- `tools/story_draft_builder.py` 的 deterministic 基线能保流程稳定，但正文表达天然带模板味

下一阶段不该继续把重点放在“再写一版更大的 prompt”，而是要把“内容气味诊断 + 定向改写”独立成工具层能力。

这一阶段的目标不是“绝对像真人写”，而是先稳定解决下面几类高频问题：

- 句式和段落职责过于整齐，一眼像模板拼接
- 情绪和关系大量用抽象词直说，缺少动作、场景、感官支撑
- 对话人物同腔，像一个人换名字说话
- 重复短语、重复起手式、重复转折词过多
- 解释句、总结句、升华句偏多，现场感偏弱
- 豆瓣风容易空泛抒情，知乎风容易钩子强但表达同质化

## 2. 先定边界

这阶段先不做下面几件事：

- 不做平台适配
- 不做“模仿具体在世作者文风”
- 不做全自动审美判断
- 不默认整篇重写

默认原则是：

1. 先诊断，再修订。
2. 优先局部改写，不轻易推翻整篇。
3. 尽量不动剧情事实、章节顺序和关键转折。
4. 去 AI 味的本质是“增加具体选择”，不是“把句子写得更花”。

## 3. 当前仓库的主要缺口

### 3.1 质量检查维度不够

当前 `inspect` 适合拦结构硬伤，不适合抓文本气味问题。它现在基本抓不到：

- 高频重复短语
- 句首重复
- AI-ism 词表命中
- 段落功能高度同构
- 对话口吻趋同
- 场景密度不足
- 抽象情绪词密度过高

### 3.2 LLM 修补还偏“整块返工”

当前正文生成失败后，修补逻辑主要还是“整段重试”或“整章重试”。这对格式失败、字数失败很有效，但对“文本有味道问题”不够细。

### 3.3 deterministic 基线只能做流程基线

`tools/story_draft_builder.py` 当前是固定段落职责拼装。它适合：

- fresh SQLite 流程打通
- 端到端 smoke
- 结构基线

它不适合继续承担“内容表达基线”。

## 4. 总体方案

下一阶段建议拆成 4 层。

### 4.1 文本气味诊断层

新增一个专门的正文分析器，先不负责改写，只负责产出结构化报告。

建议文件：

- `tools/story_prose_analyzer.py`

建议输入：

- `content` 或 `file_path`
- 可选 `style`
- 可选 `draft_id`
- 可选 `profile_id`

建议输出：

- `overall_score`
- `dimension_scores`
- `issues`
- `suggestions`
- `spans`
- `metrics`

其中 `issues` 不只是字符串，要带可操作信息：

- `issue_code`
- `severity`
- `chapter_number`
- `span_text`
- `start_offset`
- `end_offset`
- `evidence`
- `rewrite_goal`

建议第一版先做下面 8 个维度：

1. 重复短语
2. 句首重复
3. AI-ism 词表命中
4. 抽象情绪直说
5. 场景稀薄
6. 对话同腔
7. 解释句过多
8. 章节模板相似度过高

### 4.2 风格画像层

新增一个轻量风格画像能力，把“希望更像什么文字”从一句 prompt 变成结构化输入。

建议文件：

- `tools/story_style_profile.py`

建议支持两种来源：

1. 内置风格画像
   - `zhihu_tight_hook`
   - `douban_subtle_scene`
2. 用户样本文本画像
   - 从用户提供的片段抽取句长、节奏、对话密度、常见动作、偏好意象、禁用表达

建议画像字段：

- `profile_name`
- `source_type`
- `style`
- `voice_summary`
- `preferred_traits`
- `avoid_phrases`
- `dialogue_rules`
- `narration_rules`
- `scene_rules`
- `sentence_rhythm_rules`

第一版不要追求复杂 embedding 或高级聚类，先把“可以被 prompt 明确消费”的画像结构做出来。

### 4.3 局部改写层

新增 span 级别修订器，不再默认整篇重写。

建议文件：

- `tools/story_span_rewriter.py`

建议模式：

- `remove_ai_phrases`
- `concretize_emotion`
- `strengthen_scene`
- `diversify_dialogue`
- `compress_exposition`
- `break_template_rhythm`

输入不是全文随便丢进去，而是：

- 原正文
- 分析器定位出的若干 `spans`
- 风格画像
- 硬约束

硬约束至少要有：

- 不改标题
- 不改章节编号
- 不改关键剧情事实
- 不新增设定
- 不改变 POV
- 单次只改命中 span 或所属小段

建议输出：

- `rewritten_spans`
- `change_notes`
- `applied_rules`
- `risk_flags`

### 4.4 修订编排层

把“先分析，再局部改，再复检”串起来。

建议文件：

- `tools/story_revision_runner.py`

默认流程建议：

1. 读取指定 draft
2. 跑 `story_prose_analyzer`
3. 选出最高优先级问题
4. 分批调用 `story_span_rewriter`
5. 合并回 Markdown
6. 再跑 `inspect`
7. 再跑 `story_prose_analyzer`
8. 输出修订前后对比和剩余问题

这里不要一轮把所有问题全修完，默认分两轮最稳：

- 第一轮：删模板味、删重复、压解释
- 第二轮：补场景、补动作、拉开人物口吻

## 5. CLI 建议

当前 `story_cli.py` 已经是统一入口，下一阶段继续沿用这个模式。

建议新增 action：

- `analyze_story_prose`
- `build_style_profile`
- `list_style_profiles`
- `get_style_profile`
- `rewrite_story_spans`
- `revise_story_draft`
- `list_story_draft_analyses`
- `list_story_draft_revisions`

### 5.1 `analyze_story_prose`

作用：

- 对正文做去 AI 味分析

建议 payload：

```json
{
  "action": "analyze_story_prose",
  "payload": {
    "draft_id": 12,
    "style": "douban",
    "profile_name": "douban_subtle_scene"
  }
}
```

建议返回：

- `overall_score`
- `dimension_scores`
- `issue_count`
- `top_issues`
- `analysis_id`

### 5.2 `build_style_profile`

作用：

- 从样本文本或内置模板构建风格画像

建议 payload：

```json
{
  "action": "build_style_profile",
  "payload": {
    "profile_name": "user_sample_soft_melancholy",
    "style": "douban",
    "sample_texts": ["文本1", "文本2"]
  }
}
```

### 5.3 `rewrite_story_spans`

作用：

- 按问题类型改指定片段

建议 payload：

```json
{
  "action": "rewrite_story_spans",
  "payload": {
    "draft_id": 12,
    "analysis_id": 5,
    "issue_codes": ["abstract_emotion", "repeated_openers"],
    "max_spans": 6,
    "profile_name": "douban_subtle_scene"
  }
}
```

### 5.4 `revise_story_draft`

作用：

- 一次执行“分析 -> 局部改写 -> 复检”

建议 payload：

```json
{
  "action": "revise_story_draft",
  "payload": {
    "draft_id": 12,
    "profile_name": "zhihu_tight_hook",
    "revision_modes": [
      "remove_ai_phrases",
      "compress_exposition",
      "strengthen_scene"
    ],
    "max_rounds": 2
  }
}
```

## 6. SQLite 设计建议

当前库已经有：

- `story_plans`
- `story_payloads`
- `story_drafts`

下一阶段建议新增 3 张表，够用且不臃肿。

### 6.1 `story_style_profiles`

存风格画像。

建议字段：

- `id`
- `profile_name`
- `source_type`
- `style`
- `profile_json`
- `created_at`
- `updated_at`

### 6.2 `story_draft_analyses`

存正文分析结果。

建议字段：

- `id`
- `draft_id`
- `analyzer_name`
- `style`
- `profile_name`
- `overall_score`
- `dimension_scores_json`
- `issue_count`
- `analysis_report_json`
- `created_at`

说明：

- 第一版不必把 issue 拆成单独表
- 直接先落完整 `analysis_report_json`
- 真到后面需要跨分析聚合，再拆 issue 明细表

### 6.3 `story_draft_revisions`

存局部修订结果。

建议字段：

- `id`
- `draft_id`
- `analysis_id`
- `revision_mode`
- `provider_name`
- `api_mode`
- `model_name`
- `model_config_key`
- `provider_response_id`
- `token_usage_json`
- `before_content_markdown`
- `after_content_markdown`
- `changed_spans_json`
- `revision_summary`
- `created_at`

说明：

- 保留修订前后快照，方便回退和对比
- 不直接覆盖原 `story_drafts`
- 选定后再决定是否回写或另存最终版

## 7. 诊断规则建议

第一版建议先做“简单但真有用”的规则，不要一上来搞复杂模型评分。

### 7.1 重复短语

抓下面几类：

- 高频 2-4 字短语
- 相邻段落重复短语
- 章节内重复转折词

优先提示：

- 哪个词反复出现
- 出现在哪几章
- 是否达到阈值

### 7.2 句首重复

重点抓：

- “她…”
- “可是…”
- “然而…”
- “直到这时…”
- “那一刻…”

不是一刀切禁用，而是看局部密度。

### 7.3 AI-ism 词表

建议先内置可配置词表，不要写死在 prompt 里。

例如：

- “不由得”
- “仿佛”
- “似乎”
- “某种”
- “那一刻”
- “原来”
- “其实”
- “终于明白”

注意：

- 词表只是风险信号，不是命中就判死刑
- 必须结合上下文和密度

### 7.4 抽象情绪直说

重点抓这种写法：

- 直接说“她很痛苦”“她很难过”“关系开始松动”
- 但前后没有动作、对话、物件、环境变化支撑

输出建议不能只说“改具体一点”，而要明确成：

- 补动作
- 补物件互动
- 补对话停顿
- 补身体反应

### 7.5 场景稀薄

可以粗看：

- 动作动词密度
- 感官词密度
- 具象名词密度
- 对话占比

如果连续多段都只有总结和解释，应该打标。

### 7.6 对话同腔

重点检查：

- 多个角色句长和句式过于一致
- 都爱讲完整逻辑句
- 缺少人物特有的回避、停顿、打断、口头习惯

### 7.7 章节模板相似度

当前仓库特别要防这一条。

因为 deterministic 基线和一些 LLM 长文默认修补，都容易出现：

- 第一段起势
- 第二段关系
- 第三段冲突
- 第四段推进
- 第五段转折
- 第六段感悟
- 第七段章尾钩子

如果连续几章段落职责高度同构，就算单章能看，也会整体显 AI 味。

## 8. 改写策略建议

### 8.1 改写默认只做小步

优先级建议：

1. 先删重复和套话
2. 再压解释句
3. 再补具体动作和场景
4. 最后拉开人物对话差异

### 8.2 不做整篇自由重写

原因很直接：

- 容易把原本还成立的剧情写歪
- 容易把章节结构打散
- 成本高
- 难定位是哪一步把内容改坏了

### 8.3 明确每种改写模式的边界

例如：

- `remove_ai_phrases` 只改措辞，不加新剧情
- `compress_exposition` 只压缩解释，不删关键信息
- `strengthen_scene` 允许补动作、空间、感官，但不改事件结果
- `diversify_dialogue` 只调整说话方式，不改话语立场

## 9. 验收方式

下一阶段不要只看 `inspect` 是否通过，要增加“内容优化验收”。

建议新增 4 类验收：

### 9.1 规则级测试

针对分析器写纯 deterministic 测试：

- 重复短语能不能抓到
- 句首重复会不会误报
- AI-ism 词表命中是否正确
- 章节模板相似度能不能识别

### 9.2 改写器单测

给定固定问题片段和 mock LLM 响应，验证：

- 输出结构正确
- span 替换范围正确
- 不会把章节编号改坏

### 9.3 回归样本扩充

建议在 `tools/story_regression_samples.py` 之外，再补一组“去 AI 味专项样本”：

- 不是只测链路通过
- 而是测正文气味问题是否被修掉

### 9.4 前后对比指标

修订前后建议至少比：

- 重复短语命中数
- AI-ism 命中数
- 抽象情绪段落数
- 对话占比
- `inspect` 结果是否退化

原则是：

- 去 AI 味不能以破坏结构为代价

## 10. 开发顺序建议

按收益和风险，建议这样排。

### 第一阶段

- 新增 `story_prose_analyzer.py`
- 新增 `analyze_story_prose`
- 先做 deterministic 诊断，不做自动改写

交付标准：

- 能稳定抓到重复、套话、抽象表达、模板化章节
- 结果可落库、可查询

### 第二阶段

- 新增 `story_style_profile.py`
- 新增 `build_style_profile`
- 先支持内置画像，再支持样本文本画像

交付标准：

- 能把“知乎更利落”“豆瓣更具体”从口头要求变成结构化约束

### 第三阶段

- 新增 `story_span_rewriter.py`
- 新增 `rewrite_story_spans`
- 只做 span 级改写

交付标准：

- 不改剧情前提下，能消一批最明显的 AI 味

### 第四阶段

- 新增 `story_revision_runner.py`
- 新增 `revise_story_draft`
- 串起分析、改写、复检

交付标准：

- 形成可重复执行的内容修订闭环

### 第五阶段

- 在 `build_story_drafts` 接入可选自动修订后处理
- 默认关闭，不改变现有建稿行为
- 开启后自动落分析/修订轨迹，并把修订后正文回写到 `story_drafts`

交付标准：

- `build_story_drafts -> inspect -> save` 可直接消费修订后版本

### 第六阶段

- 给回归样本增加结构化草稿后处理配置
- 让 `story_regression_runner.py` 在跑 `build_story_drafts` 时透传 `auto_revise`
- 更新 `SKILL.md` 和 `references/workflow.md`，让默认正文链和回归链对齐

交付标准：

- 真实样本回归和默认正文工作流都能统一走“建稿后自动修订，再 inspect”的链路

### 第七阶段

- 给 `story_batch_runner.py` 的 jobs 增加结构化 `draft_postprocess`
- 批量 job 默认按风格启用自动修订后处理
- 允许单个 job 显式关闭自动修订，保留原始首稿

交付标准：

- 批量任务、回归样本和默认正文工作流三条链都能统一走同一套草稿后处理策略

### 第八阶段

- 给 `build_story_drafts` 增加首稿/终稿差异指标，至少包括是否真的改动、修订前后正文长度和字数净变化
- 让 `story_regression_runner.py` 和 `story_batch_runner.py` 在 JSON/Markdown 报告里统一汇总自动修订 job 数、修订总轮次、终稿字数净变化
- 让 `story_archive_manager.py` 把选中草稿的自动修订状态、修订轮次和首终稿差异指标沉到 `archive_jobs`

交付标准：

- 跑完批量任务后，可以直接从 `batch_report.json`、`batch_report.md` 和 `archive.sqlite3` 看出哪些 job 真正改过、改了多少、修了几轮

## 11. 这一阶段不建议做的坑

### 11.1 不要一开始就搞“总分模型裁判”

先把规则和问题分型做好，比追求一个“大而全评分”更有用。

### 11.2 不要把词表当成唯一标准

“仿佛”“原来”不是原罪，连续滥用才是问题。

### 11.3 不要用一次性 prompt 试图解决所有问题

“请帮我去 AI 味”这种 prompt 很容易：

- 改得虚
- 改得过度
- 改得失真

### 11.4 不要默认覆盖原稿

必须保留修订前版本，方便回看和回退。

## 12. 推荐的第一批落地项

如果只做一轮开发，建议优先落下面 4 项：

1. `story_prose_analyzer.py`
2. `story_draft_analyses` 表
3. `analyze_story_prose` action
4. `tests/tools/test_story_prose_analyzer.py`

原因：

- 投入最小
- 最容易对现有仓库无侵入接入
- 能最快把“去 AI 味”从口头感受变成结构化问题
- 后面局部改写、风格画像、回归报告都能直接复用这层输出

一句话总结：

**下一阶段的重点不是“再写得更多”，而是把正文变成“可诊断、可局部修、可回归比较”的对象。**
