# Blind Comparator

Compare two outputs without assuming which skill produced them.

## Inputs

- `output_a_path`
- `output_b_path`
- `eval_prompt`
- `expectations` (optional)
- `output_path`

## Process

1. Read both outputs in full.
2. Read the eval prompt and infer the quality criteria that matter.
3. Create a compact rubric for content quality and structure quality.
4. Score output A and B independently.
5. Use expectations as secondary evidence, not as the only decision criterion.
6. Pick `A`, `B`, or `TIE`. Ties should be rare.

## Output

Write JSON with:

- `winner`
- `reasoning`
- `rubric`
- `output_quality`
- `expectation_results` when expectations were supplied

Choose the output that better completes the task, not the output that merely looks more polished.
