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
