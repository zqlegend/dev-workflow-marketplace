# dev-workflow Plugin — Design Spec

**Date:** 2026-05-26
**Status:** Approved design, pending implementation plan
**Author:** brainstormed with Claude Code

## 1. Purpose

A stack-agnostic, reusable Claude Code plugin that ports the CYCAS development
workflow (`cycas-workflow`) into a general-purpose form. It enforces a
disciplined development lifecycle — scope assessment, plan → review → build →
review-fix → test → commit — driven by per-project configuration rather than
hardcoded physics/MPI/CMake assumptions.

The CYCAS plugin's deterministic review-loop machinery is already
domain-agnostic; the only CYCAS-specific parts are (a) the file→reviewer
routing table, (b) the reviewer agents' domain knowledge, and (c) the hook
reminder content. This plugin generalizes exactly those three.

### Non-goals

- Not a replacement for `superpowers` (brainstorming, writing-plans, TDD); it
  delegates to them for design/planning phases.
- Not a replacement for `pr-review-toolkit`; it composes those reviewers when
  present.
- Does not target any single language; all stack specifics come from config.

## 2. Chosen approach (Approach C — layered)

The plugin **owns** the CYCAS-specific value (guiding skill, Small/Large scope
gate, full Work Unit subsystem, deterministic review-loop automation,
config layer, hooks) and **delegates** generic phases (design → brainstorming
skill; planning → writing-plans skill; code-correctness/security/test review →
`pr-review-toolkit` agents when installed, with plugin-owned generic fallbacks).

## 3. Plugin identity & layout

- **Name:** `dev-workflow`
- **Distribution:** standalone local marketplace, mirroring
  `video-essay-marketplace`:

```
/Users/qingz/dev-workflow-marketplace/
  .claude-plugin/marketplace.json        # marketplace manifest
  plugins/dev-workflow/
    .claude-plugin/plugin.json
    skills/dev-workflow/SKILL.md
    skills/dev-workflow/review-loop-prompt.md
    skills/dev-workflow/work-unit-protocol.md   # Large Task protocol (ported)
    commands/init.md
    commands/workflow.md
    commands/quality-gate.md
    commands/plan-review-loop.md
    commands/code-review-loop.md
    commands/master-plan-review-loop.md
    commands/integration-review-loop.md
    agents/process-auditor.md
    agents/structural-architect.md
    agents/correctness-reviewer.md       # generic fallback
    agents/security-reviewer.md          # generic fallback
    agents/test-reviewer.md              # generic fallback
    agents/type-design-reviewer.md       # generic fallback
    hooks/hooks.json
    hooks/pretooluse.py
    hooks/stop.py
    scripts/check-approve.py             # copied verbatim from cycas
    scripts/detect-review-type.sh        # REWRITTEN — change-shape routing
    scripts/build-master-plan-manifest.sh  # ported, generalized paths
    scripts/build-integration-manifest.sh  # ported, generalized paths
    scripts/resolve-roles.sh             # NEW — role→agent resolution shim
    scripts/run-plan-review-loop.sh
    scripts/run-code-review-loop.sh
    scripts/run-master-plan-review-loop.sh
    scripts/run-integration-review-loop.sh
  docs/superpowers/specs/2026-05-26-dev-workflow-plugin-design.md
```

The marketplace is registered as a `directory` source in
`known_marketplaces.json` (same mechanism as `cycas-local` and
`video-essay-local`).

## 4. The guiding skill (`skills/dev-workflow/SKILL.md`)

Structure mirrors CYCAS's `SKILL.md`, with stack specifics removed.

- **Step 0 — Resume check:** if `doc/task/wu_status.md` exists, read it, find
  the first non-DONE Work Unit, resume from its lifecycle step. Also read the
  per-project config (Section 6) once here.
- **Step 1 — Task-type routing.** Generic lookup table:

  | Task | Typical scale |
  |------|---------------|
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

- **Step 2 — Small/Large scope gate.** Thresholds from config (defaults mirror
  CYCAS: ≤5 files, ≤1k LOC, ≤8 distinct issues, 1 subsystem). ANY threshold
  exceeded → Large → Work Unit protocol.
- **Lifecycle phases:** Design → Plan → Plan-Review → Build → Code-Review
  (Review-Fix loop) → Test → (Verify/Validate, optional) → Deliver.
  - Design delegates to `superpowers:brainstorming`.
  - Plan delegates to `superpowers:writing-plans`.
  - Code-Review is the deterministic review-loop (Section 5).
- **Quality gates** (pre-commit, merge-to-main): generated from config
  `gates.*`, not hardcoded.
- **Behavior rules** ported from CYCAS: start with scope gate, check for
  resume, be concise/proactive, enforce hard gates (scope, plan approval,
  design approval, review-fix, results review), never self-review, root-cause
  discipline (no masking/clamping/suppression).

