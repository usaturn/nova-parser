---
name: claude-superpowers-handoff
description: Use when the user asks Codex to continue, inspect, resume, or take over work that was progressed in Claude Code using Superpowers, python-tdd-team, brainstorming, writing-plans, or other Claude Code skills. Reads or generates repo-local Claude handoff artifacts under docs_draft/claude_handoffs and summarizes current phase, completed work, pending tasks, reviewer findings, and next actions before implementation.
---

# Claude Superpowers Handoff

## Overview

Bridge Claude Code Superpowers work into Codex. Use the repo-local handoff CLI to generate a stable Markdown/JSON artifact from Claude Code JSONL logs, then read the latest handoff before continuing.

## Workflow

1. Check for existing handoffs:
   ```bash
   ls -t docs_draft/claude_handoffs/*.handoff.md 2>/dev/null | head
   ```
2. If no suitable handoff exists, generate one:
   ```bash
   uv run nova-parser-claude-handoff --latest
   ```
   Use `--session-id <uuid-or-jsonl-stem>` if the user names a specific Claude session.
3. Read the newest `.handoff.md` and, when precise fields matter, the paired `.handoff.json`.
4. Report the handoff state before acting:
   - Claude session / agent name
   - detected Superpowers or Claude skill
   - current phase or gate
   - completed and pending tasks
   - verification evidence
   - reviewer findings and next recommended work
5. Continue only from the handoff state. Do not infer completed work from memory when the handoff contradicts it.

## Resources

- `references/handoff-schema.md`: Markdown/JSON fields emitted by `nova-parser-claude-handoff`.
- `evals/evals.json`: seeded behavior checks for reading/generated handoffs.
- `evals/trigger_queries.json`: trigger coverage for Claude/Superpowers takeover prompts.

## Validation

- Run `.agents/skills/skill-creator-plus/scripts/quick_validate.py .agents/skills/claude-superpowers-handoff`.
- For CLI behavior, run `uv run pytest tests/test_claude_handoff.py -q`.
