#!/bin/bash
set -e

# Create required directories
mkdir -p \
  "${HOME}/.codex" \
  "${HOME}/.claude" \
  "${HOME}/.grok" \
  "${HOME}/.config/gh" \
  "${HOME}/.config/glab-cli" \
  "${HOME}/.config/gcloud" \
  "${HOME}/.config/opencode" \
  "${HOME}/.qwen" \
  "${HOME}/.gemini/config"


# Create required files
touch \
  "${HOME}/.claude.json" \
  "${HOME}/.local/share/opencode/auth.json" \
  "${HOME}/.qwen/settings.json" \
  "${HOME}/.gemini/config/mcp_config.json"
