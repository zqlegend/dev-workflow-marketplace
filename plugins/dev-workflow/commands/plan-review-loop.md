---
description: Run the Plan Review-Fix Cycle on a plan document until both reviewers unconditionally APPROVE.
argument-hint: "[plan-file] [--force]"
allowed-tools:
  - "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/run-plan-review-loop.sh:*)"
---

# Plan Review-Fix Cycle (1-slice simple loop)

You are about to start the Plan Review-Fix Cycle. The loop iterates until both reviewers return unconditional APPROVE, or a stuck-exit triggers.

## Step 1: Prepare manifest + start ralph loop

Arguments: `$1` is the plan file (default `doc/current_plan.md`); `$2` is `--force` to overwrite prior ralph state.

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/run-plan-review-loop.sh" "$1" "$2"
```

This single wrapper does:
1. Validates preconditions (plan file exists; no stale `.claude/ralph-loop.local.md` without `--force`).
2. Builds the 1-slice manifest via `detect-review-type.sh plan <plan-file>`.
3. Schema-checks the manifest (`schema_version == 1`).
4. Resolves abstract reviewer roles to concrete subagents via `resolve-roles.py`.
5. Prepares the canonical loop prompt and hands it to ralph-loop's setup script with `--completion-promise DEV-REVIEW-DONE --max-iterations 7`.

## Step 2: Proceed with the loop

Ralph-loop state is now active at `.claude/ralph-loop.local.md`. The Stop hook replays the prompt each iteration. Read that file (the prompt body lives after the second `---` delimiter) and begin iteration 1.

## Step 3: Summary

After the loop exits, read `.claude/dev-review/latest.md` and report:
- Mode: simple
- Iterations completed: N (count `iteration-*.md` files in `.claude/dev-review/`)
- Final verdicts: APPROVE/APPROVE → next: user approval gate for the plan
- If `.claude/dev-review/convergence-report.md` exists → STUCK; surface the report to the user.

## Reminders

- This command automates the Plan Review-Fix Cycle ONLY. User approval of the plan is a SEPARATE gate AFTER this loop exits with APPROVE.
- CONDITIONAL APPROVE = NOT APPROVED. The loop enforces this.
