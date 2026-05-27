---
description: Run the Cross-Cut Integration Review-Fix Cycle on the merged diff (slices by concern) until all slices unconditionally APPROVE.
argument-hint: "[--base REF] [--head REF] [--force]"
allowed-tools:
  - "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/run-integration-review-loop.sh:*)"
---

# Cross-Cut Integration Review-Fix Cycle (multi-slice loop)

You are about to start the Cross-Cut Integration Review-Fix Cycle. The loop partitions the merged diff (`--base`..`--head`) into slices by concern, each with a dedicated role-matched reviewer pair. It iterates until all slices return unconditional APPROVE, or a stuck-exit triggers at iteration 8.

## Step 1: Build manifest + start ralph loop

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/run-integration-review-loop.sh" "$@"
```

This single wrapper does:
1. Parses `--base`, `--head`, `--force` flags (defaults base=main, head=HEAD).
2. Validates preconditions (refs valid; no stale `.claude/ralph-loop.local.md` without `--force`).
3. Builds the multi-slice manifest via `build-integration-manifest.sh` (reads `$BASE`/`$HEAD` from the environment).
4. Schema-checks + prints per-slice file counts.
5. Resolves abstract reviewer roles to concrete subagents via `resolve-roles.py`.
6. Prepares the canonical loop prompt and hands it to ralph-loop's setup script with `--completion-promise DEV-REVIEW-DONE --max-iterations 9` (integration stuck threshold 8 + 1 failsafe).

## Step 2: Proceed with the loop

Ralph-loop state is now active at `.claude/ralph-loop.local.md`. The Stop hook replays the prompt each iteration. Read that file (the prompt body lives after the second `---` delimiter) and begin iteration 1.

## Step 3: Summary

After the loop exits, read `.claude/dev-review/latest.md` and report:
- Mode: integration
- Per-slice verdicts
- Iterations completed
- If `.claude/dev-review/convergence-report.md` exists → STUCK; surface the report to the user.

## Reminders

- This command automates the Cross-Cut Integration Review. It runs AFTER all WUs merge and BEFORE the user approval gate for integration.
- CONDITIONAL APPROVE = NOT APPROVED. The loop enforces this.
