#!/usr/bin/env zsh

set -euo pipefail

#
# Pi + OpenCode Go + DeepSeek V4 Flash
#
# Idempotent setup script
#
# Creates:
#   ~/.pi/agent/auth.json     OpenCode Go credential
#   ~/.local/bin/pigo         Pi launcher
#
# Uses Pi's BUILT-IN opencode-go provider.
# It does NOT create a custom OpenCode Go provider.
#

readonly PROVIDER="opencode-go"
readonly MODEL="deepseek-v4-flash"
readonly THINKING="max"

readonly PI_DIR="${PI_CODING_AGENT_DIR:-${HOME}/.pi/agent}"
readonly AUTH_JSON="${PI_DIR}/auth.json"
readonly MODELS_JSON="${PI_DIR}/models.json"

readonly BIN_DIR="${HOME}/.local/bin"
readonly LAUNCHER="${BIN_DIR}/pigo"

readonly ZSHRC="${HOME}/.zshrc"

readonly PATH_MARKER_BEGIN="# >>> pi-opencode-go >>>"
readonly PATH_MARKER_END="# <<< pi-opencode-go <<<"


log() {
    print -r -- "[setup_pi_opencode_go] $*"
}

warn() {
    print -ru2 -- "[setup_pi_opencode_go] WARNING: $*"
}

die() {
    print -ru2 -- "[setup_pi_opencode_go] ERROR: $*"
    exit 1
}


#
# ----------------------------------------------------------------------
# 0. Preconditions
# ----------------------------------------------------------------------
#

command -v python3 >/dev/null 2>&1 ||
    die "python3 is required."

command -v pi >/dev/null 2>&1 ||
    die "pi is not installed or is not in PATH."

mkdir -p "${PI_DIR}"
mkdir -p "${BIN_DIR}"

log "Pi executable : $(command -v pi)"
log "Pi config dir : ${PI_DIR}"
log "Launcher      : ${LAUNCHER}"


#
# ----------------------------------------------------------------------
# 1. Resolve OpenCode API key
#
# Pi's official environment variable is OPENCODE_API_KEY.
#
# For compatibility with the previous script, OPENCODE_GO_API_KEY is
# accepted as a fallback.
#
# If neither exists, an existing auth.json credential is kept.
# ----------------------------------------------------------------------
#

API_KEY="${OPENCODE_API_KEY:-${OPENCODE_GO_API_KEY:-}}"

if [[ -n "${API_KEY}" ]]; then
    log "OpenCode API key found in environment."

    #
    # Make the official Pi variable available to commands executed by
    # this script as well.
    #
    export OPENCODE_API_KEY="${API_KEY}"
else
    log "No OpenCode API key found in environment."
    log "Checking existing ${AUTH_JSON} ..."
fi


#
# ----------------------------------------------------------------------
# 2. Upsert auth.json
#
# auth.json schema:
#
# {
#   "opencode-go": {
#     "type": "api_key",
#     "key": "..."
#   }
# }
#
# Existing credentials for other providers are preserved.
#
# We intentionally do NOT make backup copies of auth.json because doing
# so would unnecessarily duplicate plaintext credentials.
# ----------------------------------------------------------------------
#

python3 - "${AUTH_JSON}" "${API_KEY}" <<'PY'
import json
import os
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
new_key = sys.argv[2]

if path.exists():
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        print(
            f"ERROR: Invalid JSON in {path}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not isinstance(data, dict):
        print(
            f"ERROR: {path} must contain a JSON object.",
            file=sys.stderr,
        )
        sys.exit(1)
else:
    data = {}

existing = data.get("opencode-go")

if new_key:
    desired = {
        "type": "api_key",
        "key": new_key,
    }

    if existing == desired:
        print("OpenCode Go credential: already configured")
    else:
        data["opencode-go"] = desired

        path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_name = tempfile.mkstemp(
            prefix=".auth.json.",
            dir=path.parent,
            text=True,
        )

        try:
            with os.fdopen(fd, "w") as f:
                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, path)
            os.chmod(path, 0o600)

        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

        print("OpenCode Go credential: configured")

