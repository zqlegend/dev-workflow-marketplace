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
