---
name: league-of-idea
description: Operate the League of Idea CLI to generate, compare, Elo-rank, evolve, resume, and audit candidate ideas for research, product, engineering, or other open-ended goals. Use when a user asks to brainstorm and rank approaches, run an idea tournament, compare candidate proposals with an LLM judge, evolve high-scoring ideas, estimate or constrain model cost, configure pairing/rubrics, resume a stopped Session, inspect rankings, or export a Markdown evidence report.
---

# League of Idea

Use the project's existing `loi` CLI. Do not recreate tournament logic in ad-hoc scripts.

## Start every workflow

1. Resolve this Skill's directory as `SKILL_DIR`.
2. Run the environment check:

   ```bash
   python3 "$SKILL_DIR/scripts/loi.py" doctor
   ```

3. If no executable is found and the repository is available, install from its root:

   ```bash
   # Use Python 3.11 or newer.
   python3 -m venv .venv
   .venv/bin/python -m pip install .
   ```

4. Never print secret values. Report only whether the required provider key is configured.

The wrapper discovers, in order: `LOI_BIN`, the repository `.venv`, `loi` on `PATH`, or an importable `league_of_idea` package. Set `LEAGUE_OF_IDEA_ROOT` only when automatic repository discovery fails.

## Run a tournament

Preserve the user's goal verbatim unless they ask for rewriting. Use the current defaults when they do not specify tournament settings:

- 8 initial ideas
- 3 rounds
- Swiss pairing
- evolution enabled
- single-direction judging
- concurrency 1

Estimate before making paid calls:

```bash
python3 "$SKILL_DIR/scripts/loi.py" estimate \
  --num-ideas 8 \
  --rounds 3 \
  --pairing swiss
```

Then run with a finite call budget. A practical default for the standard configuration is 30 calls; generation/evolution retries can exceed the minimum estimate.

```bash
python3 "$SKILL_DIR/scripts/loi.py" run \
  --goal "<user goal>" \
  --num-ideas 8 \
  --rounds 3 \
  --pairing swiss \
  --max-calls 30
```

Capture and report the Session id, status, calls, token usage, estimated cost when priced, and top-ranked ideas.

## Choose quality and speed options

- Add `--double-judge` when position bias matters. It evaluates both A/B orientations and records disagreement as a disputed draw.
- Add `--concurrency N` for faster judging when using `--max-calls` or no budget.
- Keep `--concurrency 1` with `--max-tokens` or `--max-cost-usd`; the CLI rejects unsafe parallel token/cost budgets.
- Use `--pairing round-robin` only for small fields or when complete pairwise coverage justifies quadratic cost.
- Use `--no-evolve` when the task is only to rank a fixed candidate set.
- Use `--rubric-file` only when the user provides or approves custom criteria. Increment the rubric version after changing criteria or weights.
- Treat `pricing.example.json` as a schema example, never as current pricing. Require verified provider rates before enforcing a dollar budget.

Read [references/configuration.md](references/configuration.md) when models, rubrics, pricing, budgets, or concurrency need customization.

## Resume and inspect

List and inspect saved work without contacting an LLM:

```bash
python3 "$SKILL_DIR/scripts/loi.py" list
python3 "$SKILL_DIR/scripts/loi.py" rank --session <session_id>
```

Resume a `failed` or `stopped` Session. Budget overrides are total lifetime limits, not additional allowances, so raise them above existing usage:

```bash
python3 "$SKILL_DIR/scripts/loi.py" resume \
  --session <session_id> \
  --max-calls <new_total_limit>
```

Do not restart from scratch when a resumable Session exists. Pairing plans, pending paid judgments, Elo order, and evolution plans are persisted for deterministic continuation.

## Export the deliverable

Create a Markdown report after completion or when the user wants an audit of partial results:

```bash
python3 "$SKILL_DIR/scripts/loi.py" report \
  --session <session_id> \
  --output <report.md>
```

Return the report path plus a concise summary of the winner, runner-up, disputed matches, usage, and stop reason if incomplete.

Read [references/workflows.md](references/workflows.md) for ready-to-run task patterns and failure recovery.

## Guardrails

- Run `estimate` before `run` unless the user already supplied a strict budget and exact configuration.
- Never silently remove a budget, lower a deduplication threshold, change a rubric, or switch models during resume.
- Do not claim `--seed` makes provider outputs deterministic; it fixes pairing and presentation order only.
- Do not interpret Elo as absolute truth. State that it is relative to the goal, rubric, judge model, and observed matches.
- Do not push Session JSON, `.env`, API keys, or generated reports unless the user explicitly requests publication.
- When a provider call fails, preserve the Session and prefer `resume` after fixing credentials, quota, or connectivity.
