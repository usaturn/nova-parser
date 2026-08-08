#!/bin/bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZSHRC_TEMPLATE="${REPO_ROOT}/.devcontainer/zshrc.txt"
HERDR_CONFIG="${REPO_ROOT}/.devcontainer/herdr.toml"
TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "${TEST_ROOT}"' EXIT

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }
assert_contains() {
    rg -q -- "$2" "$1" || fail "$1 does not contain $2"
}
assert_before() {
    local file="$1"
    local earlier_pattern="$2"
    local later_pattern="$3"
    local earlier_line
    local later_line
    earlier_line="$(rg -n -m1 -- "$earlier_pattern" "$file" | cut -d: -f1)" \
        || fail "$file does not contain $earlier_pattern"
    later_line="$(rg -n -m1 -- "$later_pattern" "$file" | cut -d: -f1)" \
        || fail "$file does not contain $later_pattern"
    [ "$earlier_line" -lt "$later_line" ] \
        || fail "$earlier_pattern must appear before $later_pattern in $file"
}
# zshrc テンプレートを隔離環境で実行する共通部。$@ で追加の VAR=value を渡せる。
run_zshrc_code() {
    local test_home="$1"
    local zsh_code="$2"
    shift 2
    env -u TMUX -u HERDR_ENV -u HERDR_SOCKET_PATH \
        HOME="$test_home" \
        PATH="$test_home/bin:/usr/bin:/bin" \
        DEVCONTAINER_WORKSPACES_ROOT="$test_home/workspaces" \
        HERDR_TEST_LOG="$test_home/herdr.log" \
        HERDR_TEST_LOG_TMUX="$test_home/tmux.log" \
        HERDR_TEST_LOG_FZF="$test_home/fzf.log" \
        ZSHRC_TEMPLATE="$ZSHRC_TEMPLATE" \
        "$@" /usr/bin/zsh -f -c "$zsh_code" </dev/null >/dev/null
}
run_zshrc() {
    local test_home="$1"
    shift
    run_zshrc_code "$test_home" 'source "$ZSHRC_TEMPLATE"' "$@"
}
# precmd フックを明示的に発火させる。非対話 zsh では自動発火しないため。
# 関数名を直接呼ばず $precmd_functions を走査することで、登録漏れも同時に検出する。
# 各フックの失敗は rc に畳み込む（配列末尾以外での失敗を取りこぼさないため）。
# より忠実な検証が要る場合は
#   printf 'source "$ZSHRC_TEMPLATE"\nexit\n' | timeout 20 script -qec '/usr/bin/zsh -fi' /dev/null
# で実プロンプトを再現できる。
run_zshrc_precmd() {
    local test_home="$1"
    shift
    run_zshrc_code "$test_home" \
        'source "$ZSHRC_TEMPLATE"; rc=0; for f in $precmd_functions; do "$f" || rc=$?; done; exit $rc' \
        "$@"
}
run_zshrc_tty() {
    local test_home="$1"
    local zsh_command='/usr/bin/zsh -f -c '\''cd "$HOME"; source "$ZSHRC_TEMPLATE"; pwd -P > "$HERDR_TEST_AFTER_LOG"'\'' 2>"$HERDR_TEST_STDERR"'
    shift
    env -u TMUX -u HERDR_ENV -u HERDR_SOCKET_PATH \
        HOME="$test_home" \
        PATH="$test_home/bin:/usr/bin:/bin" \
        DEVCONTAINER_WORKSPACES_ROOT="$test_home/workspaces" \
        HERDR_TEST_LOG="$test_home/herdr.log" \
        HERDR_TEST_LOG_TMUX="$test_home/tmux.log" \
        HERDR_TEST_LOG_FZF="$test_home/fzf.log" \
        HERDR_TEST_AFTER_LOG="$test_home/after.log" \
        HERDR_TEST_STDERR="$test_home/stderr.log" \
        ZSHRC_TEMPLATE="$ZSHRC_TEMPLATE" \
        "$@" /usr/bin/script -qec "$zsh_command" /dev/null
}
# herdr / herdr-status-updater / starship のスタブと空ログを用意する。
make_stub_home() {
    local dir="$1"
    mkdir -p "$dir/bin" "$dir/workspaces/repo-one"
    printf '%s\n' '#!/bin/sh' 'exit 0' > "$dir/bin/starship"
    printf '%s\n' '#!/bin/sh' \
        'if [ "$1" = "status" ]; then' \
        '    if [ "${HERDR_TEST_SERVER_RUNNING:-0}" = "1" ]; then' \
        '        printf "status: running\\n"' \
        '    else' \
        '        printf "status: not running\\n"' \
        '    fi' \
        '    exit 0' \
        'fi' \
        'printf "called TZ=%s cwd=%s\\n" "${TZ:-}" "$(pwd -P)" >> "$HERDR_TEST_LOG"' \
        > "$dir/bin/herdr"
    printf '%s\n' '#!/bin/sh' \
        'printf "updater %s\\n" "$*" >> "$HERDR_TEST_LOG.upd"' \
        > "$dir/bin/herdr-status-updater"
    printf '%s\n' '#!/bin/sh' \
        'if [ "$1" = "has-session" ]; then exit "${TMUX_TEST_HAS_SESSION_RC:-1}"; fi' \
        'printf "cwd=%s args=%s\\n" "$(pwd -P)" "$*" >> "$HERDR_TEST_LOG_TMUX"' \
        > "$dir/bin/tmux"
    chmod +x "$dir/bin/starship" "$dir/bin/herdr" "$dir/bin/herdr-status-updater" "$dir/bin/tmux"
    # set -e 下で `wc -l < 不在ファイル` が無言終了しないよう先に空で作る
    : > "$dir/herdr.log"
    : > "$dir/herdr.log.upd"
    : > "$dir/after.log"
    : > "$dir/tmux.log"
    : > "$dir/fzf.log"
}

