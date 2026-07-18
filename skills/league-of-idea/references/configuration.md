# Configuration

## Environment

Common provider variables:

```dotenv
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
```

Model identifiers use `provider:model`. Availability depends on the user's provider account.

## Default run

| Setting | Default |
|---|---:|
| Initial ideas | 8 |
| Rounds | 3 |
| Pairing | `swiss` |
| Elo K-factor | 32 |
| Evolve top | 2 |
| Dedup threshold | 0.86 |
| Judge concurrency | 1 |
| Double judge | off |
| Request timeout | 60 seconds |
| Transient retries | 2 |
| Provider rate limit | unlimited |

The default 8-idea, 3-round Swiss run has a minimum plan of 20 LLM calls. Retries can add calls.

## Research workspace

- Project Brief keywords must contain 2–5 unique values.
- Constraints use `category:description`, for example `compute:one GPU` or `time:three months`.
- `paper add` accepts PDF, Markdown, and UTF-8 text. Imported source text is stored locally with a SHA-256 hash; PDF extraction uses `pypdf`.
- `paper analyze` creates Paper Cards with line/page locators and short quotes. Invalid locators or quotes fail the operation.
- `gap synthesize` requires at least two analyzed papers. Gaps are hypotheses and must reference existing evidence ids.
- `idea revise` never overwrites a prior version. `shortlist set` records the human decision and accepts at most one version per ResearchIdea.
- `arena run` freezes the selected IdeaSpec snapshots and uses rubric `research-workspace-v1` unless a custom rubric is supplied.

## Pairing

- `swiss`: cost-efficient default; pair nearby Elo and avoid rematches when possible.
- `random`: broader stochastic sampling; roughly one match per active idea per round.
- `round-robin`: every pair; quadratic cost as the population grows.

## Rubric JSON

```json
{
  "version": "research-v2",
  "tie_margin": 0.25,
  "criteria": [
    {
      "name": "novelty",
      "description": "Originality of the mechanism.",
      "weight": 1.0
    },
    {
      "name": "feasibility",
      "description": "Ability to execute and test.",
      "weight": 1.5
    }
  ]
}
```

Criterion names must be unique lowercase identifiers. Weights must be positive. Scores are 1–10.

## Pricing JSON

```json
{
  "version": "provider-prices-YYYY-MM-DD",
  "models": {
    "provider:model": {
      "input_per_million_usd": 1.0,
      "output_per_million_usd": 2.0
    }
  }
}
```

Replace example rates with verified current provider prices. Include every generator and judge model when using `--max-cost-usd`.

## Runtime reliability

- `--timeout-seconds`: deadline passed to the provider SDK for each attempt.
- `--max-retries`: exponential-backoff retries for throttling, timeout, connection, and upstream failures. Authentication and invalid requests fail immediately.
- `--requests-per-second`: shared per-provider pacing across concurrent judge workers.
- The runtime settings are persisted and can be changed with the same options on `resume`.

## Budget semantics

- `--max-calls`: total logical successful LLM calls for the Session; safe with concurrency.
- `--max-tokens`: total provider-reported tokens; require concurrency 1.
- `--max-cost-usd`: accumulated estimated cost; require concurrency 1 and a complete pricing table.
- Resume overrides are new lifetime totals, not increments.

## Persistence

- Sessions: `.loi_sessions/<session_id>.json`
- Reports: `.loi_reports/<session_id>.md`
- Research projects: `.loi_projects/<project_id>.json`
- Research project reports: `.loi_project_reports/<project_id>.md`
- Override both commands with `--sessions-dir` when the working directory is not the repository root.

The Session stores schema version, models, rubric, pricing, pairing/evolution plans, pending results, usage, status, timestamps, and all ideas/matches.

Research projects store the Brief, imported source text and hashes, Paper Cards and evidence, Gap hypotheses, immutable Idea versions, Critiques, human decisions, Arena mappings, runtime settings, and lifetime usage.
