#!/usr/bin/env bash
# Print the absolute path to ralph-loop's setup-ralph-loop.sh, or error.
set -euo pipefail

# 1) explicit override
if [[ -n "${RALPH_LOOP_ROOT:-}" ]]; then
  cand=$(ls "$RALPH_LOOP_ROOT"/*/scripts/setup-ralph-loop.sh 2>/dev/null | sort -V | tail -1 || true)
  [[ -z "$cand" ]] && cand="$RALPH_LOOP_ROOT/scripts/setup-ralph-loop.sh"
  if [[ -f "$cand" ]]; then echo "$cand"; exit 0; fi
fi

# 2) derive cache root from this plugin's own root and glob
if [[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  echo "find-ralph: CLAUDE_PLUGIN_ROOT unset and RALPH_LOOP_ROOT not found" >&2
  exit 2
fi
cache_root=$(dirname "$(dirname "$(dirname "$CLAUDE_PLUGIN_ROOT")")")  # .../plugins/cache
cand=$(ls "$cache_root"/*/ralph-loop/*/scripts/setup-ralph-loop.sh 2>/dev/null | sort -V | tail -1 || true)
if [[ -n "$cand" && -f "$cand" ]]; then echo "$cand"; exit 0; fi

echo "find-ralph: ralph-loop setup script not found under $cache_root. Install the ralph-loop plugin or set RALPH_LOOP_ROOT." >&2
exit 1
