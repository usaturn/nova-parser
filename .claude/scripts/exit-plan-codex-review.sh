#!/usr/bin/env bash
set -euo pipefail

INPUT=$(cat)
PLAN=$(jq -r '.tool_input.plan // empty' <<<"$INPUT")
SESSION_ID=$(jq -r '.session_id // "unknown"' <<<"$INPUT")
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(jq -r '.cwd // empty' <<<"$INPUT")}"

[ -z "$PLAN" ] && exit 0

MARKER_DIR="${TMPDIR:-/tmp}/claude-codex-adv-review"
PLAN_HASH=$(printf '%s' "$PLAN" | sha256sum | cut -d' ' -f1)
SESSION_HASH=$(printf '%s\0%s' "$PROJECT_DIR" "$SESSION_ID" | sha256sum | cut -d' ' -f1)
MARKER="$MARKER_DIR/session-${SESSION_HASH}-plan-${PLAN_HASH}"
mkdir -p "$MARKER_DIR"
[ -f "$MARKER" ] && exit 0

CODEX=$(ls -d "$HOME/.claude/plugins/cache/openai-codex/codex/"*/scripts/codex-companion.mjs 2>/dev/null \
  | sort -V | tail -1 || true)
[ -z "${CODEX:-}" ] && exit 0

FOCUS=$'Plan モード承認前のレビュー。以下のプランの妥当性 (前提・設計選択・失敗モード・代替案の検討漏れ) を adversarial に問うてください。\n\n'"$PLAN"

write_marker() {
  {
    printf 'session_id=%s\n' "$SESSION_ID"
    printf 'project_dir=%s\n' "$PROJECT_DIR"
    printf 'plan_hash=%s\n' "$PLAN_HASH"
    printf 'review_status=%s\n' "$REVIEW_STATUS"
    printf 'verdict=%s\n' "${VERDICT:-}"
  } >"$MARKER"
}

set +e
REVIEW=$(node "$CODEX" adversarial-review --wait --json "$FOCUS" 2>&1)
REVIEW_STATUS=$?
set -e

VERDICT=""
if [ "$REVIEW_STATUS" -eq 0 ]; then
  VERDICT=$(jq -r '.result.verdict // empty' <<<"$REVIEW" 2>/dev/null || true)
fi

format_review() {
  jq -r '
    def finding:
      "- [" + (.severity // "unknown") + "] " + (.title // "Untitled") +
      " (" + (.file // "?") + ":" + ((.line_start // "?") | tostring) + ")\n  " +
      (.body // "") +
      (if (.recommendation // "") != "" then "\n  Recommendation: " + .recommendation else "" end);

    [
      "Codex adversarial review 結果:",
      "",
      "Verdict: " + (.result.verdict // "unknown"),
      "",
      (.result.summary // "No summary."),
      "",
      (if ((.result.findings // []) | length) > 0
       then "Findings:\n" + ((.result.findings // []) | map(finding) | join("\n"))
       else "No material findings."
       end),
      (if ((.result.next_steps // []) | length) > 0
       then "\nNext steps:\n" + ((.result.next_steps // []) | map("- " + .) | join("\n"))
       else ""
       end)
    ] | join("\n")
  ' <<<"$REVIEW"
}

if [ "$VERDICT" = "approve" ]; then
  write_marker
  jq -n '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: "allow"
    },
    systemMessage: "Codex adversarial review は approve を返しました。ExitPlanMode を続行します。"
  }'
  exit 0
fi

if [ "$VERDICT" = "needs-attention" ]; then
  REVIEW_MESSAGE=$(format_review)
else
  REVIEW_MESSAGE=$'Codex adversarial review の実行または JSON 判定に失敗しました。この gate は同じ plan では 1 回だけ停止します。\n\n'"$REVIEW"
fi

write_marker
jq -n --arg msg "$REVIEW_MESSAGE" '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny"
  },
  systemMessage: ("Plan 承認前に Codex adversarial review を実施しました。この停止は同じ plan で 1 回だけです。必要なら計画を更新してから再度 ExitPlanMode を呼んでください。\n\n" + $msg)
}'