make_fzf_stub() {
    local test_home="$1"
    printf '%s\n' '#!/bin/sh' \
        'printf "called %s\\n" "$*" >> "$HERDR_TEST_LOG_FZF"' \
        'if [ -n "${FZF_TEST_EXIT:-}" ]; then exit "$FZF_TEST_EXIT"; fi' \
        'if [ "${FZF_TEST_CANCEL:-0}" = "1" ]; then exit 130; fi' \
        'found=0' \
        'while IFS= read -r candidate; do' \
        '    [ "$candidate" = "$FZF_TEST_SELECTION" ] && found=1' \
        'done' \
        '[ "$found" -eq 1 ] || exit 3' \
        'if [ "${FZF_TEST_REMOVE_SELECTION:-0}" = "1" ]; then rm -rf -- "$FZF_TEST_SELECTION"; fi' \
        'printf "%s\\n" "$FZF_TEST_SELECTION"' \
        > "$test_home/bin/fzf"
    chmod +x "$test_home/bin/fzf"
}

test_config_and_syntax() {
    zsh -n "$ZSHRC_TEMPLATE"
    assert_contains "$HERDR_CONFIG" '^prefix = "ctrl\+k"$'
    assert_contains "$HERDR_CONFIG" '\$clock'
    assert_contains "$ZSHRC_TEMPLATE" '^function herdrstart\(\)\{$'
    assert_contains "$ZSHRC_TEMPLATE" 'herdr-status-updater'
    assert_contains "$ZSHRC_TEMPLATE" '^function herdr_server_running\(\) \{'

    # 手動 tmuxstart: 関数は必須、末尾の単独呼び出しは禁止
    assert_contains "$ZSHRC_TEMPLATE" '^function tmuxstart\(\)\{$'
    ! rg -q '^tmuxstart$' "$ZSHRC_TEMPLATE" \
        || fail 'tmuxstart must not be auto-invoked'
    # ガード B: herdr 内でも no-op
    assert_contains "$ZSHRC_TEMPLATE" 'HERDR_ENV'

    # tmux status 即時更新フック
    assert_contains "$ZSHRC_TEMPLATE" '^function precmd_tmux_refresh\(\) \{'
    assert_contains "$ZSHRC_TEMPLATE" 'precmd_functions\+=\(precmd_tmux_refresh\)'

    # herdr 内で status updater が落ちたときの唯一の復旧フック
    assert_contains "$ZSHRC_TEMPLATE" '^function precmd_herdr_status_updater\(\) \{'
    assert_contains "$ZSHRC_TEMPLATE" 'precmd_functions\+=\(precmd_herdr_status_updater\)'
}

