# Work Unit Protocol (Large Tasks)

Read this only when the scope gate (SKILL.md Step 2) classifies a task as
**Large** (any `scope_thresholds` exceeded). A Large task is decomposed into
**Work Units (WUs)** — small, independently reviewable, independently
committable slices — coordinated by a master plan.

The lifecycle is: **Master Plan → Master-Plan Review → User Gate → per-WU
lifecycle (for each WU) → Integration**.

All coordination artifacts live under `doc/task/`.

## Phase A — Master Plan

1. **Create the task directory** `doc/task/`.

2. **Baseline capture (OPTIONAL — only if config defines `baseline`).** If
   `.claude/dev-workflow.local.md` defines a non-empty `baseline` command, run
   it BEFORE writing the master plan and record the results in
   `doc/task/baseline.md` (used later for the integration regression check).
   This step is **skill-guided prose, not script-enforced** — no manifest
   builder reads `baseline.md`. If no `baseline` command is configured, skip
   this step entirely.

3. **Write `doc/task/master_plan.md`** containing:
   - **Objective and scope** — what the task delivers, what is out of scope.
   - **WU definitions** — one per Work Unit. Size limits:
     - **≤ 5 files preferred**,
     - **≤ 8 files** allowed only with a written justification,
     - **≤ 10 files** is the hard limit (never exceed).
     Each WU lists its objective and target files.
   - **Dependency DAG** — which WUs can run in parallel and which must
     serialize (WU-B depends on WU-A, etc.).
   - **Ownership for shared files** — when multiple WUs touch the same file,
     document non-overlapping function/region ownership so they don't collide.
   - **Global constraints and ordering rules** — anything that applies across
     WUs (naming, interface contracts, sequencing).

4. **Write `doc/task/wu_status.md`** — the dashboard. One row per WU with its
   status (e.g. `PENDING` / `PLAN` / `BUILD` / `REVIEW` / `TEST` / `DONE`) and
   the next action. This is the file SKILL.md Step 0 reads to resume a session.

5. **Write `doc/task/wu{N}_plan.md` for each WU** (`wu1_plan.md`,
   `wu2_plan.md`, …). Keep each plan tight (mechanical detail, ≈50 lines).
   **Each per-WU plan MUST declare its target files in a `TARGETS:` block** — see
   the next section. The master-plan review loop's builder parses these blocks
   to route a role-matched reviewer per WU; a missing or malformed block
   degrades the WU to the generic `correctness-reviewer`.

## The `TARGETS:` block (EXACT format — required in every `wu{N}_plan.md`)

`build-master-plan-manifest.sh` extracts each WU's target file list with this
parser:

```
awk '/^TARGETS:/{f=1;next} f&&NF{print} f&&!NF{exit}'
```

So the block MUST be, **verbatim**:

```
TARGETS:
src/foo.py
src/bar.py

```

Rules the parser enforces (match them exactly):

- A line that **starts with** `TARGETS:` turns capture on (the `TARGETS:` line
  itself is not captured).
- Every subsequent **non-blank** line is captured as one target file path (one
  path per line, no bullets, no indentation noise, no fences).
- The **first blank line** after `TARGETS:` terminates the block. Always put a
  blank line after the last target (or end the file) so the block closes
  cleanly.

**Any other format yields empty targets.** A `Files:` heading, a Markdown
bulleted list (`- src/foo.py`), or a fenced code block will NOT be parsed —
the WU then gets an empty target list and its per-WU slice silently degrades to
`R1=correctness-reviewer` with an empty `target` array (so reviewers have no
files to read). Use the exact `TARGETS:` block above.

## Phase B — Master-Plan Review (deterministic loop)

Run the partitioned review loop on the master plan:

```
/dev-workflow:master-plan-review-loop
```

This builds a `(1 + K)`-slice manifest (`mode: master-plan`, stuck-exit at
iter ≥ 10, cap 11):

- **Structural slice** (`id: structure`) — reviews `doc/task/master_plan.md` +
  `doc/task/wu_status.md` with roles `[structural-architect, process-auditor]`
  (WU boundaries, the DAG, completeness, ownership).
- **Per-WU slices** (`id: wu{N}`) — one per `doc/task/wu{N}_plan.md`. Reviewer 1
  is routed from that WU's `TARGETS:` files (e.g. `test-reviewer` for a
  test-only WU, `correctness-reviewer` for general code); Reviewer 2 is always
  `process-auditor`.

Fix every CRITICAL/MAJOR finding at the root cause, re-run (fresh reviewers),
and loop until every slice returns unconditional APPROVE, or until the
stuck-exit writes `convergence-report.md` (surface that to the user).

## Phase C — User Approval Gate

Present the approved master plan to the user. Approval can be **batched** for
independent WUs (those with no dependency edges between them). Do not start
BUILD on a WU until it is approved.

## Phase D — Per-WU Lifecycle

For each Work Unit, in dependency order:

```
Step 1: WU-PLAN     Read doc/task/wu{N}_plan.md (already reviewed in Phase B).
Step 2: USER GATE   Confirm approval (already done if batched in Phase C).
Step 3: BUILD       Implement only this WU's target files; respect ownership.
Step 4: REVIEW-FIX  /dev-workflow:code-review-loop on the WU's uncommitted diff.
                    Two fresh role-matched reviewers each iteration; fix at the
                    root cause; loop until unconditional APPROVE.
Step 5: TEST        Run the project's test/gate commands; add tests for new
                    behavior; all tests (new + existing) must pass.
Step 6: COMMIT      Atomic commit for this WU; update doc/task/wu_status.md
                    (mark the WU DONE, advance the next action).
```

Update `wu_status.md` at every transition so a future session can resume
(SKILL.md Step 0).

## Phase E — Integration (after all WUs are DONE)

1. **Full build + full test suite** across the integrated change.
2. **Regression check vs baseline** — only if `doc/task/baseline.md` was
   captured in Phase A; re-run the `baseline` command and compare. (This stays
   skill-guided prose; it is not a manifest slice.)
3. **Cross-cut review** of the merged diff:
   ```
   /dev-workflow:integration-review-loop [--base REF] [--head REF]
   ```
   This builds a 2–3 slice manifest (`mode: integration`, stuck-exit at
   iter ≥ 8, cap 9):
   - `interface-coupling` — subsystem-boundary / public-interface files;
     roles `[correctness-reviewer, structural-architect]` (always emitted).
   - `regression-consistency` — behavioral review over the whole merged diff
     (regressions + test coverage); roles `[process-auditor, test-reviewer]`
     (always emitted).
   - `security` — only if `review.security_sensitive_paths` were touched; roles
     `[security-reviewer, process-auditor]` (omitted otherwise).
4. **Deliver** — merge, document, and archive `doc/task/` once the integration
   review approves.
