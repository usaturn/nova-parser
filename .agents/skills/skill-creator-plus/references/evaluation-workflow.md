# Evaluation Workflow

This reference defines the expected workspace layout and the minimum repeatable benchmark loop.

## Workspace Layout

Use a sibling workspace next to the skill under test:

```text
<skill-name>-workspace/
  iteration-1/
    <eval-slug>/
      eval_metadata.json
      with_skill/
        outputs/
          transcript.md
          metrics.json
      baseline/
        outputs/
          transcript.md
          metrics.json
```

When improving an existing skill, rename the baseline directory to `old_skill/` if that makes the distinction clearer. The aggregation script groups `baseline`, `without_skill`, and `old_skill` together.

## Required Artifacts per Run

- `outputs/`: the actual output files
- `outputs/transcript.md`: what happened during execution
- `outputs/metrics.json`: tool and file statistics
- `timing.json`: timing and token usage
- `grading.json`: grader output

## Recommended Loop

1. Snapshot the baseline skill if this is an edit, not a greenfield skill.
2. Create or update `evals/evals.json`.
3. For each eval, run `with_skill` and baseline variants.
4. Write `eval_metadata.json` before grading so every run has a stable prompt record.
5. Grade both runs.
6. Aggregate:

```bash
scripts/aggregate_benchmark.py <workspace>/iteration-1 --skill-name "<skill-name>"
```

7. Generate a review artifact:

```bash
scripts/generate_review.py <workspace>/iteration-1 --benchmark <workspace>/iteration-1/benchmark.json --static <workspace>/iteration-1/review.html
```

8. Record qualitative feedback in `feedback.json` and carry the findings into the next iteration.

## Reading the Results

- `benchmark.md` is the fast human summary.
- `benchmark.json` is the structured source of truth.
- `review.html` is for side-by-side artifact inspection and notes.

## Trigger Optimization Loop

1. Run `scripts/run_trigger_eval.py <skill-dir>`.
2. Inspect false positives and false negatives.
3. Run `scripts/optimize_description.py <skill-dir> --apply` only after reviewing the suggested description.
4. Re-run the trigger eval and verify that the broader wording still matches real scope.
