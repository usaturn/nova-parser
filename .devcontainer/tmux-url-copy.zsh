#!/usr/bin/env zsh
# tmux-url-copy.zsh
# tmux ペインから URL を抽出し fzf で選択してコピーする
# Usage: bind u run-shell -b 'tmux display-popup -w 80% -h 60% -E "~/bin/tmux-url-copy.zsh #{pane_id}"'

target_pane="$1"

if [ -z "$target_pane" ]; then
  echo "Error: pane_id not specified"
  read
  exit 1
fi

urls=$(tmux capture-pane -J -p -S -500 -t "$target_pane" \
  | grep -oP 'https?://[^\s>"'\'')\]}]+' \
  | sed 's/[.,;:!?]*$//' \
  | awk '!seen[$0]++')

if [ -z "$urls" ]; then
  tmux display-message "URL が見つかりません"
  exit 0
fi

selected=$(echo "$urls" | fzf --no-sort --prompt="URL> " --reverse)

if [ -z "$selected" ]; then
  exit 0
fi

# tmux バッファに格納（prefix + ] で貼り付け可能）
printf '%s' "$selected" | tmux load-buffer -

# OSC 52 でホストのシステムクリップボードにコピー
client_tty=$(tmux display-message -p '#{client_tty}')
if [ -n "$client_tty" ] && [ -w "$client_tty" ]; then
  encoded=$(printf '%s' "$selected" | base64 | tr -d '\n')
  printf "\033]52;c;%s\a" "$encoded" > "$client_tty"
fi

tmux display-message "Copied: $selected"
