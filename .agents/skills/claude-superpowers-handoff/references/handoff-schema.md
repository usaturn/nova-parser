# Claude Superpowers Handoff Schema

`uv run nova-parser-claude-handoff --latest` writes paired files under
`docs_draft/claude_handoffs/`:

- `<timestamp>-<session>.handoff.md`
- `<timestamp>-<session>.handoff.json`

## Markdown Sections

- `Session`: Claude session id, agent/title, last prompt, permission mode, source JSONL.
- `Detected Skills`: `attributionSkill` values observed in assistant records.
- `Task State`: latest Claude `task_reminder` table.
- `Completion Report`: report-like assistant messages, usually Gate or Phase summaries.
- `Next Recommended Work`: pending tasks or a line containing `次は`.
- `Source Files`: Claude plan files observed in file-history snapshots.
- `Git`: branch, short HEAD, and status when the handoff was generated.

## JSON Fields

- `schema_version`: currently `1`.
- `generated_at`: UTC timestamp.
- `project_dir`: repo path used for discovery.
- `session`: `id`, `path`, `ai_title`, `agent_name`, `permission_mode`, `last_prompt`.
- `skills`: detected Claude skill names.
- `tasks`: latest task reminder records with `id`, `subject`, `description`, `status`.
- `reports`: redacted report snippets with `timestamp`, `skill`, `text`.
- `next_work`: pending task subjects or derived next-step lines.
- `sources`: `session_jsonl`, `plan_files`.
- `git`: `branch`, `head`, `status`.

## Safety

The generator redacts assignment-like secret names containing `SECRET`, `TOKEN`,
`CREDENTIAL`, `PASSWORD`, or `API_KEY`. The handoff should still be reviewed before
sharing outside the local development environment.
