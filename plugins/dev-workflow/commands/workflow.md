---
name: workflow
description: Show the dev-workflow development lifecycle task-type table and route to the right phases
args: "[task_type]"
---

# Development Workflow Guide

## Instructions

1. Present the task-type lookup table below.
2. If a task type is provided (`{{ args }}`), match it to the table and summarize the recommended phases for that task type.
3. If no task type is provided, ask the user what kind of development task they're working on.
4. For the matched task, run the dev-workflow lifecycle defined in the `dev-workflow` skill (Scope Gate → Plan → Plan Review → Build → Code Review loop → Test → Deliver). Read the skill's `work-unit-protocol.md` only when the task classifies as Large (progressive disclosure).
5. Offer to create a TaskList to track progress through the phases.

## Task-Type Lookup Table

The "Typical Scale" column is a hint for the mandatory Scope Gate (Small vs Large). Classify against `scope_thresholds` from `.claude/dev-workflow.local.md` (defaults: `files: 5`, `loc: 1000`, `issues: 8`, `subsystems: 1`).

| Task | Typical Scale | Key Phases |
| ---- | ------------- | ---------- |
| New feature / module | Often Large | Design → Plan → Plan Review → Build → Code Review → Test → Deliver |
| New endpoint / component / CLI command | Usually Small | Design → Plan → Build → Code Review → Test → Deliver |
| Bug fix | Small (Large if audit-escalated) | Diagnose → Fix → Code Review → Test → Deliver |
| Refactor | Often Large | Plan → Plan Review → Build → Code Review → Test → Deliver |
| Dependency upgrade | Varies | Plan → Build → Code Review → Test → Deliver |
| Performance optimization | Varies | Plan → Build → Code Review → Test → Verify → Deliver |
| Code review / audit | Large if module-wide | Scope → Explore → Analyze → Report |
| Debugging / investigation | Usually Small | Observe → Reproduce → Narrow → Diagnose → Decide |
| Test development | Varies | Audit → Plan → Build → Code Review → Deliver |
| Hotfix | Always Small | Fix → Code Review → Test → Deliver (minimal) |

## Standard Lifecycle Phases

```
1. DESIGN       — Clarify intent, requirements, and approach before coding
2. PLAN         — Files, phases, test strategy (written to a file)
3. PLAN REVIEW  — Independent review loop; then user approval gate
4. BUILD        — Implement the change
5. CODE REVIEW  — Deterministic review-fix loop (MANDATORY for all code changes)
6. TEST         — Run the project's test command; add tests for new behavior
7. VERIFY       — Validate against reference criteria (optional)
8. DELIVER      — Pre-commit quality gate, commit, merge/document
```

Not every task needs every phase, but **Code Review is MANDATORY for all code changes**, and the **Scope Gate is MANDATORY for every task**.

- **Small task** (all thresholds satisfied) → follow the standard lifecycle above.
- **Large task** (any threshold exceeded) → follow the Work Unit protocol (master plan → per-WU lifecycle → integration review). The `dev-workflow` skill loads `work-unit-protocol.md` on demand.

## Review-Loop Commands

- `/dev-workflow:plan-review-loop [file]` — review a plan document (PLAN REVIEW phase).
- `/dev-workflow:code-review-loop` — review the uncommitted diff (CODE REVIEW phase).
- `/dev-workflow:master-plan-review-loop` — review a Large-task master plan.
- `/dev-workflow:integration-review-loop [--base REF] [--head REF]` — cross-cut review after Work Units merge.
- `/dev-workflow:quality-gate [pre-commit|merge]` — run the config-driven quality gate before commit/merge.

## After Identifying Task Type

1. Confirm the task type and its Small/Large classification with the user.
2. Present the task-specific phase list concisely.
3. Create TaskList items for each applicable phase.
4. Begin guiding through the first phase.
