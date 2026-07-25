#!/bin/bash
# tmux ステータスバー用 git-status（herdr-git-status.bash の薄いアダプタ）
# 使い方: tmux-git-status.bash <pane_current_path> <base_bg_color>

set -euo pipefail

readonly COLOR_CLEAN="#50FA7B"
readonly COLOR_CLEAN_TEXT="#1A5C2D"
readonly COLOR_STAGED="#E5A700"
readonly COLOR_STAGED_TEXT="#3D2800"
readonly COLOR_DIRTY="#FF5555"
readonly COLOR_DIRTY_TEXT="#FFFFFF"

dir="${1:-.}"
bg="${2:-#000000}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
core="${HERDR_GIT_STATUS:-$script_dir/herdr-git-status.bash}"

if [ ! -x "$core" ]; then
    # install 前の PATH 配置: ~/bin 同居を想定
    core="${HOME}/bin/herdr-git-status.bash"
fi
if [ ! -x "$core" ]; then
    exit 0
fi

line="$("$core" "$dir" || true)"
[ -n "$line" ] || exit 0

state="${line%%$'\t'*}"
label="${line#*$'\t'}"

case "$state" in
    clean)  color="$COLOR_CLEAN";  text_fg="$COLOR_CLEAN_TEXT" ;;
    staged) color="$COLOR_STAGED"; text_fg="$COLOR_STAGED_TEXT" ;;
    dirty)  color="$COLOR_DIRTY";  text_fg="$COLOR_DIRTY_TEXT" ;;
    *) exit 0 ;;
esac

# 旧実装と同じセグメント形状（pill は bg/fg の切り替え）
printf '#[bg=%s,fg=%s]#[bg=%s,fg=%s] %s #[bg=%s,fg=%s]\n' \
    "$bg" "$color" "$color" "$text_fg" "$label" "$bg" "$color"
