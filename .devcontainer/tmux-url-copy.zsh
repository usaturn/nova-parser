#!/usr/bin/env zsh
# tmux-copy-url.zsh
# tmux ペインから URL を抽出し fzf で選択してコピーする
# Usage: bind u run-shell -b 'tmux display-popup -w 80% -h 60% -E "~/bin/tmux-copy-url.zsh #{pane_id}"'

readonly CAPTURE_START_LINE=-500
readonly FZF_PROMPT="URL> "
readonly NO_URL_MESSAGE="URL が見つかりません"
readonly COPIED_MESSAGE_PREFIX="Copied: "
readonly PANE_ID_ERROR_MESSAGE="Error: pane_id not specified"

display_tmux_message() {
  local message="$1"

  tmux display-message "$message"
}

require_target_pane() {
  local target_pane="$1"

  if [[ -n "$target_pane" ]]; then
    return 0
  fi

  echo "$PANE_ID_ERROR_MESSAGE"
  read
  return 1
}

extract_urls() {
  local target_pane="$1"

  tmux capture-pane -J -p -S "$CAPTURE_START_LINE" -t "$target_pane" \
    | grep -oP 'https?://[^\s>"'\'')\]}]+' \
    | sed 's/[.,;:!?]*$//' \
    | awk '!seen[$0]++'
}

select_url() {
  local urls="$1"

  printf '%s\n' "$urls" | fzf --no-sort --prompt="$FZF_PROMPT" --reverse
}

copy_to_tmux_buffer() {
  local selected_url="$1"

  printf '%s' "$selected_url" | tmux load-buffer -
}

copy_to_system_clipboard() {
  local selected_url="$1"
  local client_tty
  local encoded

  client_tty=$(tmux display-message -p '#{client_tty}')
  if [[ -z "$client_tty" || ! -w "$client_tty" ]]; then
    return 0
  fi

  encoded=$(printf '%s' "$selected_url" | base64 | tr -d '\n')
  printf "\033]52;c;%s\a" "$encoded" > "$client_tty"
}

main() {
  local target_pane="${1:-}"
  local urls
  local selected_url

  require_target_pane "$target_pane" || return 1

  urls=$(extract_urls "$target_pane")
  if [[ -z "$urls" ]]; then
    display_tmux_message "$NO_URL_MESSAGE"
    return 0
  fi

  selected_url=$(select_url "$urls")
  if [[ -z "$selected_url" ]]; then
    return 0
  fi

  # tmux バッファへは常に保存し、prefix + ] で貼り付けできるようにする。
  copy_to_tmux_buffer "$selected_url"
  # OSC 52 は利用可能な端末だけでベストエフォートで送る。
  copy_to_system_clipboard "$selected_url"

  display_tmux_message "$COPIED_MESSAGE_PREFIX$selected_url"
}

main "$@"