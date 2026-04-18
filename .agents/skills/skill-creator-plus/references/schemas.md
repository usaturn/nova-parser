# JSON Schemas

These are the working JSON shapes used by `skill-creator-plus`.

## `evals/evals.json`

Repeatable functional evals for a skill.

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "name": "create-summary",
      "prompt": "Draft an internal summary for the outage.",
      "expected_output": "A structured summary with impact, timeline, and next steps.",
      "files": [],
      "expectations": [
        "The output contains impact, timeline, and next steps headings."
      ]
    }
  ]
}
```

## `evals/trigger_queries.json`

Queries used to measure whether a description should trigger.

```json
{
  "skill_name": "example-skill",
  "queries": [
    {
      "id": "q1",
      "query": "Write a customer-safe incident update",
      "should_trigger": true,
      "expected_terms": ["incident", "update", "customer"],
      "notes": "High-priority positive trigger"
    },
    {
      "id": "q2",
      "query": "Build a marketing dashboard",
      "should_trigger": false,
      "expected_terms": [],
      "notes": ""
    }
  ]
}
```

## `eval_metadata.json`

Metadata stored next to a benchmark run.

```json
{
  "eval_id": 1,
  "eval_name": "create-summary",
  "prompt": "Draft an internal summary for the outage.",
  "assertions": [
    "The output contains impact, timeline, and next steps headings."
  ]
}
```

## `outputs/metrics.json`

Executor-side counts and artifact summaries.

```json
{
  "tool_calls": {
    "Read": 5,
    "Write": 2,
    "Bash": 4
  },
  "total_tool_calls": 11,
  "total_steps": 6,
  "files_created": ["summary.md"],
  "errors_encountered": 0,
  "output_chars": 2048,
  "transcript_chars": 1800
}
```

## `timing.json`

Timing and token data captured for one run.

```json
{
  "total_tokens": 18452,
  "duration_ms": 14320,
  "total_duration_seconds": 14.32,
  "executor_duration_seconds": 12.1,
  "grader_duration_seconds": 2.22
}
```

## `grading.json`

Output from the grader prompt.

```json
{
  "expectations": [
    {
      "text": "The output contains impact, timeline, and next steps headings.",
      "passed": true,
      "evidence": "summary.md contains all three headings."
    }
  ],
  "summary": {
    "passed": 1,
    "failed": 0,
    "total": 1,
    "pass_rate": 1.0
  },
  "execution_metrics": {},
  "timing": {},
  "claims": [],
  "user_notes_summary": {
    "uncertainties": [],
    "needs_review": [],
    "workarounds": []
  },
  "eval_feedback": {
    "suggestions": [],
    "overall": "No critical gaps found."
  }
}
```

## `benchmark.json`

Aggregate benchmark output across all runs in one iteration.

```json
{
  "skill_name": "example-skill",
  "workspace_root": "/tmp/example-skill-workspace/iteration-1",
  "generated_at": "2026-04-18T15:00:00+00:00",
  "runs": [],
  "run_summary": {
    "with_skill": {
      "count": 2,
      "pass_rate": {"mean": 1.0, "stddev": 0.0},
      "duration_seconds": {"mean": 14.5, "stddev": 0.3},
      "total_tokens": {"mean": 18000, "stddev": 120}
    }
  },
  "delta": {
    "pass_rate_mean": 0.25,
    "duration_seconds_mean": 1.1,
    "total_tokens_mean": 800
  }
}
```

## `history.json`

Optional iteration history for improvement loops.

```json
{
  "started_at": "2026-04-18T15:00:00+00:00",
  "skill_name": "example-skill",
  "current_best": "v2",
  "iterations": [
    {
      "version": "v1",
      "parent": "v0",
      "expectation_pass_rate": 0.75,
      "grading_result": "won",
      "is_current_best": false
    }
  ]
}
```

## `feedback.json`

Freeform qualitative notes exported from `generate_review.py`.

```json
{
  "iteration-1-eval-create-summary-with_skill": "Clear structure, but too much customer detail."
}
```
