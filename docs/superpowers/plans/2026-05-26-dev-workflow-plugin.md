# dev-workflow Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `dev-workflow`, a stack-agnostic Claude Code plugin that ports `cycas-workflow`'s disciplined dev lifecycle (scope gate → plan → review → build → review-fix loop → test → commit) into a config-driven, reusable form.

**Architecture:** Approach C (layered). The plugin owns the guiding skill, scope gate, Work Unit subsystem, deterministic review-loop automation, config layer, and hooks; it delegates design/plan to superpowers and code-correctness/security/test review to pr-review-toolkit (with plugin-owned fallbacks). One routing table (`route-change.py`) feeds all manifest builders. The review loop runs on `ralph-loop` and exits only when `check-approve.py` (deterministic verifier) passes.

**Tech Stack:** Bash (orchestration/git/jq), Python 3 + PyYAML (config + routing + role resolution + verifier), Markdown (skill/commands/agents), Claude Code plugin/marketplace conventions, ralph-loop, pr-review-toolkit.

**Spec:** `docs/superpowers/specs/2026-05-26-dev-workflow-plugin-design.md`

**Plugin root (PR):** `/Users/qingz/dev-workflow-marketplace/plugins/dev-workflow`
**Source to port from (CY):** `/Users/qingz/.claude/plugins/cache/cycas-local/cycas-workflow/1.0.0`

**Deliberate, contract-preserving deviations from spec (language only — interfaces unchanged):**
- `route-change.sh` → **`route-change.py`** and `read-config` → **`read-config.py`**: routing needs reliable glob matching and dominant-subsystem counting, which are error-prone in bash. The stdin→`ROLE1=`/`ROLE2=` contract and config-default behavior from the spec are preserved exactly; bash callers invoke `python3 route-change.py`.
- The PyYAML choice resolves spec §10's "pyyaml vs minimal parser" open item in favor of PyYAML (added to required deps); `read-config.py` fails with an actionable message if it is missing.

**Work Unit sequence (dependency order):** WU1 verifier+prompt+drivers+find-ralph → WU2 read-config+route-change+resolve-roles → WU3 manifest builders → WU4 agents → WU5 skill+WU-protocol → WU6 commands+config+init → WU7 hooks → WU8 marketplace+smoke test. Tests land with the code they cover.

---

## WU1 — Review-loop core: verifier, prompt, drivers, ralph locator

**Files:**
- Create: `PR/scripts/check-approve.py` (copied verbatim from `CY/scripts/check-approve.py`)
- Create: `PR/scripts/find-ralph.sh`
- Create: `PR/skills/dev-workflow/review-loop-prompt.md` (copied + tokenized from CY)
- Create: `PR/scripts/run-code-review-loop.sh`, `run-plan-review-loop.sh`, `run-master-plan-review-loop.sh`, `run-integration-review-loop.sh`
- Test: `PR/scripts/tests/test_check_approve.py` (ported from CY), `PR/scripts/tests/test_find_ralph.py`

- [ ] **Step 1: Scaffold plugin dir + manifest**

```bash
cd /Users/qingz/dev-workflow-marketplace
mkdir -p plugins/dev-workflow/{skills/dev-workflow,commands,agents,hooks,scripts/tests/fixtures}
cat > plugins/dev-workflow/.claude-plugin/plugin.json <<'JSON'
{
  "name": "dev-workflow",
  "version": "0.1.0",
  "description": "Stack-agnostic disciplined development workflow: scope gate, plan/code/master-plan/integration review-fix loops, Work Units, config-driven quality gates."
}
JSON
```
Note: `.claude-plugin/` must be created first (`mkdir -p plugins/dev-workflow/.claude-plugin`).

- [ ] **Step 2: Copy the verifier verbatim**

```bash
cd /Users/qingz/dev-workflow-marketplace
export CY=/Users/qingz/.claude/plugins/cache/cycas-local/cycas-workflow/1.0.0
cp "$CY/scripts/check-approve.py" plugins/dev-workflow/scripts/check-approve.py
chmod +x plugins/dev-workflow/scripts/check-approve.py
```
This file is domain-agnostic (verifies verdict structure only); no edits. NOTE: shell state does not persist between steps — re-run `export CY=...` at the start of any later step that uses `$CY` (Steps 3 and 9).

- [ ] **Step 3: Port the verifier test, point it at the copied script**

```bash
export CY=/Users/qingz/.claude/plugins/cache/cycas-local/cycas-workflow/1.0.0
cp "$CY/scripts/test_check_approve.py" plugins/dev-workflow/scripts/tests/test_check_approve.py
```
Then open it and ensure the path it invokes is `check-approve.py` in the parent dir. If it references a relative `../check-approve.py`, keep; if it hardcodes a cycas path, replace with:

```python
SCRIPT = Path(__file__).resolve().parents[1] / "check-approve.py"
```

- [ ] **Step 4: Run the ported verifier test — expect PASS**

```bash
cd plugins/dev-workflow/scripts && python3 -m pytest tests/test_check_approve.py -q
```
Expected: all PASS (the verifier is unchanged, so the ported suite passes as-is). If any fixture path is cycas-specific, fix the fixture path and re-run.

- [ ] **Step 5: Write the failing test for `find-ralph.sh`**

`PR/scripts/tests/test_find_ralph.py`:

```python
import os, subprocess, stat
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "find-ralph.sh"

def _make_fake_cache(tmp_path):
    # tmp/.claude/plugins/cache/<mkt>/dev-workflow/1.0.0/scripts/find-ralph.sh
    plugin_root = tmp_path / ".claude/plugins/cache/mkt/dev-workflow/1.0.0"
    (plugin_root / "scripts").mkdir(parents=True)
    # fake ralph-loop under the SAME cache root
    ralph = tmp_path / ".claude/plugins/cache/official/ralph-loop/2.0.0/scripts"
    ralph.mkdir(parents=True)
    setup = ralph / "setup-ralph-loop.sh"
    setup.write_text("#!/usr/bin/env bash\necho fake-ralph\n")
    setup.chmod(0o755)
    return plugin_root, setup

def test_locates_ralph_under_cache(tmp_path):
    plugin_root, setup = _make_fake_cache(tmp_path)
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin_root))
    out = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(setup)

def test_env_override_wins(tmp_path):
    plugin_root, _ = _make_fake_cache(tmp_path)
    override = tmp_path / "custom/scripts"
    override.mkdir(parents=True)
    setup = override / "setup-ralph-loop.sh"; setup.write_text("x"); setup.chmod(0o755)
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin_root),
               RALPH_LOOP_ROOT=str(override.parent))
    out = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == str(setup)

def test_errors_when_absent(tmp_path):
    plugin_root = tmp_path / ".claude/plugins/cache/mkt/dev-workflow/1.0.0"
    (plugin_root / "scripts").mkdir(parents=True)
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(plugin_root))
    env.pop("RALPH_LOOP_ROOT", None)
    out = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
    assert out.returncode != 0
    assert "ralph-loop" in out.stderr.lower()
```

- [ ] **Step 6: Run it — expect FAIL** (`find-ralph.sh` not created)

```bash
python3 -m pytest tests/test_find_ralph.py -q
```
Expected: FAIL (No such file / non-zero from missing script).

- [ ] **Step 7: Implement `find-ralph.sh`**

`PR/scripts/find-ralph.sh`:

