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
run_zshrc() {
    local test_home="$1"
    shift
    env -u TMUX -u HERDR_ENV \
        HOME="$test_home" \
        PATH="$test_home/bin:/usr/bin:/bin" \
        HERDR_TEST_LOG="$test_home/herdr.log" \
        ZSHRC_TEMPLATE="$ZSHRC_TEMPLATE" \
        "$@" /usr/bin/zsh -f -c 'source "$ZSHRC_TEMPLATE"' </dev/null >/dev/null
}
run_zshrc_tty() {
    local test_home="$1"
    local zsh_command='/usr/bin/zsh -f -c '\''source "$ZSHRC_TEMPLATE"'\'' 2>"$HERDR_TEST_STDERR"'
    shift
    env -u TMUX -u HERDR_ENV \
        HOME="$test_home" \
        PATH="$test_home/bin:/usr/bin:/bin" \
        HERDR_TEST_LOG="$test_home/herdr.log" \
        HERDR_TEST_STDERR="$test_home/stderr.log" \
        ZSHRC_TEMPLATE="$ZSHRC_TEMPLATE" \
        "$@" script -qec "$zsh_command" /dev/null
}

test_config_and_syntax() {
    zsh -n "$ZSHRC_TEMPLATE"
    assert_contains "$HERDR_CONFIG" '^prefix = "ctrl\+k"$'
    assert_contains "$ZSHRC_TEMPLATE" '^function herdrstart\(\)\{$'
    ! rg -q '^function tmuxstart\(\)\{|^tmuxstart$' "$ZSHRC_TEMPLATE" \
        || fail 'tmuxstart remains enabled'
}

test_launch_and_guards() {
    local test_home="${TEST_ROOT}/home"
    mkdir -p "$test_home/bin"
    printf '%s\n' '#!/bin/sh' 'exit 0' > "$test_home/bin/starship"
    printf '%s\n' '#!/bin/sh' \
        'printf "called TZ=%s\\n" "${TZ:-}" >> "$HERDR_TEST_LOG"' \
        > "$test_home/bin/herdr"
    chmod +x "$test_home/bin/starship" "$test_home/bin/herdr"

    run_zshrc_tty "$test_home"
    [ "$(wc -l < "$test_home/herdr.log")" -eq 1 ] || fail 'TTY herdr call count'
    assert_contains "$test_home/herdr.log" '^called TZ=Asia/Tokyo$'

    : > "$test_home/herdr.log"
    run_zshrc "$test_home"
    [ ! -s "$test_home/herdr.log" ] || fail 'non-TTY guard'

    run_zshrc_tty "$test_home" HERDR_ENV=1
    [ ! -s "$test_home/herdr.log" ] || fail 'HERDR_ENV guard'
    run_zshrc_tty "$test_home" TMUX=/tmp/tmux-test
    [ ! -s "$test_home/herdr.log" ] || fail 'TMUX guard'

    mv "$test_home/bin/herdr" "$test_home/bin/herdr.disabled"
    run_zshrc_tty "$test_home"
    assert_contains "$test_home/stderr.log" 'herdr not found'
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
    assert_contains "$installer" 'tmux-git-status\.bash'
    assert_contains "$installer" 'tmux-url-copy\.zsh'
}

test_config_and_syntax
test_installer_wiring
test_launch_and_guards
printf 'PASS: herdr Dev Container migration\n'
