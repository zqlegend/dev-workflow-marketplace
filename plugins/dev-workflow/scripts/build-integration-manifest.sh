#!/usr/bin/env bash
# Build the generic 2-3 slice integration manifest (mode: integration).
# Reads BASE/HEAD from env (default main/HEAD).
#   interface-coupling      [correctness-reviewer, structural-architect]  (always)
#   regression-consistency  [process-auditor, test-reviewer]              (always; target capped)
#   security                [security-reviewer, process-auditor]          (only if security paths touched)
set -euo pipefail
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }
command -v git >/dev/null || { echo "git required" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=".claude/dev-review"; MANIFEST="$OUT/manifest.json"; mkdir -p "$OUT"
FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done
[[ -f "$MANIFEST" && $FORCE -eq 0 ]] && { echo "manifest exists; use --force" >&2; exit 1; }

BASE="${BASE:-main}"; HEAD="${HEAD:-HEAD}"; CAP=30
mapfile -t CHANGED < <(git diff --name-only "$BASE...$HEAD" 2>/dev/null | sort -u)
[[ ${#CHANGED[@]} -eq 0 ]] && { echo "no changed files in $BASE...$HEAD" >&2; exit 2; }

# no default -> read-config exits 3 when absent; `|| true` swallows it so SEC stays empty
mapfile -t SEC < <(python3 "$HERE/read-config.py" review.security_sensitive_paths 2>/dev/null || true)

# classify files: emit "IFACE\t<f>" and/or "SEC\t<f>" (single source of glob logic)
if [[ ${#SEC[@]} -gt 0 ]]; then SEC_STR=$(printf '%s\n' "${SEC[@]}"); else SEC_STR=""; fi
FILES_STR=$(printf '%s\n' "${CHANGED[@]}")
CLASS=$(python3 - "$SEC_STR" "$FILES_STR" <<'PY'
import sys, fnmatch
sec   = [s for s in sys.argv[1].split("\n") if s]
files = [f for f in sys.argv[2].split("\n") if f]
def gm(p, g):
    if g.endswith("/**"):
        b = g[:-3]; return p == b or p.startswith(b + "/")
    return fnmatch.fnmatch(p, g)
def is_iface(f):
    low = f.lower()
    return f.endswith(".d.ts") or f.endswith(".proto") or "types" in low or "interface" in low
for f in files:
    if is_iface(f):              print("IFACE\t" + f)
    if any(gm(f, g) for g in sec): print("SEC\t" + f)
PY
)
mapfile -t IFACE < <(printf '%s\n' "$CLASS" | awk -F'\t' '/^IFACE/{print $2}')
mapfile -t SECF  < <(printf '%s\n' "$CLASS" | awk -F'\t' '/^SEC/{print $2}')
REG=("${CHANGED[@]:0:$CAP}")

# explicit empty-array guards (no "${arr[@]:-}" footgun)
if [[ ${#IFACE[@]} -gt 0 ]]; then IFACE_JSON=$(printf '%s\n' "${IFACE[@]}" | jq -R . | jq -s .); else IFACE_JSON='[]'; fi
REG_JSON=$(printf '%s\n' "${REG[@]}" | jq -R . | jq -s .)

SLICES=$(jq -n --argjson iface "$IFACE_JSON" --argjson reg "$REG_JSON" \
  '[{id:"interface-coupling", target:$iface, roles:["correctness-reviewer","structural-architect"]},
    {id:"regression-consistency", target:$reg, roles:["process-auditor","test-reviewer"]}]')
if [[ ${#SECF[@]} -gt 0 ]]; then
  SEC_JSON=$(printf '%s\n' "${SECF[@]}" | jq -R . | jq -s .)
  SLICES=$(echo "$SLICES" | jq --argjson s "$SEC_JSON" \
    '. + [{id:"security", target:$s, roles:["security-reviewer","process-auditor"]}]')
fi
jq -n --argjson slices "$SLICES" '{schema_version:1, mode:"integration", slices:$slices}' > "$MANIFEST"
echo "Wrote $MANIFEST ($(echo "$SLICES" | jq length) slices)"
