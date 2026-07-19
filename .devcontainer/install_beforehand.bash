#!/bin/bash

set -u

cat .devcontainer/zshrc.txt >> ${HOME}/.zshrc
cp .devcontainer/tmux.conf ${HOME}/.tmux.conf
sudo perl -pi -e 's@http://archive\.ubuntu\.com@https://archive.ubuntu.com@g; s@http://security\.ubuntu\.com@https://security.ubuntu.com@g' /etc/apt/sources.list.d/ubuntu.sources && sudo apt update
sudo apt update && sudo apt install -y tmux vim tig ripgrep fzf
echo "Setting up Japanese locale..."
sudo perl -pi -e 's/# ja_JP\.UTF-8/ja_JP.UTF-8/' /etc/locale.gen
sudo locale-gen
echo "Locale setup completed."

echo "Installing Claude Code..."
curl -fsSL https://claude.ai/install.sh | bash
echo "Installing Codex CLI..."
yarn global add @openai/codex@latest
echo "Installing Grok Build..."
curl -fsSL https://x.ai/cli/install.sh | bash
echo "Installing AntiGravity CLI..."
curl -fsSL https://antigravity.google/cli/install.sh | bash

YARN_GLOBAL_BIN="$(yarn global bin)"
export PATH="$YARN_GLOBAL_BIN:$HOME/.local/bin:$PATH"

curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://bun.com/install | bash

echo "Installing Starship..."
curl -sS https://starship.rs/install.sh | sh -s -- -y
mkdir -p "${HOME}/.config"
cp .devcontainer/starship.toml "${HOME}/.config/starship.toml"

mkdir -p "${HOME}/bin"
cp .devcontainer/tmux-git-status.bash "${HOME}/bin/tmux-git-status.bash"
chmod +x "${HOME}/bin/tmux-git-status.bash"
cp .devcontainer/tmux-url-copy.zsh "${HOME}/bin/tmux-url-copy.zsh"
chmod +x "${HOME}/bin/tmux-url-copy.zsh"

# -------------------------------------------------------------------
# Headroom 専用独立 venv のセットアップ（システム Python 3.12 使用）
# 目的:
# - プロジェクトの Python 3.14 + uv 管理から完全に分離
# - PyO3 / maturin による 3.14 ビルドエラーを根本回避
# - headroom-ai[all] の重い依存（torch 等）をプロジェクト .venv に混入させない
# - uv を使わず古典的な venv + pip で管理（ユーザ指定の方式）
# -------------------------------------------------------------------
echo "Setting up isolated Headroom venv with system Python 3.12..."

HEADROOM_VENV="${HOME}/.headroom-venv"
HEADROOM_BIN="${HEADROOM_VENV}/bin/headroom"
WRAPPER_BIN="${HOME}/bin/headroom"

if [ ! -x "$HEADROOM_BIN" ]; then
    echo "Creating fresh headroom venv at ${HEADROOM_VENV} using $(python3 --version) ..."
    rm -rf "$HEADROOM_VENV"
    python3 -m venv "$HEADROOM_VENV"

    echo "Upgrading pip in headroom venv..."
    "$HEADROOM_VENV/bin/pip" install --upgrade pip setuptools wheel

    echo "Installing headroom-ai[all] (this may take several minutes and consume significant disk)..."
    "$HEADROOM_VENV/bin/pip" install "headroom-ai[all]"

    echo "Headroom venv created successfully."
else
    echo "Headroom venv already exists at ${HEADROOM_VENV}. Skipping creation."
fi

# ~/bin/headroom wrapper を作成（uv run headroom 時代と同じコマンド名で使えるようにする）
if [ ! -x "$WRAPPER_BIN" ]; then
    cat > "$WRAPPER_BIN" << 'EOF'
#!/bin/bash
# Wrapper for headroom (managed in ~/.headroom-venv with system Python 3.12)
# This allows `headroom` command to work without uv or activating the venv.
exec "$HOME/.headroom-venv/bin/headroom" "$@"
EOF
    chmod +x "$WRAPPER_BIN"
    echo "Created wrapper: $WRAPPER_BIN"
else
    echo "Wrapper already exists: $WRAPPER_BIN"
fi

echo "Headroom setup complete. Try: headroom --version"
# -------------------------------------------------------------------

