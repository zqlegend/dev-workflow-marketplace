import json
import subprocess
import textwrap
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[2] / "hooks"
PRETOOLUSE = HOOKS / "pretooluse.py"
STOP = HOOKS / "stop.py"
PLUGIN_ROOT = Path(__file__).resolve().parents[2]

CONFIG = textwrap.dedent('''\
    ---
    build: "npm run build"
    gates:
      pre_commit: [build, lint, test]
    review:
      use_external_agents: false
      security_sensitive_paths: ["auth/**", "**/crypto*"]
    ---
    # notes
    ''')


def _proj(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/dev-workflow.local.md").write_text(CONFIG)
    return tmp_path


def run_hook(script, event):
    """Invoke a hook script feeding `event` as JSON on stdin.

    CLAUDE_PLUGIN_ROOT points at the plugin so the hook can locate
    scripts/read-config.py. Process cwd is intentionally NOT the project
    dir, to prove the hook resolves project-relative reads against the
    event `cwd`, not the process working directory.
    """
    return run_hook_raw(script, json.dumps(event))


def run_hook_raw(script, stdin_text):
    """Invoke a hook script feeding raw `stdin_text` verbatim on stdin.

    Same env/cwd contract as run_hook, but does not assume the payload is
    valid JSON — used to exercise empty/malformed stdin resilience.
    """
    import os
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN_ROOT))
    return subprocess.run(
        ["python3", str(script)],
        input=stdin_text,
        capture_output=True, text=True, env=env,
    )


# ---- pretooluse.py ---------------------------------------------------------

def test_pretooluse_security_path_emits_verified_shape(tmp_path):
    p = _proj(tmp_path)
    event = {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(p / "auth" / "login.py")},
        "cwd": str(p),
        "session_id": "abc",
    }
    r = run_hook(PRETOOLUSE, event)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "security-sensitive" in out["systemMessage"]


def test_pretooluse_nonmatching_path_allows_no_message(tmp_path):
    p = _proj(tmp_path)
    event = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(p / "src" / "util.py")},
        "cwd": str(p),
        "session_id": "abc",
    }
    r = run_hook(PRETOOLUSE, event)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "systemMessage" not in out


def test_pretooluse_relative_path_matches(tmp_path):
    p = _proj(tmp_path)
    event = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "auth/session.py"},
        "cwd": str(p),
        "session_id": "abc",
    }
    r = run_hook(PRETOOLUSE, event)
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "security-sensitive" in out["systemMessage"]


def test_pretooluse_multiedit_security_path_emits_message(tmp_path):
    p = _proj(tmp_path)
    event = {
        "tool_name": "MultiEdit",
        "tool_input": {"file_path": str(p / "auth" / "login.py")},
        "cwd": str(p),
        "session_id": "abc",
    }
    r = run_hook(PRETOOLUSE, event)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "security-sensitive" in out["systemMessage"]


def test_pretooluse_empty_stdin_allows():
    r = run_hook_raw(PRETOOLUSE, "")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_pretooluse_malformed_stdin_allows():
    r = run_hook_raw(PRETOOLUSE, "{not valid json")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_pretooluse_non_edit_write_fast_exit(tmp_path):
    p = _proj(tmp_path)
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "cwd": str(p),
        "session_id": "abc",
    }
    r = run_hook(PRETOOLUSE, event)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "systemMessage" not in out


# ---- stop.py ---------------------------------------------------------------

def test_stop_emits_precommit_checklist(tmp_path):
    p = _proj(tmp_path)
    event = {"cwd": str(p), "session_id": "abc"}
    r = run_hook(STOP, event)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["decision"] == "approve"
    msg = out["systemMessage"]
    assert "build" in msg and "lint" in msg and "test" in msg


def test_stop_empty_stdin_approves():
    r = run_hook_raw(STOP, "")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["decision"] == "approve"


def test_stop_defers_when_ralph_active_in_session(tmp_path):
    p = _proj(tmp_path)
    (p / ".claude/ralph-loop.local.md").write_text("---\nsession_id: abc\n---\n")
    event = {"cwd": str(p), "session_id": "abc"}
    r = run_hook(STOP, event)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ""


def test_stop_surfaces_when_ralph_session_mismatch(tmp_path):
    p = _proj(tmp_path)
    (p / ".claude/ralph-loop.local.md").write_text("---\nsession_id: other\n---\n")
    event = {"cwd": str(p), "session_id": "abc"}
    r = run_hook(STOP, event)
    out = json.loads(r.stdout)
    assert out["decision"] == "approve"
    assert "systemMessage" in out
