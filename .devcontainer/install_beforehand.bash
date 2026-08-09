#!/bin/bash

set -u

cat .devcontainer/zshrc.txt >> ${HOME}/.zshrc
cp .devcontainer/tmux.conf ${HOME}/.tmux.conf
sudo perl -pi -e 's@http://archive\.ubuntu\.com@https://archive.ubuntu.com@g; s@http://security\.ubuntu\.com@https://security.ubuntu.com@g' /etc/apt/sources.list.d/ubuntu.sources && sudo apt update
sudo apt update && sudo apt install -y tmux vim tig ripgrep fzf bubblewrap
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
echo "Installing OpenCode..."
curl -fsSL https://opencode.ai/install | bash
export PATH="${HOME}/.opencode/bin:$PATH"
echo "Installing Qwen Code..."
curl -fsSL https://qwen-code-assets.oss-cn-hangzhou.aliyuncs.com/installation/install-qwen-standalone.sh | bash

YARN_GLOBAL_BIN="$(yarn global bin 2>/dev/null || true)"
if [ -n "$YARN_GLOBAL_BIN" ] && [ -d "$YARN_GLOBAL_BIN" ]; then
    export PATH="$YARN_GLOBAL_BIN:$PATH"
fi
export PATH="$HOME/.local/bin:$PATH"

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

echo "Installing bun..."
curl -fsSL https://bun.com/install | bash

echo "Installing Starship..."
curl -sS https://starship.rs/install.sh | sh -s -- -y
mkdir -p "${HOME}/.config"
cp .devcontainer/starship.toml "${HOME}/.config/starship.toml"

mkdir -p "${HOME}/bin"
cp .devcontainer/herdr-git-status.bash "${HOME}/bin/herdr-git-status.bash"
chmod +x "${HOME}/bin/herdr-git-status.bash"
cp .devcontainer/herdr-status-updater.bash "${HOME}/bin/herdr-status-updater.bash"
chmod +x "${HOME}/bin/herdr-status-updater.bash"
# herdrstart は PATH 上の herdr-status-updater（拡張子なし）を呼ぶ
cp .devcontainer/herdr-status-updater.bash "${HOME}/bin/herdr-status-updater"
chmod +x "${HOME}/bin/herdr-status-updater"
cp .devcontainer/tmux-git-status.bash "${HOME}/bin/tmux-git-status.bash"
chmod +x "${HOME}/bin/tmux-git-status.bash"
cp .devcontainer/tmux-url-copy.zsh "${HOME}/bin/tmux-url-copy.zsh"
chmod +x "${HOME}/bin/tmux-url-copy.zsh"
mkdir -p "${HOME}/.local/bin" && [ -d "${HOME}/.local/bin" ] && export PATH="${HOME}/.local/bin:${PATH}"

echo "Installing Herdr..."
if ! (set -o pipefail; curl -fsSL https://herdr.dev/install.sh | sh); then
    echo "Herdr installation failed." >&2
    exit 1
fi

if ! mkdir -p "${HOME}/.config/herdr"; then
    echo "Failed to create Herdr config directory." >&2
    exit 1
fi
if [ ! -f "${HOME}/.config/herdr/config.toml" ]; then
    if ! cp .devcontainer/herdr.toml "${HOME}/.config/herdr/config.toml"; then
        echo "Failed to place Herdr config." >&2
        exit 1
    fi
fi

if ! command -v herdr >/dev/null 2>&1; then
    echo "Herdr installation completed without placing herdr on PATH." >&2
    exit 1
fi
if ! herdr --version; then
    echo "Herdr version verification failed." >&2
    exit 1
fi

