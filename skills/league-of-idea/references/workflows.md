# Workflows

## Contents

- Evidence-backed research development
- Human shortlist and research Arena
- Legacy quick ideation
- Ranking without evolution
- High-confidence judging
- Cost-controlled execution
- Resume and recovery
- Audit report
- Common failures

## Evidence-backed research development

1. Initialize a Project Brief with 2–5 keywords and real constraints.
2. Use `paper search` across arXiv, Crossref, and Semantic Scholar to discover leads.
3. Show `paper results` and ask the researcher to approve representative papers.
4. Use `paper fetch` for an approved open PDF, or `paper add` for a manually supplied file.
5. Analyze each paper into a Paper Card. Do not continue if evidence validation fails.
6. After at least two cards, use `gap synthesize`; present gaps as hypotheses.
7. Use `idea generate`, then inspect the full IdeaSpec rather than only the title.
8. Critique promising ideas with strict-reviewer and, when useful, a second provider.
9. Use `idea revise` so changes become a new immutable version.
10. Ask the researcher to select exact version ids.
11. Record `shortlist set`, then use `arena run`.
12. Export `project report` and recommend discussion with a supervisor or domain expert.

The report must preserve source locators, AI inference, uncertainty, critique history, the human decision, and Arena session mapping.

## Human shortlist and research Arena

The CLI requires at least two versions from distinct ResearchIdea identities. Use one exact version per candidate. Arena input is a frozen full IdeaSpec containing method, evaluation, resources, risks, and falsification criteria.

Do not substitute the latest version automatically after a shortlist. If the user revises an idea, ask whether they want to create a new shortlist decision.

## Legacy quick ideation

Use the default Swiss tournament for a broad goal:

```bash
python3 "$SKILL_DIR/scripts/loi.py" estimate --num-ideas 8 --rounds 3
python3 "$SKILL_DIR/scripts/loi.py" run \
  --goal "<goal>" --num-ideas 8 --rounds 3 --max-calls 30
```

Prefer 6–10 initial ideas. More candidates increase breadth but also generation, judging, and evolution cost.

## Ranking without evolution

Use `--no-evolve` when the input set must remain fixed or when the user wants a baseline tournament:

```bash
python3 "$SKILL_DIR/scripts/loi.py" run \
  --goal "<goal>" --no-evolve --rounds 3 --max-calls 20
```

For user-controlled mature candidates, prefer the Research Workspace shortlist and `arena run`; it preserves their exact selected versions rather than generating replacements.

## High-confidence judging

Use both orientations when judgment quality matters more than cost:

```bash
python3 "$SKILL_DIR/scripts/loi.py" estimate \
  --num-ideas 8 --rounds 3 --double-judge
python3 "$SKILL_DIR/scripts/loi.py" run \
  --goal "<goal>" --double-judge --max-calls 50
```

Review disputed matches in the Markdown report. A disputed result is intentionally scored as a draw.

## Cost-controlled execution

Call budget with safe concurrency:

```bash
python3 "$SKILL_DIR/scripts/loi.py" run \
  --goal "<goal>" --concurrency 4 --max-calls 30
```

Token budget or verified dollar budget:

```bash
python3 "$SKILL_DIR/scripts/loi.py" run \
  --goal "<goal>" --max-tokens 100000 --concurrency 1

python3 "$SKILL_DIR/scripts/loi.py" run \
  --goal "<goal>" --pricing-file <pricing.json> \
  --max-cost-usd 2 --concurrency 1
```

Dollar limits are estimates based on provider-reported tokens and the saved pricing table.

## Resume and recovery

1. Read the error shown by `loi resume` or the Session JSON.
2. Fix the external cause: missing key, unavailable model, quota, connectivity, or too-low budget.
3. Preserve the original models, rubric, seed, pairing strategy, and Session directory.
4. Resume with a higher total limit when the previous budget was exhausted.

```bash
python3 "$SKILL_DIR/scripts/loi.py" resume \
  --session <id> --max-calls <new_total>
```

Concurrent paid judgments stored in `pending_results` are reused and then applied in the persisted match order.

## Audit report

```bash
python3 "$SKILL_DIR/scripts/loi.py" report \
  --session <id> --output <path/to/report.md>
```

Summarize:

- top ideas and Elo;
- W-D-L records and generation lineage;
- rubric version;
- disputed judgments;
- calls, tokens, priced/unpriced calls, and estimated cost;
- completion status and stop reason.

## Common failures

### No League of Idea executable found

Run `doctor`, set `LEAGUE_OF_IDEA_ROOT`, or install the repository into `.venv`.

### Model reference lacks provider

Use `provider:model`, such as `openai:gpt-4o`.

### Missing API key

Add the provider key to `.env` or the environment. Never echo its value.

### Call budget reached

Resume with a new total greater than `session.usage.calls`.

### Cost budget requires prices

Provide a pricing table containing both generator and judge model identifiers.

### Concurrent token/cost budget rejected

Set `--concurrency 1`, or use a call-count budget for safe parallel execution.

### Generation remains too similar

The generator retries near-duplicates up to its built-in limit. Keep the default threshold unless the user explicitly accepts more overlap.
