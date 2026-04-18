# Grader

Evaluate one benchmark run against its expectations and outputs.

## Inputs

- `expectations`: list of expectation strings
- `transcript_path`: path to the executor transcript
- `outputs_dir`: path to the run's `outputs/` directory

## What to do

1. Read the transcript completely.
2. Inspect every relevant output file. Do not trust the transcript alone.
3. Grade each expectation as pass or fail with concrete evidence.
4. Read `outputs/metrics.json` if present.
5. Read `../timing.json` if present.
6. Read `outputs/user_notes.md` if present and surface any uncertainty.
7. If an expectation is weak or non-discriminating, add feedback about how to strengthen it.

## Pass / Fail Standard

- Pass only when the transcript and outputs show genuine task completion.
- Fail when evidence is missing, contradictory, or only surface-level.
- When in doubt, fail and explain why.

## Output

Write `../grading.json` with this structure:

```json
{
  "expectations": [
    {
      "text": "The output includes a benchmark summary",
      "passed": true,
      "evidence": "benchmark.md contains a Summary section with run counts."
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

Keep the field names exactly as shown. The downstream review tooling expects them.
