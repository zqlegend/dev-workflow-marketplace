---
build:  ""                       # no build step (plugin marketplace)
test:   "python3 -m pytest plugins/dev-workflow/scripts/tests -q"
lint:   ""                       # none configured
typecheck: ""                    # none configured
baseline: ""
scope_thresholds: { files: 5, loc: 1000, issues: 8, subsystems: 1 }
gates:
  pre_commit: [test]             # build/lint/typecheck empty -> omitted (would be skipped anyway)
  merge_main: [test]
test_path_globs: ["**/test_*.py", "**/*_test.py", "tests/**"]
review:
  use_external_agents: false     # authoritative default (cross-plugin dispatch validated, but /init leaves false)
  security_sensitive_paths: ["plugins/**/hooks/**"]   # editing hooks affects tool execution
---
# dev-workflow's own marketplace repo — Python helpers + bash scripts, pytest suite under
# plugins/dev-workflow/scripts/tests. No compile/lint step; the `test` gate runs the full suite.