```bash
#!/usr/bin/env bash
# Print the absolute path to ralph-loop's setup-ralph-loop.sh, or error.
set -euo pipefail

# 1) explicit override
if [[ -n "${RALPH_LOOP_ROOT:-}" ]]; then
  cand=$(ls "$RALPH_LOOP_ROOT"/*/scripts/setup-ralph-loop.sh 2>/dev/null | sort -V | tail -1 || true)
  [[ -z "$cand" ]] && cand="$RALPH_LOOP_ROOT/scripts/setup-ralph-loop.sh"
  if [[ -f "$cand" ]]; then echo "$cand"; exit 0; fi
fi

# 2) derive cache root from this plugin's own root and glob
if [[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]]; then
  echo "find-ralph: CLAUDE_PLUGIN_ROOT unset and RALPH_LOOP_ROOT not found" >&2
  exit 2
fi
cache_root=$(dirname "$(dirname "$(dirname "$CLAUDE_PLUGIN_ROOT")")")  # .../plugins/cache
cand=$(ls "$cache_root"/*/ralph-loop/*/scripts/setup-ralph-loop.sh 2>/dev/null | sort -V | tail -1 || true)
if [[ -n "$cand" && -f "$cand" ]]; then echo "$cand"; exit 0; fi

echo "find-ralph: ralph-loop setup script not found under $cache_root. Install the ralph-loop plugin or set RALPH_LOOP_ROOT." >&2
exit 1
```

```bash
chmod +x plugins/dev-workflow/scripts/find-ralph.sh
```

- [ ] **Step 8: Run the test — expect PASS**

```bash
python3 -m pytest tests/test_find_ralph.py -q
```
Expected: 3 PASS.

- [ ] **Step 9: Port + tokenize the loop prompt**

```bash
export CY=/Users/qingz/.claude/plugins/cache/cycas-local/cycas-workflow/1.0.0
cp "$CY/skills/cycas-workflow/review-loop-prompt.md" plugins/dev-workflow/skills/dev-workflow/review-loop-prompt.md
cd plugins/dev-workflow/skills/dev-workflow
# inject {{REVIEW_DIR}} (no trailing slash) and rename the completion promise
sed -i '' -e 's#\.claude/cycas-review#{{REVIEW_DIR}}#g' \
          -e 's#CYCAS-REVIEW-DONE#DEV-REVIEW-DONE#g' review-loop-prompt.md
cd -
```
Verify zero leftovers:

```bash
grep -c 'cycas-review\|CYCAS-REVIEW-DONE' plugins/dev-workflow/skills/dev-workflow/review-loop-prompt.md
```
Expected: `0`. Confirm `{{CHECK_APPROVE_PATH}}` is still present (pre-existing token, untouched):

```bash
grep -c '{{CHECK_APPROVE_PATH}}' plugins/dev-workflow/skills/dev-workflow/review-loop-prompt.md
```
Expected: `>= 1`. (On Linux use `sed -i` without the `''`.)

- [ ] **Step 10: Commit WU1 part A**

```bash
cd /Users/qingz/dev-workflow-marketplace
git add plugins/dev-workflow/.claude-plugin plugins/dev-workflow/scripts/check-approve.py \
  plugins/dev-workflow/scripts/find-ralph.sh plugins/dev-workflow/scripts/tests/test_check_approve.py \
  plugins/dev-workflow/scripts/tests/test_find_ralph.py \
  plugins/dev-workflow/skills/dev-workflow/review-loop-prompt.md
git commit -m "feat(dev-workflow): WU1 verifier, find-ralph, tokenized loop prompt"
```

- [ ] **Step 11: Write the four `run-*-loop.sh` drivers**

Each driver: (a) precondition check, (b) build its manifest, (c) preflight `schema_version==1`, (d) `resolve-roles.py` on the manifest (WU2 — guard if absent), (e) render the prompt with both tokens substituted, (f) hand to ralph via `find-ralph.sh`. Template — `PR/scripts/run-code-review-loop.sh` (the other three differ only in the manifest-build line, promise stays `DEV-REVIEW-DONE`, and `--max-iterations`):

```bash
#!/usr/bin/env bash
set -euo pipefail
[[ -z "${CLAUDE_PLUGIN_ROOT:-}" ]] && { echo "CLAUDE_PLUGIN_ROOT unset" >&2; exit 2; }
ROOT="$CLAUDE_PLUGIN_ROOT"
REVIEW_DIR=".claude/dev-review"          # must match {{REVIEW_DIR}} substitution
PROMISE="DEV-REVIEW-DONE"
MAXIT=7

FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done

# (a) require a non-empty uncommitted diff (working-tree OR staged)
if git diff --quiet HEAD -- . 2>/dev/null && git diff --quiet --cached 2>/dev/null; then
  echo "ERROR: no uncommitted changes to review." >&2; exit 1
fi
if [[ -f ".claude/ralph-loop.local.md" && $FORCE -eq 0 ]]; then
  echo "ERROR: prior loop state exists (.claude/ralph-loop.local.md). Use --force." >&2; exit 1
fi
mkdir -p "$REVIEW_DIR"

# (b) build the 1-slice code manifest
"$ROOT/scripts/detect-review-type.sh" code --force

# (c) preflight schema
SCHEMA=$(jq -r '.schema_version' "$REVIEW_DIR/manifest.json")
[[ "$SCHEMA" != "1" ]] && { echo "ERROR: manifest schema_version=$SCHEMA, expected 1" >&2; exit 1; }

# (d) resolve abstract roles -> concrete subagent_type (no-op if helper absent yet)
[[ -f "$ROOT/scripts/resolve-roles.py" ]] && python3 "$ROOT/scripts/resolve-roles.py" "$REVIEW_DIR/manifest.json"

# (e) render prompt: substitute BOTH tokens with LITERAL replacement (python str.replace,
# so a '&' or '\' in $CHECK can't corrupt the output as it would with awk/sed gsub)
CHECK="$ROOT/scripts/check-approve.py"
PROMPT_FILE=$(mktemp -t dev-loop-prompt.XXXXXX)
python3 - "$ROOT/skills/dev-workflow/review-loop-prompt.md" "$CHECK" "$REVIEW_DIR" > "$PROMPT_FILE" <<'PY'
import sys
src, chk, rdir = sys.argv[1], sys.argv[2], sys.argv[3]
sys.stdout.write(open(src).read()
                 .replace("{{CHECK_APPROVE_PATH}}", chk)
                 .replace("{{REVIEW_DIR}}", rdir))
PY

# (f) hand to ralph-loop
RALPH=$("$ROOT/scripts/find-ralph.sh")
"$RALPH" "$(cat "$PROMPT_FILE")" --completion-promise "$PROMISE" --max-iterations "$MAXIT"
rm -f "$PROMPT_FILE"
echo "Ralph-loop initialized (mode: code-review). Begin iteration 1."
```

The code-review driver above keeps the uncommitted-diff precondition. The other
three drivers share steps (c)–(f) verbatim but have DIFFERENT `MAXIT`, arg
grammar, precondition (a), and build line (b). Each driver parses `--force` by
scanning all args (as in the template); none uses positional `$1` for `--force`.
Write each precondition + build block explicitly:

- **`run-plan-review-loop.sh`** — `MAXIT=7`. Args: `[--force] [<plan-path>]` — the
  first non-flag arg is the plan path (default `doc/current_plan.md`):
  ```bash
  PLAN="doc/current_plan.md"
  for a in "$@"; do [[ "$a" != --* ]] && PLAN="$a"; done
  ```
  Precondition (a): `[[ -f "$PLAN" ]] || { echo "ERROR: plan file not found: $PLAN" >&2; exit 1; }`
  Build line (b): `"$ROOT/scripts/detect-review-type.sh" plan "$PLAN" --force`
- **`run-master-plan-review-loop.sh`** — `MAXIT=11`. Args: `[--force]`.
  Precondition (a): `[[ -f "doc/task/master_plan.md" ]] || { echo "ERROR: doc/task/master_plan.md not found" >&2; exit 1; }`
  Build line (b): `"$ROOT/scripts/build-master-plan-manifest.sh" --force`
