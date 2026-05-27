"""WU8 Step 2: end-to-end dry-run wiring test.

Hermetic: builds its own throwaway git repo + config in tmp_path, then runs the
real pipeline pieces that run-code-review-loop.sh chains together:
  detect-review-type.sh code --force  ->  resolve-roles.py  ->  prompt render
and asserts the manifest shape, the fallback (dev-workflow:-namespaced) roles
that use_external_agents:false guarantees, and a fully-rendered prompt with no
leftover {{...}} tokens. Does NOT start ralph -- verifies wiring only.
"""
import json
import os
import subprocess
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[2]  # PR (.../plugins/dev-workflow)
SCRIPTS = PLUGIN_ROOT / "scripts"
DETECT = SCRIPTS / "detect-review-type.sh"
RESOLVE = SCRIPTS / "resolve-roles.py"
CHECK = SCRIPTS / "check-approve.py"
PROMPT_SRC = PLUGIN_ROOT / "skills" / "dev-workflow" / "review-loop-prompt.md"
REVIEW_DIR = ".claude/dev-review"


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


def _make_repo(tmp_path):
    """Throwaway git repo with a committed base + a staged sample diff."""
    _git(["init", "-q"], tmp_path)
    _git(["config", "user.email", "t@t"], tmp_path)
    _git(["config", "user.name", "t"], tmp_path)
    (tmp_path / "base.py").write_text("x = 1\n")
    _git(["add", "-A"], tmp_path)
    _git(["commit", "-qm", "init"], tmp_path)
    # sample staged diff -> routes to correctness-reviewer + process-auditor
    (tmp_path / "feature.py").write_text("def add(a, b):\n    return a + b\n")
    _git(["add", "-A"], tmp_path)
    # config that forces the plugin-owned fallback
    cfg_dir = tmp_path / ".claude"
    cfg_dir.mkdir(exist_ok=True)
    (cfg_dir / "dev-workflow.local.md").write_text(
        "---\nreview:\n  use_external_agents: false\n---\n"
    )


def _render_prompt(check_path, review_dir):
    """Replicate the literal-replace renderer from run-code-review-loop.sh."""
    return (PROMPT_SRC.read_text()
            .replace("{{CHECK_APPROVE_PATH}}", check_path)
            .replace("{{REVIEW_DIR}}", review_dir))


def test_e2e_dry_run(tmp_path):
    _make_repo(tmp_path)
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT)}

    # (1) detect-review-type.sh code --force -> build the 1-slice manifest
    r = subprocess.run(["bash", str(DETECT), "code", "--force"],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    manifest_path = tmp_path / REVIEW_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema_version"] == 1
    assert manifest["mode"] == "simple"
    # abstract roles before resolution
    assert manifest["slices"][0]["roles"] == [
        "correctness-reviewer", "process-auditor"]

    # (2) resolve-roles.py on the manifest -> with use_external_agents:false,
    #     fall back to dev-workflow:-namespaced concrete roles.
    r = subprocess.run(["python3", str(RESOLVE), str(manifest_path)],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    resolved = json.loads(manifest_path.read_text())
    roles = resolved["slices"][0]["roles"]
    assert roles == [
        "dev-workflow:correctness-reviewer",
        "dev-workflow:process-auditor",
    ], roles
    # every role is dev-workflow:-namespaced (the fallback)
    assert all(role.startswith("dev-workflow:") for role in roles), roles

    # (3) prompt render: literal token replacement, as the driver does.
    rendered = _render_prompt(str(CHECK), REVIEW_DIR)
    assert REVIEW_DIR in rendered
    assert "DEV-REVIEW-DONE" in rendered
    assert "{{" not in rendered and "}}" not in rendered
