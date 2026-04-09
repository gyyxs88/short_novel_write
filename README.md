# short_novel_write

这是一个给 `Agent / Skill` 使用的中文短篇小说写作项目。

它的目标不是“写一个一次性 prompt”，也不是“先做一堆平台自动化”，而是先把**短篇小说写作能力本身**做稳，再把稳定动作逐步沉淀成可复用工具。

当前仓库已经形成了比较清晰的分层：

- `SKILL.md` 负责写作流程、默认策略、交互规则
- `tools/` 负责确定性动作，例如创意生成、保存、结构检查、质量检查、统一 CLI
- `references/` 负责工作流和人工自检规则

## 当前状态

目前已经落地的能力有：

1. 成稿保存
   通过 `tools/story_output_writer.py` 把 Markdown 成稿按 UTF-8 写入本地。
2. 结构检查
   通过 `tools/story_structure_checker.py` 检查标题、简介、正文、章节编号和字数区间。
3. 质量检查
   通过 `tools/story_quality_checker.py` 做启发式检查，覆盖开头钩子、中段推进、结尾回收、标题贴题度。
4. 创意种子生成
   通过 `tools/story_idea_seed_generator.py` 从 `类型.txt` 和 `标签.txt` 里稳定生成默认 `3` 组、每组 `2 个类型 + 3 个主标签` 的创意种子。
5. 创意卡组持久化与筛选状态
   通过 `tools/story_idea_repository.py` 用 SQLite 持久化原始卡组、创意包和当前筛选状态，并做全局硬去重。
6. 一句话创意反向挑卡
   通过 `tools/story_idea_prompt_matcher.py` 把一句话创意 deterministic 地映射成候选卡组。
7. 创意包 deterministic 模板整理
   通过 `tools/story_idea_pack_builder.py` 输出 `zhihu / douban` 两档创意包，用于流程、数据库和测试打通。
8. 创意包 LLM 生成通道
   通过 `tools/story_idea_pack_llm_builder.py` 调用兼容 `chat/completions` 或 `responses` 的上游模型接口生成首版 LLM 创意包，并与 deterministic 基线并存。
9. 创意包评测与筛选基线
   通过 `tools/story_idea_pack_evaluator.py` 对创意包做 deterministic 评分、推荐和持久化，支撑筛选闭环。
10. LLM 配置与环境链路
   通过 `tools/story_llm_config.py` 在同一个 `story_ideas.sqlite3` 里管理供应商、模型配置和调用环境，支持同一环境挂多模型候选链路，前一个失败自动切下一个。
11. 故事方案生成与写作简报落库
   通过 `tools/story_plan_builder.py` 和 `tools/story_plan_llm_builder.py` 生成 `3-4` 组完整故事方案，覆盖标题、题材氛围、卖点、主角目标、关键转折、结尾方向、章节节奏和可直接下传正文阶段的 `writing_brief`。
12. 正文 payload 与正文草稿生成
   通过 `tools/story_payload_builder.py`、`tools/story_draft_builder.py` 和 `tools/story_draft_llm_builder.py` 把 `writing_brief` 收口成稳定 `story_payload`，并生成可直接接 `inspect/save` 的完整 Markdown 草稿。
13. 任务运行库归档
   通过 `tools/story_archive_manager.py` 把单次任务目录里的 `story_ideas.sqlite3` 与 `report.json` 归档进统一 `archive.sqlite3`，保留选题链路、成品正文、阶段耗时与 token 统计，并支持归档校验通过后删除源业务库。
14. 批量任务并发调度
   通过 `tools/story_batch_runner.py` 从 jobs JSON 批量创建独立运行库，并发跑单 job 写作链，再用单线程归档 worker 串行写入 `archive.sqlite3`，适合多小说同时生成。
