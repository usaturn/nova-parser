# `agents/openai.yaml` Reference

`agents/openai.yaml` is product-facing metadata for Codex skill discovery and UI.

## Example

```yaml
interface:
  display_name: "Skill Creator Plus"
  short_description: "Build, benchmark, and improve Codex skills"
  default_prompt: "Use $skill-creator-plus to create or improve a Codex skill with evals and benchmarks."
policy:
  allow_implicit_invocation: true
```

## Required practical fields

- `interface.display_name`: user-facing title
- `interface.short_description`: 25-64 character summary
- `interface.default_prompt`: short example that explicitly references `$skill-name`

## Policy

- `policy.allow_implicit_invocation: true` means Codex may pull the skill into context automatically.
- Set it to `false` only when the skill should be explicit-only.

## Notes

- Quote string values.
- Keep the file small and deterministic.
- Regenerate it with `scripts/generate_openai_yaml.py` whenever UI metadata falls out of sync with the skill intent.
