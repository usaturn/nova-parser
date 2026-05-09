#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
PLAN=$(jq -r '.tool_input.plan // empty' <<<"$INPUT")
SESSION_ID=$(jq -r '.session_id // "unknown"' <<<"$INPUT")

[ -z "$PLAN" ] && exit 0

MARKER_DIR="${TMPDIR:-/tmp}/claude-codex-adv-review"
PLAN_HASH=$(printf '%s' "$PLAN" | sha256sum | cut -d' ' -f1)
MARKER="$MARKER_DIR/${SESSION_ID}-${PLAN_HASH}"
mkdir -p "$MARKER_DIR"
[ -f "$MARKER" ] && exit 0

CODEX=$(ls -d "$HOME/.claude/plugins/cache/openai-codex/codex/"*/scripts/codex-companion.mjs 2>/dev/null \
  | sort -V | tail -1 || true)
[ -z "${CODEX:-}" ] && exit 0

FOCUS=$'Plan モード承認前のレビュー。以下のプランの妥当性 (前提・設計選択・失敗モード・代替案の検討漏れ) を adversarial に問うてください。\n\n'"$PLAN"
REVIEW=$(node "$CODEX" adversarial-review --wait "$FOCUS" 2>&1 || true)

touch "$MARKER"

jq -n --arg r "$REVIEW" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "Plan 承認前に Codex adversarial review を実施しました。下記レビューを確認し、必要なら計画を更新してから再度 ExitPlanMode を呼んでください。",
    additionalContext: ("Codex adversarial review 結果:\n\n" + $r)
  }
}'