15. 统一 CLI
   通过 `tools/story_cli.py` 统一对外暴露 `generate_ideas`、`match_idea_cards`、`store_idea_cards`、`build_idea_packs`、`evaluate_idea_packs`、`build_story_plans`、`build_story_payloads`、`build_story_drafts`、`analyze_story_prose`、`build_style_profile`、`rewrite_story_spans`、`revise_story_draft`、`get_llm_config`、`export_llm_config`、`apply_llm_config`、`list_llm_providers`、`list_llm_models`、`list_llm_environments`、`get_llm_provider`、`get_llm_model`、`get_llm_environment`、`upsert_llm_provider`、`upsert_llm_model`、`upsert_llm_environment`、`delete_llm_provider`、`delete_llm_model`、`delete_llm_environment`、`list_idea_cards`、`list_idea_packs`、`list_idea_pack_evaluations`、`list_story_plans`、`list_story_payloads`、`list_story_drafts`、`list_story_draft_analyses`、`list_style_profiles`、`get_style_profile`、`list_story_draft_revisions`、`update_idea_pack_status`、`update_story_plan_status`、`update_story_draft_status`、`archive_run`、`save`、`check_structure`、`check_quality`、`inspect` 四十五个动作。
16. Skill 调用约定
   `SKILL.md`、`references/workflow.md`、`references/quality-checklist.md` 已经接入 CLI 的收尾调用链。
17. 真实样本回归与报告
   通过 `tools/story_regression_runner.py` 和 `tools/story_regression_samples.py` 批量跑真实样本链路，输出 JSON/Markdown 回归报告，统计阶段失败点、失败类型以及各阶段 token 消耗。
18. 正文气味分析与结果落库
   通过 `tools/story_prose_analyzer.py` 对正文做 deterministic 文本气味诊断，当前覆盖重复短语、段落起手重复、AI-ism、抽象情绪、场景稀薄和章节模板感，并可把分析结果落库到 `story_draft_analyses`。
19. 风格画像构建与管理
   通过 `tools/story_style_profile.py` 提供内置画像和样本文本画像两种入口，并支持把画像落库到 `story_style_profiles`，供后续正文分析和局部改写复用。
20. 局部改写与修订记录落库
   通过 `tools/story_span_rewriter.py` 基于分析结果和风格画像做 span 级 deterministic 改写，当前覆盖去 AI 腔、压解释、情绪具象化、补场景和打散模板节奏，并把修订结果落库到 `story_draft_revisions`。
21. 修订编排闭环
   通过 `tools/story_revision_runner.py` 串起“分析 -> 局部改写 -> 复检”流程，当前支持 deterministic 多轮修订，并复用 `story_draft_analyses` 和 `story_draft_revisions` 保留每轮轨迹；高风险 span 现已降级为 `risk_alerts` 提醒，可继续接入 `judge_llm_environment` 做 LLM 判定，并把待复核片段记成 `agent_review_required`。
22. 生成链自动修订后处理
   `build_story_drafts` 现已支持显式开启 `auto_revise`，在建稿后自动执行 `revise_story_draft` 同款修订流程，并把修订后的正文安全回写到 `story_drafts` 主记录，方便后续 `inspect / save` 直接消费。
23. 回归样本与默认工作流接入自动修订
   `story_regression_runner.py`、`story_regression_samples.py`、`SKILL.md` 和 `references/workflow.md` 现已接入草稿自动修订配置，真实样本回归和默认正文工作流都能统一走 `build_story_drafts(auto_revise) -> inspect` 这条链。
24. 批量任务接入自动修订后处理
   `story_batch_runner.py` 现已支持给 jobs 透传 `draft_postprocess`，并默认按风格启用自动修订后处理；批量 job 在未显式关闭时，也会统一走 `build_story_drafts(auto_revise) -> inspect -> archive`。
25. 批量报告与归档修订指标增强
   批量报告、单 job 回归报告和 `archive.sqlite3` 现已统一记录自动修订数量、修订轮次以及首稿/终稿的字数差异，方便批量比较“去 AI 味”后处理是否真的发生了变化。
26. Windows CLI 编码兼容与 deterministic 自动修订稳定性补强
   `tools/story_cli.py` 现在统一输出 ASCII-safe JSON，减少 Windows 默认编码对子进程解析的影响；同时 `story_prose_analyzer.py` 和 `story_span_rewriter.py` 已补齐长 span 定位与重叠 span 过滤，fresh SQLite 下可稳定跑通 `build_story_drafts(auto_revise) -> inspect`。

重要说明：

- 当前 `build_idea_packs` 已支持两种生成模式：
  - `generation_mode="deterministic"`：流程/测试基线
  - `generation_mode="llm"`：首版兼容式 LLM 通道
