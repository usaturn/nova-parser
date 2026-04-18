# Analyzer

Use this prompt in two different situations.

## Mode 1: Benchmark analysis

### Inputs

- `benchmark_data_path`
- `skill_path`
- `output_path`

### Goal

Read `benchmark.json` and produce short, high-signal notes about patterns that summary statistics hide.

### Look for

- Expectations that always pass in every configuration
- Expectations that always fail in every configuration
- `with_skill` improvements that are real but narrow
- regressions where the skill is slower or more expensive with no pass-rate gain
- flaky evals with high variance across similar runs

### Output

Write `output_path` as a JSON array of short notes.

## Mode 2: Post-hoc comparison analysis

### Inputs

- `winner`
- `winner_skill_path`
- `winner_transcript_path`
- `loser_skill_path`
- `loser_transcript_path`
- `comparison_result_path`
- `output_path`

### Goal

After a blind comparison has picked a winner, explain what actually caused that outcome and what the losing skill should change.

### Output

Write `output_path` as JSON with:

- `comparison_summary`
- `winner_strengths`
- `loser_weaknesses`
- `instruction_following`
- `improvement_suggestions`
- `transcript_insights`

Be concrete. Quote specific instructions, behaviors, or output differences instead of giving generic advice.
