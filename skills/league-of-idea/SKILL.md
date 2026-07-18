---
name: league-of-idea
description: Operate League of Idea as an evidence-backed research ideation workspace and Elo Arena. Use when a user wants to turn a rough research direction and representative papers into traceable Paper Cards, gap hypotheses, complete versioned research ideas, reviewer critiques, human-shortlisted candidates, Arena comparisons, or auditable reports; also use for the legacy quick idea tournament, budgets, resume, rubrics, and rankings.
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

## Choose the workflow

For serious research ideation, use the Research Workspace workflow below. Use the legacy quick tournament only when the user explicitly wants fast brainstorming/ranking without a literature-grounded development process.

## Build an evidence-backed research project

Do not ask AI to generate ideas before a Project Brief exists. Initialize it with the user's direction verbatim, 2–5 keywords, known background, and explicit constraints:

```bash
python3 "$SKILL_DIR/scripts/loi.py" project init \
  --title "<title>" \
  --direction "<specific direction>" \
  --keyword "<keyword 1>" --keyword "<keyword 2>" \
  --background "<existing foundation>" \
  --constraint "compute:<condition>" \
  --constraint "time:<condition>" \
  --max-calls <finite total>
```

Import only papers the user supplies or explicitly approves. PDF, Markdown, and UTF-8 text are supported:

```bash
python3 "$SKILL_DIR/scripts/loi.py" paper add \
  --project <project_id> --file <paper.pdf>
python3 "$SKILL_DIR/scripts/loi.py" paper analyze \
  --project <project_id> --paper <paper_id> --model <provider:model>
```

Analyze at least two papers before gap synthesis. Then develop and challenge candidates:

```bash
python3 "$SKILL_DIR/scripts/loi.py" gap synthesize \
  --project <project_id> --count 5 --model <provider:model>
python3 "$SKILL_DIR/scripts/loi.py" idea generate \
  --project <project_id> --count 5 --model <provider:model>
python3 "$SKILL_DIR/scripts/loi.py" idea critique \
  --project <project_id> --idea <idea_id> \
  --role strict-reviewer --model <provider:model>
python3 "$SKILL_DIR/scripts/loi.py" idea revise \
  --project <project_id> --idea <idea_id> --model <provider:model>
```

Recommend cross-model critique when the user has access to multiple providers, but never imply that model agreement proves novelty or correctness.

## Require a human gate before Arena

Show the candidate versions and ask the researcher to choose. Never shortlist on the user's behalf unless they explicitly name the versions. Record their decision, then run the frozen snapshots:

```bash
python3 "$SKILL_DIR/scripts/loi.py" shortlist set \
  --project <project_id> \
  --version <version_1> --version <version_2> \
  --note "<researcher decision>"
python3 "$SKILL_DIR/scripts/loi.py" arena run \
  --project <project_id> --rounds 3 --double-judge
```

The research Arena uses evidence strength, importance, novelty, methodological validity, feasibility, and falsifiability. Explain that Elo is still relative evidence, not a final topic decision.

Export the complete research artifact:

```bash
python3 "$SKILL_DIR/scripts/loi.py" project report \
  --project <project_id> --output <research-project.md>
```

## Run a legacy quick tournament

Preserve the user's goal verbatim unless they ask for rewriting. Use the current defaults when they do not specify tournament settings:

- 8 initial ideas
- 3 rounds
- Swiss pairing
- evolution enabled
- single-direction judging
- concurrency 1
- 60-second request timeout and 2 transient-error retries

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
- Add `--requests-per-second N` when a provider needs client-side pacing. Use `--timeout-seconds` and `--max-retries` for slow or unstable networks.
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
python3 "$SKILL_DIR/scripts/loi.py" analyze --session <session_id>
```

Resume a `failed` or `stopped` Session. Budget overrides are total lifetime limits, not additional allowances, so raise them above existing usage:

```bash
python3 "$SKILL_DIR/scripts/loi.py" resume \
  --session <session_id> \
  --max-calls <new_total_limit>
```

Do not restart from scratch when a resumable Session exists. Pairing plans, pending paid judgments, Elo order, and evolution plans are persisted for deterministic continuation.

## Export a tournament deliverable

Create a Markdown report after completion or when the user wants an audit of partial results:

```bash
python3 "$SKILL_DIR/scripts/loi.py" report \
  --session <session_id> \
  --output <report.md>
```

Return the report path plus a concise summary of the winner, runner-up, creator-model attribution, disputed matches, usage, and stop reason if incomplete.

Read [references/workflows.md](references/workflows.md) for ready-to-run task patterns and failure recovery.

## Guardrails

- Keep paper facts, AI gap hypotheses, and researcher decisions visibly separate.
- Reject or retry any analysis with source locators or quotes not present in the imported paper.
- Treat every Gap as a hypothesis requiring validation, never as proof of novelty.
- Never send an Idea to the research Arena without the user's explicit shortlist decision.
- Never overwrite an IdeaVersion; use critique followed by revise to create a child version.
- Do not claim the imported paper set is comprehensive or current unless separately verified.
- Run `estimate` before `run` unless the user already supplied a strict budget and exact configuration.
- Never silently remove a budget, lower a deduplication threshold, change a rubric, or switch models during resume.
- Do not claim `--seed` makes provider outputs deterministic; it fixes pairing and presentation order only.
- Do not interpret Elo as absolute truth. State that it is relative to the goal, rubric, judge model, and observed matches.
- Do not push Session JSON, `.env`, API keys, or generated reports unless the user explicitly requests publication.
- When a provider call fails, preserve the Session and prefer `resume` after fixing credentials, quota, or connectivity.
