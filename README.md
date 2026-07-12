# League of Idea 🏟️

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB)
![Version](https://img.shields.io/badge/version-0.4.0-2ea44f)
![Tests](https://img.shields.io/badge/tests-46%20passed-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

> 让候选想法在 LLM 竞技场中对战，用 Elo 排名，并持续进化出更好的方案。

**League of Idea**（`loi`）是一个面向研究、产品和开放式问题的命令行工具。它从目标出发生成候选 idea，通过版本化评分规则让 LLM 进行成对比较，以 Elo 量化相对质量，并将高分 idea 进化到下一轮。

当前版本为 **v0.4.0 可用 MVP**。已支持瑞士轮、双向裁判、受控并发、预算保护、中断续跑和 Markdown 审计报告。

## 核心能力

- **生成与进化**：生成一组差异化候选，并从高分 idea 派生下一代。
- **可靠裁判**：按 novelty、feasibility、relevance 等版本化维度评分。
- **双向评审**：交换 A/B 顺序再次裁判；结论冲突时标为争议并按平局计分。
- **三种配对**：瑞士轮（默认）、随机抽样、全循环。
- **成本控制**：预估调用量，限制 calls、token 或估算金额。
- **确定性并发**：模型判断并行执行，Elo 始终按持久化赛程顺序更新。
- **安全续跑**：每场结果原子保存；失败或预算停止后复用已付费结果。
- **可审计输出**：导出排行榜、评分维度、idea 谱系和逐场判定证据。

## 30 秒快速开始

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
| `loi list` | 列出本地 Session |

`loi run` 的主要选项：

| 参数 | 默认 | 说明 |
|---|---:|---|
| `--num-ideas` | `8` | 初始候选数量 |
| `--rounds` | `3` | tournament 轮数 |
| `--pairing` | `swiss` | `swiss` / `random` / `round-robin` |
| `--double-judge` | 关闭 | 对调 A/B 后再次裁判 |
| `--concurrency` | `1` | 最大并发裁判比赛数 |
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

## 状态、预算与复现语义

- Session 默认保存在 `.loi_sessions/<session_id>.json`。
- 报告默认保存在 `.loi_reports/<session_id>.md`。
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

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
```

当前测试覆盖 Elo、生成校验、瑞士轮、双向裁判、去重、预算、定价、续跑、报告和并发确定性。

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
├── storage.py      # 原子 JSON 持久化
└── report.py       # Markdown 审计报告
```

## 路线图

- [ ] 可配置请求超时、重试和 provider 级限流
- [ ] 多模型生成归因与对比视图
- [ ] SQLite 存储与 schema migration
- [ ] 使用真实 provider 的可选冒烟测试
- [ ] Web / 图形界面（终端版本稳定之后）

版本变化见 [CHANGELOG.md](CHANGELOG.md)，架构取舍见 [docs/DESIGN_REVIEW.md](docs/DESIGN_REVIEW.md)。

## License

[MIT](LICENSE)
