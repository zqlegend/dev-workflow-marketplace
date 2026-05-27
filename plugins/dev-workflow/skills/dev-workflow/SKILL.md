---
name: dev-workflow
description: >
  Use when the user asks to implement, add, fix, refactor, modify, review,
  debug, investigate, optimize, or upgrade code in this project.
  Triggers on: "implement", "add feature", "new module", "new endpoint",
  "new component", "new CLI command", "fix bug", "refactor", "modify",
  "dependency upgrade", "performance optimization", "code review", "audit",
  "debug", "investigate", "why does", "wrong result", "write tests",
  "test development", "hotfix". Provides a disciplined, stack-agnostic
  development lifecycle: scope gate, plan, plan review, build, code-review
  loop, test, deliver — with Work Units for large tasks.
  Does NOT trigger on: writing docs only, general questions about Claude Code itself.
---

# Development Workflow Guidance

You are guiding a developer through a disciplined, stack-agnostic development
lifecycle. The workflow adapts to the project via per-project config in
`.claude/dev-workflow.local.md`. The Large-task protocol lives in
`work-unit-protocol.md` (read it only when a task is classified Large —
progressive disclosure).

## Step 0: Session Resume Check + Config Load

**BEFORE anything else:**

1. **Resume check.** Check if `doc/task/wu_status.md` exists.
   - If YES → read it (5 seconds), find the first non-DONE Work Unit, read its
     `doc/task/wu{N}_plan.md`, and resume from its current lifecycle step. Tell
     the user: "Resuming [task name] — WU-N is [status]. Next action: [what to do]."
   - If NO → proceed to Step 1.
2. **Config load.** Read the per-project config ONCE via `read-config.py`. The
   scope thresholds, build/test/lint commands, quality gates, test globs, and
   review settings all come from here. Read individual keys as needed, e.g.:
   ```bash
   "$CLAUDE_PLUGIN_ROOT/scripts/read-config.py" build "npm run build"
   "$CLAUDE_PLUGIN_ROOT/scripts/read-config.py" scope_thresholds.files 5
   ```
   The helper prints the documented default when the config file or a key is
   absent, so the workflow is deterministic with no config present. If
   `.claude/dev-workflow.local.md` does not exist, suggest running
   `/dev-workflow:init` to scaffold one.

## Step 1: Identify Task Type

Identify the task type (infer from context or ask). Use the "Typical Scale"
column as a hint for the Step 2 scope gate:

| Task | Typical Scale |
| ---- | ------------- |
| New feature / module | Often Large |
| New endpoint / component / CLI command | Usually Small |
| Bug fix | Small (Large if audit-escalated) |
| Refactor | Often Large |
| Dependency upgrade | Varies |
| Performance optimization | Varies |
| Code review / audit | Large if module-wide |
| Debugging / investigation | Usually Small |
| Test development | Varies |
| Hotfix | Always Small |

## Step 2: Scope Gate — Small or Large (MANDATORY for every task)

Classify the task using `scope_thresholds` from config (defaults: `files: 5`,
`loc: 1000`, `issues: 8`, `subsystems: 1`).

**Small Task** — ALL of the following hold:
- Files to modify: ≤ `scope_thresholds.files` (default 5)
- LOC changed: ≤ `scope_thresholds.loc` (default 1000)
- Distinct issues/items: ≤ `scope_thresholds.issues` (default 8)
- Subsystems (top-level directories) touched: ≤ `scope_thresholds.subsystems` (default 1)

**Large Task** — ANY threshold exceeded.

If unsure, use the "Typical Scale" column from Step 1 as guidance.

- **Small task** → proceed to the standard lifecycle below.
- **Large task** → read `work-unit-protocol.md` and follow the Work Unit
  protocol (master plan → per-WU lifecycle → integration). Do NOT inline the
  whole protocol here; load it on demand.

Note: only `scope_thresholds.files` and `scope_thresholds.subsystems` are
consumed mechanically (by the routing helper). `loc` and `issues` are
scope-gate inputs you apply by judgment here.

## Standard Lifecycle (Small tasks)

Not every task needs every phase, but **Code Review is MANDATORY for ALL code
changes.**

1. **DESIGN** — Clarify intent, requirements, and approach before touching code.
   Delegate to `superpowers:brainstorming` if installed; otherwise guide design
   inline (explore the problem, surface assumptions, agree on an approach).
2. **PLAN** — Write the plan to a file so it survives context compaction
   (`doc/current_plan.md` for small tasks; investigations go to
   `doc/current_investigation.md`). Delegate to `superpowers:writing-plans` if
   installed; otherwise write the plan inline (files to touch, phases, test
   strategy).
3. **PLAN REVIEW** — Independent review of the plan via the deterministic
   review loop: `/dev-workflow:plan-review-loop [plan-file]`. Iterate until
   APPROVE. Then get user approval before BUILD.
