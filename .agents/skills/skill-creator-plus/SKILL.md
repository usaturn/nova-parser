---
name: skill-creator-plus
description: Create, benchmark, and improve Codex skills. Use whenever the user wants to create a new skill, update an existing skill, scaffold a skill directory, add evals or seeded test prompts, benchmark with-skill versus baseline behavior, compare revisions, optimize a skill description for better triggering, or package a skill for reuse. Prefer this skill over the simpler skill-creator for general skill-authoring work, even when the user only says "make a skill" or "improve this skill".
---

# Skill Creator Plus

## Overview

Use this skill as the default path for Codex skill authoring when the work goes beyond a one-file scaffold. It covers skill creation, skill revision, seeded eval authoring, benchmark aggregation, review artifact generation, trigger-query evaluation, and description optimization.

## Core Responsibilities

1. Turn a loose user request into a reusable Codex skill bundle.
2. Keep the resulting skill Codex-native: `SKILL.md`, `agents/openai.yaml`, optional `scripts/`, `references/`, `assets/`, and optional `evals/`.
3. Add evaluation structure early enough that the skill can be benchmarked, not just "look reasonable."
4. Compare `with_skill` runs against a baseline (`without_skill` for a new skill, or `old_skill` for an existing skill).
5. Improve weak trigger descriptions with repeatable trigger-query reports.

## Choose the Path

### New skill from scratch

Use this path when the user wants a fresh skill or when an existing workflow should be turned into a skill. Capture concrete examples first, then initialize the bundle with `scripts/init_skill.py`.

### Improve an existing skill

Use this path when the user already has a skill directory, draft `SKILL.md`, or a skill that behaves inconsistently. Snapshot the original skill before substantial edits so the baseline remains reproducible.

### Optimize triggering

Use this path when the skill exists but is under-triggering or over-triggering. Use `evals/trigger_queries.json`, `scripts/run_trigger_eval.py`, and `scripts/optimize_description.py`.

## Workflow

### 1. Capture Intent with Concrete Examples

- Ask for or infer realistic user prompts, expected outputs, important failure modes, and any required files.
- Prefer 2-4 examples over abstract statements like "it should be smart."
- If a relevant workflow already exists in the conversation, extract its steps instead of re-interviewing from scratch.

### 2. Decide the Bundle Shape

- Add `scripts/` when reliability or repetition matters.
- Add `references/` when detailed knowledge should be loaded on demand.
- Add `assets/` when the skill needs templates, boilerplate, or reusable sample inputs.
- Add `evals/` when the skill benefits from repeatable acceptance checks.

### 3. Initialize or Snapshot the Skill

For a new skill, use the initializer instead of hand-creating the directory:

```bash
scripts/init_skill.py my-skill --path "${CODEX_HOME:-$HOME/.codex}/skills" --resources scripts,references,assets --evals
```

If the user did not specify a location:

- Default to repo-local skill directories when the request is clearly project-scoped.
- Otherwise default to `$CODEX_HOME/skills`.
- If `CODEX_HOME` is unset, use `~/.codex/skills`.

For an existing skill:

- Copy it to a workspace snapshot before editing.
- Treat the snapshot as the immutable baseline for `old_skill` comparisons.

### 4. Implement the Skill

- Write a broad, concrete frontmatter `description` that explains both what the skill does and when Codex should use it.
- Keep the body procedural. Put trigger guidance in the frontmatter, not in a "When to use" body section.
- Keep `SKILL.md` concise. Push schemas, layout conventions, and deeper guidance into references.
- Update or regenerate `agents/openai.yaml` with `scripts/generate_openai_yaml.py` when the UI metadata is stale.

### 5. Validate Before Benchmarking

Run:

```bash
scripts/quick_validate.py <path/to/skill>
```

Validation should pass before you seed or rerun benchmarks.

### 6. Author Evals Early

- Keep functional evals in `evals/evals.json`.
- Keep triggering checks in `evals/trigger_queries.json`.
- Use explicit expectations when the result is objectively checkable.
- Prefer a few discriminating expectations over many weak ones.

The exact JSON shapes live in [references/schemas.md](references/schemas.md).

### 7. Run the Benchmark Loop

Use the workspace layout from [references/evaluation-workflow.md](references/evaluation-workflow.md). The minimum iteration structure is:

```text
<skill-name>-workspace/
  iteration-1/
    <eval-slug>/
      eval_metadata.json
      with_skill/
        outputs/
      baseline/
        outputs/
```

If subagents are available:

- Spawn `with_skill` and baseline runs in the same turn.
- Record `timing.json` as each run finishes.
- Grade each run using the expectations and the grader instructions in `agents/grader.md`.

If subagents are not available:

- Run the same prompts sequentially.
- Keep the same directory shape and artifact names.
- Be explicit that the comparison is lower confidence because the same agent is both author and evaluator.

After runs are complete:

```bash
scripts/aggregate_benchmark.py <workspace>/iteration-1 --skill-name "<skill-name>"
scripts/generate_review.py <workspace>/iteration-1 --benchmark <workspace>/iteration-1/benchmark.json --static <workspace>/iteration-1/review.html
```

Use the blind comparator and analyzer prompts when you want an additional qualitative pass across candidate outputs.

### 8. Optimize Triggering

Run:

```bash
scripts/run_trigger_eval.py <path/to/skill>
scripts/optimize_description.py <path/to/skill> --apply
```

Treat the description optimizer as a proposal engine, not a substitute for judgment. After applying a new description, rerun the trigger eval and confirm the wording still matches the actual scope of the skill.

## Script Reference

- `scripts/init_skill.py`: Create a new Codex skill bundle with optional eval templates.
- `scripts/generate_openai_yaml.py`: Generate `agents/openai.yaml` with implicit invocation policy.
- `scripts/quick_validate.py`: Validate `SKILL.md`, `agents/openai.yaml`, and optional eval files.
- `scripts/package_skill.py`: Build a distributable `.skill` archive while excluding caches and workspaces.
- `scripts/aggregate_benchmark.py`: Convert workspace artifacts into `benchmark.json` and `benchmark.md`.
- `scripts/generate_review.py`: Build a self-contained review page for outputs and benchmark data.
- `scripts/run_trigger_eval.py`: Score the current description against trigger queries.
- `scripts/optimize_description.py`: Suggest or apply a stronger description based on missed trigger terms.

## Seeded Starting Points

- `evals/evals.json` includes three self-test scenarios for this skill.
- `evals/trigger_queries.json` includes broad trigger coverage for this skill's own description.
- `assets/fixtures/incident-summary-helper/` contains a deliberately weak sample skill for improvement and trigger-optimization exercises.

## Guardrails

- Do not create README-style auxiliary docs unless the user explicitly asks for them.
- Do not package benchmark workspaces inside the final `.skill` archive.
- Do not claim benchmark evidence unless the workspace artifacts actually exist.
- Do not broaden the description beyond the workflows the skill genuinely supports.
