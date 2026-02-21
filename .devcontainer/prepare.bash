#!/bin/bash

set -u

echo "Setting up Japanese locale..."
sudo sed -i 's/# ja_JP.UTF-8/ja_JP.UTF-8/' /etc/locale.gen
sudo locale-gen
echo "Locale setup completed."

if ! command -v claude >/dev/null 2>&1; then
	echo "Installing Claude CLI..."
	if ! curl -fsSL https://claude.ai/install.sh | bash; then
		echo "Warning: Claude CLI installation failed. Skipping MCP registration."
		exit 0
	fi
fi

export PATH="$HOME/.local/bin:$PATH"

if command -v claude >/dev/null 2>&1; then
	claude mcp add -s project context7 -- npx -y @upstash/context7-mcp || \
		echo "Warning: Failed to register context7 MCP."
else
	echo "Warning: claude command not found. Skipping MCP registration."
fi

echo 'alias ccd="claude --allow-dangerously-skip-permissions"' >> ${HOME}/.bashrc