- `generation_mode="llm"` 下默认优先走兼容 `chat/completions` 的接口，更适合第三方中转和兼容供应商
- 当前 LLM 层已支持“环境 -> 候选模型链路”的配置方式
- 同一 `llm_environment` 可以挂多个候选模型，前一个失败会自动试下一个
- 写作任务在使用 `llm_environment` 时，可以临时传 `llm_model_keys_override` 重排本次调用的模型优先级，不会改动 SQLite 里的默认顺序
- 同一条写作链的不同阶段可以使用不同 `llm_environment`
- 当前默认字数档位已按风格拆开：
  - `zhihu` 默认 `10000-30000` 字
  - `douban` 默认 `10000-20000` 字
- 对长输出链路，尤其是豆瓣风格，建议把 `build_story_plans` 和 `build_story_drafts` 拆到不同环境，不要默认共用同一套 timeout
- `build_story_plans` 和 `build_story_drafts` 在 `chat/completions` 长输出阶段默认启用 `stream=true`
- LLM 生成链路现在会尽量提取并落库标准化 token 统计：`prompt_tokens`、`completion_tokens`、`total_tokens`
- `build_idea_packs`、`build_story_plans`、`build_story_drafts` 的 CLI 返回值里会带本次动作的 `token_usage`
- `list_idea_packs`、`list_story_plans`、`list_story_drafts` 现在会返回对应记录保存下来的 `token_usage`
- 这两个长输出阶段的 `timeout_seconds` 按“连续多久没收到新的流式数据块”计算，不按整包返回时长计算
- 当目标字数进入长稿档位时，`build_story_drafts` 会默认切到“先生成 summary，再逐章生成正文，最后拼稿”的分段模式，不再尝试单次整篇输出
- 分段正文的单章预算现在按风格保留弹性浮动，不再按平均字数做过硬上限；只要简介合格且整稿达到目标下限，正文和单章即使超长也默认放行，不再因超过目标上限而失败
- 当前推荐的数据分层是：`template.sqlite3` 只放稳定配置，单次任务使用独立运行库，任务结束后再把业务数据写入统一 `archive.sqlite3`
- `archive_run` 归档时会把选题链路、最终成品、阶段耗时和 token 统计一起落库；只有归档校验通过后才建议删除任务运行库
- `story_batch_runner.py` 当前就是这套分层的批量执行入口：每个 job 独立运行库，并发生成，归档串行收口
- `story_batch_runner.py` 现已默认复用风格化草稿后处理；如果某个批量 job 需要保留原始首稿，可在 jobs JSON 里显式传 `draft_postprocess.auto_revise=false`
- `story_batch_runner.py` 和 `story_archive_manager.py` 现已把自动修订 job 数、修订轮次、终稿字数净变化等指标收进批量报告和统一归档，便于后续横向比较不同风格和不同后处理策略
- 如果整个候选链路都失败，CLI 会返回 `AGENT_FALLBACK_REQUIRED`，交给 agent 做最后兜底
- 当前已新增 deterministic 创意包评测层，可对已有创意包做打分、推荐和排序
- 当前已新增完整方案层，可基于创意包生成 deterministic / llm 两种故事方案，并把写作简报一并落到 SQLite
- 当前已新增正文 payload 层和正文草稿层，可基于已选方案生成稳定 payload，并产出 deterministic / llm 两种 Markdown 成稿草稿
- `build_story_drafts` 现已支持可选自动修订后处理：默认关闭；开启 `auto_revise=true` 后，会在建稿完成后自动落分析/修订轨迹，并把修订后的正文回写到当前 draft
- 当前 deterministic 自动修订链已补齐 span 定位与重叠过滤，fresh SQLite 下可稳定跑通 `build_story_drafts(auto_revise=true) -> inspect`
- 当前 deterministic 正文基线已经补到可在 fresh SQLite 链路下通过 `build_story_drafts -> inspect -> save` 端到端 smoke，适合作为流程和测试基线
- deterministic 版仍然只负责流程稳定、数据库和测试基线，不代表生产可用质量
- LLM 版已经接入，但仍需要持续做真实卡组评估、提示词调优和线上验收
- 创意包、故事方案和正文草稿的 deterministic / llm 版本都会并存保存，方便直接对比，不会互相覆盖

