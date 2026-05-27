#!/usr/bin/env bash
set -euo pipefail
[[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]] && { echo "CLAUDE_PLUGIN_ROOT unset" >&2; exit 2; }
ROOT="$CLAUDE_PLUGIN_ROOT"
REVIEW_DIR=".claude/dev-review"          # must match {{REVIEW_DIR}} substitution
PROMISE="DEV-REVIEW-DONE"
MAXIT=7

FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done

# (a) require a non-empty uncommitted diff (working-tree OR staged)
if git diff --quiet HEAD -- . 2>/dev/null && git diff --quiet --cached 2>/dev/null; then
  echo "ERROR: no uncommitted changes to review." >&2; exit 1
fi
if [[ -f ".claude/ralph-loop.local.md" && $FORCE -eq 0 ]]; then
  echo "ERROR: prior loop state exists (.claude/ralph-loop.local.md). Use --force." >&2; exit 1
fi
mkdir -p "$REVIEW_DIR"

# (b) build the 1-slice code manifest
"$ROOT/scripts/detect-review-type.sh" code --force

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
echo "Ralph-loop initialized (mode: code-review). Begin iteration 1."
