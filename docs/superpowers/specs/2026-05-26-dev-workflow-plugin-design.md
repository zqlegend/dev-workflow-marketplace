# dev-workflow Plugin — Design Spec

**Date:** 2026-05-26
**Status:** Under review (iteration 2)
**Author:** brainstormed with Claude Code

## 1. Purpose

A stack-agnostic, reusable Claude Code plugin that ports the CYCAS development
workflow (`cycas-workflow`) into a general-purpose form. It enforces a
disciplined development lifecycle — scope assessment, plan → review → build →
review-fix → test → commit — driven by per-project configuration rather than
hardcoded physics/MPI/CMake assumptions.

The CYCAS plugin's deterministic review-loop machinery is *mostly*
domain-agnostic; the CYCAS-specific parts are (a) the file→reviewer routing
tables, (b) the reviewer agents' domain knowledge, (c) the hook reminder
content, (d) the multi-slice (master-plan / integration) slice taxonomy, and
(e) hardcoded path/name tokens (`.claude/cycas-review/`, `CYCAS-REVIEW-DONE`).
This plugin generalizes all of those.

### Non-goals

- Not a replacement for `superpowers` (brainstorming, writing-plans, TDD); it
  delegates to them for design/planning phases.
- Not a replacement for `pr-review-toolkit`; it composes those reviewers when
  present.
- Does not target any single language; all stack specifics come from config.

## 2. Chosen approach (Approach C — layered)