- **`run-integration-review-loop.sh`** — `MAXIT=9`. Args: `[--force] [--base REF] [--head REF]` —
  parse explicitly so flags don't collide:
  ```bash
  BASE="main"; HEAD="HEAD"
  while [[ $# -gt 0 ]]; do case "$1" in
    --base) BASE="$2"; shift 2;; --head) HEAD="$2"; shift 2;;
    --force) shift;; *) shift;; esac; done
  ```
  Precondition (a): validate refs — `git rev-parse --verify -q "$BASE" >/dev/null && git rev-parse --verify -q "$HEAD" >/dev/null || { echo "ERROR: bad --base/--head ref" >&2; exit 1; }` (no uncommitted-diff check).
  Build line (b): `BASE="$BASE" HEAD="$HEAD" "$ROOT/scripts/build-integration-manifest.sh" --force`
  (the builder reads `$BASE`/`$HEAD` from the environment — see WU3 Step 10).

```bash
chmod +x plugins/dev-workflow/scripts/run-*.sh
```

- [ ] **Step 12: Smoke-check driver wiring (preconditions only)**

The builders don't exist until WU3, so just lint syntax and the no-change guard:

```bash
bash -n plugins/dev-workflow/scripts/run-code-review-loop.sh   # syntax OK = exit 0
```
Expected: exit 0 (no syntax errors). Full driver execution is exercised in WU8.

- [ ] **Step 13: Commit WU1 part B**

```bash
git add plugins/dev-workflow/scripts/run-*.sh
git commit -m "feat(dev-workflow): WU1 four review-loop drivers (token sub, find-ralph, resolve-roles hook)"
```

---

## WU2 — Helpers: read-config.py, route-change.py, resolve-roles.py

**Files:**
- Create: `PR/scripts/read-config.py`, `PR/scripts/route-change.py`, `PR/scripts/resolve-roles.py`
- Test: `PR/scripts/tests/test_read_config.py`, `test_route_change.py`, `test_resolve_roles.py`

- [ ] **Step 1: Write failing tests for `read-config.py`**

`PR/scripts/tests/test_read_config.py`:

```python
import os, subprocess, textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "read-config.py"

CONFIG = textwrap.dedent('''\
    ---
    build: "npm run build"
    scope_thresholds: { files: 5, loc: 1000, issues: 8, subsystems: 1 }
    test_path_globs: ["tests/**", "**/*_test.*"]
    review:
      use_external_agents: false
      security_sensitive_paths: ["auth/**", "**/crypto*"]
    ---
    # notes
    ''')

def run(key, *rest, cwd):
    return subprocess.run(["python3", str(SCRIPT), key, *rest],
                          cwd=cwd, capture_output=True, text=True)

def _proj(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/dev-workflow.local.md").write_text(CONFIG)
    return tmp_path

def test_scalar(tmp_path):
    p = _proj(tmp_path)
    assert run("build", cwd=p).stdout.strip() == "npm run build"

def test_dotted_map(tmp_path):
    p = _proj(tmp_path)
    assert run("scope_thresholds.files", cwd=p).stdout.strip() == "5"

def test_bool_lowercased(tmp_path):
    p = _proj(tmp_path)
    assert run("review.use_external_agents", cwd=p).stdout.strip() == "false"

def test_list_newline_joined(tmp_path):
    p = _proj(tmp_path)
    out = run("review.security_sensitive_paths", cwd=p).stdout.strip().splitlines()
    assert out == ["auth/**", "**/crypto*"]

def test_missing_key_uses_default(tmp_path):
    p = _proj(tmp_path)
    r = run("nope.key", "DEFLT", cwd=p)
    assert r.returncode == 0 and r.stdout.strip() == "DEFLT"

def test_missing_key_no_default_exits_3(tmp_path):
    p = _proj(tmp_path)
    assert run("nope.key", cwd=p).returncode == 3

def test_no_config_uses_default(tmp_path):
    r = run("build", "FB", cwd=tmp_path)   # no .claude/ dir
    assert r.returncode == 0 and r.stdout.strip() == "FB"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
cd plugins/dev-workflow/scripts && python3 -m pytest tests/test_read_config.py -q
```
Expected: FAIL (script missing).

- [ ] **Step 3: Implement `read-config.py`**

```python
#!/usr/bin/env python3
"""Read a dotted key from .claude/dev-workflow.local.md YAML frontmatter.

Usage: read-config.py <dotted.key> [default]
  - prints the value (lists newline-joined; bools as true/false)
  - key absent + default given  -> print default, exit 0
  - key absent + no default     -> exit 3
  - config file absent + default-> print default, exit 0
  - config file absent + none   -> exit 3
  - PyYAML missing              -> exit 4 (actionable message)
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.stderr.write("dev-workflow: PyYAML required (pip install pyyaml)\n")
    sys.exit(4)

CONFIG = Path(".claude/dev-workflow.local.md")

def load_frontmatter(path):
    text = path.read_text()
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}

_MISSING = object()

def dig(data, dotted):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur

def emit(val):
    if isinstance(val, list):
        print("\n".join(str(x) for x in val))
    elif isinstance(val, bool):
        print("true" if val else "false")
    else:
        print(val)

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: read-config.py <dotted.key> [default]\n")
        sys.exit(2)
    key = sys.argv[1]
    default = sys.argv[2] if len(sys.argv) > 2 else None

    if not CONFIG.is_file():
        if default is not None:
            print(default); return
        sys.exit(3)

    val = dig(load_frontmatter(CONFIG), key)
    if val is _MISSING:
        if default is not None:
            print(default); return
        sys.exit(3)
    emit(val)

if __name__ == "__main__":
    main()
```

```bash
chmod +x read-config.py
```

- [ ] **Step 4: Run — expect PASS**

```bash
python3 -m pytest tests/test_read_config.py -q
```
Expected: 7 PASS. (Requires PyYAML: `python3 -c "import yaml"`; if it errors, `pip install pyyaml`.)

- [ ] **Step 5: Commit**

```bash
cd /Users/qingz/dev-workflow-marketplace
git add plugins/dev-workflow/scripts/read-config.py plugins/dev-workflow/scripts/tests/test_read_config.py
git commit -m "feat(dev-workflow): WU2 read-config.py (YAML frontmatter reader)"
```

- [ ] **Step 6: Write failing tests for `route-change.py`**

`PR/scripts/tests/test_route_change.py` — covers the five rows + `--no-cross-cut` + empty input. Run with NO config present (defaults apply), except the security test which writes one.

```python
import os, subprocess, textwrap
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "route-change.py"

def route(files, *flags, cwd=None):
    r = subprocess.run(["python3", str(SCRIPT), *flags],
                       input="\n".join(files), capture_output=True, text=True,
                       cwd=cwd or str(Path.cwd()))
    return r

def parse(r):
    d = {}
    for line in r.stdout.strip().splitlines():
        k, _, v = line.partition("=")
        d[k] = v
    return d

def test_default_general_code(tmp_path):
    d = parse(route(["src/app.py"], cwd=tmp_path))
    assert d == {"ROLE1": "correctness-reviewer", "ROLE2": "process-auditor"}

def test_test_only(tmp_path):
    d = parse(route(["tests/test_x.py", "src/foo_test.py"], cwd=tmp_path))
    assert d["ROLE1"] == "test-reviewer" and d["ROLE2"] == "process-auditor"

def test_cross_cutting_by_file_count(tmp_path):
    files = [f"src/f{i}.py" for i in range(6)]   # > default files threshold (5)
    d = parse(route(files, cwd=tmp_path))
    assert d == {"ROLE1": "correctness-reviewer", "ROLE2": "structural-architect"}

def test_cross_cutting_by_subsystems(tmp_path):
    d = parse(route(["a/x.py", "b/y.py"], cwd=tmp_path))  # 2 top dirs > subsystems(1)
    assert d["ROLE2"] == "structural-architect"

def test_no_cross_cut_falls_through_to_default(tmp_path):
    files = [f"src/f{i}.py" for i in range(6)]
    d = parse(route(files, "--no-cross-cut", cwd=tmp_path))
    assert d == {"ROLE1": "correctness-reviewer", "ROLE2": "process-auditor"}

def test_security_paths(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/dev-workflow.local.md").write_text(textwrap.dedent('''\
        ---
        review:
          security_sensitive_paths: ["auth/**"]
        ---
        '''))
    d = parse(route(["auth/login.py", "src/app.py"], cwd=tmp_path))
    assert d == {"ROLE1": "security-reviewer", "ROLE2": "process-auditor"}

def test_empty_input_exits_2(tmp_path):
    assert route([], cwd=tmp_path).returncode == 2

def test_always_two_lines(tmp_path):
    r = route(["src/app.py"], cwd=tmp_path)
    assert len([l for l in r.stdout.strip().splitlines() if l.startswith("ROLE")]) == 2
```

