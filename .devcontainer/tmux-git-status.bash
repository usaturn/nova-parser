#!/bin/bash
# tmux ステータスバー用 git-status スクリプト
# zshrc.txt の git-prompt 関数と同等のロジックをピル型デザインで実装
#
# 使い方: tmux-git-status.bash <pane_current_path> <base_bg_color>

readonly DETACHED_PREFIX="detached@"
readonly NAME_REV_UNDEFINED="undefined"
readonly PUSH_INDICATOR_AHEAD=" ↑"
readonly PUSH_INDICATOR_MISSING_UPSTREAM=" !"

readonly GIT_STATE_CLEAN="clean"
readonly GIT_STATE_STAGED="staged"
readonly GIT_STATE_DIRTY="dirty"

readonly COLOR_CLEAN="#50FA7B"
readonly COLOR_CLEAN_TEXT="#1A5C2D"
readonly COLOR_STAGED="#E5A700"
readonly COLOR_STAGED_TEXT="#3D2800"
readonly COLOR_DIRTY="#FF5555"
readonly COLOR_DIRTY_TEXT="#FFFFFF"

dir="${1:-.}"
bg="${2:-#000000}"

resolve_named_ref() {
    local refs_glob="$1"
    local prefix="$2"
    local ref_name

    ref_name=$(git name-rev --name-only --exclude='refs/tags/*' --refs="$refs_glob" HEAD 2>/dev/null) || return 1

    if [ -z "$ref_name" ] || [ "$ref_name" = "$NAME_REV_UNDEFINED" ]; then
        return 1
    fi

    printf '%s\n' "${ref_name#"$prefix"}"
}

resolve_branch_name() {
    local branch_name
    local short_hash

    branch_name=$(git symbolic-ref --short HEAD 2>/dev/null)
    if [ -n "$branch_name" ]; then
        printf '%s\n' "$branch_name"
        return 0
    fi

    branch_name=$(resolve_named_ref 'refs/remotes/*' 'remotes/')
    if [ -n "$branch_name" ]; then
        printf '%s\n' "$branch_name"
        return 0
    fi

    branch_name=$(resolve_named_ref 'refs/heads/*' 'heads/')
    if [ -n "$branch_name" ]; then
        printf '%s\n' "$branch_name"
        return 0
    fi

    short_hash=$(git rev-parse --short HEAD 2>/dev/null) || return 1
    printf '%s%s\n' "$DETACHED_PREFIX" "$short_hash"
}

classify_git_state() {
    local porcelain_status
    local line
    local index_status
    local worktree_status
    local has_staged=0
    local has_dirty=0

    porcelain_status=$(git status --porcelain=v1 --untracked-files=all 2>/dev/null) || return 1

    if [ -z "$porcelain_status" ]; then
        printf '%s\n' "$GIT_STATE_CLEAN"
        return 0
    fi

    while IFS= read -r line; do
        index_status=${line:0:1}
        worktree_status=${line:1:1}

        if [ "$index_status" = "?" ] && [ "$worktree_status" = "?" ]; then
            has_dirty=1
            continue
        fi

        if [ "$index_status" != " " ]; then
            has_staged=1
        fi

        if [ "$worktree_status" != " " ]; then
            has_dirty=1
        fi
    done <<< "$porcelain_status"

    if [ "$has_dirty" -eq 1 ]; then
        printf '%s\n' "$GIT_STATE_DIRTY"
        return 0
    fi

    if [ "$has_staged" -eq 1 ]; then
        printf '%s\n' "$GIT_STATE_STAGED"
        return 0
    fi

    printf '%s\n' "$GIT_STATE_DIRTY"
}

resolve_state_colors() {
    local git_state="$1"

    case "$git_state" in
        "$GIT_STATE_CLEAN")
            printf '%s %s\n' "$COLOR_CLEAN" "$COLOR_CLEAN_TEXT"
            ;;
        "$GIT_STATE_STAGED")
            printf '%s %s\n' "$COLOR_STAGED" "$COLOR_STAGED_TEXT"
            ;;
        "$GIT_STATE_DIRTY")
            printf '%s %s\n' "$COLOR_DIRTY" "$COLOR_DIRTY_TEXT"
            ;;
        *)
            return 1
            ;;
    esac
}

resolve_push_indicator() {
    local head_ref
    local upstream_ref

    head_ref=$(git symbolic-ref -q HEAD 2>/dev/null) || return 0
    upstream_ref=$(git for-each-ref --format='%(upstream:short)' "$head_ref" 2>/dev/null)

    if [ -z "$upstream_ref" ]; then
        return 0
    fi

    if ! git show-ref --verify --quiet "refs/remotes/${upstream_ref}"; then
        printf '%s\n' "$PUSH_INDICATOR_MISSING_UPSTREAM"
        return 0
    fi

    if [ -n "$(git rev-list --max-count=1 "${upstream_ref}..HEAD" 2>/dev/null)" ]; then
        printf '%s\n' "$PUSH_INDICATOR_AHEAD"
    fi
}

render_segment() {
    local base_bg="$1"
    local pill_bg="$2"
    local pill_fg="$3"
    local label="$4"

    printf '#[bg=%s,fg=%s]#[bg=%s,fg=%s] %s #[bg=%s,fg=%s]\n' \
        "$base_bg" "$pill_bg" "$pill_bg" "$pill_fg" "$label" "$base_bg" "$pill_bg"
}

cd "$dir" 2>/dev/null || exit 0

# git リポジトリでなければ何も出力しない
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

branch_name=$(resolve_branch_name) || exit 0
git_state=$(classify_git_state) || exit 0
read -r color text_fg <<< "$(resolve_state_colors "$git_state")" || exit 0
push_indicator=$(resolve_push_indicator)

render_segment "$bg" "$color" "$text_fg" "${branch_name}${push_indicator}"
