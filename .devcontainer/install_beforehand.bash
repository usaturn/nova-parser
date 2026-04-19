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

echo "Installing Claude CLI..."
curl -fsSL https://claude.ai/install.sh | bash
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
cp .devcontainer/tmux-copy-url.zsh "${HOME}/bin/tmux-copy-url.zsh"
chmod +x "${HOME}/bin/tmux-copy-url.zsh"

