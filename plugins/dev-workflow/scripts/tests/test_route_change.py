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