### Work Unit subsystem (Large tasks)

Ported near-verbatim from CYCAS Section 12.2 into `work-unit-protocol.md`
(progressive disclosure — read only when a Large task is identified):

- Master Plan phase: `doc/task/` dir, `master_plan.md` (objective, WU
  definitions ≤5 files preferred / ≤10 hard limit, dependency DAG, function/
  region ownership for shared files, global ordering rules), `wu_status.md`
  dashboard, per-WU `wu{N}_plan.md`.
- Master Plan Review: partitioned review loop (Section 5).
- User approval gate (batchable for independent WUs).
- Per-WU lifecycle: PLAN → USER GATE → BUILD → REVIEW-FIX → TEST → COMMIT.
- Integration phase: full build + test suite, regression check vs baseline,
  cross-cut review, deliver.

(CYCAS's performance-baseline benchmark step generalizes to "run the config
`test` + any `baseline` command and record results" — only included when the
project config defines a `baseline` command; otherwise skipped.)

## 5. Review-loop automation

### Ported verbatim (already domain-agnostic)

- **`check-approve.py`** — deterministic verifier. Validates: `nonce:` header,
  `slices_expected:` matches manifest, each slice has exactly 2 reviewer
  subsections, each reviewer has a `VERDICT:` line, declared verdict matches the
  embedded raw-transcript verdict (drift detection), all verdicts are literal
  `APPROVE`. Exit 0 only if all pass. Copied unchanged — it checks verdict
  *structure*, nothing CYCAS-specific.
- **`review-loop-prompt.md`** — the iteration decision tree (check previous
  verdict → apply root-cause fixes for CRITICAL/MAJOR → dispatch fresh reviewer
  pairs in parallel → persist verdicts with nonce-protected embedded transcripts
  → convergence check → loop). Copied with only the `{{CHECK_APPROVE_PATH}}`
  token preserved.
- **`run-*-loop.sh`** drivers — copied and renamed. Build manifest → preflight
  schema check → render prompt → hand to `ralph-loop` setup with completion
  promise `DEV-REVIEW-DONE` and a mode-specific max-iteration cap.

### Rewritten — `detect-review-type.sh` (change-shape routing)

Replaces CYCAS's physics-path routing with change-shape routing. Produces a
1-slice manifest with a role-matched reviewer pair:

| Change shape (from diff) | Reviewer 1 | Reviewer 2 |
|--------------------------|-----------|-----------|
| Touches `security_sensitive_paths` (config) | security-reviewer | process-auditor |
| Test-only diff | test-reviewer | process-auditor |
| Mostly type/interface definitions | type-design-reviewer | process-auditor |
| Cross-cutting (≥2 top-level subsystems, or file count over threshold) | correctness-reviewer | structural-architect |
| Default (general production code) | correctness-reviewer | process-auditor |

- Subsystem detection: top-level directory of each changed file (generic),
  replacing CYCAS's hardcoded physics module list.
- Test detection: configurable test-path glob (default `**/test*`, `**/*test*`,
  `**/*_test.*`, `**/*.spec.*`, `tests/**`).
- Type/interface detection: heuristic on changed files (`.d.ts`, files matching
  `*types*`/`*interface*`/`*.proto`, or a high ratio of `type`/`interface`/
  `struct` declarations in the diff).
- The `+source-term-checklist` append in CYCAS has no generic analogue and is
  dropped.

`build-master-plan-manifest.sh` and `build-integration-manifest.sh` are ported
with path patterns generalized to top-level subsystems.

### Reviewer roles & resolution shim

Manifests reference **abstract role names**. `resolve-roles.sh` (and a
companion note in the skill) maps each role to a concrete `subagent_type` at
dispatch time:

- **Plugin-owned, always present:**
  - `process-auditor` (ported, CYCAS specifics stripped) — workflow/lifecycle
    compliance, approval-gate preservation, root-cause discipline, test
    presence, doc parity, config-derived gate items.
  - `structural-architect` (ported) — WU boundaries, DAG cycle-freeness,
    completeness, ownership conflicts in shared files, scope thresholds.
- **Delegated when `pr-review-toolkit` installed and
  `review.use_external_agents: true`:**
  - `correctness-reviewer` → `pr-review-toolkit:code-reviewer`
  - `security-reviewer` → `pr-review-toolkit:silent-failure-hunter`
  - `test-reviewer` → `pr-review-toolkit:pr-test-analyzer`
  - `type-design-reviewer` → `pr-review-toolkit:type-design-analyzer`
- **Fallback** (external unavailable or disabled): each role resolves to a
  plugin-owned generic reviewer agent of the same name.

