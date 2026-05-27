#!/usr/bin/env python3
"""Stop hook: pre-commit checklist reminder when Claude is about to finish.

Ported from CYCAS stop.py. Defers silently (sys.exit(0)) when a ralph-loop is
active in the CURRENT session — so ralph's blocking Stop hook is the only hook
producing a decision and review-loops aren't interrupted. The session match
reads `.claude/ralph-loop.local.md`'s `session_id` against the event
`session_id`.

Otherwise emits the documented Stop-hook shape
    {"decision": "approve", "systemMessage": "<checklist from gates.pre_commit>"}
The checklist is assembled from `gates.pre_commit` (read via the shared
read-config.py; default [build, lint, test]). Project-relative reads resolve
against the event `cwd`, not the process working directory.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _load_ralph_session_id(cwd):
    """Return ralph-loop.local.md's session_id (resolved at `cwd`), or None."""
    state = Path(cwd) / ".claude" / "ralph-loop.local.md"
    if not state.is_file():
        return None
    try:
        text = state.read_text()
    except OSError:
        return None
    m = re.search(r"^session_id:\s*(\S+)\s*$", text, re.MULTILINE)
    return m.group(1) if m else None


def _pre_commit_gates(cwd):
    """Read gates.pre_commit via read-config.py, resolved at `cwd`."""
    default = ["build", "lint", "test"]
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT", "")
    rc = Path(plugin_root) / "scripts" / "read-config.py"
    if not rc.is_file():
        return default
    try:
        r = subprocess.run(
            ["python3", str(rc), "gates.pre_commit", "\n".join(default)],
            cwd=cwd or None,
            capture_output=True,
            text=True,
        )
    except OSError:
        return default
    if r.returncode != 0 or not r.stdout.strip():
        return default
    return [line for line in r.stdout.strip().splitlines() if line]


def main():
    try:
        hook_input = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        hook_input = {}

    cwd = hook_input.get("cwd", "") or os.getcwd()
    current_session = hook_input.get("session_id", "")
    ralph_session = _load_ralph_session_id(cwd)

    if ralph_session is not None and ralph_session == current_session:
        # Ralph is active in THIS session — defer silently.
        sys.exit(0)

    gates = _pre_commit_gates(cwd)
    checklist = "\n".join(f"- [ ] {g}" for g in gates)
    message = (
        "SESSION ENDING — Pre-commit checklist reminder:\n"
        f"{checklist}\n"
        "- [ ] Consider running /quality-gate to verify before committing"
    )
    print(json.dumps({"decision": "approve", "systemMessage": message}))


if __name__ == "__main__":
    main()
