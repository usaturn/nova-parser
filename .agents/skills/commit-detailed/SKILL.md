---
name: commit-detailed
description: Commit already-staged files to the `main` branch with a detailed commit message. Use when the user asks to commit staged changes only, wants a rich or detailed commit message, asks for a Conventional Commits subject plus explanatory body, or says things like "commit the staged files", "commit only what is staged", "commit this on main", "write a detailed commit message", or "$commit-detailed". Do not use this skill for `git add`, branch switching, rebasing, amending old commits, or pushing.
---

# Commit Detailed

## Overview

Use this skill to commit exactly the files that are already staged, and only when the current branch is `main`. Write a detailed commit message with a Conventional Commits subject and a Japanese body that explains background, key changes, impact, and tests when known.

## Workflow

### 1. Verify Preconditions

Run these checks first and stop if any fail:

```bash
git rev-parse --abbrev-ref HEAD
git diff --staged --name-only
```

Required conditions:

- The current branch must be `main`.
- There must be at least one staged file.

If the branch is not `main`:

- Do not run `git switch`, `git checkout`, or any other branch-changing command.
- Tell the user the current branch name and ask them to switch to `main` or confirm a different plan.

If there are no staged files:

- Do not run `git add`.
- Tell the user there is nothing staged to commit.

### 2. Inspect Only the Staged Change Set

Read the staged state, not the whole working tree:

```bash
git status --short
git diff --staged --name-only
git diff --staged --stat
git diff --staged
git log --oneline -10
```

Interpretation rules:

- Base the commit message on the staged diff only.
- Ignore unstaged edits except to mention that they remain in the working tree if that matters for user clarity.
- Prefer the dominant change type when choosing the Conventional Commits prefix.

### 3. Reject Obvious Sensitive Files

If the staged list contains files that look like secrets or credentials, stop and ask the user before committing. Treat these as suspicious by default:

- `.env`
- `.env.*`
- `*.pem`
- `*.key`
- `*.pfx`
- `id_rsa*`
- filenames containing `secret`, `token`, or `credential`

### 4. Write the Commit Message

Use this structure:

```text
<type>: <short subject in Japanese>

背景:
- ...

変更点:
- ...

影響:
- ...

テスト:
- ...
```

Message rules:

- Use a Conventional Commits subject such as `feat`, `fix`, `docs`, `refactor`, `test`, `style`, or `chore`.
- Keep the subject concise and do not end it with a period.
- Write the body in Japanese unless the user explicitly asks for another language.
- Include `背景` and `変更点` whenever the staged diff is non-trivial.
- Include `影響` when behavior, workflow, or user-visible expectations changed.
- Include `テスト` only when there is concrete evidence. If no test was run, say so plainly instead of inventing one.
- Avoid filler. The body should explain why the change exists and what was actually staged.

### 5. Commit the Staged Files Only

Commit without staging anything new:

```bash
git commit -m "$(cat <<'EOF'
<final message>
EOF
)"
```

Do not add flags that widen scope or skip safety checks.

### 6. Report the Result

After a successful commit, run:

```bash
git log -1 --stat
git log -1 --name-status
```

Report back with:

- the short commit hash
- the exact commit message used
- the files included in the commit
- whether unstaged changes are still present afterward, if any

## Resources

This skill includes `evals/` only.

- `evals/evals.json`: seeded scenarios for success and refusal paths
- `evals/trigger_queries.json`: trigger coverage for staged-only and main-only commit requests

## Validation

- Ensure the frontmatter description stays aligned with staged-only, main-only commit behavior.
- Keep the seeded evals in sync if the commit message structure or refusal conditions change.

## Guardrails

- Do not run `git add`.
- Do not switch branches.
- Do not push.
- Do not use `--amend`.
- Do not use `--no-verify` unless the user explicitly instructs it.
- Do not include unstaged files in the commit.
