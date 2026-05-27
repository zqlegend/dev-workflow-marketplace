#!/usr/bin/env bash
# Build the 1-slice (mode: simple) manifest for plan/code review loops.
# Usage: detect-review-type.sh <code|plan [path]> [--force]
set -euo pipefail
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }
command -v git >/dev/null || { echo "git required" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=".claude/dev-review"; MANIFEST="$OUT/manifest.json"; mkdir -p "$OUT"

MODE="${1:-}"; FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done
[[ -z "$MODE" ]] && { echo "usage: $0 <code|plan [path]> [--force]" >&2; exit 2; }
[[ -f "$MANIFEST" && $FORCE -eq 0 ]] && { echo "manifest exists; use --force" >&2; exit 1; }

if [[ "$MODE" == "code" ]]; then
  # capture BOTH working-tree and staged changes vs HEAD, deduplicated
  mapfile -t CHANGED < <({ git diff --name-only HEAD; git diff --cached --name-only; } 2>/dev/null | sort -u)
  [[ ${#CHANGED[@]} -eq 0 ]] && { echo "no changed files" >&2; exit 2; }
  read R1 R2 < <(printf '%s\n' "${CHANGED[@]}" | python3 "$HERE/route-change.py" \
                 | awk -F= '/ROLE1/{r1=$2} /ROLE2/{r2=$2} END{print r1, r2}')
  TARGETS=("${CHANGED[@]}")
elif [[ "$MODE" == "plan" ]]; then
  PLAN="${2:-doc/current_plan.md}"
  [[ "$PLAN" == --* ]] && PLAN="doc/current_plan.md"   # don't mistake a flag for the path
  R1="structural-architect"; R2="process-auditor"
  TARGETS=("$PLAN")
else
  echo "unknown mode: $MODE" >&2; exit 2
fi

TARGET_JSON=$(printf '%s\n' "${TARGETS[@]}" | jq -R . | jq -s .)
jq -n --argjson target "$TARGET_JSON" --arg r1 "$R1" --arg r2 "$R2" \
  '{schema_version:1, mode:"simple",
    slices:[{id:"default", target:$target, roles:[$r1,$r2]}]}' > "$MANIFEST"
echo "Wrote $MANIFEST (roles: $R1 + $R2)"