- [ ] **Step 7: Run — expect FAIL**

```bash
python3 -m pytest tests/test_route_change.py -q
```
Expected: FAIL (script missing).

- [ ] **Step 8: Implement `route-change.py`**

Reads stdin file list, reads config via the sibling `read-config.py` (subprocess, so default-handling stays in one place), applies the five-row table in priority order, prints `ROLE1=`/`ROLE2=`.

```python
#!/usr/bin/env python3
"""Route a change (file list on stdin) to a reviewer role pair.

Output: two lines, `ROLE1=<role>` then `ROLE2=<role>` (abstract vocabulary).
Exit: 0 success; 2 empty input.
Flag: --no-cross-cut  skips the cross-cutting row (per-WU caller).
"""
import fnmatch, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RC = HERE / "read-config.py"

DEFAULT_TEST_GLOBS = ["tests/**", "**/*_test.*", "**/*.spec.*", "**/test_*"]

def cfg(key, default):
    r = subprocess.run(["python3", str(RC), key, default],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return default
    return r.stdout.rstrip("\n")

def cfg_list(key, default_list):
    r = subprocess.run(["python3", str(RC), key],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return default_list
    return [l for l in r.stdout.strip().splitlines() if l]

def gmatch(path, glob):
    # support a trailing /** as "this dir and anything under it"
    if glob.endswith("/**"):
        base = glob[:-3]
        return path == base or path.startswith(base + "/")
    return fnmatch.fnmatch(path, glob)

def main():
    args = sys.argv[1:]
    no_cross_cut = "--no-cross-cut" in args
    files = [l.strip() for l in sys.stdin.read().splitlines() if l.strip()]
    if not files:
        sys.stderr.write("route-change: empty input\n"); sys.exit(2)

    sec = cfg_list("review.security_sensitive_paths", [])
    tglobs = cfg_list("test_path_globs", DEFAULT_TEST_GLOBS)
    max_files = int(cfg("scope_thresholds.files", "5"))
    max_subs = int(cfg("scope_thresholds.subsystems", "1"))

    def is_test(f): return any(gmatch(f, g) for g in tglobs)
    def is_sec(f):  return any(gmatch(f, g) for g in sec)
    def is_type(f):
        low = f.lower()
        return (f.endswith(".d.ts") or f.endswith(".proto")
                or "types" in low or "interface" in low)

    top_dirs = {f.split("/")[0] for f in files if "/" in f}
    cross_cutting = (len(top_dirs) > max_subs) or (len(files) > max_files)

    # priority order
    if any(is_sec(f) for f in files):
        r1, r2 = "security-reviewer", "process-auditor"
    elif all(is_test(f) for f in files):
        r1, r2 = "test-reviewer", "process-auditor"
    elif all(is_type(f) for f in files):
        r1, r2 = "type-design-reviewer", "process-auditor"
    elif cross_cutting and not no_cross_cut:
        r1, r2 = "correctness-reviewer", "structural-architect"
    else:
        r1, r2 = "correctness-reviewer", "process-auditor"

    print(f"ROLE1={r1}")
    print(f"ROLE2={r2}")

if __name__ == "__main__":
    main()
```

```bash
chmod +x route-change.py
```

- [ ] **Step 9: Run — expect PASS**

```bash
python3 -m pytest tests/test_route_change.py -q
```
Expected: 8 PASS.

- [ ] **Step 10: Commit**

```bash
cd /Users/qingz/dev-workflow-marketplace
git add plugins/dev-workflow/scripts/route-change.py plugins/dev-workflow/scripts/tests/test_route_change.py
git commit -m "feat(dev-workflow): WU2 route-change.py (single change-shape router)"
```

- [ ] **Step 11: Write failing tests for `resolve-roles.py`**

`PR/scripts/tests/test_resolve_roles.py`:

```python
import json, os, subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "resolve-roles.py"

def write_manifest(p, roles):
    m = {"schema_version": 1, "mode": "simple",
         "slices": [{"id": "default", "target": ["a.py"], "roles": roles}]}
    (p / "m.json").write_text(json.dumps(m))
    return p / "m.json"

def run(manifest, *, external_present, use_external, cwd):
    # fake plugins-root: cwd/.claude/plugins/installed_plugins.json
    reg = cwd / ".claude/plugins"
    reg.mkdir(parents=True, exist_ok=True)
    plugins = {"pr-review-toolkit@x": [{}]} if external_present else {}
    (reg / "installed_plugins.json").write_text(json.dumps(plugins))
    # CLAUDE_PLUGIN_ROOT = cwd/.claude/plugins/cache/mkt/dev-workflow/1.0.0
    pr = reg / "cache/mkt/dev-workflow/1.0.0"; pr.mkdir(parents=True, exist_ok=True)
    # config controlling use_external_agents
    proj = cwd / "proj"; (proj / ".claude").mkdir(parents=True, exist_ok=True)
    (proj / ".claude/dev-workflow.local.md").write_text(
        f"---\nreview:\n  use_external_agents: {str(use_external).lower()}\n---\n")
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(pr))
    return subprocess.run(["python3", str(SCRIPT), str(manifest)],
                          env=env, cwd=str(proj), capture_output=True, text=True)

def roles_of(manifest):
    return json.loads(Path(manifest).read_text())["slices"][0]["roles"]

def test_external_resolution(tmp_path):
    m = write_manifest(tmp_path, ["correctness-reviewer", "process-auditor"])
    run(m, external_present=True, use_external=True, cwd=tmp_path)
    assert roles_of(m) == ["pr-review-toolkit:code-reviewer", "dev-workflow:process-auditor"]

def test_fallback_when_disabled(tmp_path):
    m = write_manifest(tmp_path, ["correctness-reviewer", "security-reviewer"])
    run(m, external_present=True, use_external=False, cwd=tmp_path)
    assert roles_of(m) == ["dev-workflow:correctness-reviewer", "dev-workflow:security-reviewer"]

def test_fallback_when_absent(tmp_path):
    m = write_manifest(tmp_path, ["test-reviewer", "process-auditor"])
    run(m, external_present=False, use_external=True, cwd=tmp_path)
    assert roles_of(m) == ["dev-workflow:test-reviewer", "dev-workflow:process-auditor"]

def test_idempotent(tmp_path):
    m = write_manifest(tmp_path, ["correctness-reviewer", "process-auditor"])
    run(m, external_present=True, use_external=True, cwd=tmp_path)
    first = roles_of(m)
    run(m, external_present=True, use_external=True, cwd=tmp_path)
    assert roles_of(m) == first   # already-namespaced roles unchanged
```

- [ ] **Step 12: Run — expect FAIL**

```bash
python3 -m pytest tests/test_resolve_roles.py -q
```
Expected: FAIL (script missing).

- [ ] **Step 13: Implement `resolve-roles.py`**

