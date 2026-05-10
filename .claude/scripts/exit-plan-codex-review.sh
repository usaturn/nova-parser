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

FOCUS=$'Plan モード承認前のレビュー。以下のプランの妥当性 (前提・設計選択・失敗モード・代替案の検討漏れ) を adversarial に問うてください。\n\n'"$PLAN"

emit_decision() {
  local decision="$1"
  local reason="$2"
  local message="$3"

  jq -n --arg decision "$decision" --arg reason "$reason" --arg msg "$message" '{
    hookSpecificOutput: {
      hookEventName: "PreToolUse",
      permissionDecision: $decision,
      permissionDecisionReason: $reason
    },
    systemMessage: $msg
  }'
}

truncate_text() {
  local text="$1"
  local max_chars=12000

  if [ "${#text}" -gt "$max_chars" ]; then
    printf '... (truncated to last %s chars)\n%s' "$max_chars" "${text: -$max_chars}"
  else
    printf '%s' "$text"
  fi
}

worktree_hash() {
  local state

  if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    state=$(
      {
        git -C "$PROJECT_DIR" status --porcelain=v1
        git -C "$PROJECT_DIR" diff --cached --no-ext-diff
        git -C "$PROJECT_DIR" diff --no-ext-diff
      } 2>/dev/null || true
    )
  else
    state="not-a-git-worktree:$PROJECT_DIR"
  fi

  printf '%s' "$state" | sha256sum | cut -d' ' -f1
}

BYPASS_REASON=$(
  sed -n 's/^[[:space:]]*Codex-Review-Bypass:[[:space:]]*//p' <<<"$PLAN" \
    | sed 's/[[:space:]]*$//' \
    | sed -n '/[^[:space:]]/{p;q;}'
)
WORKTREE_HASH=$(worktree_hash)
MARKER="$MARKER_DIR/session-${SESSION_HASH}-plan-${PLAN_HASH}-worktree-${WORKTREE_HASH}"
mkdir -p "$MARKER_DIR"

if [ -f "$MARKER" ]; then
  emit_decision \
    "allow" \
    "Codex adversarial plan review was already approved for this plan and worktree state." \
    "Codex adversarial plan review は同じ plan と worktree 状態で既に approve 済みです。ExitPlanMode を続行します。"
  exit 0
fi

CODEX=$(ls -d "$HOME/.claude/plugins/cache/openai-codex/codex/"*/scripts/codex-companion.mjs 2>/dev/null \
  | sort -V | tail -1 || true)

write_marker() {
  {
    printf 'session_id=%s\n' "$SESSION_ID"
    printf 'project_dir=%s\n' "$PROJECT_DIR"
    printf 'plan_hash=%s\n' "$PLAN_HASH"
    printf 'worktree_hash=%s\n' "$WORKTREE_HASH"
    printf 'review_status=%s\n' "$REVIEW_STATUS"
    printf 'verdict=%s\n' "${VERDICT:-}"
  } >"$MARKER"
}

if [ -z "${CODEX:-}" ]; then
  REVIEW_STATUS=127
  VERDICT=""
  SYSTEM_MESSAGE="Codex adversarial plan review を実行できませんでした。codex-companion.mjs が見つからないため、Plan 妥当性レビューは未実施です。"

  if [ -n "$BYPASS_REASON" ]; then
    emit_decision \
      "allow" \
      "Codex review was bypassed by an explicit plan token." \
      "$SYSTEM_MESSAGE"$'\n\n'"Codex-Review-Bypass: $BYPASS_REASON"$'\n\n'"ExitPlanMode を続行します。"
  else
    emit_decision \
      "ask" \
      "Codex adversarial plan review could not run." \
      "$SYSTEM_MESSAGE"$'\n\n'"続行する場合はユーザ確認が必要です。意図的に bypass する場合は plan に Codex-Review-Bypass: <reason> を追加してください。"
  fi
  exit 0
fi

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
  emit_decision \
    "allow" \
    "Codex adversarial plan review approved this plan." \
    "Codex adversarial plan review は approve を返しました。ExitPlanMode を続行します。"
  exit 0
fi

if [ "$VERDICT" = "needs-attention" ]; then
  if ! REVIEW_MESSAGE=$(format_review); then
    REVIEW_MESSAGE=$'Codex adversarial plan review の JSON 整形に失敗しました。\n\n'"$(truncate_text "$REVIEW")"
  fi
  SYSTEM_MESSAGE=$'Codex adversarial plan review は needs-attention を返しました。これは Plan 妥当性レビューであり、実コードレビュー済みであることは意味しません。\n\n'"$REVIEW_MESSAGE"
else
  REVIEW_MESSAGE=$(truncate_text "$REVIEW")
  SYSTEM_MESSAGE=$'Codex adversarial plan review の実行または JSON 判定に失敗しました。Plan 妥当性レビューは未完了です。\n\n'"$REVIEW_MESSAGE"
fi

if [ -n "$BYPASS_REASON" ]; then
  emit_decision \
    "allow" \
    "Codex review was bypassed by an explicit plan token." \
    "$SYSTEM_MESSAGE"$'\n\n'"Codex-Review-Bypass: $BYPASS_REASON"$'\n\n'"ExitPlanMode を続行します。"
else
  emit_decision \
    "ask" \
    "Codex adversarial plan review did not approve this plan." \
    "$SYSTEM_MESSAGE"$'\n\n'"続行する場合はユーザ確認が必要です。意図的に bypass する場合は plan に Codex-Review-Bypass: <reason> を追加してください。"
fi
