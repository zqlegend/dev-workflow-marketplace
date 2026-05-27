---
name: init
description: Scaffold the per-project .claude/dev-workflow.local.md config by detecting the stack, then confirm with the user
args: ""
allowed-tools:
  - "Read"
  - "Write"
  - "Bash"
---

# Initialize dev-workflow config

Scaffold `.claude/dev-workflow.local.md` for this project by auto-detecting the stack, drafting the config from the default template below, and asking the user to confirm or edit before writing. This is the only "detect" step — the result is persisted, not re-derived each session.

## Step 1: Don't clobber an existing config

If `.claude/dev-workflow.local.md` already exists, read it and tell the user it is already initialized. Offer to review/update specific keys instead of overwriting. Stop unless the user asks to regenerate.

## Step 2: Detect the stack

Peek at manifest files in the project root (use `Read`; absent files are fine) and infer the build/test/lint/typecheck commands:

- `package.json` → Node/JS/TS. Read its `scripts` to pick real commands (e.g. `build` → `npm run build`, `test` → `npm test`, `lint` → `npm run lint`, `typecheck` → `npm run typecheck` or `tsc --noEmit`). Prefer the actual script names present.
- `pyproject.toml` / `setup.py` → Python (e.g. build `python -m build`, test `pytest`, lint `ruff check .`, typecheck `mypy .`). Check for declared tools.
- `Cargo.toml` → Rust (build `cargo build`, test `cargo test`, lint `cargo clippy`, typecheck `cargo check`).
- `go.mod` → Go (build `go build ./...`, test `go test ./...`, lint `golangci-lint run`, typecheck `go vet ./...`).
- `Makefile` → use its targets if present (e.g. `make`, `make test`, `make lint`).

Use detected commands where confident; leave a key as `""` (empty) when unknown rather than guessing — empty gate keys are skipped with a warning.

## Step 3: Draft the config

Start from this default template (this is the authoritative §6 schema). Substitute the detected commands into `build`/`test`/`lint`/`typecheck`; adjust `test_path_globs` and `security_sensitive_paths` to the detected stack if obvious. Keep `review.use_external_agents: false` — it is the authoritative shipped default.

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

Notes for the draft:
- Names in `gates.*` reference the top-level command keys. A gate listing a key whose command is empty/undefined is skipped with a warning.
- Only `scope_thresholds.files` and `scope_thresholds.subsystems` are consumed mechanically (by routing). `loc` and `issues` are skill-prose scope-gate inputs.
- The `test_path_globs` default above is the canonical default; routing uses the identical list when config is absent.

## Step 4: Confirm with the user

Present the drafted config and the detected commands. Ask the user to confirm or edit (commands, thresholds, security-sensitive paths). Do NOT change `use_external_agents` to `true` here — leave it `false` (it should only be flipped after the cross-plugin agent dispatch is confirmed).

## Step 5: Write the file

After the user confirms, ensure `.claude/` exists and `Write` the agreed content to `.claude/dev-workflow.local.md`. Confirm the path, and tell the user this file should be committed so the workflow is reproducible. Mention they can re-run `/dev-workflow:quality-gate` to verify the gate commands work.
