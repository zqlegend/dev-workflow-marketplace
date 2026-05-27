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