当前还**没有**落地的能力：

- 平台发布、浏览器自动化投稿、外部系统上传

所以你可以把现在的仓库理解成：

**一个已经具备“保存 + 检查 + 统一调用协议”的短篇写作工具底座，正在往完整写作 skill 演进。**

## 这个仓库适合谁

这个 README 主要写给两类人：

- 后续继续维护这个仓库的开发者
- 需要把这个仓库接进别的 `agent / skill` 工作流的人

如果你期待的是“直接运行一个命令自动写完整短篇”，那现在还没到这一步。  
当前更像是：写作流程已经成型，底层收尾工具已经成型，正文生成能力还在继续补。

## 仓库结构

当前实际结构里最重要的部分是：

```text
short_novel_write/
├─ README.md
├─ SKILL.md
├─ pytest.ini
├─ references/
│  ├─ workflow.md
│  └─ quality-checklist.md
├─ tools/
│  ├─ __init__.py
│  ├─ story_cli.py
│  ├─ story_idea_pack_builder.py
│  ├─ story_idea_pack_evaluator.py
│  ├─ story_idea_pack_llm_builder.py
│  ├─ story_idea_prompt_matcher.py
│  ├─ story_idea_repository.py
│  ├─ story_idea_seed_generator.py
│  ├─ story_archive_manager.py
│  ├─ story_batch_runner.py
│  ├─ story_llm_config.py
│  ├─ story_output_writer.py
│  ├─ story_payload_builder.py
│  ├─ story_draft_builder.py
│  ├─ story_draft_llm_builder.py
│  ├─ story_prose_analyzer.py
│  ├─ story_revision_runner.py
│  ├─ story_style_profile.py
│  ├─ story_span_judge.py
│  ├─ story_span_rewriter.py
│  ├─ story_plan_builder.py
│  ├─ story_plan_llm_builder.py
│  ├─ story_regression_runner.py
│  ├─ story_regression_samples.py
│  ├─ story_quality_checker.py
│  └─ story_structure_checker.py
├─ tests/
│  └─ tools/
│     ├─ test_story_cli.py
│     ├─ test_story_cli_archive.py
│     ├─ test_story_cli_idea_pipeline.py
│     ├─ test_story_archive_manager.py
│     ├─ test_story_batch_runner.py
│     ├─ test_story_idea_pack_builder.py
│     ├─ test_story_idea_pack_llm_builder.py
│     ├─ test_story_idea_prompt_matcher.py
│     ├─ test_story_idea_repository.py
│     ├─ test_story_idea_seed_generator.py
│     ├─ test_story_output_writer.py
│     ├─ test_story_payload_builder.py
│     ├─ test_story_draft_builder.py
│     ├─ test_story_draft_llm_builder.py
│     ├─ test_story_prose_analyzer.py
│     ├─ test_story_revision_runner.py
│     ├─ test_story_style_profile.py
│     ├─ test_story_span_rewriter.py
│     ├─ test_story_plan_builder.py
│     ├─ test_story_plan_llm_builder.py
│     ├─ test_story_regression_runner.py
│     ├─ test_story_quality_checker.py
│     └─ test_story_structure_checker.py
└─ docs/
```

补充说明：

- 开发目录里可以保留实现过程文档、参考项目或其他内部资料
- 发布目录默认只同步可公开的主工具链内容，不会把所有开发辅助材料一并带出去
- 当前推荐工作流是：开发目录只做本地 `git commit`，发布目录负责对外 `git push`
- 临时开发分支只允许留在本地；要对外发布时，必须先把有效改动合并或摘回开发目录 `main`，再从发布目录 `main` 推送

## 核心设计

### 1. Skill 层

`SKILL.md` 负责：

- 判断用户属于“从零开始、补创意、补方案、继续写、修订稿子”中的哪类场景
- 组织创意、方案、正文、自检、保存这条主流程
- 决定默认字数档位和自动继续策略
- 在收尾阶段调用 CLI 做自动自检和保存

Skill 负责“怎么推进写作”，不负责把所有确定性规则硬编码进 prompt。

### 2. Tool 层

`tools/` 负责：