# ここで検証するのは herdrstart 経路のみ。precmd 経路（herdr 内で updater を起こす）は
# test_precmd_status_updater が担当する（このハーネスでは precmd は発火しない）。
test_launch_and_guards() {
    local test_home="${TEST_ROOT}/home"
    make_stub_home "$test_home"

    run_zshrc_tty "$test_home"
    [ "$(wc -l < "$test_home/herdr.log")" -eq 1 ] || fail 'TTY herdr call count'
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}/workspaces/repo-one$"
    assert_contains "$test_home/after.log" "^${test_home}$"
    assert_contains "$test_home/herdr.log.upd" '^updater --daemon$'
    [ "$(wc -l < "$test_home/herdr.log.upd")" -eq 1 ] || fail 'TTY herdrstart updater call count'

    : > "$test_home/herdr.log"
    : > "$test_home/herdr.log.upd"
    run_zshrc "$test_home"
    [ ! -s "$test_home/herdr.log" ] || fail 'non-TTY guard'
    [ ! -s "$test_home/herdr.log.upd" ] || fail 'non-TTY herdrstart updater guard'

    : > "$test_home/herdr.log"
    : > "$test_home/herdr.log.upd"
    run_zshrc_tty "$test_home" HERDR_ENV=1
    [ ! -s "$test_home/herdr.log" ] || fail 'HERDR_ENV guard'
    # herdrstart 経路限定。herdr 内での起動は precmd 側の責務。
    [ ! -s "$test_home/herdr.log.upd" ] || fail 'HERDR_ENV herdrstart updater guard'

    : > "$test_home/herdr.log"
    : > "$test_home/herdr.log.upd"
    run_zshrc_tty "$test_home" TMUX=/tmp/tmux-test
    [ ! -s "$test_home/herdr.log" ] || fail 'TMUX guard'
    [ ! -s "$test_home/herdr.log.upd" ] || fail 'TMUX herdrstart updater guard'

    # herdr ペイン内（HERDR_SOCKET_PATH 設定済み）では起動しない。
    : > "$test_home/herdr.log"
    : > "$test_home/herdr.log.upd"
    run_zshrc_tty "$test_home" HERDR_SOCKET_PATH="$test_home/herdr.sock"
    [ ! -s "$test_home/herdr.log" ] || fail 'HERDR_SOCKET_PATH guard'
    [ ! -s "$test_home/herdr.log.upd" ] || fail 'HERDR_SOCKET_PATH herdrstart updater guard'

    mv "$test_home/bin/herdr" "$test_home/bin/herdr.disabled"
    : > "$test_home/herdr.log.upd"
    run_zshrc_tty "$test_home"
    assert_contains "$test_home/stderr.log" 'herdr not found'
    [ ! -s "$test_home/herdr.log.upd" ] || fail 'herdrstart updater skipped when herdr missing'
}

test_workspace_selection() {
    local test_home="${TEST_ROOT}/home-selection"
    make_stub_home "$test_home"

    mkdir -p "$test_home/linked-repo"
    ln -s "$test_home/linked-repo" "$test_home/workspaces/repo-link"
    make_fzf_stub "$test_home"

    run_zshrc_tty "$test_home" \
        FZF_TEST_SELECTION="$test_home/workspaces/repo-link"
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}/linked-repo$"

    rm "$test_home/workspaces/repo-link"
    : > "$test_home/herdr.log"
    : > "$test_home/stderr.log"

    mkdir -p "$test_home/workspaces/repo-two"

    run_zshrc_tty "$test_home" \
        FZF_TEST_SELECTION="$test_home/workspaces/repo-two"
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}/workspaces/repo-two$"

    : > "$test_home/herdr.log"
    : > "$test_home/stderr.log"
    run_zshrc_tty "$test_home" \
        FZF_TEST_SELECTION="$test_home/workspaces/repo-two" \
        FZF_TEST_REMOVE_SELECTION=1
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}$"
    [ "$(wc -l < "$test_home/herdr.log")" -eq 1 ] || \
        fail 'herdr starts exactly once when selected workspace cannot be entered'
    assert_contains "$test_home/stderr.log" 'cannot enter'

    rm -rf "$test_home/workspaces/repo-one" "$test_home/workspaces/repo-two"
    : > "$test_home/herdr.log"
    : > "$test_home/stderr.log"
    run_zshrc_tty "$test_home"
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}$"
    assert_contains "$test_home/stderr.log" 'no workspace directories found'

    mkdir -p "$test_home/workspaces/repo-one" "$test_home/workspaces/repo-two"
    rm "$test_home/bin/fzf"
    : > "$test_home/herdr.log"
    : > "$test_home/stderr.log"
    run_zshrc_tty "$test_home" PATH="$test_home/bin"
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}$"
    assert_contains "$test_home/stderr.log" 'fzf not found'

    make_fzf_stub "$test_home"
    : > "$test_home/herdr.log"
    : > "$test_home/stderr.log"
    run_zshrc_tty "$test_home" FZF_TEST_CANCEL=1
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}$"
    assert_contains "$test_home/stderr.log" 'workspace selection cancelled'

    : > "$test_home/herdr.log"
    : > "$test_home/stderr.log"
    run_zshrc_tty "$test_home" FZF_TEST_EXIT=2
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}$"
    assert_contains "$test_home/stderr.log" 'selection failed \(fzf exit 2\)'
}

