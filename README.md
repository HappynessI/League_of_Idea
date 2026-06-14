# League of Idea 🏟️

> 一个让想法在竞技场里互相厮杀、用 Elo 决出胜负的命令行工具。

**League of Idea**（`loi`）是一个命令行工具，用于自动化地**生成、对战、评分并迭代优化想法（idea）**。

它借鉴了 _Towards an AI Co-Scientist_（Google, 2025）中提出的 Elo 评分与"想法竞赛"机制：让多个候选 idea 通过两两对战，由大语言模型担任裁判判定优劣，用 Elo 分数量化每个 idea 的相对质量，并（可选地）让高分 idea 不断进化产生改进版本，最终输出一份按质量排序的 idea 排行榜。

> ⚠️ **项目状态：早期脚手架（v0.1.0）。** 核心循环已经实现并可运行，但尚未在真实大规模场景下打磨。欢迎试用与反馈。

---

## 核心机制

整个系统是一个循环（tournament loop），由五个阶段组成：

```
1. 生成 (Generate)  根据研究目标生成 N 个候选 idea
        ▼
2. 对战 (Match)     idea 两两配对，LLM 裁判判定谁更优
        ▼
3. 评分 (Score)     按每场胜负更新双方 Elo 分
        ▼
4. 进化 (Evolve)    挑选高分 idea，生成改进版作为下一代
        ▼
5. 排名 (Rank)      循环若干轮后，按 Elo 输出排行榜
```

---

## 安装

