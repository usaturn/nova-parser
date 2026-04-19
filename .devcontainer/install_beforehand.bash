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

if ! command -v claude >/dev/null 2>&1; then
    echo "Installing Claude CLI..."
    if ! curl -fsSL https://claude.ai/install.sh | bash; then
        echo "Warning: Claude CLI installation failed. Skipping MCP registration."
    fi
fi
echo "Installing Codex CLI..."
yarn global add @openai/codex@latest
yarn global add @google/gemini-cli@latest

YARN_GLOBAL_BIN="$(yarn global bin)"
export PATH="$YARN_GLOBAL_BIN:$HOME/.local/bin:$PATH"

curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://bun.com/install | bash

mkdir -p "${HOME}/bin"
cp .devcontainer/tmux-git-segment.bash "${HOME}/bin/tmux-git-segment.bash"
chmod +x "${HOME}/bin/tmux-git-segment.bash"
cp .devcontainer/tmux-url-copy.zsh "${HOME}/bin/tmux-url-copy.zsh"
chmod +x "${HOME}/bin/tmux-url-copy.zsh"

