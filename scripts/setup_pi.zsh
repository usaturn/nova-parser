#!/usr/bin/env zsh
PROVIDER="deepinfra"
MODEL="deepseek-ai/DeepSeek-V4-Flash-0731"
BASE_URL="https://api.deepinfra.com/v1/openai"

# PI_CODING_AGENT_DIR が設定されている場合も考慮
PI_DIR="${PI_CODING_AGENT_DIR:-${HOME}/.pi/agent}"
MODELS_JSON="${PI_DIR}/models.json"

echo "=== Pi + DeepInfra setup ==="

#
# 1. API token check
#
if [[ -z "${DEEPINFRA_TOKEN:-}" ]]; then
  echo "ERROR: DEEPINFRA_TOKEN is not set."
  echo
  echo 'Run:'
  echo '  export DEEPINFRA_TOKEN="your-token"'
  exit 1
fi

echo "DEEPINFRA_TOKEN: SET"

#
# 2. Pi config directory
#
mkdir -p "${PI_DIR}"

echo "Pi config dir: ${PI_DIR}"

#
# 3. Backup
#
if [[ -f "${MODELS_JSON}" ]]; then
  BACKUP="${MODELS_JSON}.bak.$(date +%Y%m%d-%H%M%S)"
  cp "${MODELS_JSON}" "${BACKUP}"
  echo "Backup: ${BACKUP}"
fi

#
# 4. Add/update DeepInfra provider
#
python3 - "${MODELS_JSON}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

if path.exists():
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {path}: {e}", file=sys.stderr)
        sys.exit(1)
else:
    data = {}

providers = data.setdefault("providers", {})

providers["deepinfra"] = {
    "name": "DeepInfra",
    "baseUrl": "https://api.deepinfra.com/v1/openai",
    "apiKey": "$DEEPINFRA_TOKEN",
    "api": "openai-completions",
    "authHeader": True,
    "models": [
        {
            "id": "deepseek-ai/DeepSeek-V4-Flash-0731",
            "name": "DeepSeek V4 Flash 0731",
            "reasoning": True,
            "input": ["text"],
            "cost": {
                "input": 0.09,
                "output": 0.18,
                "cacheRead": 0.018,
                "cacheWrite": 0
            },
            "compat": {
                "supportsDeveloperRole": False,
                "thinkingFormat": "deepseek"
            },
            "contextWindow": 1048576,
            "maxTokens": 65536
        }
    ]
}

path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n"
)

print(f"Updated: {path}")
PY

#
# 5. Validate JSON
#
python3 -m json.tool "${MODELS_JSON}" >/dev/null

echo "models.json JSON validation: OK"

#
# 6. Result
#
echo
echo "=== Setup complete ==="
echo "Provider : ${PROVIDER}"
echo "Model    : ${MODEL}"
echo "Config   : ${MODELS_JSON}"
echo
echo "Verify with:"
echo "  pi --list-models deepinfra"
echo
echo "Start with:"
echo "  pi --provider deepinfra --model ${MODEL}"

