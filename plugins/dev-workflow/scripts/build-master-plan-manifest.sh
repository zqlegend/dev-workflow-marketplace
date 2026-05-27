#!/usr/bin/env bash
# Build the (1+K)-slice master-plan manifest (mode: master-plan).
set -euo pipefail
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=".claude/dev-review"; MANIFEST="$OUT/manifest.json"; mkdir -p "$OUT"
FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done
[[ -f "$MANIFEST" && $FORCE -eq 0 ]] && { echo "manifest exists; use --force" >&2; exit 1; }

TASK="doc/task"
[[ -f "$TASK/master_plan.md" ]] || { echo "missing $TASK/master_plan.md" >&2; exit 2; }

# structural slice
STRUCT_TARGETS=$(printf '%s\n' "$TASK/master_plan.md" "$TASK/wu_status.md" | jq -R . | jq -s .)
SLICES=$(jq -n --argjson t "$STRUCT_TARGETS" \
  '[{id:"structure", target:$t, roles:["structural-architect","process-auditor"]}]')

# per-WU slices
for plan in "$TASK"/wu*_plan.md; do
  [[ -e "$plan" ]] || continue
  id=$(basename "$plan" | sed -E 's/_plan\.md$//')   # wu1, wu2, ...
  # WU plan declares its files after a 'TARGETS:' line, one per line until blank/EOF
  mapfile -t WUF < <(awk '/^TARGETS:/{f=1;next} f&&NF{print} f&&!NF{exit}' "$plan")
  if [[ ${#WUF[@]} -eq 0 ]]; then
    R1="correctness-reviewer"; TJSON='[]'
  else
    R1=$(printf '%s\n' "${WUF[@]}" | python3 "$HERE/route-change.py" --no-cross-cut \
         | awk -F= '/ROLE1/{print $2}')
    TJSON=$(printf '%s\n' "${WUF[@]}" | jq -R . | jq -s .)
  fi
  SLICES=$(echo "$SLICES" | jq --arg id "$id" --arg r1 "$R1" --argjson t "$TJSON" \
    '. + [{id:$id, target:$t, roles:[$r1,"process-auditor"]}]')
done

jq -n --argjson slices "$SLICES" '{schema_version:1, mode:"master-plan", slices:$slices}' > "$MANIFEST"
echo "Wrote $MANIFEST ($(echo "$SLICES" | jq length) slices)"
