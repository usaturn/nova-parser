#!/bin/bash
set -e

# Create required directories
mkdir -p \
  "${HOME}/.codex" \
  "${HOME}/.claude" \
  "${HOME}/.grok" \
  "${HOME}/.config/gh" \
  "${HOME}/.config/gcloud"

# Create required files
touch \
  "${HOME}/.claude.json"
