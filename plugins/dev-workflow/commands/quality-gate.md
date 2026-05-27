---
name: quality-gate
description: Run the config-driven pre-commit or merge-to-main quality gate and report pass/fail
args: "[pre-commit|merge]"
allowed-tools:
  - "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/read-config.py:*)"
  - "Bash"
---

# Quality Gate: {{ args | default: "pre-commit" }}

Run the appropriate quality gate. Gates are NOT hardcoded — they are generated from `gates.*` in `.claude/dev-workflow.local.md`. Each gate is a list of command keys (e.g. `build`, `lint`, `test`, `typecheck`) that reference the top-level command keys in the same config. A key whose command is empty/undefined is skipped with a warning.

## Step 1: Determine the gate

From the argument `{{ args | default: "pre-commit" }}`:
- `merge` or `merge-to-main` → use `gates.merge_main` (default `[build, lint, test, typecheck]`).
- anything else (default) → use `gates.pre_commit` (default `[build, lint, test]`).

## Step 2: Read the gate's command-key list

Read the ordered list of command keys for the chosen gate. The reader prints the documented default when config or key is absent, so this is deterministic with no config present.

Pre-commit gate:
```!
"${CLAUDE_PLUGIN_ROOT}/scripts/read-config.py" gates.pre_commit "build
lint
test"
```

Merge-to-main gate (use this instead when the argument is `merge`):
```!
"${CLAUDE_PLUGIN_ROOT}/scripts/read-config.py" gates.merge_main "build
lint
test
typecheck"
```

(Lists are emitted newline-joined, one key per line.)

## Step 3: Resolve each key to its command and run it

For EACH command key `K` from Step 2, in order:

1. Resolve the command for that key (top-level config key of the same name):
   ```bash
   "${CLAUDE_PLUGIN_ROOT}/scripts/read-config.py" K ""
   ```
   e.g. for `build`: `"${CLAUDE_PLUGIN_ROOT}/scripts/read-config.py" build ""`.
2. If the resolved command is empty (no value and no default), SKIP this key and record a warning: `WARN: gate key "K" has no command — skipped`.
3. Otherwise RUN the resolved command with `Bash` and capture its exit status:
   - exit 0 → PASS
   - non-zero → FAIL (capture the last lines of output for the report)

Do not stop on the first failure — run every gate key so the report is complete.

## Step 4: Report

Present a checklist, one line per gate key, in gate order:

```
Quality Gate: <pre-commit|merge-to-main>
- [x] build   (`<resolved command>`) — PASS
- [ ] lint    (`<resolved command>`) — FAIL: <short reason>
- [-] test    — SKIPPED (no command configured)
```

End with an overall verdict:
- All non-skipped keys PASS → **GATE PASSED**. For pre-commit, you may proceed to commit. For merge, you may proceed to merge.
- Any key FAILED → **GATE FAILED**. List the failing keys; do NOT commit/merge until they pass.
- Note any SKIPPED keys explicitly so the user can fill in missing config.