else:
    if (
        isinstance(existing, dict)
        and existing.get("type") == "api_key"
        and existing.get("key")
    ):
        print("OpenCode Go credential: using existing auth.json entry")
    else:
        print(
            "ERROR: No OpenCode Go API key is configured.\n"
            "\n"
            "Set one of:\n"
            '  export OPENCODE_API_KEY="..."\n'
            "\n"
            "or, for compatibility with the previous setup:\n"
            '  export OPENCODE_GO_API_KEY="..."\n',
            file=sys.stderr,
        )
        sys.exit(1)
PY

chmod 600 "${AUTH_JSON}"


#
# ----------------------------------------------------------------------
# 3. Remove ONLY the obsolete provider generated by the previous script
#
# Pi now has a built-in "opencode-go" provider.
#
# The previous script added this provider manually to models.json:
#
#   providers.opencode-go
#
# That override is unnecessary and may override Pi's current built-in
# model metadata.
#
# IMPORTANT:
#
# We remove it ONLY when it matches the signature of the old script.
# Any user-created/custom opencode-go configuration is left untouched.
# ----------------------------------------------------------------------
#

if [[ -f "${MODELS_JSON}" ]]; then

    CLEANUP_RESULT="$(
        python3 - "${MODELS_JSON}" <<'PY'
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

path = Path(sys.argv[1])

try:
    data = json.loads(path.read_text())
except json.JSONDecodeError as exc:
    print(
        f"ERROR: Invalid JSON in {path}: {exc}",
        file=sys.stderr,
    )
    sys.exit(1)

providers = data.get("providers")

if not isinstance(providers, dict):
    print("unchanged")
    sys.exit(0)

provider = providers.get("opencode-go")

if not isinstance(provider, dict):
    print("unchanged")
    sys.exit(0)

#
# Detect ONLY configurations generated by the earlier ChatGPT script.
#
api_key = provider.get("apiKey")
base_url = provider.get("baseUrl")
api = provider.get("api")

models = provider.get("models", [])

model_ids = {
    model.get("id")
    for model in models
    if isinstance(model, dict)
}

old_script_signature = (
    base_url == "https://opencode.ai/zen/go/v1"
    and api == "openai-completions"
    and api_key in {
        "$OPENCODE_GO_API_KEY",
        "$OPENCODE_API_KEY",
    }
    and model_ids == {"deepseek-v4-flash"}
)

if not old_script_signature:
    print("custom")
    sys.exit(0)

#
# Backup only models.json because it contains configuration, not the
# API key itself in the old generated form.
#
timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = path.with_name(
    path.name + f".bak.{timestamp}"
)

shutil.copy2(path, backup)

del providers["opencode-go"]

if not providers:
    data.pop("providers", None)

tmp = path.with_name(path.name + ".tmp")

tmp.write_text(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2,
    ) + "\n"
)

os.replace(tmp, path)

print(f"removed:{backup}")
PY
    )"

    case "${CLEANUP_RESULT}" in
        unchanged)
            log "models.json: no obsolete OpenCode Go override found."
            ;;

        custom)
            warn "models.json contains a custom opencode-go configuration."
            warn "It was NOT modified."
            ;;

        removed:*)
            BACKUP="${CLEANUP_RESULT#removed:}"
            log "Removed obsolete custom opencode-go provider."
            log "Backup: ${BACKUP}"
            ;;

        *)
            die "Unexpected models.json cleanup result: ${CLEANUP_RESULT}"
            ;;
    esac
fi


#
# ----------------------------------------------------------------------
# 4. Ensure ~/.local/bin is configured in ~/.zshrc
#
# Use a managed marker block so rerunning this script never duplicates it.
# ----------------------------------------------------------------------
#

python3 - "${ZSHRC}" "${PATH_MARKER_BEGIN}" "${PATH_MARKER_END}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
begin = sys.argv[2]
end = sys.argv[3]

if path.exists():
    text = path.read_text()
else:
    text = ""

block = f"""\
{begin}
export PATH="$HOME/.local/bin:$PATH"
{end}
"""

if begin in text and end in text:
    before = text.split(begin, 1)[0]
    after = text.split(end, 1)[1]

    text = (
        before.rstrip()
        + "\n\n"
        + block
        + after.lstrip("\n")
    )

