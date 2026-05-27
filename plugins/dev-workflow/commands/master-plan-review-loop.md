---
description: Run the Master Plan Review-Fix Cycle on doc/task/ (partitioned into structural + per-WU slices) until all slices unconditionally APPROVE.
argument-hint: "[--force]"
allowed-tools:
  - "Bash(${CLAUDE_PLUGIN_ROOT}/scripts/run-master-plan-review-loop.sh:*)"
---

# Master Plan Review-Fix Cycle ((1+K)-slice loop)

You are about to start the Master Plan Review-Fix Cycle. The loop partitions the master plan into a structural slice (reviewed by `structural-architect` + `process-auditor`) and one slice per Work Unit (reviewed by a role-matched pair derived from the WU's target-file list). It iterates until every slice returns unconditional APPROVE, or a stuck-exit triggers at iteration 10.

## Step 1: Build manifest + start ralph loop

```!
"${CLAUDE_PLUGIN_ROOT}/scripts/run-master-plan-review-loop.sh" "$1"
```

This single wrapper does:
1. Validates preconditions (`doc/task/master_plan.md` exists; no stale `.claude/ralph-loop.local.md` without `--force`).
2. Builds the (1+K)-slice manifest via `build-master-plan-manifest.sh`.
3. Schema-checks + prints the slice count.
4. Resolves abstract reviewer roles to concrete subagents via `resolve-roles.py`.
5. Prepares the canonical loop prompt and hands it to ralph-loop's setup script with `--completion-promise DEV-REVIEW-DONE --max-iterations 11` (master-plan stuck threshold 10 + 1 failsafe).

## Step 2: Proceed with the loop

Ralph-loop state is now active at `.claude/ralph-loop.local.md`. The Stop hook replays the prompt each iteration. Read that file (the prompt body lives after the second `---` delimiter) and begin iteration 1. The prompt's Step 3 dispatches 2 agents per slice in parallel (chunked to batches under the concurrency cap).

## Step 3: Summary

After the loop exits, read `.claude/dev-review/latest.md` and report:
- Mode: master-plan
- Slice count: N (1 structural + K WU)
- Iterations completed
- Final verdicts per slice
- If `.claude/dev-review/convergence-report.md` exists → STUCK; surface the report to the user.

## Reminders

- This command automates the Master Plan Review-Fix Cycle. User approval of the master plan is a SEPARATE gate AFTER the loop exits with all APPROVE.
- CONDITIONAL APPROVE = NOT APPROVED. The loop enforces this.