**Verdict contract:** every reviewer — owned or external — must emit a first
line matching `^VERDICT: (APPROVE|CONDITIONAL APPROVE|REJECT)$`. Plugin-owned
agents are natively contract-bound. External agents are instructed to prepend
the verdict line via the dispatch prompt; unparseable output is treated as
REJECT (identical to CYCAS). **Known limitation:** external-agent verdict
compliance depends on prompt adherence rather than a native contract. Accepted.

### Loop commands

- `/dev-workflow:plan-review-loop [file]` — 1-slice, plan document. Cap 7.
- `/dev-workflow:code-review-loop` — 1-slice, uncommitted diff. Cap 7.
- `/dev-workflow:master-plan-review-loop` — partitioned (1+K)-slice for Large
  Task master plan. Cap 11.
- `/dev-workflow:integration-review-loop [--base REF] [--head REF]` — 3-slice
  cross-cut after WUs merge. Cap 9.

All share the same `review-loop-prompt.md` body and `check-approve.py` verifier;
they differ only in manifest builder and stuck-exit threshold.

## 6. Per-project config (`.claude/dev-workflow.local.md`)

Committed file with YAML frontmatter, read once at skill Step 0.

```yaml
---
build:  "npm run build"
test:   "npm test"
lint:   "npm run lint"
typecheck: "npm run typecheck"   # optional
baseline: ""                      # optional perf baseline command for Large tasks
scope_thresholds: { files: 5, loc: 1000, issues: 8, subsystems: 1 }
gates:
  pre_commit: [build, lint, test]
  merge_main: [build, lint, test, typecheck]
test_path_globs: ["tests/**", "**/*_test.*", "**/*.spec.*"]
review:
  use_external_agents: true
  security_sensitive_paths: ["auth/", "**/crypto*"]
---
# Free-form project notes the skill should respect.
```

Referenced command names in `gates.*` (e.g. `build`, `lint`) map to the
top-level command keys. A gate listing a key whose command is empty/undefined
is skipped with a warning.

### `/dev-workflow:init`

Scaffolds the config by auto-detecting the stack (peeks at `package.json`,
`Makefile`, `pyproject.toml`/`setup.py`, `Cargo.toml`, `go.mod`, etc.), writes a
draft `.claude/dev-workflow.local.md`, and asks the user to confirm/edit. This
is the only "detect" step; the result is persisted, not re-derived each session.

## 7. Hooks (`hooks/hooks.json` → two Python scripts)

Both advisory (non-blocking), matching CYCAS's design.

- **PreToolUse** (on `Edit`/`Write`): if the edited path matches
  `review.security_sensitive_paths`, surface a short reminder. Silent fast-exit
  otherwise. Reminder content is generic ("security-sensitive path — review
  auth/crypto/input-validation invariants").
- **Stop:** pre-commit checklist reminder assembled from `gates.pre_commit`.
  Defers silently when a `ralph-loop` is active in the current session
  (identical session-id check to CYCAS `stop.py`), so review-loops aren't
  interrupted.

**Note on "enforcement":** CYCAS's hooks are advisory; enforcement comes from
the review-fix loop's deterministic exit gate and the skill's user-approval
gates. This plugin matches that. An optional **blocking** PreToolUse guard on
`git commit` (exit non-zero unless `gates.pre_commit` passed) is deferred unless
explicitly requested.

## 8. Dependencies

- **`ralph-loop`** — hard dependency; the review-loop iteration engine.
- **`pr-review-toolkit`** — soft dependency; gracefully degrades to plugin-owned
  reviewers when absent or disabled.
- **`superpowers`** — soft dependency for design/plan delegation; if absent, the
  skill guides those phases inline.
- **`jq`, `git`** — required by manifest scripts (CYCAS requires these too).

## 9. Build-vs-reuse summary

| Component | Disposition |
|-----------|-------------|
| `check-approve.py` | Copy verbatim |
| `review-loop-prompt.md` | Copy, swap path token + promise name |
| `run-*-loop.sh` drivers | Copy, rename, repoint plugin root |
| `detect-review-type.sh` | **Rewrite** — change-shape routing |
| `build-master-plan-manifest.sh`, `build-integration-manifest.sh` | Port, generalize paths |
| `process-auditor`, `structural-architect` agents | Port, strip CYCAS specifics |
| Generic fallback reviewers (correctness/security/test/type) | **New**, thin |
| `resolve-roles.sh` shim | **New** |
| `SKILL.md` + `work-unit-protocol.md` | **New**/ported backbone |
| Hooks | Port, config-driven |
| Config schema + `/init` | **New** |

## 10. Open items for the planning phase

- Final marketplace registration mechanics (add `dev-workflow-local` to
  `known_marketplaces.json`).
- Exact heuristics for type/interface change detection (may start conservative).
- Whether to ship the optional blocking commit guard.
- Test strategy for the plugin itself (port CYCAS's pytest suites for
  `check-approve.py` and the manifest builders; add fixtures for the new
  change-shape routing).
