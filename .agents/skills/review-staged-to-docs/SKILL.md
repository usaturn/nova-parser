---
name: review-staged-to-docs
description: Use when the user asks Codex to review staged or commit-ready git changes, perform a /review-style code review, or create a Japanese Markdown review document under docs_draft/ from staged diffs. Do not use for unstaged-only or untracked-only review requests unless the user stages those changes or explicitly changes the scope.
---

# Review Staged To Docs

## Overview

Review only the staged git diff, then write a new Japanese Markdown review document under `docs_draft/`. Treat this as a code review: prioritize bugs, regressions, safety issues, and missing tests over summaries.

## Workflow

1. Verify staged scope:
   ```bash
   git diff --staged --name-only
   git diff --staged --stat
   git diff --staged --check
   git diff --name-only
   git ls-files --others --exclude-standard
   ```
2. If `git diff --staged --name-only` is empty, do not create a review document. Report that there are no staged changes to review.
3. Review the staged state, not the working tree state:
   - Use `git diff --staged` as the primary source.
   - Use `git show :path/to/file` for staged file content when full context is needed.
   - Avoid relying on plain file reads for files that also have unstaged edits, because they may include changes outside the review scope.
4. Write a new file under `docs_draft/` named `staged-review-YYYYMMDD-HHMMSS.md`. If the name already exists, append a short numeric suffix; never overwrite an existing document.
5. Write the review in Japanese with this structure:
   ```markdown
   # Staged 差分レビュー結果

   - ステータス: Draft
   - 作成日: YYYY-MM-DD
   - 対象: staged git diff

   ## 対象差分

   - ...

   ## 対象外

   - unstaged / untracked があれば記録する

   ## 指摘一覧

   ### 1. `[P1]` 見出し

   対象:

   - [file.ext](/absolute/path/file.ext:123)

   問題:

   影響:

   修正方針:

   ## テスト観点

   ## まとめ
   ```
6. List findings first, ordered by severity:
   - `[P0]`: data loss, security exposure, or complete production outage
   - `[P1]`: user-visible breakage, serious regression, or high-risk correctness issue
   - `[P2]`: moderate bug, missing important test coverage, or maintainability issue likely to matter soon
   - `[P3]`: minor concern worth fixing but not blocking
7. For each finding, include a staged-diff-grounded file and line reference, the concrete failure mode, user or system impact, and a specific repair direction. Do not include low-confidence or purely stylistic notes as findings.
8. If no material issues are found, still create the document for non-empty staged diffs. Put `重大な指摘なし` in `## 指摘一覧`, then document residual risks or test gaps in `## テスト観点`.

## Resources

This skill intentionally has no bundled scripts or references. Use git commands and the staged index as the source of truth.

## Validation

- After editing the skill, run:
  ```bash
  uv run python .agents/skills/skill-creator-plus/scripts/quick_validate.py .agents/skills/review-staged-to-docs
  ```