```python
#!/usr/bin/env python3
"""Rewrite a manifest's abstract roles into concrete subagent_type strings.

Usage: resolve-roles.py <manifest.json>
Static, idempotent: only roles still in the abstract vocabulary are rewritten.
External agents used only if pr-review-toolkit is installed AND
review.use_external_agents is true; otherwise plugin-owned fallbacks.
"""
import json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RC = HERE / "read-config.py"

OWNED = {"process-auditor", "structural-architect",
         "correctness-reviewer", "security-reviewer",
         "test-reviewer", "type-design-reviewer"}

EXTERNAL = {
    "correctness-reviewer": "pr-review-toolkit:code-reviewer",
    "security-reviewer":   "pr-review-toolkit:silent-failure-hunter",
    "test-reviewer":       "pr-review-toolkit:pr-test-analyzer",
    "type-design-reviewer":"pr-review-toolkit:type-design-analyzer",
}
ALWAYS_OWNED = {"process-auditor", "structural-architect"}

def use_external():
    r = subprocess.run(["python3", str(RC), "review.use_external_agents", "false"],
                       capture_output=True, text=True)
    return r.stdout.strip() == "true"

def pr_toolkit_installed():
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not root:
        return False
    # plugins-root = parent of cache_root = 4 dirname hops from CLAUDE_PLUGIN_ROOT
    plugins_root = Path(root).parents[3]   # .../.claude/plugins
    reg = plugins_root / "installed_plugins.json"
    if not reg.is_file():
        return False
    try:
        data = json.loads(reg.read_text())
    except Exception:
        return False
    return any(k.split("@")[0] == "pr-review-toolkit" for k in data)

def resolve(role, external_ok):
    if role in ALWAYS_OWNED:
        return f"dev-workflow:{role}"
    if role in OWNED:
        if external_ok and role in EXTERNAL:
            return EXTERNAL[role]
        return f"dev-workflow:{role}"
    return role   # already concrete -> idempotent no-op

def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: resolve-roles.py <manifest.json>\n"); sys.exit(2)
    path = Path(sys.argv[1])
    manifest = json.loads(path.read_text())
    external_ok = use_external() and pr_toolkit_installed()
    for sl in manifest.get("slices", []):
        sl["roles"] = [resolve(r, external_ok) for r in sl.get("roles", [])]
    path.write_text(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
```

```bash
chmod +x resolve-roles.py
```

- [ ] **Step 14: Run — expect PASS**

```bash
python3 -m pytest tests/test_resolve_roles.py -q
```
Expected: 4 PASS. Then run the whole suite: `python3 -m pytest -q` → all green.

- [ ] **Step 15: Commit**

```bash
cd /Users/qingz/dev-workflow-marketplace
git add plugins/dev-workflow/scripts/resolve-roles.py plugins/dev-workflow/scripts/tests/test_resolve_roles.py
git commit -m "feat(dev-workflow): WU2 resolve-roles.py (abstract->concrete role rewriter)"
```

---

## WU3 — Manifest builders

**Files:**
- Create: `PR/scripts/detect-review-type.sh`, `build-master-plan-manifest.sh`, `build-integration-manifest.sh`
- Test: `PR/scripts/tests/test_detect_review_type.py`, `test_build_master_plan_manifest.py`, `test_build_integration_manifest.py`

All three emit `.claude/dev-review/manifest.json` with `schema_version: 1` and call `python3 route-change.py` for routing (no inline routing tables).

- [ ] **Step 1: Failing test for `detect-review-type.sh` (code + plan modes)**

`test_detect_review_type.py` (excerpt — full version covers both modes + schema):

```python
import json, os, subprocess
from pathlib import Path
SCRIPT = Path(__file__).resolve().parents[1] / "detect-review-type.sh"

def init_repo(tmp_path):
    subprocess.run(["git","init","-q"], cwd=tmp_path, check=True)
    subprocess.run(["git","config","user.email","t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git","config","user.name","t"], cwd=tmp_path, check=True)
    (tmp_path/"base.py").write_text("x=1\n")
    subprocess.run(["git","add","-A"], cwd=tmp_path, check=True)
    subprocess.run(["git","commit","-qm","init"], cwd=tmp_path, check=True)

def test_code_mode_routes_via_router(tmp_path):
    init_repo(tmp_path)
    (tmp_path/"src.py").write_text("y=2\n")
    subprocess.run(["git","add","-A"], cwd=tmp_path, check=True)
    r = subprocess.run(["bash",str(SCRIPT),"code","--force"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    m = json.loads((tmp_path/".claude/dev-review/manifest.json").read_text())
    assert m["schema_version"] == 1 and m["mode"] == "simple"
    assert m["slices"][0]["roles"] == ["correctness-reviewer","process-auditor"]

def test_plan_mode_fixed_roles(tmp_path):
    init_repo(tmp_path)
    (tmp_path/"plan.md").write_text("# plan\n")
    r = subprocess.run(["bash",str(SCRIPT),"plan","plan.md","--force"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    m = json.loads((tmp_path/".claude/dev-review/manifest.json").read_text())
    assert m["slices"][0]["roles"] == ["structural-architect","process-auditor"]
```

- [ ] **Step 2: Run — expect FAIL.** `python3 -m pytest tests/test_detect_review_type.py -q` → FAIL.

- [ ] **Step 3: Implement `detect-review-type.sh`**

```bash
#!/usr/bin/env bash
# Build the 1-slice (mode: simple) manifest for plan/code review loops.
# Usage: detect-review-type.sh <code|plan [path]> [--force]
set -euo pipefail
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }
command -v git >/dev/null || { echo "git required" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=".claude/dev-review"; MANIFEST="$OUT/manifest.json"; mkdir -p "$OUT"

MODE="${1:-}"; FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done
[[ -z "$MODE" ]] && { echo "usage: $0 <code|plan [path]> [--force]" >&2; exit 2; }
[[ -f "$MANIFEST" && $FORCE -eq 0 ]] && { echo "manifest exists; use --force" >&2; exit 1; }

if [[ "$MODE" == "code" ]]; then
  # capture BOTH working-tree and staged changes vs HEAD, deduplicated
  mapfile -t CHANGED < <({ git diff --name-only HEAD; git diff --cached --name-only; } 2>/dev/null | sort -u)
  [[ ${#CHANGED[@]} -eq 0 ]] && { echo "no changed files" >&2; exit 2; }
  read R1 R2 < <(printf '%s\n' "${CHANGED[@]}" | python3 "$HERE/route-change.py" \
                 | awk -F= '/ROLE1/{r1=$2} /ROLE2/{r2=$2} END{print r1, r2}')
  TARGETS=("${CHANGED[@]}")
elif [[ "$MODE" == "plan" ]]; then
  PLAN="${2:-doc/current_plan.md}"
  R1="structural-architect"; R2="process-auditor"
  TARGETS=("$PLAN")
else
  echo "unknown mode: $MODE" >&2; exit 2
fi

TARGET_JSON=$(printf '%s\n' "${TARGETS[@]}" | jq -R . | jq -s .)
jq -n --argjson target "$TARGET_JSON" --arg r1 "$R1" --arg r2 "$R2" \
  '{schema_version:1, mode:"simple",
    slices:[{id:"default", target:$target, roles:[$r1,$r2]}]}' > "$MANIFEST"
echo "Wrote $MANIFEST (roles: $R1 + $R2)"
```

```bash
chmod +x detect-review-type.sh
```

- [ ] **Step 4: Run — expect PASS.** `python3 -m pytest tests/test_detect_review_type.py -q` → PASS.

- [ ] **Step 5: Commit.** `git add` the script + test; `git commit -m "feat(dev-workflow): WU3 detect-review-type.sh"`.

- [ ] **Step 6: Failing test for `build-master-plan-manifest.sh`**

Structural slice `[structural-architect, process-auditor]` over `master_plan.md`+`wu_status.md`; one `wu{N}` slice per WU plan file, ROLE1 from `route-change.py --no-cross-cut` over that WU's targets, ROLE2 always `process-auditor`. Test sets up `doc/task/master_plan.md`, `wu_status.md`, and `wu1_plan.md` declaring target files, asserts slice ids `["structure","wu1"]`, `mode:"master-plan"`, and the wu1 roles.

