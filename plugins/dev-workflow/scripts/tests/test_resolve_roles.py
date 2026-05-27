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
    # MUST mirror the real nested shape: {"version": N, "plugins": {...}}
    reg = cwd / ".claude/plugins"
    reg.mkdir(parents=True, exist_ok=True)
    pmap = {"pr-review-toolkit@official": [{}]} if external_present else {}
    (reg / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": pmap}))
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