test_tmux_workspace_selection() {
    local test_home="${TEST_ROOT}/home-tmux"
    make_stub_home "$test_home"

    run_zshrc_code "$test_home" \
        'cd "$HOME"; source "$ZSHRC_TEMPLATE"; tmuxstart'
    assert_contains "$test_home/tmux.log" \
        "args=-u new-session -A -s yamada -n yamada -c ${test_home}/workspaces/repo-one ; set-environment -g TZ Asia/Tokyo"

    rm -rf "$test_home/workspaces/repo-one"
    : > "$test_home/tmux.log"
    : > "$test_home/stderr.log"
    run_zshrc_code "$test_home" \
        'cd "$HOME"; source "$ZSHRC_TEMPLATE"; tmuxstart' \
        2>"$test_home/stderr.log"
    assert_contains "$test_home/tmux.log" \
        "args=-u new-session -A -s yamada -n yamada -c ${test_home} ; set-environment -g TZ Asia/Tokyo"
    assert_contains "$test_home/stderr.log" 'no workspace directories found'

    # herdr ペイン内（HERDR_SOCKET_PATH 設定済み）では tmuxstart も no-op。
    : > "$test_home/tmux.log"
    run_zshrc_code "$test_home" \
        'cd "$HOME"; source "$ZSHRC_TEMPLATE"; tmuxstart' \
        HERDR_SOCKET_PATH="$test_home/herdr.sock"
    [ ! -s "$test_home/tmux.log" ] || fail 'HERDR_SOCKET_PATH tmuxstart guard'
}

# herdr サーバ稼働中は attach になり選択した cwd が効かないため、fzf を出さない。
test_herdr_attach_skips_selection() {
    local test_home="${TEST_ROOT}/home-attach"
    make_stub_home "$test_home"

    mkdir -p "$test_home/workspaces/repo-two"
    make_fzf_stub "$test_home"

    run_zshrc_tty "$test_home" \
        HERDR_TEST_SERVER_RUNNING=1 \
        FZF_TEST_SELECTION="$test_home/workspaces/repo-two"

    [ ! -s "$test_home/fzf.log" ] \
        || fail 'fzf must not run while the herdr server is running'
    assert_contains "$test_home/herdr.log" \
        "^called TZ=Asia/Tokyo cwd=${test_home}$"
    [ "$(wc -l < "$test_home/herdr.log")" -eq 1 ] \
        || fail 'attach must launch herdr exactly once'
}

# tmux new-session -A は既存セッションがあると attach 相当になり -c が無視されるため、
# herdrstart と同じく選択をスキップする。
test_tmux_attach_skips_selection() {
    local test_home="${TEST_ROOT}/home-tmux-attach"
    make_stub_home "$test_home"

    mkdir -p "$test_home/workspaces/repo-two"
    make_fzf_stub "$test_home"

    run_zshrc_code "$test_home" \
        'cd "$HOME"; source "$ZSHRC_TEMPLATE"; tmuxstart' \
        TMUX_TEST_HAS_SESSION_RC=0 \
        FZF_TEST_SELECTION="$test_home/workspaces/repo-two"

    [ ! -s "$test_home/fzf.log" ] \
        || fail 'fzf must not run while a tmux session already exists'
    assert_contains "$test_home/tmux.log" \
        "args=-u new-session -A -s yamada -n yamada -c ${test_home} ; set-environment -g TZ Asia/Tokyo"
}

