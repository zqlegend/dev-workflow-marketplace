#!/usr/bin/env bash
set -euo pipefail
[[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]] && { echo "CLAUDE_PLUGIN_ROOT unset" >&2; exit 2; }
ROOT="$CLAUDE_PLUGIN_ROOT"
REVIEW_DIR=".claude/dev-review"          # must match {{REVIEW_DIR}} substitution
PROMISE="DEV-REVIEW-DONE"
MAXIT=9

# Args: [--force] [--base REF] [--head REF] — parse explicitly so flags don't collide
BASE="main"; HEAD="HEAD"; FORCE=0
while [[ $# -gt 0 ]]; do case "$1" in
  --base) BASE="$2"; shift 2;; --head) HEAD="$2"; shift 2;;
  --force) FORCE=1; shift;; *) shift;; esac; done

# (a) validate refs (no uncommitted-diff check)
if ! git rev-parse --verify -q "$BASE" >/dev/null 2>&1 || \
   ! git rev-parse --verify -q "$HEAD" >/dev/null 2>&1; then
  echo "ERROR: bad --base/--head ref" >&2; exit 1
fi
if [[ -f ".claude/ralph-loop.local.md" && $FORCE -eq 0 ]]; then
  echo "ERROR: prior loop state exists (.claude/ralph-loop.local.md). Use --force." >&2; exit 1
fi
mkdir -p "$REVIEW_DIR"

# (b) build the integration manifest (builder reads $BASE/$HEAD from the environment)
BASE="$BASE" HEAD="$HEAD" "$ROOT/scripts/build-integration-manifest.sh" --force

# (c) preflight schema
SCHEMA=$(jq -r '.schema_version' "$REVIEW_DIR/manifest.json")
[[ "$SCHEMA" != "1" ]] && { echo "ERROR: manifest schema_version=$SCHEMA, expected 1" >&2; exit 1; }

# (d) resolve abstract roles -> concrete subagent_type (no-op if helper absent yet)
[[ -f "$ROOT/scripts/resolve-roles.py" ]] && python3 "$ROOT/scripts/resolve-roles.py" "$REVIEW_DIR/manifest.json"

# (e) render prompt: substitute BOTH tokens with LITERAL replacement (python str.replace,
# so a '&' or '\' in $CHECK can't corrupt the output as it would with awk/sed gsub)
CHECK="$ROOT/scripts/check-approve.py"
PROMPT_FILE=$(mktemp -t dev-loop-prompt.XXXXXX)
trap 'rm -f "$PROMPT_FILE"' EXIT   # clean up even if ralph exits non-zero
python3 - "$ROOT/skills/dev-workflow/review-loop-prompt.md" "$CHECK" "$REVIEW_DIR" > "$PROMPT_FILE" <<'PY'
import sys
src, chk, rdir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.stdout.write(open(src).read()
                 .replace("{{CHECK_APPROVE_PATH}}", chk)
                 .replace("{{REVIEW_DIR}}", rdir))
PY

# (f) hand to ralph-loop (PROMPT_FILE is removed by the EXIT trap)
RALPH=$("$ROOT/scripts/find-ralph.sh")
"$RALPH" "$(cat "$PROMPT_FILE")" --completion-promise "$PROMISE" --max-iterations "$MAXIT"  # ralph-loop expects the prompt text as $1
echo "Ralph-loop initialized (mode: integration-review). Begin iteration 1."
