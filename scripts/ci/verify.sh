#!/usr/bin/env bash
# lock の確認・依存の同期・lint と format の検査・テスト・依存の脆弱性の検査を、
# ローカルで 1 回で実行する。
#
# 使い方: scripts/ci/verify.sh [full]
#   full（省略時）  下の手順をすべて順に実行し、最初に失敗した手順で止まる
#
# 終了コード: すべて成功なら 0、失敗した手順があればその終了コード。
# 未知のプロファイル名・余分な引数は、何も実行せずに 64。
# シグナルで打ち切られたら 128 + シグナル番号（HUP 129、INT 130、QUIT 131、TERM 143）。
#
# 対話の確認で止まらないよう、標準入力を閉じる。追跡対象のファイルは変えない
# （uv lock --check と uv sync --locked は uv.lock を書き換えない）。
# Python は呼び出し元の環境（UV_PYTHON・UV_PYTHON_PREFERENCE・UV_PYTHON_DOWNLOADS など）に
# 従って選ばれ、このスクリプトは uv の Python の設定を変えない。
set -euo pipefail

usage() {
    printf 'usage: scripts/ci/verify.sh [full]\n' >&2
}

if (($# > 1)); then
    printf 'verify.sh: too many arguments\n' >&2
    usage
    exit 64
fi
# 省略は full。空文字列は省略ではなく、未知のプロファイル名として扱う
profile="${1-full}"
if [[ "$profile" != full ]]; then
    printf "verify.sh: unknown verification profile: '%s'\n" "$profile" >&2
    usage
    exit 64
fi

# CDPATH があると、相対パスの cd が別のディレクトリへ移り得る
CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

exec </dev/null

# 最後の手順まで終えたときだけ 1 にする。passed は、これと終了コード 0 の両方がそろったときだけ出す
completed=0
on_exit() {
    local rc=$?
    if ((rc == 0 && completed)); then
        printf '\nverify.sh: %s passed\n' "$profile" >&2
    else
        # trap の無いシグナルで打ち切られると、終了コード 0 のままここに来ることがある
        ((rc != 0)) || rc=1
        printf '\nverify.sh: %s failed (exit %d)\n' "$profile" "$rc" >&2
    fi
    exit "$rc"
}
trap on_exit EXIT
# シグナルで止められたときも EXIT の trap で failed を出す
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 131' QUIT
trap 'exit 143' TERM

# 手順の見出しを出してから実行する。失敗すると set -e で止まる（条件の文脈で呼ばない）
step() {
    printf '\n==> %s\n' "$*" >&2
    "$@"
}

# 準備（--locked で、pyproject.toml と uv.lock がずれていれば失敗する）
step uv lock --check
step uv sync --locked --all-groups

# lint と format の検査（ruff の版は uv.lock が固定する）
step uv run --no-sync ruff check src tests
step uv run --no-sync ruff format --check src tests

# テスト（Images/ のサンプル画像が無いテストは skip になり、失敗にはならない）
step uv run --no-sync pytest -q

# 依存の脆弱性の検査。見つかったら失敗する（依存の更新で直す）
step uv audit --locked

completed=1
