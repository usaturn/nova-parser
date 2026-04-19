#!/bin/bash
# tmux ステータスバー用 git-prompt スクリプト
# zshrc.txt の git-prompt 関数と同等のロジックをピル型デザインで実装
#
# 使い方: tmux-git-prompt.bash <pane_current_path> <base_bg_color>

dir="${1:-.}"
bg="${2:-#000000}"

cd "$dir" 2>/dev/null || exit 0

# git リポジトリでなければ何も出力しない
git rev-parse --git-dir >/dev/null 2>&1 || exit 0

# ブランチ名を取得
branchname=$(git symbolic-ref --short HEAD 2>/dev/null)

if [ -z "$branchname" ]; then
    # detached HEAD 状態の場合

    # まずリモートブランチを優先して検索（タグを除外）
    ref_name=$(git name-rev --name-only --exclude='refs/tags/*' --refs='refs/remotes/*' HEAD 2>/dev/null)

    if [ -n "$ref_name" ] && [ "$ref_name" != "undefined" ]; then
        # remotes/origin/feature -> origin/feature に変換
        branchname=$(echo "$ref_name" | sed 's|^remotes/||')
    else
        # リモートブランチがない場合、ローカルブランチを検索
        ref_name=$(git name-rev --name-only --exclude='refs/tags/*' --refs='refs/heads/*' HEAD 2>/dev/null)

        if [ -n "$ref_name" ] && [ "$ref_name" != "undefined" ]; then
            # heads/feature -> feature に変換
            branchname=$(echo "$ref_name" | sed 's|^heads/||')
        else
            # どのブランチにも属さない場合、短縮ハッシュを表示
            branchname="detached@$(git rev-parse --short HEAD 2>/dev/null)"
        fi
    fi
fi

# 作業ツリー状態を取得してピルの色を決定
st=$(git status 2>/dev/null)

if echo "$st" | grep -q "^nothing to"; then
    # クリーン（緑）
    color="#50FA7B"
    text_fg="#1A5C2D"
elif echo "$st" | grep -q "^nothing added"; then
    # ステージ済み変更のみ（アンバー）
    color="#E5A700"
    text_fg="#3D2800"
else
    # 未ステージ変更あり（赤）
    color="#FF5555"
    text_fg="#FFFFFF"
fi

# プッシュ状態を確認
push_indicator=""
remote=$(git config "branch.${branchname}.remote" 2>/dev/null)

if [ -n "$remote" ]; then
    upstream="${remote}/${branchname}"
    if git show-ref --verify --quiet "refs/remotes/${upstream}"; then
        if [ -n "$(git log "${upstream}..${branchname}" 2>/dev/null)" ]; then
            # 未プッシュコミットあり
            push_indicator=" ↑"
        fi
    else
        # upstream ブランチが消失
        push_indicator=" !"
    fi
fi

# ピル形式で出力
label=" ${branchname}${push_indicator} "
echo "#[bg=${bg},fg=${color}]#[bg=${color},fg=${text_fg}]${label}#[bg=${bg},fg=${color}]"
