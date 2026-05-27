You are iterating the dev-workflow Review-Fix Cycle. Follow this decision tree exactly.

Inputs:
  - Manifest: read `{{REVIEW_DIR}}/manifest.json` — a list of slices
              where each slice is {id, target (file list), roles (pair)}.
  - Last N:   highest integer M such that `{{REVIEW_DIR}}/iteration-M.md` exists.

Step 1 — Check previous verdict (deterministic, not judgment-based).
  If iteration-M.md exists:
    Run `{{CHECK_APPROVE_PATH}} iteration-M.md {{REVIEW_DIR}}/manifest.json`.
    The script exits 0 ONLY if:
      - iteration-M.md begins with header `slices_expected: [id1, id2, ...]`
        matching manifest.json's slice IDs exactly (order-insensitive).
      - Every expected slice has exactly two lines matching the anchored
        regex ^VERDICT: APPROVE$ (literal "APPROVE", no modifiers, no trailing
        text, no "CONDITIONAL APPROVE").
    If the script exits 0:
      → Output exactly: <promise>DEV-REVIEW-DONE</promise>
      → Stop. Do not dispatch more agents. Do not apply more fixes.
    If the script exits non-zero:
      → Continue to Step 2. Do NOT emit the promise.
  The promise emission is gated on the script's exit code, not on the
  model's own parse of iteration-M.md. This is a deterministic verifier;
  it is the ONLY permitted path to exit.

Step 2 — Apply fixes (if iteration-M.md exists with issues).
  Read iteration-M.md. For every CRITICAL and MAJOR finding across ALL slices:
    - Fix at the root cause (no clamping, no workaround, no suppression).
    - Reference the finding ID (slice_id.finding_id) in the edit.
  MINOR findings are non-blocking; skip unless you're editing that code anyway.
  Cross-slice findings (e.g., a finding against wu2 implies master_plan.md edits):
    - Apply the edit wherever it belongs. Record in iteration-M.md which slice's
      finding triggered it.
  If a finding is disputed: document rebuttal in iteration-M.md but do NOT
  emit the promise — the next reviewer pair must still agree.

Step 3 — Dispatch fresh reviewer pairs in parallel.
  For EACH slice that does NOT already have a carried-over APPROVE from the
  prior iteration (see "Partial-failure handling" below), dispatch 2 agents
  via the Agent tool. Send ALL Agent calls in a single message so they run
  concurrently.

  Concurrency cap: at most 8 Agent calls per message. If the slice count ×
  2 exceeds 8, chunk into sequential batches of 4 slices (8 agents). This
  is a hard limit — do not exceed it.

  For each slice:
    Agent 1: subagent_type = slice.roles[0]
    Agent 2: subagent_type = slice.roles[1]
    Prompt to each agent includes:
      - slice.target file list with instruction "read these full files"
      - slice_id for attribution
      - explicit verdict format (see below)

  Verdict format (enforced structurally):
    Each agent's response MUST begin with a line matching exactly one of:
      VERDICT: APPROVE
      VERDICT: CONDITIONAL APPROVE
      VERDICT: REJECT
    No leading whitespace, no additional text on that line. Findings follow
    on subsequent lines. The parser in Step 4 uses anchored regex
    `^VERDICT:\s+(APPROVE|CONDITIONAL APPROVE|REJECT)\s*$` to extract the
    verdict. Any other response shape is treated as "unparseable → REJECT
    for that slice".

  Fresh-agent guarantee: Claude Code's Agent tool dispatches a new subagent
  conversation per call with no shared state across calls — this is a
  runtime property, not a prompt constraint. You do not need to take any
  action to enforce freshness beyond calling Agent().

  Partial-failure handling (with freshness invalidation):
  If an agent errors or returns unparseable output, record verdict=REJECT
  for that slice (the failing agent only) and continue.

  Slice re-dispatch rule for iteration M+1:
    A slice is re-dispatched if ANY of:
      (a) it had any non-APPROVE verdict in iteration M, OR
      (b) Step 2 of this iteration modified ANY file that appears in the
          slice's target list (including read-only context files like
          master_plan.md), OR
      (c) this is integration mode and ANY file was modified this iteration
          (integration slices overlap by design; safest to always re-review).

  A slice is carried over (APPROVEd verdict copied verbatim into
  iteration-{M+1}.md) ONLY if none of (a),(b),(c) apply.

  Each reviewer returns, after the VERDICT line:
    Findings: {id, severity (CRITICAL|MAJOR|MINOR), file:line, issue, recommendation}
  Reviewers do not execute builds or tests; they Read/Grep/Glob only.