```python
import json, subprocess
from pathlib import Path
SCRIPT = Path(__file__).resolve().parents[1] / "build-master-plan-manifest.sh"

def test_structure_plus_per_wu(tmp_path):
    task = tmp_path/"doc/task"; task.mkdir(parents=True)
    (task/"master_plan.md").write_text("# mp\n")
    (task/"wu_status.md").write_text("# status\n")
    # wu1 plan declares its target files in a 'Files:' fenced list the script reads
    (task/"wu1_plan.md").write_text("# WU1\nTARGETS:\nsrc/a.py\nsrc/b.py\n")
    r = subprocess.run(["bash",str(SCRIPT),"--force"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    m = json.loads((tmp_path/".claude/dev-review/manifest.json").read_text())
    assert m["mode"] == "master-plan"
    ids = [s["id"] for s in m["slices"]]
    assert ids == ["structure","wu1"]
    assert m["slices"][0]["roles"] == ["structural-architect","process-auditor"]
    assert m["slices"][1]["roles"][1] == "process-auditor"
    assert m["slices"][1]["roles"][0] in {"correctness-reviewer","test-reviewer","type-design-reviewer","security-reviewer"}
```

- [ ] **Step 7: Run — expect FAIL.**

- [ ] **Step 8: Implement `build-master-plan-manifest.sh`**

```bash
#!/usr/bin/env bash
# Build the (1+K)-slice master-plan manifest (mode: master-plan).
set -euo pipefail
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=".claude/dev-review"; MANIFEST="$OUT/manifest.json"; mkdir -p "$OUT"
FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done
[[ -f "$MANIFEST" && $FORCE -eq 0 ]] && { echo "manifest exists; use --force" >&2; exit 1; }

TASK="doc/task"
[[ -f "$TASK/master_plan.md" ]] || { echo "missing $TASK/master_plan.md" >&2; exit 2; }

# structural slice
STRUCT_TARGETS=$(printf '%s\n' "$TASK/master_plan.md" "$TASK/wu_status.md" | jq -R . | jq -s .)
SLICES=$(jq -n --argjson t "$STRUCT_TARGETS" \
  '[{id:"structure", target:$t, roles:["structural-architect","process-auditor"]}]')

# per-WU slices
for plan in "$TASK"/wu*_plan.md; do
  [[ -e "$plan" ]] || continue
  id=$(basename "$plan" | sed -E 's/_plan\.md$//')   # wu1, wu2, ...
  # WU plan declares its files after a 'TARGETS:' line, one per line until blank/EOF
  mapfile -t WUF < <(awk '/^TARGETS:/{f=1;next} f&&NF{print} f&&!NF{exit}' "$plan")
  if [[ ${#WUF[@]} -eq 0 ]]; then
    R1="correctness-reviewer"; TJSON='[]'
  else
    R1=$(printf '%s\n' "${WUF[@]}" | python3 "$HERE/route-change.py" --no-cross-cut \
         | awk -F= '/ROLE1/{print $2}')
    TJSON=$(printf '%s\n' "${WUF[@]}" | jq -R . | jq -s .)
  fi
  SLICES=$(echo "$SLICES" | jq --arg id "$id" --arg r1 "$R1" --argjson t "$TJSON" \
    '. + [{id:$id, target:$t, roles:[$r1,"process-auditor"]}]')
done

jq -n --argjson slices "$SLICES" '{schema_version:1, mode:"master-plan", slices:$slices}' > "$MANIFEST"
echo "Wrote $MANIFEST ($(echo "$SLICES" | jq length) slices)"
```

```bash
chmod +x build-master-plan-manifest.sh
```

- [ ] **Step 9: Run — expect PASS.** Commit.

- [ ] **Step 10: Write failing test for `build-integration-manifest.sh`**

`PR/scripts/tests/test_build_integration_manifest.py`:

```python
import json, os, subprocess
from pathlib import Path
SCRIPT = Path(__file__).resolve().parents[1] / "build-integration-manifest.sh"

def git(args, cwd): subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

def setup(tmp_path):
    git(["init","-q"], tmp_path); git(["config","user.email","t@t"], tmp_path)
    git(["config","user.name","t"], tmp_path)
    (tmp_path/"base.py").write_text("x=1\n"); git(["add","-A"], tmp_path)
    git(["commit","-qm","base"], tmp_path); git(["branch","-M","main"], tmp_path)
    git(["checkout","-q","-b","feature"], tmp_path)

def run(tmp_path):
    env = dict(os.environ, BASE="main", HEAD="HEAD")
    return subprocess.run(["bash", str(SCRIPT), "--force"], cwd=tmp_path, env=env,
                          capture_output=True, text=True)

def manifest(tmp_path):
    return json.loads((tmp_path/".claude/dev-review/manifest.json").read_text())

def test_two_slices_no_security(tmp_path):
    setup(tmp_path)
    (tmp_path/"src.py").write_text("y=2\n"); git(["add","-A"], tmp_path); git(["commit","-qm","c"], tmp_path)
    r = run(tmp_path); assert r.returncode == 0, r.stderr
    m = manifest(tmp_path); assert m["mode"] == "integration"
    assert [s["id"] for s in m["slices"]] == ["interface-coupling","regression-consistency"]
    assert m["slices"][1]["roles"] == ["process-auditor","test-reviewer"]
    assert m["slices"][0]["roles"] == ["correctness-reviewer","structural-architect"]

def test_three_slices_with_security(tmp_path):
    setup(tmp_path)
    (tmp_path/".claude").mkdir()
    (tmp_path/".claude/dev-workflow.local.md").write_text(
        '---\nreview:\n  security_sensitive_paths: ["auth/**"]\n---\n')
    (tmp_path/"auth").mkdir(); (tmp_path/"auth/login.py").write_text("z=3\n")
    git(["add","-A"], tmp_path); git(["commit","-qm","c"], tmp_path)
    r = run(tmp_path); assert r.returncode == 0, r.stderr
    m = manifest(tmp_path)
    assert [s["id"] for s in m["slices"]] == ["interface-coupling","regression-consistency","security"]
    assert m["slices"][2]["roles"] == ["security-reviewer","process-auditor"]

def test_interface_slice_captures_type_files(tmp_path):
    setup(tmp_path)
    (tmp_path/"api.d.ts").write_text("export type T = number;\n")
    git(["add","-A"], tmp_path); git(["commit","-qm","c"], tmp_path)
    r = run(tmp_path); assert r.returncode == 0, r.stderr
    iface = [s for s in manifest(tmp_path)["slices"] if s["id"]=="interface-coupling"][0]
    assert "api.d.ts" in iface["target"]

def test_empty_range_exits_2(tmp_path):
    setup(tmp_path)   # feature == main, no new commits
    assert run(tmp_path).returncode == 2
```

- [ ] **Step 11: Run — expect FAIL**

```bash
cd plugins/dev-workflow/scripts && python3 -m pytest tests/test_build_integration_manifest.py -q
```
Expected: FAIL (script missing).

- [ ] **Step 12: Implement `build-integration-manifest.sh`**

