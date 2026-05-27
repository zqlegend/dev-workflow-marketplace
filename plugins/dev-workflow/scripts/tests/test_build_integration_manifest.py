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
