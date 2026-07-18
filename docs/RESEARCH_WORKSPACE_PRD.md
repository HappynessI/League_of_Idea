# League of Idea v0.6 — Research Idea Workspace PRD

状态：实现基线
版本：0.6
日期：2026-07-18

## 1. 产品重新定位

League of Idea 不再把“一句粗糙研究目标 → AI 批量生成 → AI 排名”作为完整产品。它应帮助研究者把模糊方向逐步构建为有证据、可批判、可执行、可验证的研究方案；Idea Arena 只负责比较经过研究者筛选的成熟候选。

一句话定位：

> 一个以真实文献、现实约束和人工决策为边界，把粗糙研究构想发展为可审查 Idea，并用 Arena 辅助比较的科研工作台。

## 2. 核心原则

1. **证据优先**：论文事实、AI 推断和研究者判断必须分开保存。
2. **人类关卡**：只有研究者明确 shortlist 的 Idea 才能进入 Arena。
3. **版本不可覆盖**：批判和修订产生新版本，保留完整演化链。
4. **现实约束进入全流程**：数据、算力、时间、技能和伦理条件同时影响生成、批判和比较。
5. **不把 Elo 当真理**：排名只在指定目标、rubric、裁判模型和比赛证据内有效。
6. **可证伪**：成熟 Idea 必须说明如何被实验否定，而不只是如何获得正面结果。
7. **来源可追溯**：文献卡片和 Gap 必须指向项目内的论文与证据条目。

## 3. 两个相连但独立的循环

### 3.1 Idea Development Loop

```text
Project Brief
  → Paper Sources
  → Evidence-backed Paper Cards
  → Gap Hypotheses
  → Research Questions / Idea Candidates
  → Reviewer Critiques
  → Versioned Revisions
  → Human Shortlist
```

### 3.2 Competition Loop

```text
Shortlisted Idea Version Snapshots
  → Arena Pairing and Judging
  → Elo and Match Evidence
  → Researcher Decision / Further Revision
```

Arena 不得读取“最新版本”这种可变引用。每次入场都保存明确的 Idea version id 和文本快照，保证结果可审计。

## 4. v0.6 范围

### 必须完成

- 创建研究项目并记录方向、关键词、已有基础和现实约束。
- 导入 TXT、Markdown 或 PDF 论文全文；保存来源哈希。
- 将论文整理为结构化 Paper Card，并保留短证据摘录与定位符。
- 基于已分析论文合成 Gap Hypothesis，区分证据与 AI 推断。
- 从 Gap 生成结构化 Idea，而不是一句话点子。
- 以严格审稿人等角色生成结构化 Critique。
- 根据 Critique 创建不可覆盖的新 IdeaVersion。
- 由研究者显式 shortlist 指定版本。
- 将 shortlist 快照送入现有 Arena。
- 导出完整项目 Markdown 报告。
- 所有 AI 操作复用现有预算、定价、超时、重试和 provider 限流。

### 暂不完成

- 自动联网检索论文及自动判断“最新文献”。
- 引文数据库去重、DOI 元数据自动补全。
- 多人权限、云同步和 Web UI。
- 自动替研究者决定最终选题。
- 将 AI 生成的 Gap 表述为已被文献证明的事实。

## 5. 核心数据模型

### ResearchProject

保存 ProjectBrief、Paper、GapHypothesis、ResearchIdea、Critique、HumanDecision、ArenaRun，以及项目级模型调用配置与用量。

### ProjectBrief

- direction：具体研究方向
- keywords：2–5 个关键词
- background：研究者已有基础
- constraints：数据、算力、时间、实验、技能、伦理等约束
- success_criteria：研究者认为何时值得继续

### Paper / PaperCard

Paper 保存来源路径、内容哈希和带定位符的可分析文本。PaperCard 保存研究问题、方法、创新、数据与实验、局限、相关性以及 EvidenceItem。EvidenceItem 由短摘录、来源定位符和它支撑的主张组成。

### GapHypothesis

Gap 是“待验证研究假设”，不是事实。它必须保存：描述、重要性、未解决原因、支持 paper/evidence ids、反证或不确定性、置信度和下一步验证动作。

### ResearchIdea / IdeaVersion

ResearchIdea 是稳定身份；IdeaVersion 是不可覆盖快照。完整版本至少包含：研究问题、动机、证据、Gap、假设、方法、预期贡献、评价方案、所需资源、风险、证伪条件和开放问题。

### Critique

保存 reviewer role、目标版本、主要问题、致命缺陷、改进建议、需要补充的证据以及 verdict。Critique 不能直接修改 IdeaVersion。

### HumanDecision

保存研究者 shortlist 的明确动作、选中的 version ids、备注和时间。进入 Arena 前必须存在该记录。

## 6. CLI 信息架构

```text
loi project init|show|list|report
loi paper add|list|analyze
loi gap synthesize|list
loi idea generate|list|show|critique|revise
loi shortlist set|show
loi arena run
```

原有 `loi run/rank/resume/report/analyze/list` 保持兼容。

## 7. 安全与质量边界

- Paper Card 中的定位符必须来自导入文本中的真实标签。
- 单条证据摘录限制长度，避免报告复制大段原文。
- Gap 中引用的 paper/evidence id 必须在项目中存在，否则拒绝保存。
- Idea 引用的 gap id 必须存在。
- 修订必须创建 version number +1，并记录 parent version id。
- Arena 入口不足两个 shortlisted versions 时拒绝运行。
- AI 输出解析失败时不写入半成品对象；项目保留失败前状态。
- PDF 无可提取文本时明确报错，不调用模型猜测内容。

## 8. v0.6 验收标准

在无网络测试中，使用模拟 LLM 完成：

1. 初始化项目并持久化。
2. 导入至少两篇带定位符的文本论文。
3. 生成并验证 Paper Cards。
4. 合成带有效证据引用的 Gap。
5. 生成完整 Idea，完成一次 Critique 和一次 Revision。
6. 人工 shortlist 两个明确版本。
7. 以快照形式进入 Arena，并可恢复查看映射关系。
8. 导出同时包含证据、推断、版本、批判和 Arena 信息的报告。

## 9. 后续版本

- v0.7：Crossref / Semantic Scholar / arXiv 等可选检索连接器与 DOI 去重。
- v0.8：SQLite、项目查询、跨项目复用 Paper Cards。
- v0.9：裁判校准、研究者反馈学习与多模型共识分析。
- v1.0：稳定的终端科研选题工作流与可迁移数据格式。