# herdr 内で status updater が死んだときの復旧経路（precmd）を検証する。
# herdrstart 経路は test_launch_and_guards が担当。
test_precmd_status_updater() {
    local test_home="${TEST_ROOT}/home-precmd"
    make_stub_home "$test_home"

    # (a) herdr 内: precmd が updater をちょうど 1 回起こす。
    #     非 TTY なので herdrstart は早期 return し、ログは precmd 由来のみ。
    run_zshrc_precmd "$test_home" HERDR_ENV=1 \
        || fail 'precmd invocation failed (HERDR_ENV=1)'
    [ "$(wc -l < "$test_home/herdr.log.upd")" -eq 1 ] \
        || fail 'precmd updater must run exactly once inside herdr'
    assert_contains "$test_home/herdr.log.upd" '^updater --daemon$'
    [ ! -s "$test_home/herdr.log" ] || fail 'precmd must not launch herdr'

    # (b) herdr 外: precmd は完全に no-op。
    : > "$test_home/herdr.log"
    : > "$test_home/herdr.log.upd"
    run_zshrc_precmd "$test_home" || fail 'precmd invocation failed (outside herdr)'
    [ ! -s "$test_home/herdr.log.upd" ] \
        || fail 'precmd updater must stay quiet outside herdr'
    [ ! -s "$test_home/herdr.log" ] || fail 'precmd must not launch herdr outside herdr'

    # (c) updater 不在でも precmd 自体は非 0 を返さない（プロンプト毎のエラー表示を防ぐ）。
    #     破壊的操作なのでこのテスト関数の最後に置く。
    mv "$test_home/bin/herdr-status-updater" "$test_home/bin/herdr-status-updater.disabled"
    : > "$test_home/herdr.log.upd"
    run_zshrc_precmd "$test_home" HERDR_ENV=1 \
        || fail 'precmd must tolerate missing updater'
    [ ! -s "$test_home/herdr.log.upd" ] || fail 'missing updater must not log'
}

test_installer_wiring() {
    local installer="${REPO_ROOT}/.devcontainer/install_beforehand.bash"
    local apt_install
    bash -n "$installer"

    assert_before "$installer" 'https://astral\.sh/uv/install\.sh' 'https://herdr\.dev/install\.sh'
    assert_before "$installer" 'https://bun\.com/install' 'https://herdr\.dev/install\.sh'
    assert_before "$installer" 'Installing Starship' 'https://herdr\.dev/install\.sh'
    assert_before "$installer" 'Headroom setup complete' 'https://herdr\.dev/install\.sh'

    assert_contains "$installer" 'if \[ ! -f "\$\{HOME\}/\.config/herdr/config\.toml" \]'
    assert_contains "$installer" 'if ! mkdir -p "\$\{HOME\}/\.config/herdr"; then'
    assert_contains "$installer" 'if ! cp \.devcontainer/herdr\.toml "\$\{HOME\}/\.config/herdr/config\.toml"; then'
    assert_contains "$installer" 'command -v herdr'
    assert_contains "$installer" 'herdr --version'

    apt_install="$(rg -m1 -- 'apt install -y' "$installer")" \
        || fail "$installer does not contain an apt install command"
    printf '%s\n' "$apt_install" | rg -q -- '(^|[[:space:]])tmux([[:space:]]|$)' \
        || fail 'apt install command does not retain tmux'
    assert_contains "$installer" 'cp \.devcontainer/tmux\.conf'
    assert_contains "$installer" 'herdr-git-status\.bash'
    assert_contains "$installer" 'herdr-status-updater\.bash'
    assert_contains "$installer" 'tmux-git-status\.bash'
    assert_contains "$installer" 'tmux-url-copy\.zsh'
}

test_config_and_syntax
test_installer_wiring
test_launch_and_guards
test_workspace_selection
test_tmux_workspace_selection
test_herdr_attach_skips_selection
test_tmux_attach_skips_selection
test_precmd_status_updater
printf 'PASS: herdr Dev Container migration\n'