- 创意种子随机生成
- 一句话创意反向挑卡
- SQLite 持久化与硬去重
- `zhihu / douban` 两档 deterministic 创意包整理
- 创意包 deterministic 评测与推荐
- 基于兼容 `chat/completions` / `responses` 的 LLM 创意包生成
- 基于创意包的 deterministic / LLM 故事方案生成
- 写作简报落库与方案状态流转
- `writing_brief -> story_payload` 的稳定输入组装
- 基于 payload 的 deterministic / LLM 正文草稿生成
- 真实样本批量回归、失败分类和 JSON/Markdown 报告输出
- LLM 供应商 / 模型 / 环境配置与候选链路重试
- 标题清洗
- UTF-8 落盘
- Markdown 结构检查
- 启发式质量检查
- 统一 JSON CLI 协议

Tool 层负责“怎么稳定执行”。

### 3. CLI 层

`tools/story_cli.py` 是当前最重要的机器接口。

它不是“写小说 CLI”，而是“工具调度 CLI”。

也就是说：

- 它不会直接帮你生成一篇小说
- 它会帮 skill/agent 统一调用已有工具
- 它的重点是：**输入输出稳定、后台好接、结果可解析**

### 4. 创意标签池分层约定

创意生成阶段默认读取 `类型.txt` 和 `标签.txt`。

- `标签.txt`：主随机池
- `标签_补充池.txt`：第二层补充标签
- `标签_移出主流程.txt`：保存已降级但暂不彻底删除的标签

## CLI 协议

### 调用方式

当前 CLI 面向 `skill / agent` 后台调用，统一采用：

- 输入：`stdin JSON`
- 输出：`stdout JSON`
- 为兼容 Windows 默认控制台编码，CLI 现在统一输出 ASCII-safe JSON；中文字段会保留在 JSON 结构里，但内容按 `\uXXXX` 形式转义，便于父进程稳定解析
- 成功退出码：`0`
- 失败退出码：`1`

PowerShell 传中文 JSON 前，先切 UTF-8：

```powershell
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
chcp 65001 > $null
```

### 支持的 action

- `generate_ideas`
- `match_idea_cards`
- `store_idea_cards`
- `build_idea_packs`
- `evaluate_idea_packs`
- `build_story_plans`
- `build_story_payloads`
- `build_story_drafts`
- `analyze_story_prose`
- `build_style_profile`
- `rewrite_story_spans`
- `revise_story_draft`
- `get_llm_config`
- `export_llm_config`
- `apply_llm_config`
- `list_llm_providers`
- `list_llm_models`
- `list_llm_environments`
- `get_llm_provider`
- `get_llm_model`
- `get_llm_environment`
- `upsert_llm_provider`
- `upsert_llm_model`
- `upsert_llm_environment`
- `delete_llm_provider`
- `delete_llm_model`
- `delete_llm_environment`
- `list_idea_cards`
- `list_idea_packs`
- `list_idea_pack_evaluations`
- `list_story_plans`
- `list_story_payloads`
- `list_story_drafts`
- `list_story_draft_analyses`
- `list_style_profiles`
- `get_style_profile`
- `list_story_draft_revisions`
- `update_idea_pack_status`
- `update_story_plan_status`
- `update_story_draft_status`
- `archive_run`
- `save`
- `check_structure`
- `check_quality`
- `inspect`

默认 SQLite 路径：

- `outputs/idea_pipeline/story_ideas.sqlite3`

默认评测数据也保存在同一个 SQLite 里：

- `idea_pack_evaluations`

默认方案数据也保存在同一个 SQLite 里：

- `story_plans`

默认正文 payload 和正文草稿也保存在同一个 SQLite 里：

- `story_payloads`
- `story_drafts`

默认正文分析结果也保存在同一个 SQLite 里：

- `story_draft_analyses`

默认风格画像也保存在同一个 SQLite 里：

- `story_style_profiles`

默认正文修订记录也保存在同一个 SQLite 里：

- `story_draft_revisions`

默认 LLM 配置也存放在同一个 SQLite 里：

- `outputs/idea_pipeline/story_ideas.sqlite3`

### 标准请求格式

```json
{
  "action": "inspect",
  "payload": {}
}
```

### `inspect` 示例

