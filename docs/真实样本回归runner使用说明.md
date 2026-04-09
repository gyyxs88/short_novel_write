# 真实样本回归 runner 使用说明

## 作用

`tools/story_regression_runner.py` 用来批量跑“真实样本 -> 创意包 -> 方案 -> payload -> 正文 -> inspect”链路，并输出两份报告：

- JSON：适合脚本继续消费
- Markdown：适合人工快速查看

当前报告除了耗时外，还会汇总标准化 token 统计：

- `prompt_tokens`
- `completion_tokens`
- `total_tokens`

如果样本启用了草稿自动修订，报告现在还会额外汇总：

- `auto_revised_job_count`
- `draft_changed_job_count`
- `revision_round_count_total`
- `revision_round_count_avg`
- `selected_draft_body_char_delta_total`
- `selected_draft_body_char_change_total`

它的目标不是替代 `story_cli.py`，而是把原本零散的真实样本验收，收口成一条可重复执行的回归流程。

## 相关文件

- 样本定义：`tools/story_regression_samples.py`
- 执行入口：`tools/story_regression_runner.py`
- 测试：`tests/tools/test_story_regression_runner.py`

## 当前默认约定

### 1. 默认样本集

当前内置样本集分为：

- `default`
- `verified`
- `zhihu`
- `douban`

其中：

- `verified` 只保留已经在记忆文档里出现过的样本
- `default` 会跑当前启用的全部内置样本

### 2. 默认生成路线

内置样本当前默认按下面的路线跑：

- 创意包：`deterministic`
- 方案：`llm`
- 正文：`llm`

原因是：

- 创意包层当前 deterministic 仍然是比较稳的筛选基线
- 当前更需要持续回归的是 `LLM 方案` 和 `LLM 正文`

如果后续想把某个样本改成 `LLM 创意包`，直接改 `tools/story_regression_samples.py` 里对应样本的 `idea_pack_route` 即可。

### 3. 选中策略

runner 第一版不会把一个样本下所有方案和正文全跑完，而是做确定性选择：

- 创意包：取 `evaluate_idea_packs` 里评分最高的一条
- 方案：优先取 `variant_index=1`，如果不存在就退回第一条
- payload：取选中方案对应的单条 payload
- 正文：只取该 payload 对应的单条草稿

这样做的目的，是先把批量回归稳定起来，避免单次运行成本过高。

## 运行前准备

如果样本里方案或正文走 `llm` 路线，需要先在本次运行使用的 SQLite 里准备好 LLM 配置。

默认配置和产物共用同一个数据库：

- `outputs/idea_pipeline/story_ideas.sqlite3`

常见前置动作是先用 `story_cli.py` 配好：

- `upsert_llm_provider`
- `upsert_llm_model`
- `upsert_llm_environment`

如果样本引用的 `llm_environment` 不存在，runner 会把该样本记为失败，并在报告里归到配置缺失类错误。

## 运行方式

### 跑默认样本集

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B tools\story_regression_runner.py
```

### 只跑验证过的样本

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B tools\story_regression_runner.py --sample-set verified
```

### 只跑知乎样本

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B tools\story_regression_runner.py --styles zhihu
```

### 只跑指定样本

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B tools\story_regression_runner.py --sample-keys zhihu_wedding_sms,douban_funeral_letter
```

### 指定输出目录和运行名

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B tools\story_regression_runner.py `
  --sample-set verified `
  --output-root outputs/regression `
  --run-name deepseek_verified_smoke
```

### 有任一样本失败就返回退出码 1

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B tools\story_regression_runner.py --fail-on-sample-failure
```

## 输出目录

默认输出根目录：

- `outputs/regression/`

每次运行会新建一个子目录，里面至少包含：

- `story_ideas.sqlite3`
- `report.json`
- `report.md`

这样可以避免污染默认的：

- `outputs/idea_pipeline/story_ideas.sqlite3`

## 报告里重点看什么

### 1. 总览

先看：

- `passed_count`
- `failed_count`
- `inspect_pass_rate`
- `token_usage`
- `auto_revised_job_count`
- `draft_changed_job_count`
- `revision_round_count_total`
- `selected_draft_body_char_delta_total`

它们决定这次回归整体有没有退化。

建议这样理解：

- `auto_revised_job_count`
  这次有多少样本真的进入了自动修订链
- `draft_changed_job_count`
  自动修订后有多少样本的正文主记录真的发生了变化
- `revision_round_count_total`
  这次回归总共跑了多少轮局部修订
- `selected_draft_body_char_delta_total`
  所有终稿相对首稿的字数净变化，适合判断后处理总体是在扩写还是压缩

### 2. 按风格汇总

再看：

- `style_summary.zhihu`
- `style_summary.douban`

这样能分清问题是全局退化，还是只集中在某一种风格。

### 3. 失败阶段统计

重点关注：

- `stage_failure_counts`

如果失败大量集中在：

- `build_story_plans`
- `build_story_drafts`
- `inspect`

说明问题分别更偏向：

- 上游方案层
- 正文层
- 结构/长度验收层

### 4. 失败类型统计

重点关注：

- `failure_type_counts`

当前第一版已经会把失败粗分成：

- `timeout`
- `invalid_json`
- `length_constraint`
- `missing_config`
- `upstream_error`
- 其他

这能直接告诉后续调优该先打哪一层。

### 5. 自动修订效果汇总

如果当前回归目标是验收“去 AI 味”后处理，除了 pass/fail，还要重点看：

- `auto_revised_job_count`
- `draft_changed_job_count`
- `revision_round_count_avg`
- `selected_draft_body_char_change_total`

一个很常见的异常信号是：

- 自动修订 job 数不低，但 `draft_changed_job_count` 很低

这通常说明：

- 自动修订链路虽然被调用了
- 但真正命中的可改 span 太少，或者改写器没有把改动落回主 draft

## 测试

只跑 runner 相关测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider tests/tools/test_story_regression_runner.py
```

## 当前边界

- 第一版只做串行执行，不做并发
- 第一版默认只选一条创意包、一条方案和一条正文，不跑整批方案对比
- 第一版优先服务真实样本回归，不接入 `story_cli.py` 的统一 action

如果后续要继续扩展，优先顺序建议是：

1. 增加更多已验证样本
2. 把失败分类继续细化
3. 再考虑是否把 runner 接进统一 CLI