else:
    if text and not text.endswith("\n"):
        text += "\n"

    if text:
        text += "\n"

    text += block

path.write_text(text)
PY

log "~/.local/bin PATH configuration: OK"


#
# ----------------------------------------------------------------------
# 5. Create/update ~/.local/bin/pigo
#
# The file content is deterministic. Re-running the installer simply
# writes the same launcher.
# ----------------------------------------------------------------------
#

TMP_LAUNCHER="${LAUNCHER}.tmp.$$"

cat > "${TMP_LAUNCHER}" <<'EOF'
#!/usr/bin/env zsh

set -euo pipefail

#
# Compatibility with the environment variable used by an older setup.
#
if [[ -z "${OPENCODE_API_KEY:-}" && -n "${OPENCODE_GO_API_KEY:-}" ]]; then
    export OPENCODE_API_KEY="${OPENCODE_GO_API_KEY}"
fi

exec pi \
    --provider opencode-go \
    --model deepseek-v4-flash \
    --thinking max \
    "$@"
EOF

chmod 755 "${TMP_LAUNCHER}"

if [[ -f "${LAUNCHER}" ]] && cmp -s "${TMP_LAUNCHER}" "${LAUNCHER}"; then
    rm -f "${TMP_LAUNCHER}"
    log "pigo launcher: already up to date."
else
    mv -f "${TMP_LAUNCHER}" "${LAUNCHER}"
    chmod 755 "${LAUNCHER}"
    log "pigo launcher: installed."
fi


#
# ----------------------------------------------------------------------
# 6. Refresh Pi model catalog
#
# Pi has a built-in OpenCode Go provider and its catalog can be refreshed
# independently of models.json.
#
# Failure to refresh is not fatal: an existing catalog may still work.
# ----------------------------------------------------------------------
#

log "Refreshing Pi model catalog..."

if pi update --models >/dev/null 2>&1; then
    log "Pi model catalog: refreshed."
else
    warn "'pi update --models' failed."
    warn "Continuing with the currently installed model catalog."
fi


#
# ----------------------------------------------------------------------
# 7. Validate provider/model availability
# ----------------------------------------------------------------------
#

log "Checking OpenCode Go model availability..."

MODEL_LIST="$(
    pi --list-models "${PROVIDER}" 2>&1 || true
)"

if ! print -r -- "${MODEL_LIST}" | grep -Fq "${MODEL}"; then
    print -ru2 -- ""
    print -ru2 -- "OpenCode Go model was not found."
    print -ru2 -- ""
    print -ru2 -- "Expected:"
    print -ru2 -- "  ${PROVIDER}/${MODEL}"
    print -ru2 -- ""
    print -ru2 -- "Pi output:"
    print -ru2 -- "${MODEL_LIST}"
    print -ru2 -- ""
    print -ru2 -- "Try updating Pi:"
    print -ru2 -- "  pi update"
    print -ru2 -- ""
    exit 1
fi

log "Model found: ${PROVIDER}/${MODEL}"


#
# ----------------------------------------------------------------------
# 8. Verify launcher
# ----------------------------------------------------------------------
#

[[ -x "${LAUNCHER}" ]] ||
    die "${LAUNCHER} was not created correctly."

log "Launcher executable: OK"


#
# ----------------------------------------------------------------------
# 9. Summary
# ----------------------------------------------------------------------
#

print
print "========================================"
print " Pi + OpenCode Go setup complete"
print "========================================"
print
print "Provider : ${PROVIDER}"
print "Model    : ${MODEL}"
print "Thinking : ${THINKING}"
print "Launcher : ${LAUNCHER}"
print "Auth     : ${AUTH_JSON}"
print
print "pigo executes:"
print
print "  pi \\"
print "    --provider ${PROVIDER} \\"
print "    --model ${MODEL} \\"
print "    --thinking ${THINKING}"
print
print "Run:"
print
print "  pigo"
print
print "If the current shell cannot find pigo yet:"
print
print "  source ~/.zshrc"
print "  rehash"
print "  pigo"
print