```powershell
@'
{"action":"inspect","payload":{"content":"# 标题\n\n## 简介\n...","target_char_range":[5000,8000],"summary_char_range":[50,120]}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

### `save` 示例

```powershell
@'
{"action":"save","payload":{"title":"雨夜来信","content":"# 雨夜来信\n\n## 简介\n...","output_dir":"outputs/novels","suffix":".md"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

### `generate_ideas` 示例

```powershell
@'
{"action":"generate_ideas","payload":{"count":3,"seed":"demo-seed"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

返回结果会包含：

- `data.seed`
- `data.count`
- `data.items[].id`
- `data.items[].types`
- `data.items[].main_tags`

### `match_idea_cards` 示例

```powershell
@'
{"action":"match_idea_cards","payload":{"prompt":"我想写校园初恋和失踪旧案","count":2}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

### `store_idea_cards` 示例

```powershell
@'
{"action":"store_idea_cards","payload":{"source_mode":"seed_generate","seed":"demo-seed","items":[{"types":["Mystery - 悬疑 / 推理","Modern - 现代"],"main_tags":["Missing Person - 失踪","First Love - 初恋","Secret Past - 隐秘过去"]}]}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

### `build_idea_packs` 示例

```powershell
@'
{"action":"build_idea_packs","payload":{"batch_id":1,"style":"zhihu"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

### `build_idea_packs` 的 LLM 模式示例

先准备环境变量：

```powershell
$env:OPENROUTER_API_KEY = "你的 OpenRouter Key"
```

然后调用：

```powershell
@'
{"action":"build_idea_packs","payload":{"batch_id":1,"style":"zhihu","generation_mode":"llm","provider":"openrouter","api_mode":"chat_completions","model":"qwen/qwen3.6-plus:free"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

补充说明：

- `generation_mode` 默认为 `deterministic`
- 传 `generation_mode="llm"` 时，默认优先走兼容 `chat/completions`
- `provider` 当前支持 `openai`、`openrouter` 和 `deepseek`
- `api_mode` 当前支持 `chat_completions` 和 `responses`
- `model` 可选，默认是 `gpt-5-mini`
- 如果你只是临时直连一个上游，仍然可以继续直接传 `provider / api_mode / model`
- 常用环境变量：
  - `LLM_API_KEY`
  - `OPENAI_API_KEY`
  - `OPENAI_CHAT_COMPLETIONS_URL`
  - `OPENROUTER_API_KEY`
  - `LLM_CHAT_COMPLETIONS_URL`
  - `OPENAI_RESPONSES_URL`
  - `OPENROUTER_CHAT_COMPLETIONS_URL`
  - `DEEPSEEK_API_KEY`
  - `DEEPSEEK_CHAT_COMPLETIONS_URL`

### LLM 配置 action 示例

先配置供应商：

```powershell
@'
{"action":"upsert_llm_provider","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3","provider_name":"openrouter","api_key_env":"OPENROUTER_API_KEY","chat_completions_url":"https://openrouter.ai/api/v1/chat/completions","extra_headers":{"HTTP-Referer":"OPENROUTER_HTTP_REFERER","X-Title":"OPENROUTER_X_TITLE"}}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

再配置模型：

```powershell
@'
{"action":"upsert_llm_model","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3","model_key":"openrouter_qwen_free","provider_name":"openrouter","model_name":"qwen/qwen3.6-plus:free","api_mode":"chat_completions","timeout_seconds":60}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

然后配置调用环境：

```powershell
@'
{"action":"upsert_llm_environment","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3","environment_name":"idea_pack_default","model_keys":["openrouter_qwen_free"],"agent_fallback":true,"description":"创意包默认环境"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

查看当前配置：

```powershell
@'
{"action":"get_llm_config","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

导出完整快照：

```powershell
@'
{"action":"export_llm_config","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

把导出的快照整体应用到另一个 SQLite：

```powershell
@'
{"action":"apply_llm_config","payload":{"db_path":"outputs/idea_pipeline/another_story_ideas.sqlite3","snapshot":{"format_version":1,"config":{"providers":{},"models":{},"environments":{}}}}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

只看供应商列表：

```powershell
@'
{"action":"list_llm_providers","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

只看模型列表：

```powershell
@'
{"action":"list_llm_models","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

只看环境列表：

```powershell
@'
{"action":"list_llm_environments","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

查看单个环境：

```powershell
@'
{"action":"get_llm_environment","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3","environment_name":"idea_pack_default"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

删除环境：

```powershell
@'
{"action":"delete_llm_environment","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3","environment_name":"idea_pack_default"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

删除模型：

```powershell
@'
{"action":"delete_llm_model","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3","model_key":"openrouter_qwen_free"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

删除供应商：

```powershell
@'
{"action":"delete_llm_provider","payload":{"db_path":"outputs/idea_pipeline/story_ideas.sqlite3","provider_name":"openrouter"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

### `build_idea_packs` 的环境链路示例

```powershell
@'
{"action":"build_idea_packs","payload":{"batch_id":1,"style":"zhihu","generation_mode":"llm","llm_environment":"idea_pack_default"}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

如果你想只在这一次调用里临时改模型优先级，不改 SQLite 默认环境，可以这样传：

```powershell
@'
{"action":"build_idea_packs","payload":{"batch_id":1,"style":"zhihu","generation_mode":"llm","llm_environment":"idea_pack_default","llm_model_keys_override":["openrouter_qwen_free_backup","openrouter_qwen_free"]}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

补充说明：

- `llm_environment` 用来选调用环境
- LLM 配置和创意/方案/正文产物现在统一落在同一个 `db_path` 对应的 SQLite 里，不再单独使用 `llm_config.json`
- `export_llm_config` 适合 agent 先导出快照、修改 JSON、再用 `apply_llm_config` 整体回写
- `apply_llm_config` 会按快照整体替换当前库里的 LLM 配置，不是局部 merge
- `llm_model_keys_override` 只影响当前这次 `build_idea_packs / build_story_plans / build_story_drafts` 调用，不会改写环境默认顺序
- `llm_model_keys_override` 只能填写当前环境已经绑定过的 `model_key`
- 删除时有依赖约束：
  - 先删环境，再删模型，最后删供应商
- 每个环境可以配置多个 `model_keys`，会按顺序尝试
- 前一个模型失败会自动切到下一个
- `build_story_plans` 和 `build_story_drafts` 不必共用同一个 `llm_environment`
- 如果某一风格在长输出阶段容易超时，优先把“方案环境”和“正文环境”拆开治理
- 如果整条链路都失败，并且环境里 `agent_fallback=true`，CLI 会返回 `AGENT_FALLBACK_REQUIRED`
- 这时表示工具层已经尽力，应该交回 agent 做最终兜底

### `evaluate_idea_packs` 示例

```powershell
@'
{"action":"evaluate_idea_packs","payload":{"batch_id":1}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

返回结果会包含：

- `data.created_count`
- `data.updated_count`
- `data.recommendation_counts`
- `data.items[].pack_id`
- `data.items[].total_score`
- `data.items[].recommendation`

### `list_idea_pack_evaluations` 示例

```powershell
@'
{"action":"list_idea_pack_evaluations","payload":{"batch_id":1}}
'@ | .\.venv\Scripts\python.exe tools\story_cli.py
```

### 创意包流程边界

当前创意包流程已经可以打通：

1. `generate_ideas` 纯抽卡
2. `store_idea_cards` 入库、防重、建批次
3. `build_idea_packs` 生成 deterministic 或 llm 创意包
   其中 llm 模式既支持直接传 `provider/model`，也支持通过 `llm_environment` 走配置化候选链路
4. `evaluate_idea_packs` 对创意包做 deterministic 评测和推荐
5. `list_idea_cards` / `list_idea_packs` / `list_idea_pack_evaluations` 查询筛选
6. `update_idea_pack_status` 更新筛选状态

但要特别注意：

- deterministic 版仍然只是工程半成品
- 它保证的是流程稳定、结果可测、状态可追踪
- deterministic 评测层同样是工程基线，解决的是“可比较、可排序、可筛选”，不是最终审美判断
- llm 版负责往生产质量推进，但不是“接了 API 就自动成熟”
- 真正面向生产，还需要继续做模型、提示词和筛选策略调优

### `inspect` 返回结构

成功时大致会返回：

```json
{
  "ok": true,
  "action": "inspect",
  "data": {
    "overall_ok": true,
    "structure": {
      "is_valid": true,
      "title": "雨夜来信",
      "summary_chars": 86,
      "body_chars": 5321,
      "chapter_numbers": [1, 2, 3, 4, 5, 6],
      "issues": []
    },
    "quality": {
      "is_passable": true,
      "title": "雨夜来信",
      "opening_signal_hits": ["失踪", "短信"],
      "middle_signal_hits": ["却"],
      "ending_signal_hits": ["终于"],
      "chapter_char_counts": [320, 540, 610, 480],
      "title_overlap_chars": ["雨", "夜"],
      "issues": [],
      "suggestions": []
    }
  }
}
```

失败时统一返回：

```json
{
  "ok": false,
  "action": "inspect",
  "error": {
    "code": "INVALID_REQUEST",
    "message": "..."
  }
}
```

## Skill 当前如何使用 CLI

现在 skill 收尾已经接成这条链：

1. 正文写完
2. 如果目标是直接产出可保存版本，优先在 `build_story_drafts` 阶段开启 `auto_revise=true`
3. 再用 `inspect` 做第一轮自动自检
4. 读取：
   - `data.overall_ok`
   - `data.structure.issues`
   - `data.quality.issues`
   - `data.quality.suggestions`
5. 修订问题
6. 用 `save` 落盘
7. 记录：
   - `data.output_dir`
   - `data.output_path`
   - `data.directory_created`

这意味着当前 skill 已经不再只是“概念上说要检查和保存”，而是已经有明确的工具调用路径。

## 测试

项目当前使用根目录虚拟环境：

- `.venv`

如果要跑测试，直接使用：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

当前测试覆盖：

- `tests/tools/test_story_output_writer.py`
- `tests/tools/test_story_structure_checker.py`
- `tests/tools/test_story_quality_checker.py`
- `tests/tools/test_story_idea_seed_generator.py`
- `tests/tools/test_story_idea_repository.py`
- `tests/tools/test_story_idea_prompt_matcher.py`
- `tests/tools/test_story_idea_pack_builder.py`
- `tests/tools/test_story_idea_pack_evaluator.py`
- `tests/tools/test_story_idea_pack_llm_builder.py`
- `tests/tools/test_story_llm_config.py`
- `tests/tools/test_story_payload_builder.py`
- `tests/tools/test_story_draft_builder.py`
- `tests/tools/test_story_draft_llm_builder.py`
- `tests/tools/test_story_plan_builder.py`
- `tests/tools/test_story_plan_llm_builder.py`
- `tests/tools/test_story_prose_analyzer.py`
- `tests/tools/test_story_style_profile.py`
- `tests/tools/test_story_span_judge.py`
- `tests/tools/test_story_span_rewriter.py`
- `tests/tools/test_story_revision_runner.py`
- `tests/tools/test_story_regression_runner.py`
- `tests/tools/test_story_cli.py`
- `tests/tools/test_story_cli_idea_pipeline.py`

## 相关文档

关键文档如下：

- [SKILL.md](./SKILL.md)
- [workflow.md](./references/workflow.md)
- [quality-checklist.md](./references/quality-checklist.md)
- [LICENSE](./LICENSE)
- [开发目录与发布目录隔离方案](./docs/开发目录与发布目录隔离方案.md)
- [真实样本回归 runner 使用说明](./docs/真实样本回归runner使用说明.md)
- [验收阶段执行方案](./docs/验收阶段执行方案.md)

## 开源协议

当前仓库采用：

- `Apache License 2.0`

使用、修改和分发前，请先阅读根目录 [LICENSE](./LICENSE)。

## 下一步建议

从当前状态继续推进，最顺的方向是：

1. 继续用真实卡组验证 `deterministic + llm` 创意包、方案和正文草稿三层结果的对齐程度
2. 把重点转到 LLM 方案和 LLM 正文的真实验收、提示词调优和候选模型策略
3. 持续把 deterministic 正文基线和 `inspect` 的问题类型对齐，避免简介超长、模板腔或元提示句回流到成稿
4. 再往后才是平台自动化和外部系统接入

一句话总结现在的仓库状态：

**主 skill 已接通，deterministic 端到端链路也已经实跑通过；下一步该补的是继续做真实产出校准和 LLM 生产化验收。**