需要 Python 3.11+。推荐使用 [`uv`](https://github.com/astral-sh/uv)，也可用 `pip`。

```bash
# 克隆后，在项目根目录：
pip install -e .

# 或使用 uv
uv pip install -e .
```

LLM 调用层使用 [**any-llm**](https://github.com/mozilla-ai/any-llm)（Mozilla.ai 出品，直接调用各家官方 SDK，**非 LiteLLM**）。安装时请带上需要的 provider：

```bash
pip install 'any-llm-sdk[openai,anthropic]'
```

### 配置密钥

复制 `.env.example` 为 `.env`，填入真实密钥（`.env` 已被 `.gitignore` 排除，不会提交）：

```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY / ANTHROPIC_API_KEY
```

---

## 使用

```bash
# 运行一次完整竞赛
loi run --goal "如何降低城市内涝风险" --num-ideas 8 --rounds 3

# 指定模型与配对策略
loi run -g "如何降低城市内涝风险" \
        --generator-model openai/gpt-4o \
        --judge-model anthropic/claude-sonnet-4-6 \
        --pairing round-robin

# 关闭进化（退化为"生成一批 → 对战排名"）
loi run -g "..." --no-evolve

# 查看历史会话排行榜
loi rank --session <session_id>

# 列出所有已保存的会话
loi list
```

### 主要参数

| 参数 | 含义 | 默认 |
|---|---|:-:|
| `--goal` / `-g` | 研究目标 / 问题（必填） | — |
| `--num-ideas` / `-n` | 初始 idea 数 | 8 |
| `--rounds` / `-r` | 迭代轮数 | 3 |
| `--judge-model` | 裁判模型 | `anthropic/claude-sonnet-4-6` |
| `--generator-model` | 生成/进化模型 | `openai/gpt-4o` |
| `--pairing` | 配对策略：`round-robin` / `random` | `round-robin` |
| `--k` | Elo K 值 | 32 |
| `--no-evolve` | 关闭 idea 进化 | 关闭即不进化 |
| `--evolve-top` | 每轮进化排名前几的 idea | 2 |

会话状态以 JSON 形式保存在 `./.loi_sessions/<session_id>.json`。

---

## Elo 评分

采用国际象棋标准 Elo：

```
期望胜率：  E_A = 1 / (1 + 10 ^ ((R_B - R_A) / 400))
分数更新：  R_A_new = R_A + K * (S_A - E_A)
```

默认初始分 1200，K 值 32。该模块（`elo.py`）为纯函数，已有单元测试覆盖。

---

## 项目结构

```
league-of-idea/
├── pyproject.toml          # 依赖 + [project.scripts] 注册 `loi` 命令
├── .env.example            # 所需环境变量（不含真实值）
├── .gitignore
├── README.md
├── LICENSE                 # MIT
├── src/league_of_idea/
│   ├── __init__.py
│   ├── cli.py              # 入口：解析命令与参数，启动主循环
│   ├── llm.py              # 封装 any-llm 调用（生成 / 裁判共用）
│   ├── models.py           # pydantic 数据结构：Idea、MatchResult、Session
│   ├── generator.py        # 生成 / 进化候选 idea
│   ├── judge.py            # 裁判：两个 idea 对战，输出胜负
│   ├── elo.py              # Elo 评分计算（纯函数）
│   ├── pairing.py          # 配对策略：随机 / 全循环
│   ├── tournament.py       # 编排：串起 生成→对战→评分→进化→排名
│   └── storage.py          # 读写 JSON 状态
└── tests/
    └── test_elo.py         # Elo 单元测试
```

运行测试：

```bash
pip install -e '.[dev]'
pytest
```

---

## 功能状态

### ✅ 已实现

- [x] 命令行接收研究目标（`loi run --goal ...`）
- [x] 一次生成 N 个候选 idea（`generator.py`）
- [x] 两两对战：全循环（round-robin）与随机（random）两种配对策略
- [x] LLM 裁判，结构化（JSON）输出胜负与理由（novelty / feasibility / relevance 三维标准）
- [x] 标准 Elo 评分更新
- [x] 多轮迭代（`--rounds`）
- [x] **Idea 进化**：每轮取高分 idea 生成改进版注入下一代（`--no-evolve` 可关闭）
- [x] 状态持久化为 JSON，可用 `loi rank` / `loi list` 查看历史
- [x] 终端排行榜输出（rich 表格）
- [x] `.env` 密钥管理，密钥不入库
- [x] Elo 模块单元测试

### 🚧 未实现 / 计划中

- [ ] **瑞士轮配对**（`pairing.swiss` 目前为占位，会抛 `NotImplementedError`）
- [ ] **并发对战**（asyncio 同时跑多场以提速）
- [ ] **裁判位置偏见消除**（对调 A/B 顺序各判一次）
- [ ] **分维度打分**（目前裁判只给整体胜负，未拆分 novelty/feasibility/relevance 的分值）
- [ ] **成本统计**（累计 token 用量与花费）
- [ ] **中断续跑**（从上次会话状态恢复未完成的竞赛）
- [ ] **多模型混战的归因分析**（`created_by` 字段已记录，但尚无分析视图）
- [ ] **失败重试 / 超时 / 限流处理**（当前 LLM 调用失败会直接抛错）
- [ ] **idea 去重**（生成阶段尚未做语义去重）
- [ ] SQLite 持久化后端（当前仅 JSON）
- [ ] 更全面的测试（generator / judge / tournament 尚无测试）
- [ ] Web / 图形界面（明确的非目标，首期仅终端）

---

## 设计说明 & 待确认项

完整设计文档见仓库外的 PRD。几个仍需人工最终确认的关键点：

- **裁判评判标准**：当前默认 novelty / feasibility / relevance 三维等权，整体判胜负。这是 Elo 分是否有意义的核心，可在 `judge.py` 调整。
- **默认模型**：生成用 `openai/gpt-4o`，裁判用 `anthropic/claude-sonnet-4-6`，可通过命令行参数覆盖。
- **配对策略**：默认全循环（最公平，场次随 idea 数平方增长），idea 较多时可改 `--pairing random` 降低成本。
- **是否引用原论文出处**：_Towards an AI Co-Scientist_ 最初以 arXiv 预印本 + 官方博客发布，是否正式发表于期刊需自行核实后再写入正式引用。

---

## License

[MIT](./LICENSE)
