---
description: Run the Code Review-Fix Cycle on the current uncommitted diff until both reviewers unconditionally APPROVE.
argument-hint: "[--force]"
allowed-tools:
  - "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/run-code-review-loop.sh:*)"
---

# Code Review-Fix Cycle (1-slice simple loop, post-build)

You are about to start the Code Review-Fix Cycle on the current uncommitted diff. The loop iterates until both reviewers return unconditional APPROVE, or a stuck-exit triggers.

## Step 1: Prepare manifest + start ralph loop

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/run-code-review-loop.sh" "$1"
```

This single wrapper does:
1. Validates preconditions (non-empty uncommitted diff; no stale `.claude/ralph-loop.local.md` without `--force`).
2. Builds the 1-slice manifest via `detect-review-type.sh code`.
3. Schema-checks the manifest (`schema_version == 1`).
4. Resolves abstract reviewer roles to concrete subagents via `resolve-roles.py`.
5. Prepares the canonical loop prompt and hands it to ralph-loop's setup script with `--completion-promise DEV-REVIEW-DONE --max-iterations 7`.

## Step 2: Proceed with the loop

Ralph-loop state is now active at `.claude/ralph-loop.local.md`. The Stop hook replays the prompt each iteration. Read that file (the prompt body lives after the second `---` delimiter) and begin iteration 1.

## Step 3: Summary and next steps

After the loop exits, read `.claude/dev-review/latest.md` and report:
- Mode: simple
- Iterations completed: N (count `iteration-*.md` files in `.claude/dev-review/`)
- Final verdicts per slice
- If APPROVED: recommend running `/dev-workflow:quality-gate` next.
- If `.claude/dev-review/convergence-report.md` exists → STUCK; surface the report to the user.

## Reminders

- This command automates the Code Review-Fix Cycle ONLY. Build correctness, lint, and test passage are separate gates (`/dev-workflow:quality-gate`).
- CONDITIONAL APPROVE = NOT APPROVED. The loop enforces this.