```bash
#!/usr/bin/env bash
# Build the generic 2-3 slice integration manifest (mode: integration).
# Reads BASE/HEAD from env (default main/HEAD).
#   interface-coupling      [correctness-reviewer, structural-architect]  (always)
#   regression-consistency  [process-auditor, test-reviewer]              (always; target capped)
#   security                [security-reviewer, process-auditor]          (only if security paths touched)
set -euo pipefail
command -v jq >/dev/null || { echo "jq required" >&2; exit 2; }
command -v git >/dev/null || { echo "git required" >&2; exit 2; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT=".claude/dev-review"; MANIFEST="$OUT/manifest.json"; mkdir -p "$OUT"
FORCE=0; for a in "$@"; do [[ "$a" == "--force" ]] && FORCE=1; done
[[ -f "$MANIFEST" && $FORCE -eq 0 ]] && { echo "manifest exists; use --force" >&2; exit 1; }

BASE="${BASE:-main}"; HEAD="${HEAD:-HEAD}"; CAP=30
mapfile -t CHANGED < <(git diff --name-only "$BASE...$HEAD" 2>/dev/null | sort -u)
[[ ${#CHANGED[@]} -eq 0 ]] && { echo "no changed files in $BASE...$HEAD" >&2; exit 2; }

mapfile -t SEC < <(python3 "$HERE/read-config.py" review.security_sensitive_paths "" 2>/dev/null || true)

# classify files: emit "IFACE\t<f>" and/or "SEC\t<f>" (single source of glob logic)
SEC_STR=$(printf '%s\n' "${SEC[@]:-}")
FILES_STR=$(printf '%s\n' "${CHANGED[@]}")
CLASS=$(python3 - "$SEC_STR" "$FILES_STR" <<'PY'
import sys, fnmatch
sec   = [s for s in sys.argv[1].split("\n") if s]
files = [f for f in sys.argv[2].split("\n") if f]
def gm(p, g):
    if g.endswith("/**"):
        b = g[:-3]; return p == b or p.startswith(b + "/")
    return fnmatch.fnmatch(p, g)
def is_iface(f):
    low = f.lower()
    return f.endswith(".d.ts") or f.endswith(".proto") or "types" in low or "interface" in low
for f in files:
    if is_iface(f):              print("IFACE\t" + f)
    if any(gm(f, g) for g in sec): print("SEC\t" + f)
PY
)
mapfile -t IFACE < <(printf '%s\n' "$CLASS" | awk -F'\t' '/^IFACE/{print $2}')
mapfile -t SECF  < <(printf '%s\n' "$CLASS" | awk -F'\t' '/^SEC/{print $2}')
REG=("${CHANGED[@]:0:$CAP}")

# explicit empty-array guards (no "${arr[@]:-}" footgun)
if [[ ${#IFACE[@]} -gt 0 ]]; then IFACE_JSON=$(printf '%s\n' "${IFACE[@]}" | jq -R . | jq -s .); else IFACE_JSON='[]'; fi
REG_JSON=$(printf '%s\n' "${REG[@]}" | jq -R . | jq -s .)

SLICES=$(jq -n --argjson iface "$IFACE_JSON" --argjson reg "$REG_JSON" \
  '[{id:"interface-coupling", target:$iface, roles:["correctness-reviewer","structural-architect"]},
    {id:"regression-consistency", target:$reg, roles:["process-auditor","test-reviewer"]}]')
if [[ ${#SECF[@]} -gt 0 ]]; then
  SEC_JSON=$(printf '%s\n' "${SECF[@]}" | jq -R . | jq -s .)
  SLICES=$(echo "$SLICES" | jq --argjson s "$SEC_JSON" \
    '. + [{id:"security", target:$s, roles:["security-reviewer","process-auditor"]}]')
fi
jq -n --argjson slices "$SLICES" '{schema_version:1, mode:"integration", slices:$slices}' > "$MANIFEST"
echo "Wrote $MANIFEST ($(echo "$SLICES" | jq length) slices)"
```

```bash
chmod +x build-integration-manifest.sh
```
Note: `interface-coupling` uses a filename/type heuristic (testable in file-list mode); the spec's richer "imported by ≥2 subsystems" detection is deferred (spec §10 open item) — the heuristic above is the v1 behavior and is what the test asserts.

- [ ] **Step 13: Run — expect PASS**

```bash
python3 -m pytest tests/test_build_integration_manifest.py -q
```
Expected: 4 PASS.

- [ ] **Step 14: Commit.** `git add` the script + test; `git commit -m "feat(dev-workflow): WU3 build-integration-manifest.sh (generic 2-3 slice taxonomy)"`.

- [ ] **Step 15: Run full script suite — all green.** `cd plugins/dev-workflow/scripts && python3 -m pytest -q`.

---

## WU4 — Reviewer agents

**Files:** Create `PR/agents/process-auditor.md`, `structural-architect.md`, `correctness-reviewer.md`, `security-reviewer.md`, `test-reviewer.md`, `type-design-reviewer.md`.

Each agent's frontmatter: `name`, `description` (when-to-use), `tools` as a block list (`Read`/`Grep`/`Glob` — matching the convention in `CY/agents/process-auditor.md`), `model: sonnet`. Each body MUST open with the exact verdict contract so `check-approve.py` can parse it.

- [ ] **Step 1: Port `process-auditor.md` from CY, strip CYCAS specifics**

Copy `CY/agents/process-auditor.md`; replace the focus list with generic items: (1) lifecycle/phase compliance, (2) review-fix integrity (CONDITIONAL = not approved), (3) user-approval-gate preservation, (4) root-cause discipline (no masking/clamping/suppression), (5) test presence for new/changed code, (6) doc parity if user-facing behavior changed, (7) gate items from config (no debug leftovers, etc.). Keep the verbatim verdict-contract block:

```markdown
Your response MUST begin with a line exactly matching one of:
  VERDICT: APPROVE
  VERDICT: CONDITIONAL APPROVE
  VERDICT: REJECT
No leading whitespace. Findings follow on subsequent lines.
```

- [ ] **Step 2: Port `structural-architect.md` from CY**, generic version: WU boundaries, DAG cycle-freeness, completeness vs objective, ownership conflicts in shared files, scope thresholds. Same verdict contract.

- [ ] **Step 3: Write the four generic fallback reviewers.** Each is thin and self-contained, same frontmatter + verdict contract:
  - `correctness-reviewer.md`: logic errors, edge cases, error handling, security basics, convention adherence.
  - `security-reviewer.md`: injection/authz/secret-handling/input-validation, silent failures, unsafe fallbacks.
  - `test-reviewer.md`: coverage of new behavior + edge cases, test quality, missing negative tests.
  - `type-design-reviewer.md`: encapsulation, invariant expression, illegal-states-unrepresentable, interface clarity.

  Body skeleton (fill the focus bullets per role):

```markdown
---
name: correctness-reviewer
description: Generic code-correctness reviewer for dev-workflow review-fix loops; fresh independent reviewer, emits a structured VERDICT line.
tools:
  - Read
  - Grep
  - Glob
model: sonnet
---
You are a fresh, independent reviewer dispatched by the dev-workflow Review-Fix Cycle. You did NOT write the code under review.

Your response MUST begin with a line exactly matching one of:
  VERDICT: APPROVE
  VERDICT: CONDITIONAL APPROVE
  VERDICT: REJECT
No leading whitespace, nothing else on that line. CONDITIONAL APPROVE = NOT approved.

## Focus
- <role-specific bullets>

## Output
VERDICT: <...>
Findings:
  [N] severity: CRITICAL|MAJOR|MINOR  file:line  issue  recommendation
Reference file:line for every finding. Do not invent findings. You Read/Grep/Glob only; you do not run builds or tests.
```

- [ ] **Step 4: Commit.** `git add plugins/dev-workflow/agents && git commit -m "feat(dev-workflow): WU4 reviewer agents (owned + fallbacks)"`.

---

## WU5 — Guiding skill + Work Unit protocol

**Files:** Create `PR/skills/dev-workflow/SKILL.md`, `PR/skills/dev-workflow/work-unit-protocol.md`.

- [ ] **Step 1: Write `SKILL.md`** — port the structure of `CY/skills/cycas-workflow/SKILL.md` with stack specifics removed. Must include: frontmatter (`name: dev-workflow`, broad `description` of trigger verbs); Step 0 resume-check + config load via `read-config.py`; Step 1 generic task-type table (spec §4); Step 2 Small/Large gate using `scope_thresholds`; lifecycle phases (Design→brainstorming, Plan→writing-plans, Plan-Review, Build, Code-Review loop, Test, Deliver); the role-resolution table (spec §5); quality gates generated from `gates.*`; behavior rules (start with scope gate, never self-review, root-cause discipline, enforce hard gates); and the review-loop command list. Reference `work-unit-protocol.md` for Large tasks (progressive disclosure).