4. **BUILD** — Implement the change.
5. **CODE REVIEW (Review-Fix loop)** — After BUILD, run
   `/dev-workflow:code-review-loop` on the uncommitted diff. Two role-matched
   reviewers (resolved per the table below) run in parallel each iteration;
   fix all CRITICAL/MAJOR findings at the root cause; re-dispatch FRESH
   reviewers; loop until every reviewer returns unconditional APPROVE (verified
   deterministically by `check-approve.py`) or the stuck-exit triggers with
   `convergence-report.md`. MANDATORY for all code changes.
6. **TEST** — Run the project's test command (`gates`/`test` from config).
   Add tests for new behavior. All tests (new and existing) must pass.
7. **VERIFY / VALIDATE (optional)** — For changes with external correctness
   criteria, validate against reference data. Skip when not applicable.
8. **DELIVER** — Pass the pre-commit quality gate, commit atomically, then
   merge/document as appropriate.

## Role-Matched Reviewers

The review loop routes each change to a reviewer pair automatically (via
`route-change.py`, the single routing table). You do not pick reviewers by
hand; this is the table it applies, in priority order:

| Change shape (from the changed-file list) | Reviewer 1 | Reviewer 2 |
|--------------------------------------------|------------|------------|
| Touches `review.security_sensitive_paths` | security-reviewer | process-auditor |
| Test-only diff (all files match `test_path_globs`) | test-reviewer | process-auditor |
| Mostly type / interface definitions | type-design-reviewer | process-auditor |
| Cross-cutting (top-level dirs > `scope_thresholds.subsystems` OR file count > `scope_thresholds.files`) | correctness-reviewer | structural-architect |
| Default (general production code) | correctness-reviewer | process-auditor |
| Plan document (plan-review loop) | structural-architect | process-auditor |

These six abstract roles are resolved at loop-setup time (by
`resolve-roles.py`) into concrete agents. If `review.use_external_agents` is
`true` AND `pr-review-toolkit` is installed, `correctness-reviewer`,
`security-reviewer`, `test-reviewer`, and `type-design-reviewer` map to
pr-review-toolkit agents; otherwise (and always for `process-auditor` and
`structural-architect`) the plugin-owned `dev-workflow:*` agents are used. The
shipped default is `use_external_agents: false`.

## Quality Gates (generated from config)

Quality gates are NOT hardcoded — they are generated from `gates.*` in config.
Each gate is a list of command keys (e.g. `build`, `lint`, `test`,
`typecheck`); a key whose command is empty/undefined is skipped with a warning.

- **Pre-commit gate** (`gates.pre_commit`, default `[build, lint, test]`):
  present and run before any commit. Use `/dev-workflow:quality-gate` to run it.
- **Merge-to-main gate** (`gates.merge_main`, default
  `[build, lint, test, typecheck]`): run before merging to the main branch.

Always present the relevant gate before the corresponding action, and run each
named command, reporting pass/fail.

## Review-Loop Commands

Four deterministic review-fix loops share the same prompt body and
`check-approve.py` verifier; they differ only in manifest builder and
stuck-exit threshold:

- `/dev-workflow:plan-review-loop [file]` — 1-slice review of a plan document
  (PLAN REVIEW phase). Cap 7 iterations.
- `/dev-workflow:code-review-loop` — 1-slice review of the uncommitted diff
  (CODE REVIEW phase). Cap 7 iterations.
- `/dev-workflow:master-plan-review-loop` — `(1+K)`-slice loop for a Large-task
  master plan (structural slice + per-WU role-matched slices). Cap 11
  iterations. See `work-unit-protocol.md`.
- `/dev-workflow:integration-review-loop [--base REF] [--head REF]` — 2–3 slice
  cross-cut review after all Work Units merge. Cap 9 iterations. See
  `work-unit-protocol.md`.

## Behavior Rules

- **Start with the scope gate**: ALWAYS classify Small/Large (Step 2) before
  anything else.
- **Check for resume**: ALWAYS check `doc/task/wu_status.md` at session start
  (Step 0).
- **Be proactive and concise**: present the next checklist without being asked;
  show only the current phase's items, not the entire workflow.
- **Be adaptive**: if the user skips a phase, note it but don't block — unless
  it is a hard gate.
- **Enforce all hard gates**: the scope gate, plan-approval gate,
  design-approval gate, the review-fix gate (every code change), and the
  results-review gate.
- **Never self-review**: always dispatch independent agents (via the review
  loop) for review/audit. An agent must never review code it wrote.
- **Root-cause discipline**: never bypass root causes. Never suggest clamping,
  suppressing errors, masking failures, or tuning parameters to hide a bug. A
  visible failure is better than a silently wrong result. Temporary mitigations
  are allowed only after the root cause is identified, and must be tracked to
  closure.
- **Track progress**: update task tracking as phases complete; for Large tasks
  keep `doc/task/wu_status.md` current.
- **Remind at commit time**: always present the pre-commit quality gate before
  any commit.