The plugin **owns** the CYCAS-specific value (guiding skill, Small/Large scope
gate, full Work Unit subsystem, deterministic review-loop automation, config
layer, hooks) and **delegates** generic phases (design → brainstorming skill;
planning → writing-plans skill; code-correctness/security/test review →
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
    scripts/read-config.py               # NEW — config reader (shared)
    scripts/route-change.sh              # NEW — shared change-shape router
    scripts/find-ralph.sh                # NEW — portable ralph-loop locator
    scripts/resolve-roles.py             # NEW — abstract role → agent rewriter
    scripts/detect-review-type.sh        # REWRITTEN — calls route-change.sh
    scripts/build-master-plan-manifest.sh  # REWRITTEN — calls route-change.sh per WU
    scripts/build-integration-manifest.sh  # REWRITTEN — generic slice taxonomy
    scripts/run-plan-review-loop.sh
    scripts/run-code-review-loop.sh
    scripts/run-master-plan-review-loop.sh
    scripts/run-integration-review-loop.sh
    scripts/tests/                       # ported + new pytest suites (see §9)
      test_check_approve.py
      test_route_change.py
      test_detect_review_type.py
      test_build_master_plan_manifest.py
      test_build_integration_manifest.py
      test_resolve_roles.py
      test_read_config.py
      fixtures/                          # generic-path fixtures
  docs/superpowers/specs/2026-05-26-dev-workflow-plugin-design.md
```

The marketplace is registered as a `directory` source in
`known_marketplaces.json` (same mechanism as `cycas-local` and
`video-essay-local`).

## 4. The guiding skill (`skills/dev-workflow/SKILL.md`)

Structure mirrors CYCAS's `SKILL.md`, with stack specifics removed.

- **Step 0 — Resume check + config load:** if `doc/task/wu_status.md` exists,
  read it, find the first non-DONE Work Unit, resume from its lifecycle step.
  Read the per-project config (Section 6) once here via `read-config.py`.
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

- **Step 2 — Small/Large scope gate.** Thresholds from config
  `scope_thresholds` (defaults mirror CYCAS: `files: 5`, `loc: 1000`,
  `issues: 8`, `subsystems: 1`). ANY threshold exceeded → Large → Work Unit
  protocol.
- **Lifecycle phases:** Design → Plan → Plan-Review → Build → Code-Review
  (Review-Fix loop) → Test → (Verify/Validate, optional) → Deliver.
  - Design delegates to `superpowers:brainstorming` (if installed; else the
    skill guides design inline).
  - Plan delegates to `superpowers:writing-plans` (same fallback).
  - Code-Review is the deterministic review-loop (Section 5).
- **Quality gates** (pre-commit, merge-to-main): generated from config
  `gates.*`, not hardcoded.
- **Behavior rules** ported from CYCAS: start with scope gate, check for
  resume, be concise/proactive, enforce hard gates (scope, plan approval,
  design approval, review-fix, results review), never self-review, root-cause
  discipline (no masking/clamping/suppression).

### Work Unit subsystem (Large tasks)

Ported from CYCAS Section 12.2 into `work-unit-protocol.md` (progressive
disclosure — read only when a Large task is identified):

- Master Plan phase: `doc/task/` dir, `master_plan.md` (objective, WU
  definitions ≤5 files preferred, ≤8 with written justification, ≤10 hard
  limit, dependency DAG, function/
  region ownership for shared files, global ordering rules), `wu_status.md`
  dashboard, per-WU `wu{N}_plan.md`.
- **Baseline capture (optional):** if config defines a `baseline` command, the
  skill runs it and records results in `doc/task/baseline.md` before Master
  Plan creation. This is **skill-guided prose, not script-enforced** — no
  manifest builder references the baseline file. If no `baseline` command is
  configured, the step is skipped.
- Master Plan Review: partitioned review loop (Section 5).
- User approval gate (batchable for independent WUs).
- Per-WU lifecycle: PLAN → USER GATE → BUILD → REVIEW-FIX → TEST → COMMIT.
- Integration phase: full build + test suite, regression check vs baseline (if
  captured), cross-cut review (Section 5 integration loop), deliver.

## 5. Review-loop automation

### Single source of truth for routing — `route-change.sh` (NEW)

CYCAS duplicates its routing logic in two places (`detect-review-type.sh` and
an inlined `match_rule_index` inside `build-master-plan-manifest.sh`, with a
"must stay in sync" comment). To avoid carrying that maintenance trap into the
port, the change-shape routing is extracted into one helper, `route-change.sh`,
which takes a file list and returns a role pair. `detect-review-type.sh`,
`build-master-plan-manifest.sh` (per WU), and `build-integration-manifest.sh`
all call it. There is exactly one routing table in the plugin.

**`route-change.sh` interface contract:**
- **Input:** a newline-separated file list on stdin
  (`printf '%s\n' "${FILES[@]}" | route-change.sh`).
- **Output:** exactly two lines on stdout — `ROLE1=<role>` then `ROLE2=<role>`
  — using the abstract role vocabulary only (no `subagent_type` namespacing,
  no modifiers). Callers parse these two lines.
- **Exit:** 0 on success; 2 on empty input.
- Reads config (`security_sensitive_paths`, `test_path_globs`,
  `scope_thresholds.{files,subsystems}`) via `read-config.py`, falling back to
  documented defaults when config is absent.
- **Optional flag `--no-cross-cut`:** skips the cross-cutting row during
  evaluation (used by the per-WU caller — see "Master-plan manifest" below), so
  routing falls through to the next matching row (Default if nothing else
  matches), keeping ROLE1 single-domain. `route-change.sh` always emits exactly
  two `ROLE=` lines regardless of this flag.

**Change-shape routing table** (replaces CYCAS physics-path routing):

| Change shape (from the file list) | Reviewer 1 (role) | Reviewer 2 (role) |
|-----------------------------------|-------------------|-------------------|
| Touches `review.security_sensitive_paths` (config glob) | security-reviewer | process-auditor |
| Test-only diff (all files match `test_path_globs`) | test-reviewer | process-auditor |
| Mostly type/interface definitions (see heuristic) | type-design-reviewer | process-auditor |
| Cross-cutting (top-level dirs touched > `scope_thresholds.subsystems`, OR file count > `scope_thresholds.files`) | correctness-reviewer | structural-architect |
| Default (general production code) | correctness-reviewer | process-auditor |

- **Subsystem detection:** top-level directory of each changed file (generic),
  replacing CYCAS's hardcoded physics-module list.
- **Test detection:** files matching `test_path_globs` from config (default
  list defined in §6; `route-change.sh` and §6 share the identical default).
- **Type/interface heuristic:** changed files that are `*.d.ts`, match
  `*types*`/`*interface*`/`*.proto`, OR whose diff is dominated by
  `type`/`interface`/`struct`/`enum` declarations. Starts conservative; refined
  during implementation with fixtures.
- CYCAS's `+source-term-checklist` role modifier has no generic analogue and is
  dropped: `route-change.sh` returns clean, unmodified role names, and no caller
  mutates the role strings after it returns.

### Config reading — `read-config.py` (NEW)

All shell scripts and both hooks read `.claude/dev-workflow.local.md` through
one helper, `read-config.py`, which parses the YAML frontmatter and prints a
requested key (scalars on one line; lists newline-joined). Shell callers use
`$(python3 "$ROOT/read-config.py" review.security_sensitive_paths)`; the Python
hooks `import` it. **Fallback:** if the config file is absent or a key is
missing, the helper exits with the documented default for that key, so every
script has deterministic behavior with no config present. YAML parsing lives in
exactly one place (Python `yaml` or a minimal frontmatter parser if `pyyaml` is
unavailable — decided at implementation; no shell YAML parsing anywhere).

### Ported verbatim (domain-agnostic)

- **`check-approve.py`** — deterministic verifier. Validates: `nonce:` header,
  `slices_expected:` matches manifest, each slice has exactly 2 reviewer
  subsections, each reviewer has a `VERDICT:` line, declared verdict matches the
  embedded raw-transcript verdict (drift detection), all verdicts are literal
  `APPROVE`. Exit 0 only if all pass. Copied unchanged — it takes paths as args
  and checks verdict *structure*, nothing CYCAS-specific.

### Ported with explicit token substitutions

- **`review-loop-prompt.md`** — the iteration decision tree (check previous
  verdict → apply root-cause fixes for CRITICAL/MAJOR → dispatch fresh reviewer
  pairs in parallel → persist verdicts with nonce-protected embedded transcripts
  → convergence check → loop). It contains **two** token classes that MUST be
  substituted on copy (CYCAS hardcodes both):
  1. `{{CHECK_APPROVE_PATH}}` → absolute path to the ported `check-approve.py`.
     This token **already exists** in CYCAS's prompt; the drivers substitute it
     (CYCAS does this via `awk`).
  2. `{{REVIEW_DIR}}` → `.claude/dev-review`. This token does **NOT** exist in
     CYCAS's prompt — CYCAS hardcodes the literal string `.claude/cycas-review`
     in ~8 places (manifest path, `iteration-M.md`, `latest.md` symlink,
     `convergence-report.md`, `findings-index.md`). The port is a two-step
     operation: (a) copy the file, then (b) find-replace the literal
     `.claude/cycas-review` — **without** trailing slash — → `{{REVIEW_DIR}}`,
     so the prompt's existing path slashes are preserved and paths render as
     `{{REVIEW_DIR}}/manifest.json`. Skipping step (b) leaves the loop
     reading/writing the wrong directory and silently breaks it.
     The drivers then substitute BOTH tokens in one pass, e.g.:
     `awk -v chk="$CHECK_APPROVE" -v rdir='.claude/dev-review' '{gsub(/\{\{CHECK_APPROVE_PATH\}\}/,chk); gsub(/\{\{REVIEW_DIR\}\}/,rdir); print}'`
     (`rdir` has no trailing slash, matching the stripped literal). Substituting
     only `{{CHECK_APPROVE_PATH}}` — by copying CYCAS's single-variable `awk`
     line verbatim — would leave `{{REVIEW_DIR}}` unresolved; the second `gsub`
     is mandatory. In v1 the review dir is the hardcoded literal
     `.claude/dev-review` (not config-driven); the prompt substitution and all
     four `run-*-loop.sh` drivers (`mkdir` + `awk`) must use this identical
     string.
  The completion-promise tag `<promise>CYCAS-REVIEW-DONE</promise>` →
  `<promise>DEV-REVIEW-DONE</promise>`. The stuck-exit artifact is written to
  `{{REVIEW_DIR}}/convergence-report.md`.

- **`run-*-loop.sh` drivers** — copied, renamed, and edited so that:
  - `mkdir`/manifest/iteration paths use `.claude/dev-review` (the value
    tokenized as `{{REVIEW_DIR}}` in the prompt).
  - The prompt template is located at
    `$CLAUDE_PLUGIN_ROOT/skills/dev-workflow/review-loop-prompt.md` (rendered to
    a temp file after token substitution, as CYCAS does).
  - The `--completion-promise` argument is `DEV-REVIEW-DONE` (must match the
    prompt's `<promise>` tag exactly — a coupled substitution; mismatch means
    the loop never unblocks).
  - The ralph-loop setup script is located via `find-ralph.sh` (below), NOT a
    hardcoded absolute path.
  - After building the manifest, the driver calls `resolve-roles.py` (below)
    to rewrite abstract roles into concrete `subagent_type` strings, THEN
    renders the prompt and hands off to ralph-loop.
  - Per-mode `--max-iterations` cap: plan/code 7, integration 9, master-plan 11.

### Portable ralph-loop location — `find-ralph.sh` (NEW)

CYCAS hardcodes `/Users/qingz/.claude/plugins/cache/.../ralph-loop/1.0.0/scripts/setup-ralph-loop.sh`
— breaks on any other machine. `find-ralph.sh` resolves it portably:
1. `$RALPH_LOOP_ROOT` env var if set; else
2. `$CLAUDE_PLUGIN_ROOT` points to *this* plugin's own dir
   (`.../cache/<marketplace>/dev-workflow/<version>/`). Walk up to the cache
   root — `cache_root=$(dirname $(dirname $(dirname "$CLAUDE_PLUGIN_ROOT")))` —
   then glob `"$cache_root"/*/ralph-loop/*/scripts/setup-ralph-loop.sh` and pick
   the highest version via `sort -V`.
Hard error with an actionable message if not found (ralph-loop is a required
dependency, §8). ralph-loop's verified interface: `--completion-promise '<text>'`
and `--max-iterations <n>`.

### Reviewer roles & resolution — `resolve-roles.py` (NEW)

Manifests are written by the builders with **abstract role names**
(`correctness-reviewer`, `security-reviewer`, `test-reviewer`,
`type-design-reviewer`, `process-auditor`, `structural-architect`). Resolution
is **static, at loop-setup time** (not dynamic inside the prompt): each
`run-*-loop.sh` driver invokes `resolve-roles.py` once after the manifest is
built. `resolve-roles.py`:
1. Reads `review.use_external_agents` from config and detects whether
   `pr-review-toolkit` is installed by probing
   `<plugins-root>/installed_plugins.json` for a `pr-review-toolkit@*` key.
   `<plugins-root>` is the **parent** of the `cache_root` that `find-ralph.sh`
   computes — i.e. `dirname "$cache_root"`, equivalently four `dirname` hops
   from `$CLAUDE_PLUGIN_ROOT`, resolving to `…/.claude/plugins` (the directory
   that also holds `known_marketplaces.json`). If the registry file or key
   can't be resolved, it conservatively falls back to plugin-owned reviewers.
   WU2 asserts this path on first run and fails with an actionable message if
   the registry is not found there.
2. **Rewrites the manifest `roles` arrays in place**, replacing each abstract
   role with a concrete `subagent_type` string the Agent tool accepts.
3. The prompt then reads already-concrete names and dispatches them verbatim.

Resolution table:

| Abstract role | External (pr-review-toolkit present & enabled) | Fallback (plugin-owned) |
|---------------|------------------------------------------------|-------------------------|
| `correctness-reviewer` | `pr-review-toolkit:code-reviewer` | `dev-workflow:correctness-reviewer` |
| `security-reviewer` | `pr-review-toolkit:silent-failure-hunter` | `dev-workflow:security-reviewer` |
| `test-reviewer` | `pr-review-toolkit:pr-test-analyzer` | `dev-workflow:test-reviewer` |
| `type-design-reviewer` | `pr-review-toolkit:type-design-analyzer` | `dev-workflow:type-design-reviewer` |
| `process-auditor` | `dev-workflow:process-auditor` (always owned) | same |
| `structural-architect` | `dev-workflow:structural-architect` (always owned) | same |

(The left column is this plugin's abstract vocabulary; the right columns are
real, dispatchable agent names.) Plugin-namespaced `subagent_type` strings like
`pr-review-toolkit:code-reviewer` are *inferred* to be valid from existing
ecosystem usage (e.g. `feature-dev:code-architect`), but this is **not yet
empirically confirmed for cross-plugin dispatch**. WU8 (§10) MUST include a
smoke test that dispatches one plugin-namespaced agent and verifies it resolves;
if the format proves invalid, the fallback is to use plugin-owned reviewers only
(set `use_external_agents: false` as the default until validated).
`resolve-roles.py` is idempotent — re-running it on an already-resolved manifest
is a no-op (it only rewrites roles still in the abstract vocabulary).

**Verdict contract:** every reviewer — owned or external — must emit a first
line matching `^VERDICT: (APPROVE|CONDITIONAL APPROVE|REJECT)$`. Plugin-owned
agents are natively contract-bound by their system prompt. External agents are
instructed to prepend the verdict line via the dispatch prompt; unparseable
output is treated as REJECT (identical to CYCAS). **Known limitation:**
external-agent verdict compliance depends on prompt adherence, not a native
contract. Accepted; the deterministic `check-approve.py` still gates the exit.

### Manifest `mode` values (the prompt branches on these)

`review-loop-prompt.md` Step 4a selects stuck-exit thresholds by the manifest
`mode` field. The builders MUST emit these exact values (preserved from CYCAS):

| Builder | `mode` | Stuck threshold | Driver `--max-iterations` |
|---------|--------|-----------------|---------------------------|
| `detect-review-type.sh` (plan & code modes) | `simple` | iter ≥ 6 | 7 |
| `build-integration-manifest.sh` | `integration` | iter ≥ 8 | 9 |
| `build-master-plan-manifest.sh` | `master-plan` | iter ≥ 10 | 11 |

### `detect-review-type.sh` — plan vs code mode

`detect-review-type.sh` builds the 1-slice `mode: simple` manifest for both the
plan-review and code-review loops, but routes differently by mode:
- **`code` mode:** pipes the `git diff` file list into `route-change.sh` and
  uses the returned `[ROLE1, ROLE2]` pair.
- **`plan` mode:** the target is a plan/design *document*, not a code change, so
  change-shape routing does not apply. It emits a fixed pair
  `[structural-architect, process-auditor]` (structural soundness + process
  compliance — the right lens for a plan document).

### Master-plan manifest — per-WU roles (REWRITTEN)

`build-master-plan-manifest.sh` emits a partitioned `(1 + K)`-slice manifest:
- **Structural slice** (`id: structure`): targets `master_plan.md` +
  `wu_status.md`; roles `[structural-architect, process-auditor]`.
- **Per-WU slices** (`id: wu{N}`): for each Work Unit, the script calls
  `route-change.sh --no-cross-cut` on that WU's declared target file list and
  takes **only ROLE1** as-is from the router (e.g. `test-reviewer` for a
  test-only WU, `correctness-reviewer` for general code); ROLE2 is **always**
  hardcoded to `process-auditor` regardless of what the router returns as its
  own ROLE2. The router's own ROLE2 is intentionally
  discarded here — `structural-architect` is reserved for the `structure` slice,
  which already reviews cross-WU architecture. `--no-cross-cut` guarantees the
  router never returns the cross-cutting pair for a WU (which could otherwise
  yield `structural-architect` as ROLE1/ROLE2 and collide with this rule). This
  replaces CYCAS's physics-domain ROLE1 with the generic router output — no
  separate routing table.

### Integration manifest — generic slice taxonomy (REWRITTEN)

CYCAS's integration slices (`coupling`/`mpi`/`physics-consistency` with physics
roles) are domain-specific. `build-integration-manifest.sh` emits a generic,
**2–3 slice** taxonomy from the merged diff:
- `interface-coupling`: files on subsystem boundaries / changed public
  interfaces (heuristic: files imported by ≥2 subsystems, or matching the
  interface heuristic). Roles `[correctness-reviewer, structural-architect]`.
  Always emitted (target list may be empty). **Limitation (mirrors CYCAS):** the
  import-based "≥2 subsystems" detection requires a real `git diff` and is
  skipped in `--file-list` mode; `test_build_integration_manifest.py` therefore
  covers this bin only with git-backed fixtures, not file-list fixtures.
- `regression-consistency`: a **behavioral-review** slice over the whole merged
  diff (regressions + test coverage). Roles `[process-auditor, test-reviewer]`.
  Always emitted; its `target` is the full changed-file list
  (`git diff --name-only` over the merge range) so reviewers have files to read.
  NB: this is distinct from the optional perf-`baseline`
  comparison in §4, which stays skill-guided prose and is not a manifest slice.
- `security` (conditional — only if `security_sensitive_paths` were touched):
  roles `[security-reviewer, process-auditor]`. Omitted otherwise (→ 2 slices).

### Loop commands

- `/dev-workflow:plan-review-loop [file]` — 1-slice, plan document. Cap 7.
- `/dev-workflow:code-review-loop` — 1-slice, uncommitted diff. Cap 7.
- `/dev-workflow:master-plan-review-loop` — `(1+K)`-slice for Large Task master
  plan. Cap 11.
- `/dev-workflow:integration-review-loop [--base REF] [--head REF]` — 2–3 slice
  cross-cut after WUs merge. Cap 9.

All share the same `review-loop-prompt.md` body and `check-approve.py` verifier;
they differ only in manifest builder, `mode` value, and stuck-exit threshold.

## 6. Per-project config (`.claude/dev-workflow.local.md`)

Committed file with YAML frontmatter, read once at skill Step 0 and by scripts
via `read-config.py` (§5).

```yaml
---
build:  "npm run build"
test:   "npm test"
lint:   "npm run lint"
typecheck: "npm run typecheck"   # optional
baseline: ""                      # optional perf-baseline command for Large tasks
scope_thresholds: { files: 5, loc: 1000, issues: 8, subsystems: 1 }
gates:
  pre_commit: [build, lint, test]
  merge_main: [build, lint, test, typecheck]
test_path_globs: ["tests/**", "**/*_test.*", "**/*.spec.*", "**/test_*"]
review:
  use_external_agents: false   # AUTHORITATIVE shipped default — /init scaffolds
                               # this as false. Flip to true only after the WU8
                               # smoke test confirms cross-plugin agent dispatch
                               # (§5 resolve-roles, §10).
  security_sensitive_paths: ["auth/**", "**/crypto*"]
---
# Free-form project notes the skill should respect.
```

- Names in `gates.*` (e.g. `build`, `lint`) reference the top-level command
  keys. A gate listing a key whose command is empty/undefined is skipped with a
  warning.
- Only `scope_thresholds.files` and `scope_thresholds.subsystems` are consumed
  mechanically (by `route-change.sh`). `scope_thresholds.loc` and
  `scope_thresholds.issues` are **skill-prose** scope-gate inputs only (§4 Step
  2) — they are not wired into any script.
- `test_path_globs` default list here is the canonical default; `route-change.sh`
  uses the identical list when config is absent.

### `/dev-workflow:init`

Scaffolds the config by auto-detecting the stack (peeks at `package.json`,
`Makefile`, `pyproject.toml`/`setup.py`, `Cargo.toml`, `go.mod`, etc.), writes a
draft `.claude/dev-workflow.local.md`, and asks the user to confirm/edit. This
is the only "detect" step; the result is persisted, not re-derived each session.

## 7. Hooks (`hooks/hooks.json` → two Python scripts)

Both advisory (non-blocking) by default, matching CYCAS. Both read config via
the shared `read-config.py` (§5). Hooks receive the project `cwd` in their JSON
input; project-relative reads (`.claude/dev-workflow.local.md`,
`.claude/ralph-loop.local.md`) resolve against that `cwd` (or use absolute
paths) rather than assuming the process working directory.

- **PreToolUse** (on `Edit`/`Write`): if the edited path matches
  `review.security_sensitive_paths`, surface a short generic reminder
  ("security-sensitive path — review auth/crypto/input-validation invariants")
  via the verified advisory shape
  `{"hookSpecificOutput": {"permissionDecision": "allow"}, "systemMessage": "…"}`.
  Silent fast-exit otherwise.
- **Stop:** pre-commit checklist reminder assembled from `gates.pre_commit`,
  emitted as `{"decision": "approve", "systemMessage": "…"}` (the documented
  Stop-hook shape; `"block"` with a `"reason"` is available but unused here).
  Defers silently when a `ralph-loop` is active in the current session
  (identical session-id check to CYCAS `stop.py`, reading
  `.claude/ralph-loop.local.md`), so review-loops aren't interrupted.

**Hook-format correction:** CYCAS's `pretooluse.py` emits a bare
`{"decision": "approve"}`, which matches **neither** the documented PreToolUse
shape (`hookSpecificOutput.permissionDecision`) **nor** the documented Stop
shape (`decision` + `reason`). This port deliberately uses the correct
PreToolUse shape per the plugin-dev hook-development reference — a small, safe
correction, not a verbatim port of the CYCAS hook body.

**Note on "enforcement":** CYCAS's hooks are advisory; real enforcement comes
from the review-fix loop's deterministic exit gate (`check-approve.py`) and the
skill's user-approval gates. This plugin matches that — the "enforcement hooks"
pillar is delivered as advisory reminders plus those hard gates, not as a
tool-blocking hook. **Optional blocking guard (deferred unless requested):** a
PreToolUse hook on `git commit` (a `Bash` tool call) can genuinely block by
emitting the verified shape
`{"hookSpecificOutput": {"permissionDecision": "deny"}, "systemMessage": "<why>"}`
(or exiting non-zero) when `gates.pre_commit` has not passed — the explanation
goes in `systemMessage`, not inside `hookSpecificOutput`. PreToolUse *can* deny
tool calls; this is a real mechanism (per the plugin-dev hook-development
reference), just out of scope for v1.

## 8. Dependencies

Claude Code plugins have **no declarative dependency field** in `plugin.json`
(verified: cycas's manifest has only name/version/description). "Dependency"
below means runtime/best-effort, not a platform-declared relationship.

- **`ralph-loop`** — required at runtime; the review-loop iteration engine.
  Located portably via `find-ralph.sh` (§5); loops error with an actionable
  message if it is absent.
- **`pr-review-toolkit`** — optional; if not installed or
  `review.use_external_agents: false`, `resolve-roles.py` substitutes
  plugin-owned reviewers. Checked at runtime, not declared.
- **`superpowers`** — optional; the skill delegates design/plan to it when
  present, else guides those phases inline.
- **`jq`, `git`, `python3`** — required by the manifest scripts and helpers.

## 9. Build-vs-reuse summary

| Component | Disposition |
|-----------|-------------|
| `check-approve.py` | Copy verbatim |
| `review-loop-prompt.md` | Copy; substitute `{{CHECK_APPROVE_PATH}}`, `{{REVIEW_DIR}}`, and `CYCAS-REVIEW-DONE`→`DEV-REVIEW-DONE` |
| `run-*-loop.sh` drivers | Copy, rename; repoint review dir, promise token, ralph locator, add resolve-roles step |
| `route-change.sh` | **New** — single routing table (extracted from cycas's two copies) |
| `read-config.py` | **New** — shared config reader (used by scripts + hooks) |
| `find-ralph.sh` | **New** — portable ralph-loop locator |
| `resolve-roles.py` | **New** — abstract role → concrete subagent_type manifest rewriter |
| `detect-review-type.sh` | **Rewrite** — calls `route-change.sh`; emits `mode: simple` |
| `build-master-plan-manifest.sh` | **Rewrite** — structural slice + per-WU slices via `route-change.sh`; emits `mode: master-plan` |
| `build-integration-manifest.sh` | **Rewrite** — generic 2–3 slice taxonomy; emits `mode: integration` |
| `process-auditor`, `structural-architect` agents | Port, strip CYCAS specifics |
| Generic fallback reviewers (correctness/security/test/type) | **New**, thin |
| `SKILL.md` + `work-unit-protocol.md` | **New**/ported backbone |
| `commands/workflow.md`, `commands/quality-gate.md` | Port from cycas, strip specifics |
| `commands/{plan,code,master-plan,integration}-review-loop.md` (4 files) | Port from cycas, rename; each is a thin wrapper invoking the matching `scripts/run-*-loop.sh` driver |
| `commands/init.md` + config schema | **New** |
| Hooks (`pretooluse.py`, `stop.py`, `hooks.json`) | Port, config-driven via `read-config.py` |
| pytest suites (`scripts/tests/*`) + fixtures | Port `test_check_approve.py`/`test_detect_review_type.py`/`test_build_*_manifest.py`; **new** `test_route_change.py`/`test_resolve_roles.py`/`test_read_config.py`; convert fixtures to generic paths. Part of every script's Work Unit (tests land with the code they cover). |

## 10. Scope note & open items

**Scope:** by this spec's own thresholds (≫5 files, multiple subsystems: skill,
commands, agents, hooks, scripts, config, tests) the plugin is itself a **Large
task**. The implementation plan (writing-plans phase) will decompose it into
Work Units — suggested partition: (WU1) verbatim/token-substituted core
(`check-approve.py`, prompt, drivers, `find-ralph.sh`) + tests; (WU2)
`route-change.sh` + `read-config.py` + `resolve-roles.py` + tests; (WU3) the
three rewritten manifest builders + tests; (WU4) agents; (WU5)
`SKILL.md` + `work-unit-protocol.md`; (WU6) commands + config + `/init`; (WU7)
hooks; (WU8) marketplace registration + end-to-end smoke test, **including a
test that dispatches one plugin-namespaced agent (e.g.
`pr-review-toolkit:code-reviewer`) to confirm cross-plugin `subagent_type`
dispatch actually works** — gating whether `use_external_agents` can default to
true.

**Open items (acceptable to defer to planning):**
- Exact type/interface change-detection heuristic (start conservative, tune
  with fixtures).
- Whether `pyyaml` is assumed present or a minimal frontmatter parser is bundled
  in `read-config.py`.
- Whether to ship the optional blocking commit guard (§7).
- `interface-coupling` boundary heuristic for the integration builder (start
  with interface-file matching; refine if needed).
