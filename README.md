# League of Idea 🏟️

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![Version](https://img.shields.io/badge/version-0.6.0-2ea44f)
![Tests](https://img.shields.io/badge/tests-61%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

![League of Idea — LLM idea tournament poster](assets/league-of-idea-poster.png)

> 从真实文献和现实约束出发，把粗糙方向发展成可审查研究 Idea，再由研究者选择是否送入 Arena。

**League of Idea**（`loi`）是一个证据驱动的科研 Idea 构建工作台。它保存研究方向、现实约束和代表性论文，把论文整理成可追溯 Paper Card，协助研究者发现待验证 Gap、构建完整 Idea、进行审稿式批判和版本化修订。只有研究者明确 shortlist 的候选才会进入 Elo Arena。

当前版本为 **v0.6.0 Research Idea Workspace**。原有快速 tournament 保持兼容，但严肃科研场景推荐使用“文献 → Gap → Idea → Critique → 人工 shortlist → Arena”工作流。

## 核心能力

- **研究 Brief**：明确方向、2–5 个关键词、研究者基础和数据/算力/时间等约束。
- **证据化文献卡片**：导入 PDF、Markdown、TXT；每条证据必须通过真实定位符和短摘录校验。
- **Gap Hypothesis**：把研究缺口作为需要验证的 AI 推断，并保存依据、不确定性和验证动作。
- **完整 IdeaSpec**：包含问题、假设、方法、贡献、评价、资源、风险和证伪条件。
- **批判与版本链**：Critique 不修改原文；Revision 创建可追踪的新版本。
- **人工 shortlist**：研究者的显式决策是进入 Arena 的强制关卡。
- **生成与进化**：生成一组差异化候选，并从高分 idea 派生下一代。
- **可靠裁判**：按 novelty、feasibility、relevance 等版本化维度评分。
- **双向评审**：交换 A/B 顺序再次裁判；结论冲突时标为争议并按平局计分。
- **三种配对**：瑞士轮（默认）、随机抽样、全循环。
- **成本控制**：预估调用量，限制 calls、token 或估算金额。
- **确定性并发**：模型判断并行执行，Elo 始终按持久化赛程顺序更新。
- **安全续跑**：每场结果原子保存；失败或预算停止后复用已付费结果。
- **可审计输出**：导出排行榜、评分维度、idea 谱系和逐场判定证据。

## 快速开始

需要 Python 3.11+。

```bash
git clone https://github.com/HappynessI/League_of_Idea.git
cd League_of_Idea

python -m venv .venv
source .venv/bin/activate
pip install .

cp .env.example .env
# 在 .env 中填写 OPENAI_API_KEY / ANTHROPIC_API_KEY
```

### 推荐：Research Workspace

先建立研究 Brief，不会调用模型：

```bash
loi project init \
  --title "小模型 Agent 可靠性" \
  --direction "研究小模型 Agent 长程任务失败的提前预测方法" \
  --keyword agents --keyword reliability --keyword failure-prediction \
  --background "可运行开源 7B 模型和 Agent benchmark" \
  --constraint "compute:单张 24GB GPU" \
  --constraint "time:三个月" \
  --max-calls 30
```

导入并分析真实论文：

```bash
loi paper add --project <project_id> --file paper.pdf
loi paper analyze --project <project_id> --paper <paper_id> --model openai:gpt-4o
```

至少分析两篇论文后，形成 Gap 和完整候选：

```bash
loi gap synthesize --project <project_id> --count 5
loi idea generate --project <project_id> --count 5
loi idea critique --project <project_id> --idea <idea_id> \
  --model anthropic:claude-sonnet-4-6 --role strict-reviewer
loi idea revise --project <project_id> --idea <idea_id>
```

研究者选择明确版本后才能进入 Arena：

```bash
loi shortlist set --project <project_id> \
  --version <version_id_1> --version <version_id_2> \
  --note "已人工核对文献依据和实验条件"
loi arena run --project <project_id> --rounds 3 --double-judge
loi project report --project <project_id> --output research-project.md
```

### 快速 Tournament（兼容模式）

先查看计划调用量，不会连接模型服务：

```bash
loi estimate --num-ideas 8 --rounds 3
# 默认配置：Estimated minimum LLM calls: 20
```

运行第一次竞赛：

```bash
loi run \
  --goal "如何降低城市内涝风险" \
  --num-ideas 8 \
  --rounds 3 \
  --max-calls 30
```

## 常用工作流

### 更稳健的双向裁判

```bash
loi run \
  --goal "如何提高小模型代理的长程任务成功率" \
  --double-judge \
  --max-calls 50
```

### 受控并发

```bash
loi run \
  --goal "如何提高科研 idea 的实验可证伪性" \
  --concurrency 4 \
  --max-calls 40
```

模型判断可以并行完成，但 Elo 更新顺序固定，因此不同请求完成顺序不会改变最终排名。`--max-calls` 支持并发额度预留；使用 `--max-tokens` 或 `--max-cost-usd` 时必须保持 `--concurrency 1`，避免多个在途请求共同越过预算。

### 自定义评分规则

```bash
loi run \
  --goal "设计低成本机器人数据采集方案" \
  --rubric-file rubric.example.json \
  --max-calls 30
```

Rubric 会随 Session 一起保存。调整评分维度或权重时应更新 `version`，保证历史结果可解释。

### 金额估算与上限

```bash
loi run \
  --goal "研究目标" \
  --pricing-file pricing.example.json \
  --max-cost-usd 2 \
  --concurrency 1
```

> `pricing.example.json` 中的数字只是格式示例，不代表当前真实价格。使用前必须根据模型提供商的官方价格更新费率和版本字段。

### 续跑与报告

```bash
# 提高总调用预算后继续失败或停止的 Session
loi resume --session <session_id> --max-calls 80

# 再次查看排行榜
loi rank --session <session_id>

# 导出完整 Markdown 报告
loi report --session <session_id> --output result.md

# 列出历史 Session
loi list
```

## 命令概览

| 命令 | 作用 |
|---|---|
| `loi run` | 创建并运行一个 idea tournament |
| `loi estimate` | 估算最低计划 LLM 调用量，不发起 API 请求 |
| `loi resume` | 继续失败或预算停止的 Session |
| `loi rank` | 查看已保存的排行榜 |
| `loi report` | 导出 Markdown 审计报告 |
| `loi analyze` | 按 idea 创建模型对比平均/最佳 Elo 与战绩 |
| `loi list` | 列出本地 Session |
| `loi project init/show/list/report` | 管理研究项目与完整审计报告 |
| `loi paper add/list/analyze` | 导入论文并创建证据化 Paper Card |
| `loi gap synthesize/list` | 形成带证据引用的 Gap Hypothesis |
| `loi idea generate/list/show/critique/revise` | 构建、批判和修订版本化 Idea |
| `loi shortlist set/show` | 保存研究者人工筛选决策 |
| `loi arena run` | 比较 shortlist 的成熟版本快照 |

`loi run` 的主要选项：

| 参数 | 默认 | 说明 |
|---|---:|---|
| `--num-ideas` | `8` | 初始候选数量 |
| `--rounds` | `3` | tournament 轮数 |
| `--pairing` | `swiss` | `swiss` / `random` / `round-robin` |
| `--double-judge` | 关闭 | 对调 A/B 后再次裁判 |
| `--concurrency` | `1` | 最大并发裁判比赛数 |
| `--timeout-seconds` | `60` | 单次 provider 请求超时 |
| `--max-retries` | `2` | 仅对限流、网络和上游故障重试 |
| `--requests-per-second` | 无限制 | 每个 provider 的共享请求速率上限 |
| `--evolve-top` | `2` | 每轮进化的高分 idea 数 |
| `--no-evolve` | 关闭 | 禁止进化，仅做排名 |
| `--rubric-file` | 内置规则 | 自定义版本化评分规则 |
| `--dedup-threshold` | `0.86` | 近重复相似度阈值 |
| `--max-calls` | 无限制 | LLM 逻辑调用总上限 |
| `--max-tokens` | 无限制 | provider 已报告 token 上限 |
| `--pricing-file` | 不计金额 | 版本化模型费率表 |
| `--max-cost-usd` | 无限制 | 估算金额上限 |
| `--seed` | 随机 | 固定配对和 A/B 展示顺序 |

使用 `loi run --help` 查看完整参数。

## Tournament 机制

```text
研究目标
   │
   ▼
生成候选 ──► 近重复过滤
   │
   ▼
持久化配对计划 ──► LLM 裁判 ──► 维度分数 / 置信度 / 争议
   │                                  │
   │                                  ▼
   └──────────────────────────────► Elo 更新
                                      │
                                      ▼
                              高分 idea 进化
                                      │
                                      └──► 下一轮 / 最终报告
```

默认瑞士轮优先匹配 Elo 相近且尚未交手的 idea。新 idea 从统一的 1200 Elo 开始，必须通过比赛获得排名，不直接继承父代分数。

Research Workspace 的 Arena 默认使用 `research-workspace-v1` rubric，比较问题重要性、证据强度、新颖性、方法有效性、现实可行性和可证伪性。Elo 仍然只是这些明确条件下的相对比较结果。

## 状态、预算与复现语义

- Session 默认保存在 `.loi_sessions/<session_id>.json`。
- 报告默认保存在 `.loi_reports/<session_id>.md`。
- Research Project 默认保存在 `.loi_projects/<project_id>.json`。
- Project 报告默认保存在 `.loi_project_reports/<project_id>.md`。
- pairing plan、evolution plan 和已完成裁判结果都会持久化。
- 并发任务先预留调用额度，再执行模型请求。
- 并发返回的结果先进入 pending cache，随后按赛程顺序串行计分。
- `--seed` 固定配对和 A/B 顺序，但不能保证第三方模型输出完全确定。
- Elo 是特定目标、rubric、裁判模型和比赛集合下的相对分数，不是绝对质量指标。

## 模型与密钥

所有模型调用经由 [Mozilla.ai any-llm](https://github.com/mozilla-ai/any-llm)，模型标识使用 `provider:model`：

```bash
loi run \
  --goal "研究目标" \
  --generator-model openai:gpt-4o \
  --judge-model anthropic:claude-sonnet-4-6
```

密钥从环境变量或 `.env` 读取。`.env` 已加入 `.gitignore`，不要把真实密钥提交到版本库。

## Codex Skill

仓库内置了开箱即用的 Codex Skill：[skills/league-of-idea](skills/league-of-idea)。它会指导 Codex 完成环境检查、调用量预估、预算安全运行、失败续跑和报告导出，并始终复用项目 CLI。

在 macOS / Linux 中推荐使用软链接安装，这样 Skill 会随仓库更新：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -s "$(pwd)/skills/league-of-idea" \
  "${CODEX_HOME:-$HOME/.codex}/skills/league-of-idea"
```

也可以复制安装：

```bash
cp -R skills/league-of-idea "${CODEX_HOME:-$HOME/.codex}/skills/"
```

随后在 Codex 中调用：

```text
Use $league-of-idea to run a cost-controlled idea tournament for:
如何提高小模型代理的长程任务成功率
```

单独检查环境，不会发起模型请求：

```bash
python3 skills/league-of-idea/scripts/loi.py doctor
```

如果复制后的 Skill 无法自动定位仓库，设置 `LEAGUE_OF_IDEA_ROOT` 为本项目根目录；也可以用 `LOI_BIN` 指定已安装的 `loi` 可执行文件。

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

当前测试覆盖证据定位、Project 持久化、Gap 引用、Idea 版本、Critique/Revision、人工 shortlist、Arena 快照，以及原有 Elo、预算、续跑和并发确定性。

主要模块：

```text
src/league_of_idea/
├── cli.py          # 命令行入口
├── tournament.py   # tournament 编排、续跑与确定性并发
├── generator.py    # idea 生成与进化
├── judge.py        # 分维度及双向裁判
├── pairing.py      # 瑞士轮、随机、全循环
├── elo.py          # Elo 纯函数
├── rubric.py       # 版本化评分规则
├── dedup.py        # 本地近重复检测
├── usage.py        # 调用/token 预算与并发额度预留
├── pricing.py      # 版本化费率与金额估算
├── runtime.py      # 超时、可恢复重试与 provider 限流
├── analysis.py     # 创建模型表现归因
├── workspace_models.py  # Project/Paper/Gap/IdeaVersion/Critique 契约
├── ingest.py       # PDF/Markdown/TXT 导入与真实定位符
├── research.py     # 证据驱动生成、批判和修订
├── workspace_storage.py # Research Project 原子持久化
├── workspace_report.py  # 完整研究项目报告
├── workspace_cli.py     # Research Workspace 命令组
├── arena_bridge.py      # 人工 shortlist 到不可变 Arena 快照
├── storage.py      # 原子 JSON 持久化
└── report.py       # Markdown 审计报告
```

## 路线图

- [x] 可配置请求超时、重试和 provider 级限流
- [x] 多模型生成归因与对比视图
- [x] 文献证据、Gap、版本化 Idea、Critique 与人工 shortlist 工作流
- [ ] 可选的 arXiv / Semantic Scholar / Crossref 检索连接器
- [ ] SQLite 存储与 schema migration
- [ ] 使用真实 provider 的可选冒烟测试
- [ ] Web / 图形界面（终端版本稳定之后）

版本变化见 [CHANGELOG.md](CHANGELOG.md)，v0.6 产品定义见 [docs/RESEARCH_WORKSPACE_PRD.md](docs/RESEARCH_WORKSPACE_PRD.md)，架构取舍见 [docs/DESIGN_REVIEW.md](docs/DESIGN_REVIEW.md)。

## License

[MIT](LICENSE)