- [ ] **Step 2: Write `work-unit-protocol.md`** — port CY Section 12.2: master-plan phase (`doc/task/`, `master_plan.md` with WU defs ≤5 pref/≤8 justified/≤10 hard + DAG + ownership, `wu_status.md` dashboard, per-WU `wu{N}_plan.md` with the `TARGETS:` block the builder reads), optional baseline capture (only if config `baseline` set), master-plan review loop, user gate, per-WU lifecycle, integration phase.

- [ ] **Step 3: Validate skill frontmatter loads** — `python3 -c "import yaml,sys; print(yaml.safe_load(open('plugins/dev-workflow/skills/dev-workflow/SKILL.md').read().split('---')[1]))"` prints a dict with `name` and `description`.

- [ ] **Step 4: Commit.**

---

## WU6 — Commands + config schema + /init

**Files:** Create `PR/commands/{init,workflow,quality-gate,plan-review-loop,code-review-loop,master-plan-review-loop,integration-review-loop}.md`.

- [ ] **Step 1: Four loop-command wrappers** — each a thin command invoking its driver, e.g. `code-review-loop.md` frontmatter `allowed-tools` granting the `run-code-review-loop.sh` path, body instructs running `${CLAUDE_PLUGIN_ROOT}/scripts/run-code-review-loop.sh` then beginning iteration 1. Repeat for plan/master-plan/integration with their drivers and `--base/--head` passthrough for integration.

- [ ] **Step 2: `workflow.md`** — port CY's workflow command (task-type table + routing), strip specifics.

- [ ] **Step 3: `quality-gate.md`** — reads `gates.pre_commit`/`gates.merge_main` via `read-config.py`, runs each named command, reports pass/fail. Body shows the exact `read-config.py` calls and the run-and-report loop.

- [ ] **Step 4: `init.md`** — detects stack (peek `package.json`/`Makefile`/`pyproject.toml`/`Cargo.toml`/`go.mod`), drafts `.claude/dev-workflow.local.md` with the spec §6 schema and **`use_external_agents: false`** (authoritative default), asks the user to confirm/edit. Include the full default config template in the command body (copy the §6 YAML block exactly, with the `use_external_agents: false` comment).

- [ ] **Step 5: Commit.**

---

## WU7 — Hooks

**Files:** Create `PR/hooks/hooks.json`, `pretooluse.py`, `stop.py`. Test: `PR/scripts/tests/test_hooks.py`.

- [ ] **Step 1: `hooks.json`** — PreToolUse → `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/pretooluse.py`; Stop → `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/stop.py` (same shape as `CY/hooks/hooks.json`).

- [ ] **Step 2: Failing test for `pretooluse.py`** — feeds a JSON event for `Edit` of an `auth/**` file (config present), asserts stdout is the verified shape `{"hookSpecificOutput": {"permissionDecision": "allow"}, "systemMessage": "...security-sensitive..."}`; and for a non-matching path, asserts a silent/allow no-message exit.

- [ ] **Step 3: Implement `pretooluse.py`** — read JSON stdin; only act on `Edit`/`Write`; read `review.security_sensitive_paths` via the shared `read-config.py` resolving paths against the event `cwd`; if the file matches, print `{"hookSpecificOutput": {"permissionDecision": "allow"}, "systemMessage": "security-sensitive path — review auth/crypto/input-validation invariants"}`; else print `{"hookSpecificOutput": {"permissionDecision": "allow"}}`. Fast-exit (<5ms) for non-Edit/Write.

- [ ] **Step 4: Implement `stop.py`** — port `CY/hooks/stop.py`: defer silently (`sys.exit(0)`) when `.claude/ralph-loop.local.md`'s `session_id` matches the event `session_id`; otherwise print `{"decision": "approve", "systemMessage": "<pre-commit checklist from gates.pre_commit>"}`, building the checklist via `read-config.py gates.pre_commit`. Resolve `.claude/...` against the event `cwd`.

- [ ] **Step 5: Run hook tests — PASS. Commit.**

---

## WU8 — Marketplace registration + end-to-end smoke test

**Files:** Create `/Users/qingz/dev-workflow-marketplace/.claude-plugin/marketplace.json`. Test: `PR/scripts/tests/test_smoke_e2e.py`.

- [ ] **Step 1: Write `marketplace.json`** (mirror `video-essay-marketplace`):

```json
{
  "name": "dev-workflow-local",
  "description": "Stack-agnostic disciplined development workflow plugin",
  "owner": { "name": "qingz" },
  "plugins": [
    { "name": "dev-workflow", "description": "Scope gate, review-fix loops, Work Units, config-driven gates", "version": "0.1.0", "source": "./plugins/dev-workflow" }
  ]
}
```

- [ ] **Step 2: End-to-end manifest→resolve→token-render dry run.** In a throwaway git repo with a sample diff and a `use_external_agents: false` config, run `detect-review-type.sh code --force`, then `resolve-roles.py` on the manifest, then the driver's `awk` render step, and assert: manifest `schema_version==1`, roles are `dev-workflow:`-namespaced (fallback), the rendered prompt contains `.claude/dev-review` and `DEV-REVIEW-DONE` and no `{{...}}` tokens remain. (Does NOT start ralph — verifies wiring only.)

- [ ] **Step 3: Cross-plugin dispatch smoke test (gates `use_external_agents`).** From within Claude Code, dispatch one `pr-review-toolkit:code-reviewer` agent via the Agent tool on a trivial file and confirm it returns. If it resolves, document that `use_external_agents: true` is safe to enable; if not, leave the default `false` and record the finding. (This step is run interactively by the executing agent, not via pytest.)

- [ ] **Step 4: Register the marketplace + install locally.**

```bash
# from Claude Code: add the directory marketplace and install the plugin
/plugin marketplace add /Users/qingz/dev-workflow-marketplace
/plugin install dev-workflow@dev-workflow-local
```
Then verify `/dev-workflow:workflow` and `/dev-workflow:init` are listed.

- [ ] **Step 5: Full suite + commit.** `cd plugins/dev-workflow/scripts && python3 -m pytest -q` (all green), then commit marketplace.json + smoke test.

---

## Self-Review (completed by plan author)

**Spec coverage:** §3 layout → WU1–WU8 create every listed file (verifier/prompt/drivers/find-ralph = WU1; read-config/route-change/resolve-roles = WU2; three builders = WU3; six agents = WU4; skill+protocol = WU5; commands+config+init = WU6; hooks = WU7; marketplace+tests = WU8). §5 routing/role-resolution → WU2+WU3. §6 config → WU6 + consumed throughout. §7 hooks → WU7. §9 dispositions all mapped. §10 WU partition matches. Open items resolved: pyyaml chosen (WU2); `use_external_agents` default false + smoke gate (WU6/WU8); interface-coupling heuristic deferred within WU3 step 10.

**Placeholder scan:** All new scripts (read-config.py, route-change.py, resolve-roles.py, find-ralph.sh, detect-review-type.sh, build-master-plan-manifest.sh, build-integration-manifest.sh) have complete code + complete tests with FAIL→implement→PASS→commit steps. Ported items give exact `cp`+`sed` from exact source paths (with `export CY=...` in each step that uses it) + verification greps. Agents/skill/commands are doc-type files specified by frontmatter + mandatory verbatim verdict-contract block + required-contents + cited CY source + spec sections (acceptable deferral for prose deliverables; the executing agent expands them).

**Type/name consistency:** role vocabulary (6 abstract names), `ROLE1=`/`ROLE2=` contract, mode values (`simple`/`master-plan`/`integration`), tokens (`{{CHECK_APPROVE_PATH}}`, `{{REVIEW_DIR}}`=`.claude/dev-review`, promise `DEV-REVIEW-DONE`), and `resolve-roles.py` external map are consistent across WU1–WU8.