Step 4 — Persist verdicts (atomically, with embedded transcripts).

  Per-iteration nonce: generate a random 8-hex-char nonce for this iteration
  (e.g., `a7f3c2e9`). Before committing, scan all agent raw-response texts
  for the literal BEGIN-RAW-<nonce> or END-RAW-<nonce> substring. If found
  (probability ~2^-32 per response), regenerate.

  Build iteration-{M+1}.md in memory with the following structure:

    nonce: a7f3c2e9
    slices_expected: [id1, id2, ...]

    ## Slice: <id1>

    ### Reviewer 1 (<role>)
    VERDICT: APPROVE
    <!-- BEGIN-RAW-a7f3c2e9 -->
    <full verbatim text of the Agent()'s response, unchanged>
    <!-- END-RAW-a7f3c2e9 -->

    ### Reviewer 2 (<role>)
    VERDICT: APPROVE
    <!-- BEGIN-RAW-a7f3c2e9 -->
    <full verbatim response>
    <!-- END-RAW-a7f3c2e9 -->

    ## Slice: <id2>
    ...

  Atomic write protocol:
    1. Write to `{{REVIEW_DIR}}/iteration-{M+1}.md.tmp`.
    2. Verify: every expected slice_id has `## Slice:` section; every reviewer
       section has one `VERDICT:` line and one matched BEGIN/END raw block.
    3. Rename .tmp → iteration-{M+1}.md (single atomic rename).
    4. Replace {{REVIEW_DIR}}/latest.md with a symlink to iteration-{M+1}.md
       (rm -f latest.md; ln -sf iteration-{M+1}.md latest.md).
    5. Best-effort append to findings-index.md:
         iter={M+1}  slice_id  severity  file:line  hash(issue-text)

Step 4a — Convergence check.
  A "recurring finding" is one with the same (file:line, hash(issue-text))
  appearing in ≥2 of the last 3 iterations.

  Hash key rules:
    simple:       hash = (slice_id, file:line, hash(issue-text))
    master-plan:  slice_id stripped when file:line is in doc/task/master_plan.md
                  or doc/task/wu_status.md; else slice_id included.
    integration:  slice_id stripped globally.

  Per-mode stuck thresholds:
    simple:       iteration ≥ 6
    integration:  iteration ≥ 8
    master-plan:  iteration ≥ 10

  If 3+ recurring findings exist OR iteration ≥ threshold AND the latest
  iteration still had ≥1 non-APPROVE verdict:
    Write {{REVIEW_DIR}}/convergence-report.md summarizing recurring
    findings and outstanding verdicts grouped by slice, plus iteration
    history.
    Output exactly: <promise>DEV-REVIEW-DONE</promise>
    Stop.

Step 5 — Loop.
  Do NOT emit the promise this iteration — the next iteration will read the
  just-written verdicts and decide. Exit your turn normally; ralph will replay.

Hard rules:
  - Never emit <promise>DEV-REVIEW-DONE</promise> unless Step 1's
    check-approve.py exited 0, OR Step 4a fires.
  - Fresh Agent calls every iteration (runtime-enforced).
  - CONDITIONAL APPROVE = NOT APPROVED.
  - All slices must APPROVE for exit.
  - Root-cause discipline: no clamping, no table extension, no parameter
    tuning to silence findings.
  - Schema version: wrapping command pre-flight checks schema_version == 1;
    if somehow a mismatched manifest reaches here, write one-line error to
    convergence-report.md and emit the promise immediately.
