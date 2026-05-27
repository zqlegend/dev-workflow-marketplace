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

def test_code_mode_no_changes_exits_2(tmp_path):
    init_repo(tmp_path)
    r = subprocess.run(["bash", str(SCRIPT), "code", "--force"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 2, r.stderr

def test_manifest_exists_no_force_exits_1(tmp_path):
    init_repo(tmp_path)
    out = tmp_path / ".claude/dev-review"; out.mkdir(parents=True)
    (out / "manifest.json").write_text("{}")
    (tmp_path / "src.py").write_text("y=2\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    r = subprocess.run(["bash", str(SCRIPT), "code"], cwd=tmp_path,
                       capture_output=True, text=True)
    assert r.returncode == 1
